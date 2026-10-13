"""case T2 진입 함수 `reflect_execution()` — 고도화 8-8, `decisions/result-reflection.md`.

Worker가 terminal execution을 넘기면 case가 행을 잠그고, 처리한 `execution_id`로 중복을 거르고, 기다리는 job의
결과만 kind별로 반영한다(Runtime Tech Spec §12.2 · #245 D-5). 결과 내용은 주입한 `ProducedReader`가 준다.
"""
from __future__ import annotations

from typing import Any

import pytest

from daesingo.case import command, jobs, service
from daesingo.case.reflection import ExecutionOutcome, reflect_execution
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline


class FakeTimelines:
    def timeline_for(self, sources):
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=10_000)


class FakeReader:
    """kind별 결과 내용. 받은 호출을 남긴다."""

    def __init__(self, content: dict[str, Any] | None = None):
        self.content = content or {}
        self.calls: list[tuple[Any, str, tuple]] = []

    def __call__(self, conn: Any, kind: str, produced: tuple) -> dict[str, Any]:
        self.calls.append((conn, kind, produced))
        return self.content


EVENT = {
    "candidate_id": "cand_1",
    "summary": "흰 SUV 실선 변경",
    "thumbnail_ref": "fr_thumb_1",
    "rank": 1,
    "span": {"representative_ms": 4_000, "timeline_revision": 1},
}


def _store_searching(description: str = "") -> tuple[CaseStore, str]:
    store = CaseStore(conn=object())
    case_id = service.create_case(store=store)
    service.record_source_registered(
        case_id,
        {"source_asset_ref": "sa_0", "availability": "AVAILABLE", "duration_sec": 10.0},
        media_streams=[{"media_stream_ref": "ms_0", "media_type": "VIDEO"}],
        store=store,
    )
    request = {"case_id": case_id, "expected_case_rev": 1, "kind": "START_ANALYSIS", "payload": {"description": description}}
    assert command.execute_command(request, store=store, timelines=FakeTimelines()).response["ok"] is True
    return store, case_id


def _outcome(store: CaseStore, case_id: str, kind: str, *, status: str = "SUCCEEDED", execution_id: str = "exec_1",
             job_id: str | None = None) -> ExecutionOutcome:
    job = jobs.latest_job_record(store.get_case(case_id), kind)
    return ExecutionOutcome(
        execution_id=execution_id,
        job_id=job_id or job["job_id"],
        case_id=case_id,
        kind=kind,
        attempt=1,
        status=status,
        produced=({"kind": "analysis_run", "ref": "run_1"},) if status == "SUCCEEDED" else (),
        failure_kind=None if status == "SUCCEEDED" else "SEARCH_PROVIDER_FAILED",
    )


def _reflect(store: CaseStore, outcome: ExecutionOutcome, reader: FakeReader | None = None):
    return reflect_execution(outcome, store=store, reader=reader or FakeReader(), timelines=FakeTimelines())


# ── COARSE_SEARCH ──────────────────────────────────────────────────────────


def test_coarse_candidates_are_applied_and_execution_recorded():
    store, case_id = _store_searching()
    outcome = _outcome(store, case_id, "COARSE_SEARCH")
    reader = FakeReader({"outcome": "SUCCEEDED", "candidate_events": [EVENT]})

    result = _reflect(store, outcome, reader)

    assert (result.status, result.reason, result.appended_job_records) == ("APPLIED", None, [])
    case = store.get_case(case_id)
    assert case.stage == "CANDIDATE_REVIEW"
    assert [c.candidate_id for c in case.candidates] == ["cand_1"]
    assert case.candidates[0].representative_ms == 4_000
    assert case.settled_jobs[outcome.job_id] == "REFLECTED"
    assert case.processed_executions == {"exec_1": outcome.job_id}
    assert reader.calls == [(store.conn, "COARSE_SEARCH", outcome.produced)]


def test_coarse_failed_run_records_search_failure():
    store, case_id = _store_searching()
    outcome = _outcome(store, case_id, "COARSE_SEARCH")

    result = _reflect(store, outcome, FakeReader({"outcome": "FAILED", "candidate_events": []}))

    assert result.status == "APPLIED"
    case = store.get_case(case_id)
    assert (case.stage, case.candidate_search_failed) == ("SEARCHING", True)


def test_coarse_failed_execution_records_search_failure_without_reading():
    store, case_id = _store_searching()
    reader = FakeReader()

    result = _reflect(store, _outcome(store, case_id, "COARSE_SEARCH", status="FAILED"), reader)

    assert result.status == "APPLIED"
    assert store.get_case(case_id).candidate_search_failed is True
    assert reader.calls == []


# ── HINT_EXTRACT ───────────────────────────────────────────────────────────


