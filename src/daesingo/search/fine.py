from datetime import UTC, datetime
from uuid import uuid4

from .config import GeminiSearchConfig
from .errors import InvalidFineSpanError
from .execution import RunDeadline
from .ledger import SearchLedger, UsageRecord
from .media import PreparedMedia
from .media_contract import CoarseMediaPreparer
from .prompts import FINE_PROMPT, fine_prompt_for, sent_prompt_fingerprint
from .provider import FineRequest, SearchProvider
from .runs import (
    AnalysisRun,
    CandidateEvent,
    ContractRef,
    Implementation,
    Operation,
    RunId,
    RunOutcome,
    UsageSummary,
)
from .schemas import FineTemporalFact, WireModel
from .scope import SearchHint, VisualEventType
from .smoke_errors import ProviderPayloadError
from .sources import AnalysisSourceResolver, CandidateSourceLink
from .visual import (
    Primitive,
    Target,
    TemporalFact,
    Uncertainty,
    VisualEvidence,
    VisualVerificationResult,
)

_LEGACY_EVENT_NAMES = {"LANE_CHANGE": VisualEventType.SOLID_LINE_LANE_CHANGE}

# `FrameRef`는 `recording.resolve_frame(locator)`만 발급한다
# (`contract-source-asset-media-stream.md` §5.3). Fine 입력은 clip 한 덩어리라
# 모델에게 준 frame inventory가 없고, 따라서 모델이 답할 수 있는 ref도 없다 —
# 실제로 Gemini는 이 칸에 `"00:03"` 같은 타임스탬프를 넣어 돌려줬다(이슈 #135).
# 타임스탬프를 `fr_...`로 합성하는 길은 막혀 있다: `contract-visual-evidence.md` §4
# "위치는 ID에 인코딩하지 않는다", `module-architecture.md` "Consumer가 여러 값을
# 이어 붙여 ref를 합성하는 것도 금지다". 그래서 wire schema에서 이 칸을 빼 애초에
# 묻지 않고, 공개 계약의 `evidence_refs`는 발급받은 ref가 생길 때까지 비워 둔다.
_NO_FRAME_REFS: tuple[str, ...] = ()


def _with_no_frame_refs(item: WireModel) -> dict[str, object]:
    return {**item.model_dump(), "evidence_refs": _NO_FRAME_REFS}


def _clip_relative_temporal_facts(
    facts: tuple[FineTemporalFact, ...],
    prepared: PreparedMedia,
    source_duration_sec: float,
) -> tuple[TemporalFact, ...]:
    """모델이 답한 offset을 그대로 싣는다 — 기준은 Fine input(잘라낸 clip)의 0초다.

    `contract-visual-evidence.md` §7과 `adr-visual-evidence.md`가 `at_offset_ms`를
    "Fine input 시작점 기준 상대 시간"으로 정의한다. Fine input은 candidate span이
    아니라 `verify_fine`이 앞뒤 `fine_padding_sec`을 붙여 잘라낸 clip이다.

    유효 범위는 clip 전체다. padding은 경계에서 시작하는 사건을 보라고 붙인 것이므로
    padding 구간에서 짚은 시각을 거절하면 padding을 준 이유가 사라진다(이슈 #132).

    coarse의 `span.representative_ms`와 일치하는지는 검사하지 않는다. 그 값은 coarse가
    본 대략적 시점이고 이쪽은 fine이 본 시점이다 — 둘이 ms까지 같기를 요구하면 실제
    호출은 통과할 수 없다. mock fixture에서 성립하던
    `representative_ms = span.start_ms + at_offset_ms`는 padding이 0일 때의 파생식이지
    검증 조건이 아니다.
    """
    # 준비 영상은 늘어나 있을 수 있다. provider가 시각을 원본으로 되돌리므로 원본 구간 길이로 잰다.
    # 늘린 영상이면 마지막 준비 프레임 하나(원본 playback_speed 초)만큼 여유를 둔다.
    slack_sec = prepared.playback_speed if prepared.playback_speed < 1.0 else 0.0
    clip_duration_ms = round(
        (prepared.origin_end_sec - prepared.origin_start_sec + slack_sec) * 1000
    )
    origin_start_ms = round(prepared.origin_start_sec * 1000)
    source_duration_ms = round(source_duration_sec * 1000)
    checked: list[TemporalFact] = []
    for item in facts:
        offset = item.at_offset_ms
        if offset is not None:
            if offset < 0 or offset > clip_duration_ms:
                raise ProviderPayloadError("Fine temporal offset outside prepared clip")
            # 방출하지는 않지만, clip이 원본 밖을 가리키면 준비 단계가 어긋난 것이다.
            if origin_start_ms + offset > source_duration_ms:
                raise ProviderPayloadError(
                    "Fine temporal offset outside source duration"
                )
        checked.append(
            TemporalFact(
                at_offset_ms=offset,
                fact=item.fact,
                evidence_refs=_NO_FRAME_REFS,
            )
        )
    return tuple(checked)


