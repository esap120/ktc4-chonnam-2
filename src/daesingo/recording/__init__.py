"""Recording 모듈의 공개 패키지 경계."""

from .fixtures import RecordingFixture, load_recording_fixture
from .errors import RecordingCapabilityError
from .models import (
    GPSCoordinate,
    GPSObservation,
    AnalysisSource,
    AssetFacts,
    AssetSpan,
    ContractRef,
    DeletionReport,
    DerivedAsset,
    FrameRef,
    IncidentClip,
    MediaStream,
    RecordingTimeline,
    RemoteCopy,
    RemoteCopyInfo,
    SourceAsset,
    SpanResolution,
    TimeRange,
    TimelineRef,
    TimelinePositionLocator,
)
from .probe import FfprobeMediaProbe
from .materialization import AnalysisProfile, LocalAnalysisMaterializer
from .incidents import IncidentClipEncoding, LocalIncidentMaterializer
from .time_sources import (AnchorApplication, LocalTimeSourceObserver, ObservedTimeSources,
                           TimeSourceCandidate, TimeSourceCheck)
from .service import OpenedAnalysisSource, RecordingService, RegisteredSource

__all__ = [
    "GPSCoordinate",
    "GPSObservation",
    "AnchorApplication",
    "LocalTimeSourceObserver",
    "ObservedTimeSources",
    "TimeSourceCandidate",
    "TimeSourceCheck",
    "IncidentClipEncoding",
    "LocalIncidentMaterializer",
    "AnalysisProfile",
    "LocalAnalysisMaterializer",
    "AnalysisSource",
    "AssetFacts",
    "AssetSpan",
    "ContractRef",
    "DeletionReport",
    "DerivedAsset",
    "FrameRef",
    "FfprobeMediaProbe",
    "IncidentClip",
    "MediaStream",
    "OpenedAnalysisSource",
    "RecordingCapabilityError",
    "RecordingFixture",
    "RecordingService",
    "RegisteredSource",
    "RecordingTimeline",
    "RemoteCopy",
    "RemoteCopyInfo",
    "SourceAsset",
    "SpanResolution",
    "TimeRange",
    "TimelineRef",
    "TimelinePositionLocator",
    "load_recording_fixture",
]
