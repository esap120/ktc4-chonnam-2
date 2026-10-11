from daesingo.search.config import GeminiSearchConfig
from daesingo.search.provider import CoarseRequest, FineRequest, ProviderResult
from daesingo.search.runs import (
    CandidateEvent,
    CandidateId,
    CandidateSpan,
    ContractRef,
    RunId,
)
from daesingo.search.schemas import CoarseResponse, FineResponse
from daesingo.search.scope import (
    AnalysisScope,
    SearchBudget,
    SearchHint,
    TimelineRef,
    TimelineRelativeTimeRange,
    TimeRangeKind,
    VisualEventType,
)
from daesingo.search.service import SearchService
from daesingo.search.sources import ResolvedAnalysisSource, StaticAnalysisSourceResolver
from daesingo.search.usage import ProviderUsage
from tests.search._search_service_support import (
    FixtureMediaPreparer,
    OpenableResolver,
    frozen_clock,
    remember_coarse_run,
)


class _Provider:
    def search_coarse(self, request: CoarseRequest) -> ProviderResult[CoarseResponse]:
        assert request.source.timeline_id == "clip-1"
        response = CoarseResponse.model_validate(
            {
                "candidates": [
                    {
                        "event_type": "SOLID_LINE_LANE_CHANGE",
                        "span": {"start_sec": 6, "end_sec": 8},
                        "at_sec": 7,
                        "observed": [
                            "점선처럼 보이나 횡단",
                            "선 종류 판별 불확실",
                            "점선 차로로 변경",
                        ],
                        "score": 0.3,
                    },
                    {
                        "event_type": "SIGNAL",
                        "span": {"start_sec": 1, "end_sec": 3},
                        "at_sec": 2,
                        "observed": ["적색 점등"],
                        "score": 0.9,
                    },
                ]
            }
        )
        return ProviderResult(response, ProviderUsage(10, 2, 0, 12), 15)

    def verify_fine(self, request: FineRequest) -> ProviderResult[FineResponse]:
        assert request.event_type is VisualEventType.SOLID_LINE_LANE_CHANGE
        response = FineResponse.model_validate(
            {
                "verification": "UNCERTAIN",
                "visual_event_type": None,
                "target": {
                    "association_status": "AMBIGUOUS",
                    "described_as": None,
                    "match_with_hint": None,
                    "association_confidence": None,
                    "track_ref": None,
                },
                "primitives": [],
                "temporal_facts": [],
                "uncertainties": [
                    {
                        "kind": "LOW_RESOLUTION",
                        "detail": "선 종류 판별 불가",
                    }
                ],
            }
        )
        return ProviderResult(response, ProviderUsage(10, 2, 0, 12), 15)


def test_service_keeps_uncertain_lane_candidates_and_normalizes_rank_and_time():
    source = ResolvedAnalysisSource(
        ContractRef(kind="analysis_source", ref="clip-1"), 10.0, "clip-1", 4
    )
    resolver = StaticAnalysisSourceResolver({"scope-1": (source,)}, {})
    service = SearchService(
        OpenableResolver(resolver),
        _Provider(),
        GeminiSearchConfig(),
        FixtureMediaPreparer(source.duration_sec),
        frozen_clock,
    )
    scope = AnalysisScope(
        scope_id="scope-1",
        time_ranges=(
            TimelineRelativeTimeRange(
                kind=TimeRangeKind.TIMELINE_RELATIVE,
                timeline_ref=TimelineRef(timeline_id="clip-1", revision=4),
                start_ms=0,
                end_ms=10_000,
            ),
        ),
        target_event_types=tuple(VisualEventType),
        hint=SearchHint(vehicle=None, free_text=None),
        budget=SearchBudget(max_cost_krw=1000, max_latency_sec=30),
        contract_version="1.1.0",
    )

    result = service.search_candidates(scope)

    assert [candidate.rank for candidate in result.candidates] == [1, 2]
    assert result.candidates[0].event_type_hint is VisualEventType.SIGNAL
    lane = result.candidates[1]
    assert lane.span.representative_ms == 7000
    assert lane.span.timeline_revision == 4
    assert "점선처럼 보이나 횡단" in lane.uncertainties
    assert "점선 차로로 변경" not in lane.uncertainties
    record = service.ledger.records()[0]
    assert record.prompt_version == "coarse-p3"
    assert len(record.prompt_fingerprint) == 64


def test_fine_routes_legacy_event_name_to_the_contract_enum():
    source = ResolvedAnalysisSource(
        ContractRef(kind="analysis_source", ref="source-1"), 10.0, "clip-1", 1
    )
    resolver = StaticAnalysisSourceResolver({}, {"source-1": source})
    service = SearchService(
        OpenableResolver(resolver),
        _Provider(),
        GeminiSearchConfig(),
        FixtureMediaPreparer(source.duration_sec),
        frozen_clock,
    )
    candidate = CandidateEvent(
        candidate_id=CandidateId("candidate-1"),
        run_id=RunId("run-coarse-1"),
        span=CandidateSpan(
            timeline_id="clip-1",
            timeline_revision=1,
            start_ms=1000,
            end_ms=3000,
            representative_ms=2000,
        ),
        rank=1,
        ranking_score=0.9,
        event_type_hint=VisualEventType.SOLID_LINE_LANE_CHANGE,
        summary="lane change",
        uncertainties=(),
        thumbnail_ref=None,
    )

    remember_coarse_run(service, candidate.run_id)
    result = service.verify_visual(
        ContractRef(kind="analysis_source", ref="source-1"),
        candidate,
        event_type="LANE_CHANGE",
    )

    assert result.visual_evidence.verification.value == "UNCERTAIN"
    assert result.visual_evidence.visual_event_type is None
