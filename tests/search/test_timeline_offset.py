"""Timeline 중간에서 시작하는 AnalysisSource의 좌표 변환(#252)."""

from daesingo.search.config import GeminiSearchConfig
from daesingo.search.provider import FineRequest, ProviderResult
from daesingo.search.runs import ContractRef
from daesingo.search.schemas import FineResponse
from daesingo.search.scope import VisualEventType
from daesingo.search.service import SearchService
from daesingo.search.sources import ResolvedAnalysisSource, StaticAnalysisSourceResolver
from tests.search._search_service_support import (
    FixtureMediaPreparer,
    OpenableResolver,
    frozen_clock,
)
from tests.search.test_scope_budget import _scope, _TimeoutSpy

_REF = ContractRef(kind="analysis_source", ref="clip-budget-1")
# Timeline 30초부터 10초 길이의 입력
_SOURCE = ResolvedAnalysisSource(
    _REF, 10.0, "clip-budget-1", 1, timeline_start_sec=30.0
)


class _FineWindowSpy(_TimeoutSpy):
    windows: list[tuple[float, float]]

    def __init__(self) -> None:
        super().__init__()
        self.windows = []

    def verify_fine(self, request: FineRequest) -> ProviderResult[FineResponse]:
        self.windows.append((request.start_sec, request.end_sec))
        return super().verify_fine(request)


def test_coarse_shifts_to_timeline_and_fine_shifts_back() -> None:
    spy = _FineWindowSpy()
    service = SearchService(
        OpenableResolver(
            StaticAnalysisSourceResolver(
                {"scope-budget-1": (_SOURCE,)}, {"clip-budget-1": _SOURCE}
            )
        ),
        spy,
        GeminiSearchConfig(),
        FixtureMediaPreparer(_SOURCE.duration_sec),
        frozen_clock,
    )

    # 입력 좌표 1~3초(대표 2초) 후보 → Timeline 31~33초
    (candidate,) = service.search_candidates(_scope(30)).candidates
    assert (
        candidate.span.start_ms,
        candidate.span.end_ms,
        candidate.span.representative_ms,
    ) == (31_000, 33_000, 32_000)

    # Fine은 입력 좌표로 되돌려 ±4초 padding: max(0, 1-4)=0 ~ min(10, 3+4)=7
    _ = service.verify_visual(_REF, candidate, event_type=VisualEventType.SIGNAL)
    assert spy.windows == [(0.0, 7.0)]
