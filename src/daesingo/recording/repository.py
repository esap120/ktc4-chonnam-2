"""1차 Mock E2E에서 사용하는 in-memory recording 저장 경계."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import BinaryIO

from .probe import LocalSource

from .models import (
    AnalysisSource,
    AssetSpan,
    AssetFacts,
    ContractRef,
    DerivedAsset,
    FrameRef,
    GPSObservation,
    MediaStream,
    IncidentClip,
    RecordingTimeline,
    RemoteCopy,
    SourceAsset,
    SpanResolution,
    TimeRange,
    TimelineRef,
)


def _offset_key(value: float) -> Decimal:
    return Decimal(str(value))


class InMemoryRecordingRepository:
    def __init__(self) -> None:
        self._source_assets: dict[str, SourceAsset] = {}
        self._local_sources: dict[str, LocalSource] = {}
        self._local_stream_indices: dict[str, int] = {}
        self._media_streams: dict[str, MediaStream] = {}
        self._gps_observations: list[GPSObservation] = []
        self._frames: dict[str, FrameRef] = {}
        self._frame_by_position: dict[tuple[str, Decimal], str] = {}
        self._frame_content: dict[str, bytes] = {}
        self._asset_facts: dict[tuple[str, str], AssetFacts] = {}
        self._timelines: dict[tuple[str, int], RecordingTimeline] = {}
        self._span_resolutions: dict[tuple[str, int, Decimal, Decimal], SpanResolution] = {}
        self._analysis_sources: dict[str, AnalysisSource] = {}
        self._analysis_stream_factories: dict[str, Callable[[], BinaryIO]] = {}
        self._analysis_content_types: dict[str, str] = {}
        self._remote_copies: dict[str, RemoteCopy] = {}
        self._remote_copy_by_source_provider: dict[tuple[str, str], str] = {}
        self._incident_clips: dict[str, IncidentClip] = {}
        self._derived_assets: dict[str, DerivedAsset] = {}
        self._case_assets: dict[str, list[ContractRef]] = {}
        self._deleted_assets: set[tuple[str, str]] = set()

    def add_source_asset(self, asset: SourceAsset) -> None:
        self._source_assets[asset.source_asset_ref] = asset

    def get_source_asset(self, source_ref: str) -> SourceAsset | None:
        return self._source_assets.get(source_ref)

    def add_local_source(
        self, asset: SourceAsset, streams: tuple[MediaStream, ...], source: LocalSource,
    ) -> None:
        indices = dict(zip(asset.media_stream_refs, (s.index for s in source.streams), strict=True))
        self.add_source_asset(asset)
        for stream in streams:
            self.add_media_stream(stream)
        self._local_sources[asset.source_asset_ref] = source
        self._local_stream_indices.update(indices)

    def get_local_source(self, source_ref: str) -> LocalSource | None:
        return self._local_sources.get(source_ref)

    def get_local_stream_index(self, stream_ref: str) -> int | None:
        return self._local_stream_indices.get(stream_ref)

    def add_media_stream(self, stream: MediaStream) -> None:
        self._media_streams[stream.media_stream_ref] = stream

    def get_media_stream(self, stream_ref: str) -> MediaStream | None:
        return self._media_streams.get(stream_ref)

    def add_gps_observation(self, observation: GPSObservation) -> None:
        checked = GPSObservation.model_validate(observation)
        if checked.source.ref is not None and checked.source.ref.ref not in self._media_streams:
            raise ValueError("GPS source ref에 대응하는 MediaStream이 없습니다")
        if checked in self._gps_observations:
            raise ValueError("동일한 GPS Observation은 중복 등록할 수 없습니다")
        self._gps_observations.append(checked.model_copy(deep=True))

    def list_gps_observations(self) -> list[GPSObservation]:
        return [observation.model_copy(deep=True) for observation in self._gps_observations]

    def add_frame(self, frame: FrameRef, *, content: bytes | None = None) -> None:
        self._frames[frame.frame_ref] = frame
        self._frame_by_position[(frame.media_stream_ref, _offset_key(frame.source_offset_sec))] = (
            frame.frame_ref
        )
        if content is not None:
            self._frame_content[frame.frame_ref] = content

    def find_frame_at(self, stream_ref: str, source_offset_sec: float) -> FrameRef | None:
        frame_ref = self._frame_by_position.get((stream_ref, _offset_key(source_offset_sec)))
        return self._frames.get(frame_ref) if frame_ref is not None else None

    def get_frame(self, frame_ref: str) -> FrameRef | None:
        return self._frames.get(frame_ref)

    def get_frame_content(self, frame_ref: str) -> bytes | None:
        return self._frame_content.get(frame_ref)

    def add_asset_facts(self, facts: AssetFacts) -> None:
        key = (facts.asset_ref.kind, facts.asset_ref.ref)
        self._asset_facts[key] = facts

    def get_asset_facts(self, kind: str, ref: str) -> AssetFacts | None:
        return self._asset_facts.get((kind, ref))

    def add_timeline(self, timeline: RecordingTimeline) -> None:
        key = (timeline.timeline_id, timeline.revision)
        current = self._timelines.get(key)
        if current is not None and current != timeline:
            raise ValueError("같은 timeline revision을 다른 payload로 덮어쓸 수 없습니다")
        # frozen model도 내부 list는 변경 가능하다. 저장 revision을 외부 변경과 분리한다.
        self._timelines[key] = timeline.model_copy(deep=True)

    def get_timeline(self, timeline_ref: TimelineRef) -> RecordingTimeline | None:
        timeline = self._timelines.get((timeline_ref.timeline_id, timeline_ref.revision))
        return timeline.model_copy(deep=True) if timeline is not None else None

    def get_latest_timeline(self, timeline_id: str) -> RecordingTimeline | None:
        revisions = [
            timeline
            for (stored_id, _), timeline in self._timelines.items()
            if stored_id == timeline_id
        ]
        latest = max(revisions, key=lambda timeline: timeline.revision, default=None)
        return latest.model_copy(deep=True) if latest is not None else None

    def find_frames_at_timeline_position(
        self,
        timeline: RecordingTimeline,
        at_sec: float,
    ) -> list[FrameRef]:
        matches: dict[str, FrameRef] = {}
        for placement in timeline.source_placements:
            if not (placement.timeline_start_sec <= at_sec < placement.timeline_end_sec):
                continue
            source_offset_sec = at_sec - placement.timeline_start_sec
            for stream_ref in placement.media_stream_refs:
                frame = self.find_frame_at(stream_ref, source_offset_sec)
                if frame is not None:
                    matches[frame.frame_ref] = frame
        return list(matches.values())

    def add_span_resolution(self, resolution: SpanResolution) -> None:
        key = self._resolution_key(resolution.timeline_ref, resolution.requested_range)
        current = self._span_resolutions.get(key)
        if current is not None and current != resolution:
            raise ValueError("같은 span 요청을 다른 결과로 덮어쓸 수 없습니다")
        self._span_resolutions[key] = resolution

    def get_span_resolution(
        self,
        timeline_ref: TimelineRef,
        requested_range: TimeRange,
    ) -> SpanResolution | None:
        return self._span_resolutions.get(self._resolution_key(timeline_ref, requested_range))

    @staticmethod
    def _resolution_key(
        timeline_ref: TimelineRef,
        requested_range: TimeRange,
    ) -> tuple[str, int, Decimal, Decimal]:
        return (
            timeline_ref.timeline_id,
            timeline_ref.revision,
            _offset_key(requested_range.start_sec),
            _offset_key(requested_range.end_sec),
        )

    def add_analysis_source(
        self,
        source: AnalysisSource,
        *,
        stream_factory: Callable[[], BinaryIO] | None = None,
        content_type: str = "application/octet-stream",
    ) -> None:
        current = self._analysis_sources.get(source.analysis_source_ref)
        if current is not None and current != source:
            raise ValueError("같은 AnalysisSource ref를 다른 payload로 덮어쓸 수 없습니다")
        self._analysis_sources[source.analysis_source_ref] = source
        if stream_factory is not None:
            self._analysis_stream_factories[source.analysis_source_ref] = stream_factory
            self._analysis_content_types[source.analysis_source_ref] = content_type

    def get_analysis_source(self, source_ref: str) -> AnalysisSource | None:
        return self._analysis_sources.get(source_ref)

    def find_analysis_sources(self, span: AssetSpan, profile_ref: str) -> list[AnalysisSource]:
        return [
            source
            for source in self._analysis_sources.values()
            if source.profile_ref == profile_ref
            and source.timeline_range == span.timeline_range
            and span.media_stream_ref in source.media_stream_refs
            and any(
                ref.kind == "source_asset" and ref.ref == span.source_asset_ref
                for ref in source.source_refs
            )
        ]

    def open_analysis_stream(self, source_ref: str) -> tuple[BinaryIO, str] | None:
        factory = self._analysis_stream_factories.get(source_ref)
        if factory is None:
            return None
        return factory(), self._analysis_content_types[source_ref]

    def add_remote_copy(self, remote_copy: RemoteCopy) -> None:
        current = self._remote_copies.get(remote_copy.remote_copy_ref)
        if current is not None and current != remote_copy:
            raise ValueError("같은 RemoteCopy ref를 다른 payload로 덮어쓸 수 없습니다")
        self._remote_copies[remote_copy.remote_copy_ref] = remote_copy
        self._remote_copy_by_source_provider[
            (remote_copy.analysis_source_ref, remote_copy.provider)
        ] = remote_copy.remote_copy_ref

    def get_remote_copy(self, analysis_source_ref: str, provider: str) -> RemoteCopy | None:
        remote_ref = self._remote_copy_by_source_provider.get((analysis_source_ref, provider))
        return self._remote_copies.get(remote_ref) if remote_ref is not None else None

    def get_remote_copy_by_ref(self, remote_copy_ref: str) -> RemoteCopy | None:
        return self._remote_copies.get(remote_copy_ref)

    def add_incident_clip(self, clip: IncidentClip) -> None:
        current = self._incident_clips.get(clip.incident_clip_ref)
        if current is not None and current != clip:
            raise ValueError("같은 IncidentClip ref를 다른 payload로 덮어쓸 수 없습니다")
        self._incident_clips[clip.incident_clip_ref] = clip

    def find_incident_clips(self, resolution: SpanResolution) -> list[IncidentClip]:
        return [
            clip
            for clip in self._incident_clips.values()
            if clip.source_provenance.timeline_ref == resolution.timeline_ref
            and clip.source_provenance.requested_range == resolution.requested_range
            and clip.source_provenance.asset_spans == resolution.spans
        ]

    def get_incident_clip(self, clip_ref: str) -> IncidentClip | None:
        return self._incident_clips.get(clip_ref)

    def add_derived_asset(self, asset: DerivedAsset) -> None:
        current = self._derived_assets.get(asset.derived_asset_ref)
        if current is not None and current != asset:
            raise ValueError("같은 DerivedAsset ref를 다른 payload로 덮어쓸 수 없습니다")
        self._derived_assets[asset.derived_asset_ref] = asset

    def get_derived_asset(self, asset_ref: str) -> DerivedAsset | None:
        return self._derived_assets.get(asset_ref)

    def associate_case_asset(self, case_id: str, asset_ref: ContractRef) -> None:
        if asset_ref.kind == "external_source":
            raise ValueError("사용자 외부 원본은 서비스 관리 삭제 대상이 아닙니다")
        refs = self._case_assets.setdefault(case_id, [])
        if asset_ref not in refs:
            refs.append(asset_ref)

    def get_case_assets(self, case_id: str) -> list[ContractRef]:
        return list(self._case_assets.get(case_id, []))

    def mark_deleted(self, asset_ref: ContractRef) -> bool:
        key = (asset_ref.kind, asset_ref.ref)
        if key in self._deleted_assets:
            return False
        self._deleted_assets.add(key)
        return True
