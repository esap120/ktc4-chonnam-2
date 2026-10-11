"""Recording이 생산하는 canonical data contract 모델."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator


CONTRACT_VERSION = "source-asset-media-stream/v1"


class ContractModel(BaseModel):
    """Canonical JSON 경계에서 공통으로 사용하는 모델 설정."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class _GPSModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class GPSCoordinate(_GPSModel):
    """현재 Mock/Evidence의 lon 철자를 보존한다. lng와의 합의는 미결이다."""
    lat: FiniteFloat = Field(ge=-90, le=90)
    lon: FiniteFloat = Field(ge=-180, le=180)


class ObservationReference(_GPSModel):
    kind: str = Field(min_length=1)
    ref: str = Field(min_length=1)


class GPSObservationSource(_GPSModel):
    kind: Literal["recording.gps_stream"]
    ref: ObservationReference | None = None


class GPSObservationProducer(_GPSModel):
    module: Literal["recording"]
    # Recording logical run 계약이 없으므로 run_ref는 extra="forbid"로 거부한다.
    impl_ref: str | None = Field(default=None, min_length=1)


class ObservationConfidence(_GPSModel):
    score: FiniteFloat = Field(ge=0.0, le=1.0)
    metric: str = Field(min_length=1)


class ObservationReason(_GPSModel):
    code: str = Field(min_length=1)
    note: str | None = None


class GPSObservation(_GPSModel):
    """기존 Mock GPS Observation의 typed view. 새로운 GPS를 생산하지 않는다."""
    contract: Literal["Observation"]
    contract_version: Literal["observation/v1"]
    value: GPSCoordinate | None
    status: Literal["OK", "NEEDS_REVIEW", "UNKNOWN", "ERROR", "NOT_APPLICABLE"]
    source: GPSObservationSource
    support_refs: list[ObservationReference]
    produced_by: GPSObservationProducer
    confidence: ObservationConfidence | None = None
    reason: ObservationReason | None = None

    @model_validator(mode="after")
    def value_and_source_match_status(self):
        if self.status == "OK" and (self.value is None or self.source.ref is None):
            raise ValueError("OK GPS에는 좌표와 MediaStream ref가 필요합니다")
        if self.status in {"UNKNOWN", "ERROR", "NOT_APPLICABLE"} and self.value is not None:
            raise ValueError("해당 Observation 상태의 value는 null이어야 합니다")
        if self.source.ref is not None and self.source.ref.kind != "media_stream":
            raise ValueError("GPS source ref는 MediaStream이어야 합니다")
        return self


class ExternalSourceRef(ContractModel):
    kind: Literal["external_source"]
    ref: str = Field(min_length=1)


AssetRefKind = Literal[
    "external_source",
    "source_asset",
    "media_stream",
    "frame",
    "analysis_source",
    "remote_copy",
    "incident_clip",
    "derived_asset",
]


class ContractRef(ContractModel):
    kind: AssetRefKind
    ref: str = Field(min_length=1)


class SourceAsset(ContractModel):
    contract: Literal["SourceAsset"]
    contract_version: Literal[CONTRACT_VERSION]
    source_asset_ref: str = Field(min_length=1)
    asset_kind: Literal["SOURCE_ASSET"]
    external_source_ref: ExternalSourceRef | None
    media_stream_refs: list[str]
    byte_size: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    duration_sec: float | None = Field(ge=0)

    @model_validator(mode="after")
    def available_asset_has_known_size(self) -> SourceAsset:
        if self.availability == "AVAILABLE" and self.byte_size is None:
            raise ValueError("AVAILABLE SourceAsset의 byte_size는 null일 수 없습니다")
        return self


class MediaStream(ContractModel):
    contract: Literal["MediaStream"]
    contract_version: Literal[CONTRACT_VERSION]
    media_stream_ref: str = Field(min_length=1)
    source_asset_ref: str = Field(min_length=1)
    media_type: Literal["VIDEO", "AUDIO"]
    role: Literal["FRONT", "REAR", "UNKNOWN"] | None
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    duration_sec: float | None = Field(ge=0)

    @model_validator(mode="after")
    def role_matches_media_type(self) -> MediaStream:
        if self.media_type == "AUDIO" and self.role is not None:
            raise ValueError("AUDIO MediaStream에는 camera role을 지정할 수 없습니다")
        if self.media_type == "VIDEO" and self.role is None:
            raise ValueError("VIDEO MediaStream의 role은 FRONT, REAR, UNKNOWN 중 하나여야 합니다")
        return self


class FrameRef(ContractModel):
    contract: Literal["FrameRef"]
    contract_version: Literal[CONTRACT_VERSION]
    frame_ref: str = Field(min_length=1)
    media_stream_ref: str = Field(min_length=1)
    source_offset_sec: float = Field(ge=0)


