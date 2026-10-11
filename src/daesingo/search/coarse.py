from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import isfinite
from uuid import uuid4

from .config import GeminiSearchConfig
from .errors import (
    CoarseDurationMismatchError,
    InvalidCoarseSpanError,
    UnknownCandidateError,
)
from .execution import DeadlineExceededError, RunDeadline
from .ledger import SearchLedger, UsageRecord
from .media import PreparedMedia
from .media_contract import CoarseMediaPreparer
from .prompts import COARSE_PROMPT, sent_prompt_fingerprint
from .provider import CoarseRequest, ProviderResult, SearchProvider
from .runs import (
    AnalysisRun,
    CandidateEvent,
    CandidateId,
    CandidateSearchResult,
    CandidateSpan,
    ContractRef,
    FailureKind,
    Implementation,
    Issue,
    Money,
    Operation,
    RunId,
    RunOutcome,
    TokenUsage,
    UsageSummary,
)
from .schemas import CoarseCandidate, CoarseResponse
from .scope import AnalysisScope
from .sources import AnalysisSourceResolver, ResolvedAnalysisSource


@dataclass(frozen=True, slots=True)
class LinkedCoarseResult:
    """Internal wrapper retaining which analysis source the candidates came from."""

    result: CandidateSearchResult
    source_ref: ContractRef

    def source_ref_for(self, candidate_id: CandidateId) -> ContractRef:
        """Return the source ref for a candidate; raises UnknownCandidateError if not found."""
        for candidate in self.result.candidates:
            if candidate.candidate_id == candidate_id:
                return self.source_ref
        raise UnknownCandidateError(candidate_id=candidate_id)


@dataclass(frozen=True, slots=True)
class CoarseExecutionDependencies:
    resolver: AnalysisSourceResolver
    provider: SearchProvider
    config: GeminiSearchConfig
    ledger: SearchLedger
    media_preparer: CoarseMediaPreparer
    deadline: RunDeadline


def search_coarse(
    scope: AnalysisScope,
    dependencies: CoarseExecutionDependencies,
) -> LinkedCoarseResult:
    started = datetime.now(UTC)
    run_id = RunId(f"run_search_{uuid4().hex}")
    gathered: list[tuple[ResolvedAnalysisSource, CoarseCandidate]] = []
    records: list[UsageRecord] = []
    usage_refs: list[str] = []
    failure: Issue | None = None
    sources = dependencies.resolver.resolve(scope)
    if not sources:
        raise AssertionError(
            "resolve() yielded no sources for scope; cannot attach source_ref"
        )
    if len(sources) != 1:
        raise AssertionError(
            f"resolve() must yield exactly one source for coarse search; got {len(sources)}"
        )
    source = sources[0]
    # dependencies.deadline은 SearchService가 호출 시점에 scope.budget.max_latency_sec로
    # 만든 실행 상한이다(contract-analysis-scope.md §104, #149 A안) — 다른 상한과 겹치지 않는다.
    # budget.max_cost_krw는 KRW↔USD 환산이 미결이라 여기서 집행하지 않는다.
    deadline = dependencies.deadline
    with (
        dependencies.resolver.open_source(source.source_ref) as media_input,
        dependencies.media_preparer.prepare_coarse(media_input, deadline) as prepared,
    ):
        if abs(source.duration_sec - prepared.origin_end_sec) > 0.250:
            raise CoarseDurationMismatchError(
                source_id=source.source_id,
                declared_sec=source.duration_sec,
                probed_sec=prepared.origin_end_sec,
            )
        try:
            deadline.check()
            result = dependencies.provider.search_coarse(
                CoarseRequest(
                    source,
                    scope.target_event_types,
                    media=prepared,
                    timeout_sec=deadline.remaining_sec(),
                    deadline=deadline,
                )
            )
        except DeadlineExceededError as error:
            failure = _issue(FailureKind.COST, "RUN_DEADLINE_EXCEEDED", scope, error)
        except Exception as error:
            failure = _issue(FailureKind.INFRA, "PROVIDER_CALL_FAILED", scope, error)
        else:
            usage_refs.append(f"usage:{source.source_id}")
            record = _usage_record(source, prepared, result, dependencies.config)
            dependencies.ledger.append(record)
            records.append(record)
            gathered.extend(
                (source, candidate) for candidate in result.response.candidates
            )

    if failure is not None:
        return _failed_result(run_id, scope, source, started, failure, dependencies)

    ranked = sorted(gathered, key=lambda item: (-item[1].score, item[1].at_sec))
    candidates = tuple(
        _candidate(run_id, rank, source, candidate)
        for rank, (source, candidate) in enumerate(ranked, start=1)
    )
    completed = datetime.now(UTC)
    analysis_run = AnalysisRun(
        run_id=run_id,
        operation=Operation.CANDIDATE_SEARCH,
        input_ref=ContractRef(kind="ANALYSIS_SCOPE", ref=scope.scope_id),
        implementation=Implementation(
            impl_id="search:gemini-coarse-p3",
            model_ref=dependencies.config.model,
            prompt_version=COARSE_PROMPT.version,
            config_version=dependencies.config.version,
        ),
        outcome=RunOutcome.SUCCEEDED,
        started_at=started,
        completed_at=completed,
        issues=(),
        usage_refs=tuple(usage_refs),
        usage_summary=_usage_summary(records),
        contract_version="analysis-run-candidate-event/v1.1",
    )
    candidate_search_result = CandidateSearchResult(
        analysis_run=analysis_run, candidates=candidates
    )
    assert (
        source.source_ref.kind == "analysis_source"
    ), f"source_ref.kind must be 'analysis_source', got {source.source_ref.kind!r}"
    return LinkedCoarseResult(
        result=candidate_search_result, source_ref=source.source_ref
    )


