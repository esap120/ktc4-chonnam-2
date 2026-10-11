from pathlib import Path
from typing import Final

from .coarse import LinkedCoarseResult
from .config import API_KEY_ENV_NAMES, api_key_from_env
from .errors import (
    MissingCandidateError,
    UnknownCandidateError,
    UnknownCandidateRunError,
    VideoStreamSelectionError,
)
from .factory import build_gemini_search_service
from .fixtures import FixtureNotFoundError, FixtureSearchService
from .intent import (
    IntentFailureKind,
    IntentHintExtractor,
    IntentHintResult,
    IntentHintStatus,
    build_intent_hint_extractor,
)
from .runs import CandidateEvent, CandidateSearchResult, ContractRef
from .scope import AnalysisScope, SearchHint, VisualEventType
from .service import SearchService
from .sources import AnalysisSourceResolver, CandidateSourceLink, ResolvedAnalysisSource
from .stream_context import (
    AnalysisSourceStream,
    SelectedVideoStream,
    VisualVerificationExecution,
    select_single_video_stream,
)
from .visual import VisualVerificationResult

_MOCK_DIR: Final = Path(__file__).resolve().parents[3] / "data" / "mock" / "search"
_FIXTURE_SERVICE: Final = FixtureSearchService(_MOCK_DIR)


def search_candidates(
    scope: AnalysisScope,
    *,
    service: SearchService | None = None,
) -> CandidateSearchResult:
    """Return the recorded coarse run and ranked candidates for a scope."""
    if service is None:
        return _FIXTURE_SERVICE.search_candidates(scope)
    return service.search_candidates(scope)


def verify_visual(
    input_ref: ContractRef,
    target_hint: SearchHint | None = None,
    *,
    service: SearchService | None = None,
    event_type: str | VisualEventType = VisualEventType.SOLID_LINE_LANE_CHANGE,
    candidate: CandidateEvent | None = None,
) -> VisualVerificationResult:
    """Return the recorded Fine run together with its visual evidence."""
    if service is None:
        return _FIXTURE_SERVICE.verify_visual(input_ref, target_hint)
    if candidate is None:
        raise MissingCandidateError(source_ref=input_ref)
    return service.verify_visual(input_ref, candidate, target_hint, event_type)


def verify_visual_with_stream_context(
    input_ref: ContractRef,
    candidate: CandidateEvent,
    analysis_source_streams: tuple[AnalysisSourceStream, ...],
    target_hint: SearchHint | None = None,
    *,
    service: SearchService | None = None,
    event_type: str | VisualEventType = VisualEventType.SOLID_LINE_LANE_CHANGE,
) -> VisualVerificationExecution:
    """Run Fine and return its non-canonical selected VIDEO stream context.

    ``analysis_source_streams`` is an execution-only view of the authoritative
    Recording MediaStream facts.  It lets Search select a VIDEO stream without
    parsing opaque refs or applying a default stream policy.
    """
    selected_video_stream = select_single_video_stream(input_ref, analysis_source_streams)
    result = verify_visual(
        input_ref,
        target_hint,
        service=service,
        event_type=event_type,
        candidate=candidate,
    )
    return VisualVerificationExecution(
        result=result,
        selected_video_stream=selected_video_stream,
    )


__all__ = [
    "AnalysisScope",
    "AnalysisSourceStream",
    "AnalysisSourceResolver",
    "CandidateSearchResult",
    "CandidateSourceLink",
    "ContractRef",
    "FixtureNotFoundError",
    "IntentFailureKind",
    "IntentHintExtractor",
    "IntentHintResult",
    "IntentHintStatus",
    "LinkedCoarseResult",
    "ResolvedAnalysisSource",
    "SelectedVideoStream",
    "SearchHint",
    "SearchService",
    "UnknownCandidateError",
    "UnknownCandidateRunError",
    "VideoStreamSelectionError",
    "VisualEventType",
    "VisualVerificationExecution",
    "VisualVerificationResult",
    "API_KEY_ENV_NAMES",
    "api_key_from_env",
    "build_gemini_search_service",
    "build_intent_hint_extractor",
    "search_candidates",
    "select_single_video_stream",
    "verify_visual",
    "verify_visual_with_stream_context",
]