class TimelineRef(ContractModel):
    timeline_id: str = Field(min_length=1)
    revision: int = Field(ge=1)


class TimeRange(ContractModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)

    @model_validator(mode="after")
    def end_is_after_start(self) -> TimeRange:
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec는 start_sec보다 커야 합니다")
        return self


class WorkingAnchor(ContractModel):
    value: AwareDatetime | None
    source_candidate_ref: str | None
    status: str = Field(min_length=1)


class TimeBasis(ContractModel):
    mode: str = Field(min_length=1)
    working_anchor: WorkingAnchor


class SourcePlacement(ContractModel):
    source_asset_ref: str = Field(min_length=1)
    timeline_start_sec: float = Field(ge=0)
    timeline_end_sec: float = Field(ge=0)
    media_stream_refs: list[str]

    @model_validator(mode="after")
    def end_is_after_start(self) -> SourcePlacement:
        if self.timeline_end_sec <= self.timeline_start_sec:
            raise ValueError("timeline_end_sec는 timeline_start_sec보다 커야 합니다")
        return self


class RecordingTimeline(ContractModel):
    contract: Literal["RecordingTimeline"]
    contract_version: Literal["recording-timeline/v1"]
    timeline_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    time_basis: TimeBasis
    time_source_candidates: list[str]
    source_placements: list[SourcePlacement]
    gaps: list[TimeRange]
    timeline_status: Literal["USABLE", "USABLE_RELATIVE_ONLY", "PARTIAL", "UNUSABLE"]
    produced_by: Literal["recording"]

    @model_validator(mode="after")
    def relative_only_has_no_absolute_anchor(self) -> RecordingTimeline:
        if (
            self.timeline_status == "USABLE_RELATIVE_ONLY"
            and self.time_basis.working_anchor.value is not None
        ):
            raise ValueError("relative-only timeline에 absolute anchor를 만들 수 없습니다")
        return self


class AssetSpan(ContractModel):
    sequence: int = Field(ge=0)
    timeline_range: TimeRange
    source_asset_ref: str = Field(min_length=1)
    media_stream_ref: str = Field(min_length=1)
    source_range: TimeRange


class MissingRange(ContractModel):
    timeline_range: TimeRange
    reason: Literal[
        "TIMELINE_GAP",
        "SOURCE_UNAVAILABLE",
        "STREAM_UNAVAILABLE",
        "OUT_OF_TIMELINE_RANGE",
    ]
    source_ref: ContractRef | None

    @model_validator(mode="after")
    def source_ref_matches_reason(self) -> MissingRange:
        expected_kind = {
            "SOURCE_UNAVAILABLE": "source_asset",
            "STREAM_UNAVAILABLE": "media_stream",
        }.get(self.reason)
        if expected_kind is None and self.source_ref is not None:
            raise ValueError(f"{self.reason}의 source_ref는 null이어야 합니다")
        if expected_kind is not None and (
            self.source_ref is None or self.source_ref.kind != expected_kind
        ):
            raise ValueError(f"{self.reason}의 source_ref.kind는 {expected_kind}여야 합니다")
        return self


class FailureDetail(ContractModel):
    kind: str = Field(min_length=1)
    code: str = Field(min_length=1)


class SpanResolution(ContractModel):
    contract: Literal["SpanResolution"]
    contract_version: Literal["span-resolution/v1.2"]
    timeline_ref: TimelineRef
    requested_range: TimeRange
    status: Literal["COMPLETE", "PARTIAL", "FAILED"]
    spans: list[AssetSpan]
    missing_ranges: list[MissingRange]
    failure: FailureDetail | None

    @model_validator(mode="after")
    def resolution_is_complete_and_consistent(self) -> SpanResolution:
        if [span.sequence for span in self.spans] != list(range(len(self.spans))):
            raise ValueError("AssetSpan.sequence는 0부터 연속 증가해야 합니다")

        if self.status == "COMPLETE" and (
            not self.spans or self.missing_ranges or self.failure is not None
        ):
            raise ValueError("COMPLETE는 span이 있고 missing_ranges가 비며 failure가 null이어야 합니다")
        if self.status == "PARTIAL" and (
            not self.spans or not self.missing_ranges or self.failure is not None
        ):
            raise ValueError("PARTIAL은 span과 missing range가 있고 failure가 null이어야 합니다")
        if self.status == "FAILED" and (self.spans or self.failure is None):
            raise ValueError("FAILED는 span이 비고 failure가 있어야 합니다")

        intervals = [item.timeline_range for item in [*self.spans, *self.missing_ranges]]
        for interval in intervals:
            if (
                interval.start_sec < self.requested_range.start_sec
                or interval.end_sec > self.requested_range.end_sec
            ):
                raise ValueError("해소된 모든 구간은 requested_range 안에 있어야 합니다")

        if not (self.status == "FAILED" and not intervals):
            merged = _merge_ranges(intervals)
            if merged != [(self.requested_range.start_sec, self.requested_range.end_sec)]:
                raise ValueError("spans와 missing_ranges가 requested_range 전체를 설명해야 합니다")

        spans_by_stream: dict[str, list[TimeRange]] = {}
        for span in self.spans:
            spans_by_stream.setdefault(span.media_stream_ref, []).append(span.timeline_range)
        for ranges in spans_by_stream.values():
            ordered = sorted(ranges, key=lambda item: item.start_sec)
            if any(left.end_sec > right.start_sec for left, right in zip(ordered, ordered[1:])):
                raise ValueError("같은 MediaStream의 AssetSpan은 서로 겹칠 수 없습니다")
        return self


