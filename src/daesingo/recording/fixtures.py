"""공용 recording Mock fixture를 canonical 모델로 읽는 adapter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import (
    AnalysisSource,
    AssetFacts,
    ContractModel,
    DerivedAsset,
    FrameRef,
    GPSObservation,
    MediaStream,
    IncidentClip,
    RecordingTimeline,
    RemoteCopy,
    SourceAsset,
    SpanResolution,
)


_SCENARIO_ID = re.compile(r"scenario_[a-z0-9_]+")
_DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "data" / "mock" / "recording"


class RecordingFixture(ContractModel):
    """현재 구현 범위에서 소비하는 recording fixture view."""

    scenario_id: str = Field(min_length=1)
    module: Literal["recording"]
    source_assets: list[SourceAsset]
    media_streams: list[MediaStream]
    frame_refs: list[FrameRef] = Field(default_factory=list)
    asset_facts: list[AssetFacts] = Field(default_factory=list)
    recording_timelines: list[RecordingTimeline]
    span_resolutions: list[SpanResolution] = Field(default_factory=list)
    analysis_sources: list[AnalysisSource] = Field(default_factory=list)
    remote_copies: list[RemoteCopy] = Field(default_factory=list)
    incident_clips: list[IncidentClip] = Field(default_factory=list)
    derived_assets: list[DerivedAsset] = Field(default_factory=list)
    gps_observations: list[GPSObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_stream_references_are_consistent(self) -> RecordingFixture:
        assets = {asset.source_asset_ref: asset for asset in self.source_assets}
        streams = {stream.media_stream_ref: stream for stream in self.media_streams}
        frames = {frame.frame_ref: frame for frame in self.frame_refs}
        timelines = {
            (timeline.timeline_id, timeline.revision): timeline
            for timeline in self.recording_timelines
        }

        if len(assets) != len(self.source_assets):
            raise ValueError("source_asset_ref는 fixture 안에서 중복될 수 없습니다")
        if len(streams) != len(self.media_streams):
            raise ValueError("media_stream_ref는 fixture 안에서 중복될 수 없습니다")
        if len(frames) != len(self.frame_refs):
            raise ValueError("frame_ref는 fixture 안에서 중복될 수 없습니다")
        if len(timelines) != len(self.recording_timelines):
            raise ValueError("timeline_id와 revision 조합은 중복될 수 없습니다")
        for i, observation in enumerate(self.gps_observations):
            if observation in self.gps_observations[:i]:
                raise ValueError("동일한 GPS Observation은 중복 등록할 수 없습니다")
            if observation.source.ref is not None and observation.source.ref.ref not in streams:
                raise ValueError("GPS source ref에 대응하는 MediaStream이 없습니다")

        for asset in self.source_assets:
            if len(set(asset.media_stream_refs)) != len(asset.media_stream_refs):
                raise ValueError(f"{asset.source_asset_ref}의 media_stream_refs가 중복되었습니다")
            for stream_ref in asset.media_stream_refs:
                stream = streams.get(stream_ref)
                if stream is None:
                    raise ValueError(f"{stream_ref}를 가리키는 MediaStream이 없습니다")
                if stream.source_asset_ref != asset.source_asset_ref:
                    raise ValueError(f"{stream_ref}의 SourceAsset 역참조가 일치하지 않습니다")

        for stream in self.media_streams:
            asset = assets.get(stream.source_asset_ref)
            if asset is None:
                raise ValueError(f"{stream.source_asset_ref}를 가리키는 SourceAsset이 없습니다")
            if stream.media_stream_ref not in asset.media_stream_refs:
                raise ValueError(f"{stream.media_stream_ref}가 SourceAsset에 등재되지 않았습니다")

        for frame in self.frame_refs:
            stream = streams.get(frame.media_stream_ref)
            if stream is None:
                raise ValueError(f"{frame.media_stream_ref}를 가리키는 MediaStream이 없습니다")
            if stream.media_type != "VIDEO":
                raise ValueError(f"{frame.frame_ref}가 VIDEO가 아닌 MediaStream을 참조합니다")

        for timeline in self.recording_timelines:
            for placement in timeline.source_placements:
                asset = assets.get(placement.source_asset_ref)
                if asset is None:
                    raise ValueError(f"{placement.source_asset_ref} SourceAsset이 없습니다")
                for stream_ref in placement.media_stream_refs:
                    stream = streams.get(stream_ref)
                    if stream is None or stream.source_asset_ref != asset.source_asset_ref:
                        raise ValueError(f"{stream_ref}가 SourcePlacement의 SourceAsset과 맞지 않습니다")

        for resolution in self.span_resolutions:
            timeline_key = (resolution.timeline_ref.timeline_id, resolution.timeline_ref.revision)
            if timeline_key not in timelines:
                raise ValueError(f"{timeline_key} RecordingTimeline이 없습니다")
            for span in resolution.spans:
                stream = streams.get(span.media_stream_ref)
                if stream is None or stream.source_asset_ref != span.source_asset_ref:
                    raise ValueError("AssetSpan의 SourceAsset과 MediaStream 관계가 맞지 않습니다")

        analysis_source_refs = {
            analysis_source.analysis_source_ref for analysis_source in self.analysis_sources
        }
        if len(analysis_source_refs) != len(self.analysis_sources):
            raise ValueError("analysis_source_ref는 fixture 안에서 중복될 수 없습니다")
        for analysis_source in self.analysis_sources:
            if any(ref not in streams for ref in analysis_source.media_stream_refs):
                raise ValueError("AnalysisSource가 등록되지 않은 MediaStream을 참조합니다")
            if any(
                ref.kind != "source_asset" or ref.ref not in assets
                for ref in analysis_source.source_refs
            ):
                raise ValueError("AnalysisSource가 등록되지 않은 SourceAsset을 참조합니다")
        for remote_copy in self.remote_copies:
            if remote_copy.analysis_source_ref not in analysis_source_refs:
                raise ValueError("RemoteCopy가 등록되지 않은 AnalysisSource를 참조합니다")

        clip_refs = {clip.incident_clip_ref for clip in self.incident_clips}
        if len(clip_refs) != len(self.incident_clips):
            raise ValueError("incident_clip_ref는 fixture 안에서 중복될 수 없습니다")
        for clip in self.incident_clips:
            if any(ref not in streams for ref in clip.media_stream_refs):
                raise ValueError("IncidentClip이 등록되지 않은 MediaStream을 참조합니다")
        for asset in self.derived_assets:
            if any(ref.kind == "incident_clip" and ref.ref not in clip_refs for ref in asset.source_refs):
                raise ValueError("DerivedAsset이 등록되지 않은 IncidentClip을 참조합니다")

        return self


def load_recording_fixture(
    scenario_id: str,
    *,
    fixture_dir: Path | None = None,
) -> RecordingFixture:
    """시나리오 fixture를 읽고 현재 recording 계약 경계를 검증한다."""

    if _SCENARIO_ID.fullmatch(scenario_id) is None:
        raise ValueError("scenario_id 형식이 올바르지 않습니다")

    source_dir = fixture_dir if fixture_dir is not None else _DEFAULT_FIXTURE_DIR
    fixture_path = source_dir / f"{scenario_id}.json"
    return RecordingFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