def _issue(
    kind: FailureKind,
    code: str,
    scope: AnalysisScope,
    error: Exception,
) -> Issue:
    """실패 하나를 taxonomy 이름으로 기록한다.

    `detail`에는 예외 타입 이름만 남긴다 — 계약 §3-3이 stack trace와 raw provider
    payload를 금지하고, provider 메시지 자체가 마스킹되지 않은 입력을 담을 수 있다.
    stage(COARSE/FINE)는 `Issue`에 별도 필드를 두지 않는다. `operation`이 이미 구분한다.
    """
    return Issue(
        kind=kind,
        code=code,
        scope_ref=scope.scope_id,
        detail=type(error).__name__,
    )


def _failed_result(
    run_id: RunId,
    scope: AnalysisScope,
    source: ResolvedAnalysisSource,
    started: datetime,
    failure: Issue,
    dependencies: CoarseExecutionDependencies,
) -> LinkedCoarseResult:
    """FAILED AnalysisRun을 만든다 — 계약 §7 Producer는 결과 구분을 요구한다.

    usage는 비운다. 호출이 결과를 내지 못했으므로 Eval이 재평가할 snapshot이 없다.
    """
    analysis_run = AnalysisRun(
        run_id=run_id,
        operation=Operation.CANDIDATE_SEARCH,
        input_ref=ContractRef(kind="ANALYSIS_SCOPE", ref=scope.scope_id),
        implementation=Implementation(
            impl_id="search:gemini-coarse-p3",
            model_ref=dependencies.config.model,
            prompt_version=COARSE_PROMPT.version,
            config_version=dependencies.config.version,
        ),
        outcome=RunOutcome.FAILED,
        started_at=started,
        completed_at=datetime.now(UTC),
        issues=(failure,),
        usage_refs=(),
        usage_summary=UsageSummary(
            processed_duration_ms=None,
            token_usage=None,
            latency_ms=None,
            total_cost=None,
        ),
        contract_version="analysis-run-candidate-event/v1.1",
    )
    return LinkedCoarseResult(
        result=CandidateSearchResult(analysis_run=analysis_run, candidates=()),
        source_ref=source.source_ref,
    )