def _merge_ranges(ranges: list[TimeRange]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for current in sorted(ranges, key=lambda item: (item.start_sec, item.end_sec)):
        if not merged or current.start_sec > merged[-1][1]:
            merged.append((current.start_sec, current.end_sec))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], current.end_sec))
    return merged


class AnalysisSource(ContractModel):
    contract: Literal["AnalysisSource"]
    contract_version: Literal["analysis-source-derived/v1"]
    analysis_source_ref: str = Field(min_length=1)
    asset_kind: Literal["ANALYSIS_SOURCE"]
    source_refs: list[ContractRef] = Field(min_length=1)
    media_stream_refs: list[str] = Field(min_length=1)
    byte_size: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    duration_sec: float | None = Field(ge=0)
    timeline_ref: TimelineRef | None
    timeline_range: TimeRange | None
    profile_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def analysis_source_is_consistent(self) -> AnalysisSource:
        if self.availability == "AVAILABLE" and self.byte_size is None:
            raise ValueError("AVAILABLE AnalysisSource의 byte_size는 null일 수 없습니다")
        if (self.timeline_ref is None) != (self.timeline_range is None):
            raise ValueError("timeline_ref와 timeline_range는 함께 존재하거나 함께 null이어야 합니다")
        return self


class RemoteCopy(ContractModel):
    contract: Literal["RemoteCopy"]
    contract_version: Literal["analysis-source-derived/v1"]
    remote_copy_ref: str = Field(min_length=1)
    analysis_source_ref: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_object_ref: str = Field(min_length=1)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    expires_at: AwareDatetime | None


class RemoteCopyInfo(ContractModel):
    provider_object_ref: str = Field(min_length=1)
    expires_at: AwareDatetime | None


class IncidentClipProvenance(ContractModel):
    timeline_ref: TimelineRef
    requested_range: TimeRange
    asset_spans: list[AssetSpan] = Field(min_length=1)

    @model_validator(mode="after")
    def spans_are_ordered_and_inside_request(self) -> IncidentClipProvenance:
        if [span.sequence for span in self.asset_spans] != list(range(len(self.asset_spans))):
            raise ValueError("clip AssetSpan.sequence는 0부터 연속 증가해야 합니다")
        if any(
            span.timeline_range.start_sec < self.requested_range.start_sec
            or span.timeline_range.end_sec > self.requested_range.end_sec
            for span in self.asset_spans
        ):
            raise ValueError("clip AssetSpan은 requested_range 안에 있어야 합니다")
        return self


class IncidentClip(ContractModel):
    contract: Literal["IncidentClip"]
    contract_version: Literal["analysis-source-derived/v1"]
    incident_clip_ref: str = Field(min_length=1)
    asset_kind: Literal["INCIDENT_CLIP"]
    source_provenance: IncidentClipProvenance
    media_stream_refs: list[str] = Field(min_length=1)
    byte_size: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    duration_sec: float | None = Field(ge=0)
    timeline_ref: TimelineRef | None
    timeline_range: TimeRange | None

    @model_validator(mode="after")
    def clip_is_consistent(self) -> IncidentClip:
        if self.availability == "AVAILABLE" and self.byte_size is None:
            raise ValueError("AVAILABLE IncidentClip의 byte_size는 null일 수 없습니다")
        if (self.timeline_ref is None) != (self.timeline_range is None):
            raise ValueError("timeline_ref와 timeline_range는 함께 존재하거나 함께 null이어야 합니다")
        if self.timeline_ref != self.source_provenance.timeline_ref:
            raise ValueError("clip timeline_ref는 source provenance와 일치해야 합니다")
        span_streams = {span.media_stream_ref for span in self.source_provenance.asset_spans}
        if not span_streams.issubset(set(self.media_stream_refs)):
            raise ValueError("clip media_stream_refs가 provenance의 stream을 포함해야 합니다")
        return self


