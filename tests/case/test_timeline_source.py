"""타임라인 port 임시 구현 — 등록 순서대로 이어 붙인다(`decisions/start-analysis.md` §3-1)."""

import hashlib

import pytest

from daesingo.case.timeline_source import CaseTimeline, RecordingSequentialTimelineSource, TimelineUnavailable
from daesingo.recording import RecordingService
from daesingo.recording.probe import LocalSource, ProbedStream


def _service(video_streams: int = 1, duration: float = 10.0) -> RecordingService:
    class Probe:
        def probe(self, path):
            stat = path.stat()
            streams = tuple(ProbedStream(i, "VIDEO", duration) for i in range(video_streams))
            streams += (ProbedStream(video_streams, "AUDIO", None),)
            return LocalSource(path, stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest(),
                               duration, streams)

    return RecordingService(media_probe=Probe())


def _register(service: RecordingService, tmp_path, name: str) -> dict:
    path = tmp_path / name
    path.write_bytes(name.encode())
    registered = service.register_local_source(path)
    videos = [s.media_stream_ref for s in registered.media_streams if s.media_type == "VIDEO"]
    return {
        "source_asset_ref": registered.source_asset.source_asset_ref,
        "video_stream_ref": videos[0] if len(videos) == 1 else None,
        "duration_sec": registered.source_asset.duration_sec,
    }


def test_single_source_uses_relative_timeline(tmp_path):
    service = _service()
    source = _register(service, tmp_path, "a.mp4")
    timeline = RecordingSequentialTimelineSource(service).timeline_for([source])
    assert isinstance(timeline, CaseTimeline)
    assert timeline.revision == 1
    assert timeline.duration_ms == 10_000
    placements = service.get_timeline(timeline.timeline_id, timeline.revision).source_placements
    assert [p.source_asset_ref for p in placements] == [source["source_asset_ref"]]


def test_two_sources_are_placed_back_to_back_in_registration_order(tmp_path):
    service = _service()
    first = _register(service, tmp_path, "b.mp4")
    second = _register(service, tmp_path, "a.mp4")
    timeline = RecordingSequentialTimelineSource(service).timeline_for([first, second])
    assert timeline.duration_ms == 20_000
    placements = service.get_timeline(timeline.timeline_id, timeline.revision).source_placements
    assert [(p.source_asset_ref, p.timeline_start_sec, p.timeline_end_sec) for p in placements] == [
        (first["source_asset_ref"], 0.0, 10.0),
        (second["source_asset_ref"], 10.0, 20.0),
    ]


def test_no_sources_is_unavailable():
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(_service()).timeline_for([])


def test_multiple_sources_need_a_video_stream_each(tmp_path):
    service = _service(video_streams=2)
    sources = [_register(service, tmp_path, "a.avi"), _register(service, tmp_path, "b.avi")]
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(service).timeline_for(sources)


def test_multiple_sources_need_known_duration(tmp_path):
    service = _service()
    sources = [_register(service, tmp_path, "a.mp4"), _register(service, tmp_path, "b.mp4")]
    sources[1] = dict(sources[1], duration_sec=None)
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(service).timeline_for(sources)


def test_single_source_with_two_video_streams_is_unavailable(tmp_path):
    # 전방 · 후방이 한 파일(VIDEO 2개)이면 영상이 1개여도 고를 기준이 없다 — 발주 전에 막는다(spec §3-1 한계 4).
    service = _service(video_streams=2)
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(service).timeline_for([_register(service, tmp_path, "front_rear.avi")])