def _candidate(
    run_id: RunId,
    rank: int,
    source: ResolvedAnalysisSource,
    candidate: CoarseCandidate,
) -> CandidateEvent:
    values_are_finite = all(
        isfinite(value)
        for value in (
            candidate.span.start_sec,
            candidate.span.end_sec,
            candidate.at_sec,
        )
    )
    span_is_nonnegative = (
        candidate.span.start_sec >= 0
        and candidate.span.end_sec >= 0
        and candidate.at_sec >= 0
    )
    span_is_ordered = candidate.span.start_sec < candidate.span.end_sec
    span_overlaps_source = (
        candidate.span.start_sec < source.duration_sec and candidate.span.end_sec > 0
    )
    if not (
        values_are_finite
        and span_is_nonnegative
        and span_is_ordered
        and span_overlaps_source
    ):
        raise InvalidCoarseSpanError(
            source_id=source.source_id,
            start_sec=candidate.span.start_sec,
            end_sec=candidate.span.end_sec,
            at_sec=candidate.at_sec,
            duration_sec=source.duration_sec,
        )
    start = max(0.0, min(candidate.span.start_sec, source.duration_sec))
    end = max(start + 0.001, min(candidate.span.end_sec, source.duration_sec))
    representative = min(max(candidate.at_sec, start), end)
    # "점선" 단독은 정상 관찰("점선 차로로 변경")까지 잡으므로 쓰지 않는다(#169).
    # 선 종류 애매함("점선처럼 보이나")은 "처럼 보"로 잡는다.
    uncertainties = tuple(
        fact
        for fact in candidate.observed
        if any(
            word in fact for word in ("불확실", "판별", "가림", "저해상도", "처럼 보")
        )
    )
    return CandidateEvent(
        candidate_id=CandidateId(f"candidate_{uuid4().hex}"),
        run_id=run_id,
        span=CandidateSpan(
            timeline_id=source.timeline_id,
            timeline_revision=source.timeline_revision,
            # 입력 좌표 → Timeline 좌표(#252)
            start_ms=round((source.timeline_start_sec + start) * 1000),
            end_ms=round((source.timeline_start_sec + end) * 1000),
            representative_ms=round(
                (source.timeline_start_sec + representative) * 1000
            ),
        ),
        rank=rank,
        ranking_score=candidate.score,
        event_type_hint=candidate.event_type,
        summary="; ".join(candidate.observed) or "관찰 사실 없음",
        uncertainties=uncertainties,
        thumbnail_ref=None,
    )


def _usage_record(
    source: ResolvedAnalysisSource,
    prepared: PreparedMedia,
    result: ProviderResult[CoarseResponse],
    config: GeminiSearchConfig,
) -> UsageRecord:
    return UsageRecord(
        case_id=source.source_id,
        model=config.model,
        prompt_version=COARSE_PROMPT.version,
        prompt_fingerprint=sent_prompt_fingerprint(
            COARSE_PROMPT, prepared.playback_speed
        ),
        config_version=config.version,
        processed_duration_sec=source.duration_sec,
        latency_ms=result.latency_ms,
        usage=result.usage,
        cost_usd=result.usage.cost_with_rates(
            config.input_usd_per_million,
            config.output_usd_per_million,
        ),
        prepared_media_bytes=prepared.byte_size,
        prepared_duration_ms=round(prepared.duration_sec * 1000),
    )


def _usage_summary(records: list[UsageRecord]) -> UsageSummary:
    usages = [record.usage for record in records]
    complete = all(
        usage.input_tokens is not None
        and usage.output_tokens is not None
        and usage.thought_tokens is not None
        for usage in usages
    )
    token_usage = None
    if complete:
        input_tokens = sum(usage.input_tokens or 0 for usage in usages)
        output_tokens = sum(
            (usage.output_tokens or 0) + (usage.thought_tokens or 0) for usage in usages
        )
        token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
    costs = [record.cost_usd for record in records]
    total_cost = None
    if all(cost is not None for cost in costs):
        total_cost = Money(
            amount=sum((cost or Decimal(0) for cost in costs), start=Decimal(0)),
            currency="USD",
        )
    return UsageSummary(
        processed_duration_ms=round(
            sum(record.processed_duration_sec for record in records) * 1000
        ),
        token_usage=token_usage,
        latency_ms=sum(record.latency_ms for record in records),
        total_cost=total_cost,
    )