class DerivedAsset(ContractModel):
    contract: Literal["DerivedAsset"]
    contract_version: Literal["analysis-source-derived/v1"]
    derived_asset_ref: str = Field(min_length=1)
    asset_kind: Literal["DERIVED_ASSET"]
    derived_role: Literal["REPORT_VIDEO", "PLATE_IMAGE"]
    source_refs: list[ContractRef] = Field(min_length=1)
    byte_size: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    duration_sec: float | None = Field(ge=0)
    timeline_ref: TimelineRef | None
    timeline_range: TimeRange | None
    transform_ref: str | None

    @model_validator(mode="after")
    def derived_asset_is_consistent(self) -> DerivedAsset:
        if self.availability == "AVAILABLE" and self.byte_size is None:
            raise ValueError("AVAILABLE DerivedAsset의 byte_size는 null일 수 없습니다")
        if (self.timeline_ref is None) != (self.timeline_range is None):
            raise ValueError("timeline_ref와 timeline_range는 함께 존재하거나 함께 null이어야 합니다")
        return self


class DeletionItem(ContractModel):
    asset_ref: ContractRef
    result: Literal["DELETED", "NOT_FOUND", "PENDING_EXPIRY", "FAILED"]
    failure_code: Annotated[str, Field(min_length=1)] | None

    @model_validator(mode="after")
    def deletion_result_is_consistent(self) -> DeletionItem:
        if self.asset_ref.kind == "external_source":
            raise ValueError("사용자 외부 원본은 삭제 대상이 아닙니다")
        if (self.result == "FAILED") != (self.failure_code is not None):
            raise ValueError("FAILED일 때만 failure_code가 필요합니다")
        return self


class DeletionReport(ContractModel):
    contract: Literal["DeletionReport"]
    contract_version: Literal["analysis-source-derived/v1"]
    case_id: str = Field(min_length=1)
    requested_at: AwareDatetime
    completed_at: AwareDatetime | None
    status: Literal["COMPLETE", "PARTIAL", "FAILED"]
    items: list[DeletionItem]


class AssetFacts(ContractModel):
    contract: Literal["AssetFacts"]
    contract_version: Literal[CONTRACT_VERSION]
    asset_ref: ContractRef
    asset_kind: Literal["SOURCE_ASSET", "ANALYSIS_SOURCE", "INCIDENT_CLIP", "DERIVED_ASSET"]
    derived_role: Literal["REPORT_VIDEO", "PLATE_IMAGE"] | None
    byte_size: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    checked_at: AwareDatetime
    lineage: list[ContractRef]
    duration_sec: float | None = Field(ge=0)
    timeline_ref: TimelineRef | None
    timeline_range: TimeRange | None

    @model_validator(mode="after")
    def facts_are_consistent(self) -> AssetFacts:
        expected_ref_kind = {
            "SOURCE_ASSET": "source_asset",
            "ANALYSIS_SOURCE": "analysis_source",
            "INCIDENT_CLIP": "incident_clip",
            "DERIVED_ASSET": "derived_asset",
        }[self.asset_kind]
        if self.asset_ref.kind != expected_ref_kind:
            raise ValueError("asset_ref.kind와 asset_kind의 의미가 일치하지 않습니다")
        if self.availability == "AVAILABLE" and self.byte_size is None:
            raise ValueError("AVAILABLE AssetFacts의 byte_size는 null일 수 없습니다")
        if (self.timeline_ref is None) != (self.timeline_range is None):
            raise ValueError("timeline_ref와 timeline_range는 함께 존재하거나 함께 null이어야 합니다")
        if self.asset_kind != "DERIVED_ASSET" and self.derived_role is not None:
            raise ValueError("DERIVED_ASSET가 아닌 자산에는 derived_role을 지정할 수 없습니다")
        if self.asset_kind != "SOURCE_ASSET" and not any(
            item.kind in {"source_asset", "external_source"} for item in self.lineage
        ):
            raise ValueError("파생 자산 lineage에는 원본 자산 참조가 필요합니다")
        return self


class LocatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TimelinePositionLocator(LocatorModel):
    kind: Literal["TIMELINE_POSITION"]
    timeline_ref: TimelineRef
    at_sec: float = Field(ge=0)
    stream_selector: object | None


class StreamPositionLocator(LocatorModel):
    kind: Literal["STREAM_POSITION"]
    media_stream_ref: str = Field(min_length=1)
    source_offset_sec: float = Field(ge=0)


FrameLocator = Annotated[
    TimelinePositionLocator | StreamPositionLocator,
    Field(discriminator="kind"),
]