def normalize_event_type(value: str | VisualEventType) -> VisualEventType:
    if isinstance(value, VisualEventType):
        return value
    legacy = _LEGACY_EVENT_NAMES.get(value)
    return legacy if legacy is not None else VisualEventType(value)


def verify_fine(
    input_ref: ContractRef,
    candidate: CandidateEvent,
    target_hint: SearchHint | None,
    event_type: VisualEventType,
    resolver: AnalysisSourceResolver,
    provider: SearchProvider,
    config: GeminiSearchConfig,
    ledger: SearchLedger,
    media_preparer: CoarseMediaPreparer,
    deadline: RunDeadline,
) -> VisualVerificationResult:
    source = resolver.resolve_reference(input_ref)
    CandidateSourceLink(source_ref=input_ref, candidate=candidate).validate(source)
    # 후보는 Timeline 좌표다. 입력 좌표로 되돌려 자른다(#252).
    offset_sec = source.timeline_start_sec
    start_sec = max(
        0.0,
        candidate.span.start_ms / 1000 - offset_sec - config.fine_padding_sec,
    )
    end_sec = min(
        source.duration_sec,
        candidate.span.end_ms / 1000 - offset_sec + config.fine_padding_sec,
    )
    if start_sec >= end_sec:
        raise InvalidFineSpanError(
            source_ref=input_ref,
            candidate_id=candidate.candidate_id,
            start_sec=start_sec,
            end_sec=end_sec,
        )
    started = datetime.now(UTC)
    run_id = RunId(f"run_fine_{uuid4().hex}")
    hint_text = ""
    if target_hint is not None:
        hint_text = "; ".join(
            filter(None, (target_hint.vehicle, target_hint.free_text))
        )
    with (
        resolver.open_source(input_ref) as media_input,
        media_preparer.prepare_fine(
            media_input, start_sec, end_sec, deadline
        ) as prepared,
    ):
        deadline.check()
        result = provider.verify_fine(
            FineRequest(
                source,
                event_type,
                hint_text,
                start_sec,
                end_sec,
                media=prepared,
                timeout_sec=deadline.remaining_sec(),
                deadline=deadline,
            )
        )
        ledger.append(
            UsageRecord(
                case_id=source.source_id,
                model=config.model,
                prompt_version=FINE_PROMPT.version,
                prompt_fingerprint=sent_prompt_fingerprint(
                    fine_prompt_for(event_type), prepared.playback_speed
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
        )
        response = result.response
        temporal_facts = _clip_relative_temporal_facts(
            response.temporal_facts,
            prepared,
            source.duration_sec,
        )
    analysis_run = AnalysisRun(
        run_id=run_id,
        operation=Operation.VISUAL_VERIFY,
        input_ref=input_ref,
        implementation=Implementation(
            impl_id="search:gemini-fine-p3",
            model_ref=config.model,
            prompt_version=FINE_PROMPT.version,
            config_version=config.version,
        ),
        outcome=RunOutcome.SUCCEEDED,
        started_at=started,
        completed_at=datetime.now(UTC),
        issues=(),
        usage_refs=(f"usage:{source.source_id}",),
        usage_summary=UsageSummary(
            processed_duration_ms=round(source.duration_sec * 1000),
            token_usage=None,
            latency_ms=result.latency_ms,
            total_cost=None,
        ),
        contract_version="analysis-run-candidate-event/v1.1",
    )
    evidence = VisualEvidence(
        schema_version="visual-evidence/v1.0",
        visual_evidence_id=f"evidence_{uuid4().hex}",
        run_id=run_id,
        input_ref=input_ref,
        candidate_id=candidate.candidate_id,
        verification=response.verification,
        visual_event_type=response.visual_event_type,
        target=Target.model_validate(_with_no_frame_refs(response.target)),
        primitives=tuple(
            Primitive.model_validate(_with_no_frame_refs(item))
            for item in response.primitives
        ),
        temporal_facts=temporal_facts,
        uncertainties=tuple(
            Uncertainty.model_validate(_with_no_frame_refs(item))
            for item in response.uncertainties
        ),
        legal_status=None,
    )
    return VisualVerificationResult(analysis_run=analysis_run, visual_evidence=evidence)
