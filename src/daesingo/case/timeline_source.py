"""분석 범위가 가리킬 case 타임라인 — 교체 가능한 port(`decisions/start-analysis.md` §3-1).

case당 RecordingTimeline 하나로 범위 하나를 만든다. 여러 원본을 하나로 정렬하는 일은 recording 책임이고
(`module-architecture.md` §4 recording ②), 그 기능이 생기기 전까지 `RecordingSequentialTimelineSource`가 기존
recording 공개 함수로 **등록 순서대로 이어 붙인다** — 이 순서 판단은 임시이며 이 클래스 안에만 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TimelineUnavailable(RuntimeError):
    """타임라인을 만들 수 없다 — 원본 없음 · VIDEO 스트림을 정할 수 없음 · 길이를 모름."""


@dataclass(frozen=True)
class CaseTimeline:
    timeline_id: str
    revision: int
    duration_ms: int


class CaseTimelineSource(Protocol):
    def timeline_for(self, sources: list[dict[str, Any]]) -> CaseTimeline: ...


def _case_timeline(timeline: Any) -> CaseTimeline:
    end_sec = max(p.timeline_end_sec for p in timeline.source_placements)
    return CaseTimeline(timeline_id=timeline.timeline_id, revision=timeline.revision, duration_ms=round(end_sec * 1000))


class RecordingSequentialTimelineSource:
    """임시 구현 — 원본 1개는 `create_relative_timeline()`, 여러 개는 등록 순서대로 앞 원본 끝에 이어 붙인다.

    전방 · 후방을 별도 파일로 찍은 경우 앞뒤로 놓이는 한계가 있다(spec §3-1 한계 1). recording이 case
    타임라인 정렬을 맡게 되면 이 구현만 바꾼다."""

    def __init__(self, recording: Any) -> None:
        self._recording = recording

    def timeline_for(self, sources: list[dict[str, Any]]) -> CaseTimeline:
        if not sources:
            raise TimelineUnavailable("처리 가능한 원본이 없다")
        # 영상 개수와 무관하게 VIDEO 스트림을 정할 수 있어야 한다 — 전방 · 후방이 한 파일(VIDEO 2개)이면 발주 전에
        # 막는다(spec §3-1 한계 4). composition root는 등록 때 `media_streams`를 넘겨야 한다.
        for source in sources:
            if source.get("video_stream_ref") is None:
                raise TimelineUnavailable(f"VIDEO 스트림을 정할 수 없는 원본: {source['source_asset_ref']!r}")
        if len(sources) == 1:
            return _case_timeline(self._recording.create_relative_timeline(sources[0]["source_asset_ref"]))
        placements = []
        start = 0.0
        for source in sources:
            duration = source.get("duration_sec")
            if not duration or duration <= 0:
                raise TimelineUnavailable(f"길이를 모르는 원본: {source['source_asset_ref']!r}")
            placements.append(
                {
                    "source_asset_ref": source["source_asset_ref"],
                    "media_stream_ref": source["video_stream_ref"],
                    "timeline_start_sec": start,
                    "timeline_end_sec": start + float(duration),
                }
            )
            start += float(duration)
        return _case_timeline(self._recording.create_relative_timeline_from_placements(placements))
