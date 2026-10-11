"""Consumer가 저장 구조를 몰라도 호출할 수 있는 recording 공개 entry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO, RawIOBase
import hashlib
import math
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from pydantic import TypeAdapter

from .errors import RecordingCapabilityError
from .fixtures import RecordingFixture
from .models import (
    GPSObservation,
    AnalysisSource,
    AssetSpan,
    AssetFacts,
    ContractRef,
    DeletionItem,
    DeletionReport,
    DerivedAsset,
    FrameLocator,
    FrameRef,
    IncidentClip,
    IncidentClipProvenance,
    MediaStream,
    RecordingTimeline,
    RemoteCopy,
    RemoteCopyInfo,
    SpanResolution,
    SourceAsset,
    StreamPositionLocator,
    TimelinePositionLocator,
    TimeRange,
    TimelineRef,
)
from .repository import InMemoryRecordingRepository
from .probe import FfprobeMediaProbe, MediaProbe
from .timeline import build_relative_timeline
from .multi_source import build_placed_timeline, resolve_placed_span
from .multi_analysis import materialize_chain
from .analysis_tail import analysis_tail_scope
from .frames import FfmpegFrameExtractor, FrameExtractor
from .facts import inspect_local_source
from .spans import resolve_local_span
from .materialization import LocalAnalysisMaterializer, _FrameCoverageError
from .inspection import SourceFrameInspections, source_inspections
from .incidents import LocalIncidentMaterializer
from .time_sources import AnchorApplication, LocalTimeSourceObserver, ObservedTimeSources, TimeSourceCandidate


_FRAME_LOCATOR_ADAPTER = TypeAdapter(FrameLocator)
_ASSET_FACT_KINDS = {"source_asset", "analysis_source", "incident_clip", "derived_asset"}


@dataclass(frozen=True)
class OpenedAnalysisSource:
    stream: BinaryIO
    content_type: str
    byte_size: int


@dataclass(frozen=True)
class RegisteredSource:
    """기존 계약 객체를 묶는 Python 반환값. 새 Canonical Contract가 아니다."""

    source_asset: SourceAsset
    media_streams: tuple[MediaStream, ...]


class _SyntheticBinaryStream(RawIOBase):
    """Fixture의 선언 크기를 메모리 할당 없이 재현하는 seekable stream."""

    def __init__(self, size: int) -> None:
        super().__init__()
        self._size = size
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            position = offset
        elif whence == 1:
            position = self._position + offset
        elif whence == 2:
            position = self._size + offset
        else:
            raise ValueError("지원하지 않는 whence입니다")
        if position < 0:
            raise ValueError("stream 시작 전으로 이동할 수 없습니다")
        self._position = min(position, self._size)
        return self._position

    def read(self, size: int = -1) -> bytes:
        remaining = self._size - self._position
        count = remaining if size is None or size < 0 else min(size, remaining)
        self._position += count
        return bytes(count)


class RecordingService:
    def __init__(
        self, repository: InMemoryRecordingRepository | None = None,
        *, media_probe: MediaProbe | None = None,
        frame_extractor: FrameExtractor | None = None,
        analysis_materializer: LocalAnalysisMaterializer | None = None,
        incident_materializer: LocalIncidentMaterializer | None = None,
        time_source_observer: LocalTimeSourceObserver | None = None,
    ) -> None:
        self._repository = repository or InMemoryRecordingRepository()
        self._media_probe = media_probe or FfprobeMediaProbe()
        self._frame_extractor = frame_extractor or FfmpegFrameExtractor()
        self._analysis_materializer = analysis_materializer
        self._source_inspections = SourceFrameInspections()
        self._local_analysis: dict[str, tuple[AnalysisSource, bytes]] = {}
        self._analysis_reuse: dict[tuple, str] = {}
        self._local_analysis_refs: set[str] = set()
        self._analysis_closed = False
        self._incident_materializer = incident_materializer
        self._local_clips: dict[str, tuple[IncidentClip, bytes]] = {}
        self._clip_identity: dict[tuple, str] = {}
        self._local_clip_refs: set[str] = set()
        self._time_source_observer = time_source_observer or LocalTimeSourceObserver()
        self._time_observations: dict[str, ObservedTimeSources] = {}
        self._time_candidates: dict[str, TimeSourceCandidate] = {}

    def observe_time_sources(self, source_asset_ref: str) -> ObservedTimeSources:
        local = self._repository.get_local_source(source_asset_ref)
        if local is None:
            raise RecordingCapabilityError("UNKNOWN_REF", "등록된 로컬 원본 ref가 필요합니다")
        self._time_source_observer.verify_source(local)
        if source_asset_ref not in self._time_observations:
            observed = self._time_source_observer.observe(source_asset_ref, local)
            self._time_observations[source_asset_ref] = observed
            for candidate in observed.candidates:
                self._time_candidates[candidate.candidate_id] = candidate
        return self.get_time_sources(source_asset_ref)

    def get_time_sources(self, source_asset_ref: str) -> ObservedTimeSources:
        observed = self._time_observations.get(source_asset_ref)
        if observed is None:
            raise RecordingCapabilityError("NOT_FOUND", "이 원본의 시간 관찰 결과가 없습니다")
        return ObservedTimeSources(tuple(c.model_copy(deep=True) for c in observed.candidates),
                                   tuple(c.model_copy(deep=True) for c in observed.checks))

    def get_time_source_candidate(self, candidate_id: str) -> TimeSourceCandidate:
        candidate = self._time_candidates.get(candidate_id)
        if candidate is None:
            raise RecordingCapabilityError("UNKNOWN_REF", "등록되지 않은 시각 후보입니다")
        return candidate.model_copy(deep=True)

    def apply_filename_anchor(self, timeline_ref: TimelineRef | dict[str, Any], candidate_id: str | None,
                              *, overlay_matches: bool | None, trusted: bool = False) -> AnchorApplication:
        """수동 대조 입력을 별도 실행 결과로 보존한다. Candidate의 검증 상태는 바꾸지 않는다."""
        if (overlay_matches is not None and type(overlay_matches) is not bool) or type(trusted) is not bool:
            raise ValueError("수동 대조와 신뢰 입력은 명시적 bool이어야 합니다")
        ref = TimelineRef.model_validate(timeline_ref)
        timeline = self.get_timeline(ref.timeline_id, ref.revision)
        latest = self.get_latest_timeline(timeline.timeline_id)
        if timeline.revision != latest.revision:
            raise ValueError("stale timeline revision: 최신 revision만 anchor 적용 대상으로 사용할 수 있습니다")
        if (timeline.timeline_status != "USABLE_RELATIVE_ONLY" or len(timeline.source_placements) != 1
                or timeline.source_placements[0].timeline_start_sec != 0.0):
            raise ValueError("단일 원본의 0초 시작 relative-only Timeline이 필요합니다")
        if overlay_matches is not True or trusted is not True or candidate_id is None:
            return AnchorApplication(timeline, overlay_matches, trusted, False)
        candidate = self.get_time_source_candidate(candidate_id)
        placement = timeline.source_placements[0]
        if (candidate.source_kind != "FILENAME" or candidate.applies_to.source_asset_ref != placement.source_asset_ref
                or candidate.applies_to.source_offset_sec != 0.0):
            raise ValueError("해당 원본 시작점의 filename 후보만 anchor로 적용할 수 있습니다")
        local = self._repository.get_local_source(placement.source_asset_ref)
        if local is None:
            raise RecordingCapabilityError("UNAVAILABLE", "anchor 원본에 접근할 수 없습니다")
        self._time_source_observer.verify_source(local)
        payload = timeline.model_dump()
        payload.update(revision=latest.revision + 1, timeline_status="USABLE",
                       time_source_candidates=[c.candidate_id for c in self.get_time_sources(placement.source_asset_ref).candidates])
        payload["time_basis"]["working_anchor"] = {
            "value": candidate.value, "source_candidate_ref": candidate.candidate_id, "status": "OK"}
        anchored = RecordingTimeline.model_validate(payload)
        self._repository.add_timeline(anchored)
        return AnchorApplication(anchored, overlay_matches, trusted, True)

    def close(self) -> None:
        """로컬 prepared media 메모리를 해제한다. 이미 열린 독립 stream은 호출자가 닫는다."""
        self._local_analysis.clear()
        self._analysis_reuse.clear()
        self._local_clips.clear()
        self._clip_identity.clear()
        self._source_inspections.close()
        self._analysis_closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def list_gps_observations(self) -> list[GPSObservation]:
        """등록된 Mock GPS 관찰값의 독립 복사본. 미기재는 UNKNOWN이 아니라 []다."""
        return self._repository.list_gps_observations()

    def register_local_source(self, path: str | Path) -> RegisteredSource:
        """읽기 전용 로컬 영상 등록. 경로는 신뢰된 로컬 호출 입력으로만 받는다.

        실패 시 자산을 등록하지 않는다. 매 성공 호출은 새 opaque ref를 발급한다.
        Source는 파일 읽기를 확인했으므로 AVAILABLE, stream은 decode 검사 전이므로
        UNKNOWN이다. 카메라 방향과 누락된 stream duration을 추정하지 않는다.
        """
        source = self._media_probe.probe(Path(path))
        source_ref = f"sa_{uuid4().hex}"
        streams = tuple(
            MediaStream(
                contract="MediaStream", contract_version="source-asset-media-stream/v1",
                media_stream_ref=f"ms_{uuid4().hex}", source_asset_ref=source_ref,
                media_type=stream.media_type,
                role="UNKNOWN" if stream.media_type == "VIDEO" else None,
                availability="UNKNOWN", duration_sec=stream.duration_sec,
            ) for stream in source.streams
        )
        asset = SourceAsset(
            contract="SourceAsset", contract_version="source-asset-media-stream/v1",
            source_asset_ref=source_ref, asset_kind="SOURCE_ASSET", external_source_ref=None,
            media_stream_refs=[stream.media_stream_ref for stream in streams],
            byte_size=source.byte_size, availability="AVAILABLE", duration_sec=source.duration_sec,
        )
        self._repository.add_local_source(asset, streams, source)
        return RegisteredSource(asset, streams)

    @classmethod
    def from_fixture(
        cls,
        fixture: RecordingFixture,
        *,
        case_id: str | None = None,
    ) -> RecordingService:
        # frozen 모델의 내부 list/model_copy로 변조한 값도 등록 전에 다시 검증한다.
        payload = fixture.model_dump()
        # default list를 나중에 수정한 경우도 빠짐없이 검사한다. GPS 내부의
        # optional 필드 생략 여부는 revalidate_instances 모델을 통해 보존한다.
        payload["gps_observations"] = fixture.gps_observations
        fixture = RecordingFixture.model_validate(payload)
        service = cls()
        for asset in fixture.source_assets:
            service._repository.add_source_asset(asset)
        for stream in fixture.media_streams:
            service._repository.add_media_stream(stream)
        for observation in fixture.gps_observations:
            service._repository.add_gps_observation(observation)
        for frame in fixture.frame_refs:
            stub_content = f"fixture-frame:{frame.frame_ref}".encode()
            service._repository.add_frame(frame, content=stub_content)
        for facts in fixture.asset_facts:
            service._repository.add_asset_facts(facts)
        for timeline in fixture.recording_timelines:
            service._repository.add_timeline(timeline)
        for resolution in fixture.span_resolutions:
            service._repository.add_span_resolution(resolution)
        for source in fixture.analysis_sources:
            stream_factory = None
            if source.availability == "AVAILABLE" and source.byte_size is not None:
                stream_factory = lambda size=source.byte_size: _SyntheticBinaryStream(size)
            service._repository.add_analysis_source(source, stream_factory=stream_factory)
        for remote_copy in fixture.remote_copies:
            service._repository.add_remote_copy(remote_copy)
        for clip in fixture.incident_clips:
            service._repository.add_incident_clip(clip)
        for asset in fixture.derived_assets:
            service._repository.add_derived_asset(asset)
        if case_id is not None:
            for source in fixture.analysis_sources:
                service._repository.associate_case_asset(
                    case_id,
                    ContractRef(kind="analysis_source", ref=source.analysis_source_ref),
                )
            for clip in fixture.incident_clips:
                service._repository.associate_case_asset(
                    case_id,
                    ContractRef(kind="incident_clip", ref=clip.incident_clip_ref),
                )
            for asset in fixture.derived_assets:
                service._repository.associate_case_asset(
                    case_id,
                    ContractRef(kind="derived_asset", ref=asset.derived_asset_ref),
                )
            for remote_copy in fixture.remote_copies:
                service._repository.associate_case_asset(
                    case_id,
                    ContractRef(kind="remote_copy", ref=remote_copy.remote_copy_ref),
                )
        return service

    def resolve_frame(self, locator: FrameLocator | dict[str, Any]) -> FrameRef:
        parsed = _FRAME_LOCATOR_ADAPTER.validate_python(locator)
        if isinstance(parsed, TimelinePositionLocator):
            timeline = self._repository.get_timeline(parsed.timeline_ref)
            if timeline is None:
                raise RecordingCapabilityError("UNKNOWN_REF", "등록되지 않은 timeline입니다")
            frames = self._repository.find_frames_at_timeline_position(timeline, parsed.at_sec)
            if not frames:
                raise RecordingCapabilityError("FRAME_NOT_FOUND", "해당 timeline 위치의 frame이 없습니다")
            if len(frames) > 1:
                raise RecordingCapabilityError(
                    "TEMPORARY_FAILURE",
                    "여러 frame 후보를 구분할 stream_selector가 필요합니다",
                )
            return frames[0]

        if not math.isfinite(parsed.source_offset_sec):
            raise ValueError("source_offset_sec은 유한한 값이어야 합니다")
        stream = self._repository.get_media_stream(parsed.media_stream_ref)
        if stream is None:
            raise RecordingCapabilityError("UNKNOWN_REF", "등록되지 않은 MediaStream입니다")
        local = self._repository.get_local_source(stream.source_asset_ref)
        if local is not None:
            if stream.media_type != "VIDEO":
                raise RecordingCapabilityError("FRAME_NOT_FOUND", "video stream에만 frame이 있습니다")
            if stream.availability == "UNAVAILABLE":
                raise RecordingCapabilityError("STREAM_UNAVAILABLE", "MediaStream을 읽을 수 없습니다")
            if stream.duration_sec is not None and parsed.source_offset_sec >= stream.duration_sec:
                raise RecordingCapabilityError("OUT_OF_RANGE", "요청 위치가 MediaStream 범위를 벗어납니다")
            index = self._repository.get_local_stream_index(stream.media_stream_ref)
            if index is None:
                raise RecordingCapabilityError("STREAM_UNAVAILABLE", "원본 stream index가 없습니다")
            decoded = self._frame_extractor.extract(local, index, parsed.source_offset_sec)
            frame = self._repository.find_frame_at(stream.media_stream_ref, decoded.source_offset_sec)
            if frame is not None:
                if self._repository.get_frame_content(frame.frame_ref) != decoded.content:
                    raise RecordingCapabilityError("TEMPORARY_FAILURE", "동일 frame 위치의 내용이 달라졌습니다")
                return frame
            frame = FrameRef(
                contract="FrameRef", contract_version="source-asset-media-stream/v1",
                frame_ref=f"fr_{uuid4().hex}", media_stream_ref=stream.media_stream_ref,
                source_offset_sec=decoded.source_offset_sec,
            )
            self._repository.add_frame(frame, content=decoded.content)
            return frame
        if stream.availability != "AVAILABLE":
            raise RecordingCapabilityError("STREAM_UNAVAILABLE", "MediaStream을 읽을 수 없습니다")
        if stream.duration_sec is not None and parsed.source_offset_sec > stream.duration_sec:
            raise RecordingCapabilityError("OUT_OF_RANGE", "요청 위치가 MediaStream 범위를 벗어납니다")

        frame = self._repository.find_frame_at(
            parsed.media_stream_ref,
            parsed.source_offset_sec,
        )
        if frame is None:
            raise RecordingCapabilityError("FRAME_NOT_FOUND", "해당 위치의 FrameRef가 없습니다")
        return frame

    def read_frame(self, frame_ref: str) -> bytes:
        frame = self._repository.get_frame(frame_ref)
        if frame is None:
            raise RecordingCapabilityError("UNKNOWN_REF", "등록되지 않은 FrameRef입니다")
        content = self._repository.get_frame_content(frame_ref)
        if content is None:
            raise RecordingCapabilityError("FRAME_NOT_FOUND", "frame image를 읽을 수 없습니다")
        return content

    def lookup_asset_facts(self, asset_ref: ContractRef | dict[str, Any]) -> AssetFacts:
        parsed = ContractRef.model_validate(asset_ref)
        if parsed.kind not in _ASSET_FACT_KINDS:
            raise RecordingCapabilityError(
                "INVALID_REF_KIND",
                "이 ref kind는 AssetFacts 조회 대상이 아닙니다",
            )
        if parsed.kind == "source_asset":
            local = self._repository.get_local_source(parsed.ref)
            if local is not None:
                asset = self._repository.get_source_asset(parsed.ref)
                if asset is None:
                    raise RecordingCapabilityError("TEMPORARY_FAILURE", "등록된 원본 정보를 읽을 수 없습니다")
                return inspect_local_source(asset, local)
        facts = self._repository.get_asset_facts(parsed.kind, parsed.ref)
        if facts is None:
            raise RecordingCapabilityError("UNKNOWN_REF", "등록되지 않은 자산 ref입니다")
        return facts

    def create_relative_timeline(self, source_asset_ref: str) -> RecordingTimeline:
        """등록된 단일 Source를 [0, duration)에 배치한 새 revision 1을 생성한다.

        등록 당시 metadata를 사용한다. 절대시각 추정·파일 연결·rebase는 하지 않는다.
        stream 길이/가용성은 원래 사실을 유지하며 이후 span 해석에서 별도로 다룬다.
        """
        asset = self._repository.get_source_asset(source_asset_ref)
        if asset is None:
            raise RecordingCapabilityError("UNKNOWN_REF", "등록되지 않은 SourceAsset입니다")
        streams = []
        for ref in asset.media_stream_refs:
            stream = self._repository.get_media_stream(ref)
            if stream is None:
                raise ValueError("SourceAsset이 참조하는 MediaStream이 등록되지 않았습니다")
            streams.append(stream)
        timeline = build_relative_timeline(asset, tuple(streams))
        self._repository.add_timeline(timeline)
        return timeline

    def create_relative_timeline_from_placements(
        self, placements: list[dict[str, Any]], *,
        base_timeline_ref: TimelineRef | dict[str, Any] | None = None,
    ) -> RecordingTimeline:
        """같은 논리 카메라의 명시적 비중복 배치. 각 source local offset은 0부터다."""
        timeline = build_placed_timeline(self._repository, placements, base_timeline_ref)
        self._repository.add_timeline(timeline)
        return timeline

    def get_timeline(
        self,
        timeline_id: str,
        revision: int,
    ) -> RecordingTimeline:
        timeline_ref = TimelineRef(timeline_id=timeline_id, revision=revision)
        timeline = self._repository.get_timeline(timeline_ref)
        if timeline is None:
            raise ValueError("존재하지 않는 timeline reference입니다")
        return timeline

    def get_latest_timeline(self, timeline_id: str) -> RecordingTimeline:
        timeline = self._repository.get_latest_timeline(timeline_id)
        if timeline is None:
            raise ValueError("존재하지 않는 timeline_id입니다")
        return timeline

    def resolve_span(
        self,
        timeline_ref: TimelineRef | dict[str, Any],
        requested_range: TimeRange | dict[str, Any],
        *, media_stream_ref: str | None = None,
        media_stream_refs: list[str] | None = None,
    ) -> SpanResolution:
        """로컬 계산에는 Case가 전달한 VIDEO ref가 필수다. 무선택 fixture 호출만 호환한다."""
        parsed_ref = TimelineRef.model_validate(timeline_ref)
        parsed_range = TimeRange.model_validate(requested_range)
        if (not all(math.isfinite(value) for value in (parsed_range.start_sec, parsed_range.end_sec))
                or parsed_range.start_sec < 0 or parsed_range.end_sec <= parsed_range.start_sec):
            raise ValueError("요청 범위는 유한하며 0 <= start < end를 만족해야 합니다")
        timeline = self._repository.get_timeline(parsed_ref)
        if timeline is None:
            raise ValueError("존재하지 않는 timeline reference입니다")

        if media_stream_refs is not None:
            if media_stream_ref is not None:
                raise ValueError("단일 ref와 복수 ref 입력을 함께 사용할 수 없습니다")
            return resolve_placed_span(self._repository, timeline, parsed_range, media_stream_refs)

        is_local = any(self._repository.get_local_source(p.source_asset_ref) is not None
                       for p in timeline.source_placements)
        if is_local or media_stream_ref is not None:
            if not isinstance(media_stream_ref, str) or not media_stream_ref:
                raise ValueError("명시적인 VIDEO media_stream_ref가 필요합니다")
            matches = [p for p in timeline.source_placements
                       for ref in p.media_stream_refs if ref == media_stream_ref]
            stream = self._repository.get_media_stream(media_stream_ref)
            if len(matches) != 1 or stream is None or stream.media_type != "VIDEO":
                raise ValueError("선택 ref는 해당 Timeline revision에 한 번 소속된 VIDEO여야 합니다")
            placement = matches[0]
            source = self._repository.get_source_asset(placement.source_asset_ref)
            if (source is None or stream.source_asset_ref != placement.source_asset_ref
                    or source.media_stream_refs.count(media_stream_ref) != 1):
                raise ValueError("선택 ref의 원본 소속이 Timeline과 일치하지 않습니다")
        if is_local:
            resolution = resolve_local_span(self._repository, timeline, parsed_range,
                                            selected_stream_ref=media_stream_ref)
            if len(resolution.spans) > 1 or any(s.media_stream_ref != media_stream_ref for s in resolution.spans):
                raise RecordingCapabilityError("TEMPORARY_FAILURE", "Baseline에서 선택 ref의 단일 span을 확정할 수 없습니다")
            return resolution

        resolution = self._repository.get_span_resolution(parsed_ref, parsed_range)
        if resolution is None:
            raise RecordingCapabilityError(
                "TEMPORARY_FAILURE",
                "이 요청 범위의 SpanResolution이 fixture adapter에 등록되지 않았습니다",
            )
        if media_stream_ref is not None and (
                len(resolution.spans) != 1 or resolution.spans[0].media_stream_ref != media_stream_ref):
            raise RecordingCapabilityError("TEMPORARY_FAILURE", "fixture 결과가 선택 ref의 단일 span과 일치하지 않습니다")
        return resolution

    def prepare_analysis_source(
        self,
        span: AssetSpan | dict[str, Any],
        profile_ref: str,
        *, timeline_ref: TimelineRef | dict[str, Any] | None = None,
    ) -> AnalysisSource:
        parsed_span = AssetSpan.model_validate(span)
        if not profile_ref:
            raise ValueError("profile_ref는 비어 있을 수 없습니다")
        local = self._repository.get_local_source(parsed_span.source_asset_ref)
        if local is not None:
            if self._analysis_closed:
                raise RecordingCapabilityError("UNAVAILABLE", "로컬 AnalysisSource 실행이 종료되었습니다")
            if timeline_ref is None:
                raise ValueError("실제 AnalysisSource에는 명시적인 timeline_ref가 필요합니다")
            ref = TimelineRef.model_validate(timeline_ref)
            resolution = self.resolve_span(ref, parsed_span.timeline_range,
                                           media_stream_ref=parsed_span.media_stream_ref)
            if resolution.status != "COMPLETE":
                reasons = {missing.reason for missing in resolution.missing_ranges}
                failure = resolution.failure
                # 구체적인 검사 실패 코드는 그대로 전달한다. 일반적인 전체 실패는
                # 단일 missing reason이 있으면 그 관측 원인을 보존한다.
                if failure is not None and failure.code != "NO_USABLE_SPAN":
                    code = failure.code
                elif len(reasons) == 1:
                    code = next(iter(reasons))
                else:
                    code = failure.code if failure is not None else "TEMPORARY_FAILURE"
                raise RecordingCapabilityError(code, "현재 원본 상태에서 AnalysisSource 구간을 준비할 수 없습니다")
            if resolution.spans != [parsed_span]:
                raise ValueError("span이 해당 Timeline revision의 실제 매핑과 일치하지 않습니다")
            if self._analysis_materializer is None:
                raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "로컬 materialization configuration이 없습니다")
            if not self._analysis_materializer.has_profile(profile_ref):
                raise ValueError("등록되지 않은 profile_ref입니다")
            key = (ref.timeline_id, ref.revision, parsed_span.model_dump_json(), profile_ref)
            cached = self._analysis_reuse.get(key)
            if cached is not None:
                return self._local_analysis[cached][0].model_copy(deep=True)
            index = self._repository.get_local_stream_index(parsed_span.media_stream_ref)
            if index is None:
                raise RecordingCapabilityError("UNAVAILABLE", "원본 stream index가 없습니다")
            with source_inspections(self._source_inspections), analysis_tail_scope():
                prepared = self._analysis_materializer.materialize(local, index, parsed_span, profile_ref)
            source = AnalysisSource(
                contract="AnalysisSource", contract_version="analysis-source-derived/v1",
                analysis_source_ref=f"as_{uuid4().hex}", asset_kind="ANALYSIS_SOURCE",
                source_refs=[ContractRef(kind="source_asset", ref=parsed_span.source_asset_ref)],
                media_stream_refs=[parsed_span.media_stream_ref], byte_size=len(prepared.content),
                availability="AVAILABLE", duration_sec=prepared.duration_sec,
                timeline_ref=ref, timeline_range=prepared.timeline_range, profile_ref=profile_ref,
            )
            self._local_analysis[source.analysis_source_ref] = (source.model_copy(deep=True), prepared.content)
            self._local_analysis_refs.add(source.analysis_source_ref)
            self._analysis_reuse[key] = source.analysis_source_ref
            return source
        sources = self._repository.find_analysis_sources(parsed_span, profile_ref)
        if not sources:
            raise RecordingCapabilityError(
                "NOT_FOUND",
                "해당 span과 profile의 AnalysisSource가 준비되지 않았습니다",
            )
        if len(sources) > 1:
            raise RecordingCapabilityError(
                "TEMPORARY_FAILURE",
                "같은 span과 profile에 여러 AnalysisSource가 등록되어 있습니다",
            )
        return sources[0]

    def prepare_analysis_source_from_resolution(
        self, resolution: SpanResolution | dict[str, Any], profile_ref: str,
    ) -> AnalysisSource:
        """명시적 sequence의 연속 로컬 span을 하나의 분석 입력으로 준비한다."""
        data = resolution.model_dump() if isinstance(resolution, SpanResolution) else dict(resolution)
        # 배열 순서는 바뀔 수 있지만 sequence 자체를 재부여하거나 모순을 보정하지 않는다.
        spans = [AssetSpan.model_validate(s) for s in data.get("spans", [])]
        data["spans"] = sorted(spans, key=lambda s: s.sequence)
        parsed = SpanResolution.model_validate(data)
        if self._analysis_closed:
            raise RecordingCapabilityError("UNAVAILABLE", "로컬 AnalysisSource 실행이 종료되었습니다")
        if parsed.status != "COMPLETE":
            reasons = {m.reason for m in parsed.missing_ranges}
            code = (parsed.failure.code if parsed.failure is not None else
                    next(iter(reasons)) if len(reasons) == 1 else "UNSUPPORTED_MEDIA")
            raise RecordingCapabilityError(code, "완전히 해소된 연속 구간이 필요합니다")
        ordered = parsed.spans
        if (len({s.source_asset_ref for s in ordered}) != len(ordered)
                or any(a.timeline_range.end_sec != b.timeline_range.start_sec for a, b in zip(ordered, ordered[1:]))):
            raise ValueError("중복 없는 Timeline 순서의 연속 span이 필요합니다")
        timeline = self._repository.get_timeline(parsed.timeline_ref)
        if timeline is None:
            raise ValueError("존재하지 않는 timeline reference입니다")
        if len(ordered) == 1 and len(timeline.source_placements) == 1:
            return self.prepare_analysis_source(ordered[0], profile_ref, timeline_ref=parsed.timeline_ref)
        # 요청에 걸치는 배치만 검사한다. VIDEO 선택은 전달 span의 ref만 사용한다.
        placements = [p for p in timeline.source_placements
            if p.timeline_start_sec < parsed.requested_range.end_sec
            and p.timeline_end_sec > parsed.requested_range.start_sec]
        gaps = [g for g in timeline.gaps if placements
            and g.start_sec >= min(p.timeline_start_sec for p in placements)
            and g.end_sec <= max(p.timeline_end_sec for p in placements)]
        checked = resolve_placed_span(self._repository,
            timeline.model_copy(update={"source_placements": placements, "gaps": gaps}),
            parsed.requested_range, [s.media_stream_ref for s in ordered])
        if checked.status != "COMPLETE":
            reasons = {m.reason for m in checked.missing_ranges}
            code = (checked.failure.code if checked.failure and checked.failure.code != "NO_USABLE_SPAN" else
                    next(iter(reasons)) if len(reasons) == 1 else "UNSUPPORTED_MEDIA")
            raise RecordingCapabilityError(code, "현재 원본 상태에서 분석 구간을 준비할 수 없습니다")
        if checked.spans != ordered:
            raise ValueError("span이 해당 Timeline revision의 실제 매핑과 일치하지 않습니다")
        engine = self._analysis_materializer
        if engine is None:
            raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "로컬 materialization configuration이 없습니다")
        if not profile_ref or not engine.has_profile(profile_ref):
            raise ValueError("등록되지 않은 profile_ref입니다")
        key = ("multi", parsed.model_dump_json(), profile_ref)
        cached = self._analysis_reuse.get(key)
        if cached is not None:
            return self._local_analysis[cached][0].model_copy(deep=True)
        inputs = []
        for span in ordered:
            local = self._repository.get_local_source(span.source_asset_ref)
            index = self._repository.get_local_stream_index(span.media_stream_ref)
            if local is None or index is None:
                raise RecordingCapabilityError("UNAVAILABLE", "원본 또는 stream index가 없습니다")
            inputs.append((local, index, span))
        with source_inspections(self._source_inspections), analysis_tail_scope():
            prepared = materialize_chain(engine, inputs, profile_ref)
        source = AnalysisSource(contract="AnalysisSource", contract_version="analysis-source-derived/v1",
            analysis_source_ref=f"as_{uuid4().hex}", asset_kind="ANALYSIS_SOURCE",
            source_refs=[ContractRef(kind="source_asset", ref=s.source_asset_ref) for s in ordered],
            media_stream_refs=[s.media_stream_ref for s in ordered], byte_size=len(prepared.content),
            availability="AVAILABLE", duration_sec=prepared.duration_sec, timeline_ref=parsed.timeline_ref,
            timeline_range=prepared.timeline_range, profile_ref=profile_ref)
        self._local_analysis[source.analysis_source_ref] = (source.model_copy(deep=True), prepared.content)
        self._local_analysis_refs.add(source.analysis_source_ref)
        self._analysis_reuse[key] = source.analysis_source_ref
        return source

    def open_analysis_source(self, analysis_source_ref: str) -> OpenedAnalysisSource:
        prepared = self._local_analysis.get(analysis_source_ref)
        if prepared is not None:
            source, content = prepared
            return OpenedAnalysisSource(BytesIO(content), "video/mp4", len(content))
        if analysis_source_ref in self._local_analysis_refs:
            raise RecordingCapabilityError("UNAVAILABLE", "로컬 AnalysisSource 실행이 종료되었습니다")
        source = self._repository.get_analysis_source(analysis_source_ref)
        if source is None:
            raise RecordingCapabilityError("NOT_FOUND", "등록되지 않은 AnalysisSource입니다")
        if source.availability != "AVAILABLE" or source.byte_size is None:
            raise RecordingCapabilityError("UNAVAILABLE", "AnalysisSource를 읽을 수 없습니다")
        opened = self._repository.open_analysis_stream(analysis_source_ref)
        if opened is None:
            raise RecordingCapabilityError("UNAVAILABLE", "AnalysisSource stream이 없습니다")
        stream, content_type = opened
        return OpenedAnalysisSource(
            stream=stream,
            content_type=content_type,
            byte_size=source.byte_size,
        )

    def find_remote_copy(
        self,
        analysis_source_ref: str,
        provider: str,
        *,
        now: datetime | None = None,
    ) -> RemoteCopy | None:
        remote_copy = self._repository.get_remote_copy(analysis_source_ref, provider)
        if remote_copy is None or remote_copy.availability != "AVAILABLE":
            return None
        checked_at = now or datetime.now(timezone.utc)
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("now는 offset-aware datetime이어야 합니다")
        if remote_copy.expires_at is not None and remote_copy.expires_at <= checked_at:
            return None
        return remote_copy

    def register_remote_copy(
        self,
        analysis_source_ref: str,
        provider: str,
        remote_info: RemoteCopyInfo | dict[str, Any],
    ) -> RemoteCopy:
        if self._repository.get_analysis_source(analysis_source_ref) is None:
            raise RecordingCapabilityError("NOT_FOUND", "등록되지 않은 AnalysisSource입니다")
        if not provider:
            raise ValueError("provider는 비어 있을 수 없습니다")
        parsed_info = RemoteCopyInfo.model_validate(remote_info)
        remote_copy = RemoteCopy(
            contract="RemoteCopy",
            contract_version="analysis-source-derived/v1",
            remote_copy_ref=f"rc_{uuid4().hex}",
            analysis_source_ref=analysis_source_ref,
            provider=provider,
            provider_object_ref=parsed_info.provider_object_ref,
            availability="AVAILABLE",
            expires_at=parsed_info.expires_at,
        )
        self._repository.add_remote_copy(remote_copy)
        return remote_copy

    def build_incident_clip(
        self,
        resolution: SpanResolution | dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> IncidentClip:
        try:
            parsed_resolution = SpanResolution.model_validate(
                resolution.model_dump() if isinstance(resolution, SpanResolution) else resolution)
        except ValueError:
            raise RecordingCapabilityError("INCIDENT_CLIP_BUILD_FAILED", "유효한 span resolution이 필요합니다") from None
        if options:
            raise ValueError("build_incident_clip options schema는 아직 확정되지 않았습니다")
        if parsed_resolution.status == "FAILED" or not parsed_resolution.spans:
            raise RecordingCapabilityError(
                "INCIDENT_CLIP_BUILD_FAILED",
                "usable AssetSpan이 없어 IncidentClip을 만들 수 없습니다",
            )
        if any(self._repository.get_local_source(s.source_asset_ref) is not None
               for s in parsed_resolution.spans):
            if self._analysis_closed or self._incident_materializer is None:
                raise RecordingCapabilityError("INCIDENT_CLIP_BUILD_FAILED", "실행 중인 VIDEO 생성 설정이 필요합니다")
            spans = parsed_resolution.spans
            try:
                timeline = self._repository.get_timeline(parsed_resolution.timeline_ref)
                if timeline is None:
                    raise ValueError("존재하지 않는 Timeline revision")
                if len(spans) > 1 or len(timeline.source_placements) > 1:
                    if (parsed_resolution.status != "COMPLETE"
                            or len({s.source_asset_ref for s in spans}) != len(spans)
                            or any(a.timeline_range.end_sec != b.timeline_range.start_sec
                                   for a, b in zip(spans, spans[1:]))):
                        raise ValueError("중복 없는 연속 COMPLETE span이 필요합니다")
                    request = parsed_resolution.requested_range
                    placements = [p for p in timeline.source_placements
                        if p.timeline_start_sec < request.end_sec and p.timeline_end_sec > request.start_sec]
                    gaps = [g for g in timeline.gaps if placements
                        and g.start_sec >= min(p.timeline_start_sec for p in placements)
                        and g.end_sec <= max(p.timeline_end_sec for p in placements)]
                    current = resolve_placed_span(self._repository,
                        timeline.model_copy(update={"source_placements": placements, "gaps": gaps}),
                        request, [s.media_stream_ref for s in spans])
                else:
                    current = self.resolve_span(parsed_resolution.timeline_ref, parsed_resolution.requested_range,
                                                media_stream_ref=spans[0].media_stream_ref)
                if current != parsed_resolution:
                    raise RecordingCapabilityError("INCIDENT_CLIP_BUILD_FAILED", "현재 원본 해소 결과와 입력 provenance가 다릅니다")
                inputs = []
                for span in spans:
                    local = self._repository.get_local_source(span.source_asset_ref)
                    index = self._repository.get_local_stream_index(span.media_stream_ref)
                    if local is None or index is None:
                        raise RecordingCapabilityError("INCIDENT_CLIP_BUILD_FAILED", "등록된 원본 stream에 접근할 수 없습니다")
                    inputs.append((local, index, span))
                with source_inspections(self._source_inspections):
                    prepared = (self._incident_materializer.materialize(*inputs[0]) if len(inputs) == 1
                                else self._incident_materializer._materialize_many(inputs))
            except _FrameCoverageError as error:
                raise RecordingCapabilityError("INCIDENT_CLIP_BUILD_FAILED", str(error)) from None
            except (RecordingCapabilityError, ValueError, OSError):
                raise RecordingCapabilityError("INCIDENT_CLIP_BUILD_FAILED", "원본 검증 또는 IncidentClip 생성에 실패했습니다") from None
            provenance = IncidentClipProvenance(
                timeline_ref=parsed_resolution.timeline_ref,
                requested_range=parsed_resolution.requested_range,
                asset_spans=parsed_resolution.spans,
            )
            identity = (provenance.model_dump_json(), self._incident_materializer.generation_conditions,
                        hashlib.sha256(prepared.content).hexdigest(), prepared.duration_sec,
                        prepared.timeline_range.model_dump_json())
            previous = self._clip_identity.get(identity)
            if previous is not None:
                return self._local_clips[previous][0].model_copy(deep=True)
            clip = IncidentClip(
                contract="IncidentClip", contract_version="analysis-source-derived/v1",
                incident_clip_ref=f"clip_{uuid4().hex}", asset_kind="INCIDENT_CLIP",
                source_provenance=provenance, media_stream_refs=[s.media_stream_ref for s in spans],
                byte_size=len(prepared.content), availability="AVAILABLE", duration_sec=prepared.duration_sec,
                timeline_ref=parsed_resolution.timeline_ref, timeline_range=prepared.timeline_range,
            )
            self._local_clips[clip.incident_clip_ref] = (clip.model_copy(deep=True), prepared.content)
            self._local_clip_refs.add(clip.incident_clip_ref)
            self._clip_identity[identity] = clip.incident_clip_ref
            return clip.model_copy(deep=True)
        clips = self._repository.find_incident_clips(parsed_resolution)
        if not clips:
            raise RecordingCapabilityError(
                "INCIDENT_CLIP_BUILD_FAILED",
                "해당 provenance의 IncidentClip fixture가 준비되지 않았습니다",
            )
        if len(clips) > 1:
            raise RecordingCapabilityError(
                "INCIDENT_CLIP_BUILD_FAILED",
                "동일 provenance에 여러 IncidentClip이 등록되어 있습니다",
            )
        return clips[0]

    def get_incident_clip(self, incident_clip_ref: str) -> IncidentClip:
        local = self._local_clips.get(incident_clip_ref)
        if local is not None:
            return local[0].model_copy(deep=True)
        if incident_clip_ref in self._local_clip_refs:
            raise RecordingCapabilityError("UNAVAILABLE", "로컬 IncidentClip 실행이 종료되었습니다")
        clip = self._repository.get_incident_clip(incident_clip_ref)
        if clip is None:
            raise RecordingCapabilityError("NOT_FOUND", "등록되지 않은 IncidentClip입니다")
        return clip

    def register_derived_asset(self, payload: DerivedAsset | dict[str, Any]) -> DerivedAsset:
        asset = DerivedAsset.model_validate(payload)
        self._repository.add_derived_asset(asset)
        return asset

    def get_derived_asset(self, derived_asset_ref: str) -> DerivedAsset:
        asset = self._repository.get_derived_asset(derived_asset_ref)
        if asset is None:
            raise RecordingCapabilityError("NOT_FOUND", "등록되지 않은 DerivedAsset입니다")
        return asset

    def purge_case(
        self,
        case_id: str,
        *,
        requested_at: datetime | None = None,
    ) -> DeletionReport:
        if not case_id:
            raise ValueError("case_id는 비어 있을 수 없습니다")
        timestamp = requested_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("requested_at은 offset-aware datetime이어야 합니다")

        items: list[DeletionItem] = []
        for asset_ref in self._repository.get_case_assets(case_id):
            if asset_ref.kind == "remote_copy":
                remote_copy = self._repository.get_remote_copy_by_ref(asset_ref.ref)
                if (
                    remote_copy is not None
                    and remote_copy.expires_at is not None
                    and remote_copy.expires_at <= timestamp
                ):
                    result = "NOT_FOUND"
                else:
                    result = "PENDING_EXPIRY"
            else:
                result = "DELETED" if self._repository.mark_deleted(asset_ref) else "NOT_FOUND"
            items.append(DeletionItem(asset_ref=asset_ref, result=result, failure_code=None))

        status = "PARTIAL" if any(item.result == "PENDING_EXPIRY" for item in items) else "COMPLETE"
        return DeletionReport(
            contract="DeletionReport",
            contract_version="analysis-source-derived/v1",
            case_id=case_id,
            requested_at=timestamp,
            completed_at=timestamp,
            status=status,
            items=items,
        )
