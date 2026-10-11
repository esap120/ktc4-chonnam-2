"""START_ANALYSIS command · Worker 반영 진입 함수 · 여러 영상 smoke(`decisions/start-analysis.md`)."""

import hashlib

import pytest

from daesingo.case import command, service
from daesingo.case.analysis_start import InitialSearchBudget
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline, RecordingSequentialTimelineSource, TimelineUnavailable
from daesingo.recording import RecordingService
from daesingo.recording.probe import LocalSource, ProbedStream


class FakeTimelines:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def timeline_for(self, sources):
        if self.fail:
            raise TimelineUnavailable("fake")
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=10_000)


def _store_with_sources(n: int) -> tuple[CaseStore, str]:
    store = CaseStore()
    case_id = service.create_case(store=store)
    for i in range(n):
        service.record_source_registered(
            case_id,
            {"source_asset_ref": f"sa_{i}", "availability": "AVAILABLE", "duration_sec": 10.0},
            media_streams=[{"media_stream_ref": f"ms_{i}", "media_type": "VIDEO"}],
            store=store,
        )
    return store, case_id


def _start(case_id: str, description: str, rev: int = 1) -> dict:
    return {"case_id": case_id, "expected_case_rev": rev, "kind": "START_ANALYSIS", "payload": {"description": description}}


def test_start_returns_hint_extract_as_appended_and_pending():
    store, case_id = _store_with_sources(1)
    result = command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=FakeTimelines())
    assert result.response["ok"] is True
    assert [r["kind"] for r in result.appended_job_records] == ["HINT_EXTRACT"]
    view = result.response["case_view"]
    assert view["stage"] == "SEARCHING"
    assert view["description"] == "흰 SUV"
    assert [(j["kind"], j["status"]) for j in view["running_jobs"]] == [("HINT_EXTRACT", "PENDING")]


def test_blank_start_returns_coarse_search():
    store, case_id = _store_with_sources(1)
    result = command.execute_command(_start(case_id, ""), store=store, timelines=FakeTimelines())
    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]


def test_start_without_sources_is_not_allowed_and_saves_nothing():
    store, case_id = _store_with_sources(0)
    result = command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.not_allowed"
    saved = store.get_case(case_id)
    assert (saved.stage, saved.description, saved.job_records) == ("INTAKE", None, [])


def test_start_with_only_unavailable_sources_is_not_allowed():
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(
        case_id,
        {"source_asset_ref": "sa_bad", "availability": "UNAVAILABLE", "duration_sec": None},
        media_streams=[{"media_stream_ref": "ms_bad", "media_type": "VIDEO"}],
        store=store,
    )
    result = command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.not_allowed"
    saved = store.get_case(case_id)
    assert (saved.stage, saved.description, saved.job_records) == ("INTAKE", None, [])


def test_second_start_is_not_allowed():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    result = command.execute_command(_start(case_id, "y"), store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.not_allowed"
    assert result.appended_job_records == []
    assert store.get_case(case_id).description == "x"


def test_missing_description_key_is_invalid_payload():
    store, case_id = _store_with_sources(1)
    request = {"case_id": case_id, "expected_case_rev": 1, "kind": "START_ANALYSIS", "payload": {}}
    result = command.execute_command(request, store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.invalid_payload"


def test_timeline_failure_in_command_propagates_and_saves_nothing():
    store, case_id = _store_with_sources(1)
    with pytest.raises(TimelineUnavailable):
        command.execute_command(_start(case_id, ""), store=store, timelines=FakeTimelines(fail=True))
    saved = store.get_case(case_id)
    assert saved.stage == "INTAKE"
    assert saved.job_records == []


def test_start_without_injected_timelines_is_a_programming_error():
    store, case_id = _store_with_sources(1)
    with pytest.raises(RuntimeError):
        command.execute_command(_start(case_id, "x"), store=store)


def test_reflection_entrypoint_returns_appended_coarse_search():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=FakeTimelines())
    result = service.receive_hint_extraction_result(
        case_id, {"status": "OK", "vehicle_hint": "흰 SUV"}, store=store, timelines=FakeTimelines()
    )
    assert result.reflected is True
    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]
    saved = store.get_case(case_id)
    assert saved.hints["vehicle"] == "흰 SUV"
    assert [r["kind"] for r in saved.job_records] == ["HINT_EXTRACT", "COARSE_SEARCH"]


def test_duplicate_reflection_returns_nothing():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    service.receive_hint_extraction_result(case_id, {"status": "OK"}, store=store, timelines=FakeTimelines())
    again = service.receive_hint_extraction_result(case_id, {"status": "OK"}, store=store, timelines=FakeTimelines())
    assert again.reflected is False
    assert again.appended_job_records == []
    assert len(store.get_case(case_id).job_records) == 2


def test_reflection_timeline_failure_saves_nothing():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    with pytest.raises(TimelineUnavailable):
        service.receive_hint_extraction_result(case_id, {"status": "OK"}, store=store, timelines=FakeTimelines(fail=True))
    saved = store.get_case(case_id)
    assert saved.settled_jobs == {}
    assert [r["kind"] for r in saved.job_records] == ["HINT_EXTRACT"]


def test_budget_is_injectable():
    store, case_id = _store_with_sources(1)
    command.execute_command(
        _start(case_id, ""), store=store, timelines=FakeTimelines(), budget=InitialSearchBudget(max_cost_krw=500.0)
    )
    saved = store.get_case(case_id)
    assert next(iter(saved.analysis_scopes.values()))["budget"]["max_cost_krw"] == 500.0


def test_two_videos_end_to_end_with_recording(tmp_path):
    """빈 case → 업로드 2개 → START_ANALYSIS → 반영 → COARSE_SEARCH(이어 붙인 20초 타임라인)."""

    class Probe:
        def probe(self, path):
            stat = path.stat()
            return LocalSource(path, stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest(),
                               10.0, (ProbedStream(0, "VIDEO", 10.0), ProbedStream(1, "AUDIO", None)))

    recording = RecordingService(media_probe=Probe())
    store = CaseStore()
    case_id = service.create_case(store=store)
    for name in ("a.mp4", "b.mp4"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        registered = recording.register_local_source(path)
        service.record_source_registered(
            case_id,
            registered.source_asset.model_dump(mode="json"),
            media_streams=[s.model_dump(mode="json") for s in registered.media_streams],
            store=store,
        )
    timelines = RecordingSequentialTimelineSource(recording)
    command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=timelines)
    result = service.receive_hint_extraction_result(case_id, {"status": "ABSTAINED"}, store=store, timelines=timelines)
    coarse = result.appended_job_records[0]
    scope = store.get_case(case_id).analysis_scopes[coarse["scope_ref"]]
    assert scope["time_ranges"][0]["end_ms"] == 20_000
    view = service.get_view(case_id, store=store)
    assert [j["kind"] for j in view["running_jobs"]] == ["COARSE_SEARCH"]
    recording.close()
