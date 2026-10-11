"""IncidentClip 생성 설정. Readout source_profile/AnalysisSource ref와 독립이다."""

from dataclasses import dataclass
from pathlib import Path

from .materialization import AnalysisProfile, LocalAnalysisMaterializer, MaterializedVideo
from .models import AssetSpan
from .probe import LocalSource
from .analysis_tail import analysis_tail_scope
from .multi_analysis import materialize_chain


@dataclass(frozen=True)
class IncidentClipEncoding:
    height: int
    preset: str
    crf: int


class LocalIncidentMaterializer:
    def __init__(self, encoding: IncidentClipEncoding, *, ffmpeg="ffmpeg", ffprobe="ffprobe",
                 timeout_sec=120.0, temp_root: Path | None = None):
        # 기존 엔진의 설정 검증·frame cut·출력 probe·cleanup만 재사용한다.
        # 이 내부 설정 key는 AnalysisSource.profile_ref로 발행되지 않는다.
        configuration = AnalysisProfile(encoding.height, encoding.preset, encoding.crf)
        self._engine = LocalAnalysisMaterializer({"incident-encoding": configuration},
            ffmpeg=ffmpeg, ffprobe=ffprobe, timeout_sec=timeout_sec, temp_root=temp_root)
        self._identity = ("incident-materialization/v1", encoding.height, encoding.preset, encoding.crf)

    @property
    def generation_conditions(self) -> tuple:
        return self._identity

    def materialize(self, source: LocalSource, index: int, span: AssetSpan) -> MaterializedVideo:
        with analysis_tail_scope(False):
            return self._engine.materialize(source, index, span, "incident-encoding")

    def _materialize_many(self, inputs) -> MaterializedVideo:
        # Search 호출에 중첩돼도 모든 구간과 최종 연결은 strict다.
        with analysis_tail_scope(False):
            return materialize_chain(self._engine, inputs, "incident-encoding")