def test_hint_result_is_applied_and_returns_first_search():
    store, case_id = _store_searching("흰 SUV")
    outcome = _outcome(store, case_id, "HINT_EXTRACT")

    result = _reflect(store, outcome, FakeReader({"status": "OK", "vehicle_hint": "흰 SUV"}))

    assert result.status == "APPLIED"
    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]
    case = store.get_case(case_id)
    assert case.hints["vehicle"] == "흰 SUV"
    assert case.processed_executions == {"exec_1": outcome.job_id}


def test_failed_hint_execution_continues_with_empty_hints():
    """단서 구조화가 실패해도 빈 단서로 탐색한다(case-command Draft §11)."""
    store, case_id = _store_searching("흰 SUV")

    result = _reflect(store, _outcome(store, case_id, "HINT_EXTRACT", status="FAILED"))

    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]
    assert store.get_case(case_id).hints == {"time": None, "vehicle": None, "situation": None, "location": None}


# ── idempotency · guard ────────────────────────────────────────────────────


def test_same_execution_again_is_already_applied_and_changes_nothing():
    store, case_id = _store_searching("흰 SUV")
    outcome = _outcome(store, case_id, "HINT_EXTRACT")
    reader = FakeReader({"status": "OK"})
    _reflect(store, outcome, reader)
    before = store.get_case(case_id)

    again = _reflect(store, outcome, reader)

    assert (again.status, again.reason, again.appended_job_records) == ("ALREADY_APPLIED", None, [])
    assert store.get_case(case_id) == before
    assert len(reader.calls) == 1


def test_cancelled_job_is_not_applied_with_reason():
    store, case_id = _store_searching()
    outcome = _outcome(store, case_id, "COARSE_SEARCH")
    stop = {"case_id": case_id, "expected_case_rev": 1, "kind": "STOP_ANALYSIS", "payload": {}}
    assert command.execute_command(stop, store=store).response["ok"] is True
    before = store.get_case(case_id)

    result = _reflect(store, outcome, FakeReader({"outcome": "SUCCEEDED", "candidate_events": [EVENT]}))

    assert (result.status, result.reason) == ("NOT_APPLIED", "CANCELLED")
    assert store.get_case(case_id) == before


def test_superseded_job_is_not_applied_with_reason():
    store, case_id = _store_searching()
    old = _outcome(store, case_id, "COARSE_SEARCH")
    case = store.load_for_update(case_id)
    prior = jobs.latest_job_record(case, "COARSE_SEARCH")
    jobs.issue_job(case, "COARSE_SEARCH", scope_ref=prior["scope_ref"], input_fingerprint=prior["input_fingerprint"])
    store.save(case)

    result = _reflect(store, old, FakeReader({"outcome": "SUCCEEDED", "candidate_events": [EVENT]}))

    assert (result.status, result.reason) == ("NOT_APPLIED", "SUPERSEDED")


def test_job_of_other_case_is_a_programming_error():
    store, case_id = _store_searching()
    with pytest.raises(ValueError):
        _reflect(store, _outcome(store, case_id, "COARSE_SEARCH", job_id="job_not_mine"))


def test_kind_mismatch_is_a_programming_error():
    store, case_id = _store_searching()
    outcome = _outcome(store, case_id, "COARSE_SEARCH")
    with pytest.raises(ValueError):
        _reflect(store, ExecutionOutcome(**{**outcome.__dict__, "kind": "HINT_EXTRACT"}))


def test_kind_without_reflector_is_an_error_not_silent_settlement():
    store, case_id = _store_searching()
    case = store.load_for_update(case_id)
    # 신고용 영상 export 반영기는 아직 없다(`report-video-export.md` — 실행기 · 배선 보류).
    job = jobs.issue_report_video_export(case, input_fingerprint="sha1:rv")
    store.save(case)
    outcome = ExecutionOutcome(
        execution_id="exec_rv", job_id=job["job_id"], case_id=case_id, kind="REPORT_VIDEO_EXPORT", attempt=1,
        status="SUCCEEDED",
    )

    with pytest.raises(ValueError):
        _reflect(store, outcome)
    assert job["job_id"] not in store.get_case(case_id).settled_jobs


def test_job_already_reflected_by_other_path_is_an_error():
    """`REFLECTED`는 Runtime reason에 없다 — 다른 execution · 동기 경로로 반영된 job이 다시 오면 드러낸다."""
    store, case_id = _store_searching()
    outcome = _outcome(store, case_id, "COARSE_SEARCH")
    case = store.load_for_update(case_id)
    case.settle_job(outcome.job_id, "REFLECTED")
    store.save(case)

    with pytest.raises(ValueError):
        _reflect(store, outcome)


def test_reader_error_saves_nothing():
    class Broken:
        def __call__(self, conn, kind, produced):
            raise RuntimeError("storage down")

    store, case_id = _store_searching()
    outcome = _outcome(store, case_id, "COARSE_SEARCH")
    with pytest.raises(RuntimeError):
        reflect_execution(outcome, store=store, reader=Broken(), timelines=FakeTimelines())
    case = store.get_case(case_id)
    assert case.processed_executions == {}
    assert outcome.job_id not in case.settled_jobs
