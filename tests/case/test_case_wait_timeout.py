"""case 대기 timeout — `COARSE_SEARCH`의 마감이 지나면 기다리기를 멈춘다(고도화 8-9, `decisions/case-wait-timeout.md`).

타이머는 없다. 마감 = 발주 시각 + AnalysisScope `budget.max_latency_sec` + 큐 대기 여유 30초이고, CaseView 조립은 마감이
지난 job을 기다리지 않는 것으로 보이고(저장 안 함), command · T2 반영은 `STOPPED_WAITING`으로 정산해 저장한다. 마감 뒤
도착한 결과는 반영하지 않는다(`NOT_APPLIED(STOPPED_WAITING)`). 실행은 취소하지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from daesingo.case import command, jobs, service
from daesingo.case.analysis_start import InitialSearchBudget
from daesingo.case.reflection import ExecutionOutcome, reflect_execution
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline

TIMED_OUT = "case.analysis_timed_out"
EVENT = {
    "candidate_id": "cand_1",
    "summary": "흰 SUV 실선 변경",
    "thumbnail_ref": "fr_thumb_1",
    "rank": 1,
    "span": {"representative_ms": 4_000, "timeline_revision": 1},
}


class FakeTimelines:
    def timeline_for(self, sources):
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=10_000)


def _searching(description: str = "", budget: InitialSearchBudget | None = None) -> tuple[CaseStore, str]:
    store = CaseStore(conn=object())
    case_id = service.create_case(store=store)
    service.record_source_registered(
        case_id,
        {"source_asset_ref": "sa_0", "availability": "AVAILABLE", "duration_sec": 10.0},
        media_streams=[{"media_stream_ref": "ms_0", "media_type": "VIDEO"}],
        store=store,
    )
    start = {"case_id": case_id, "expected_case_rev": 1, "kind": "START_ANALYSIS", "payload": {"description": description}}
    result = command.execute_command(start, store=store, timelines=FakeTimelines(), budget=budget)
    assert result.response["ok"] is True
    return store, case_id


def _requested_at(store: CaseStore, case_id: str, kind: str = "COARSE_SEARCH") -> datetime:
    return datetime.fromisoformat(jobs.latest_job_record(store.get_case(case_id), kind)["requested_at"])


def _codes(view: dict) -> list[str]:
    return [n["code"] for n in view["notices"]]


def _coarse_state(view: dict) -> str:
    return next(s["state"] for s in view["progress"] if s["step"] == "coarse_search")


def _coarse_outcome(store: CaseStore, case_id: str) -> ExecutionOutcome:
    job = jobs.latest_job_record(store.get_case(case_id), "COARSE_SEARCH")
    return ExecutionOutcome("exec_1", job["job_id"], case_id, "COARSE_SEARCH", 2, "SUCCEEDED",
                            ({"kind": "analysis_run", "ref": "run_1"},))


class Reader:
    def __init__(self):
        self.calls = 0

    def __call__(self, conn, kind, produced):
        self.calls += 1
        return {"outcome": "SUCCEEDED", "candidate_events": [EVENT]}


# ── 마감 ───────────────────────────────────────────────────────────────────


def test_deadline_is_requested_at_plus_scope_latency_plus_queue_margin():
    store, case_id = _searching()
    case = store.get_case(case_id)
    record = jobs.latest_job_record(case, "COARSE_SEARCH")
    assert case.wait_deadline(record) == _requested_at(store, case_id) + timedelta(seconds=150 + 30)


def test_deadline_follows_the_scope_budget():
    store, case_id = _searching(budget=InitialSearchBudget(max_latency_sec=60.0))
    case = store.get_case(case_id)
    record = jobs.latest_job_record(case, "COARSE_SEARCH")
    assert case.wait_deadline(record) == _requested_at(store, case_id) + timedelta(seconds=90)


def test_hint_extraction_has_no_deadline():
    # 단서 구조화의 「90초 뒤 빈 단서로 진행」은 발주가 필요해 타이머 없이 할 수 없다 — 이번 판본은 계속 기다린다.
    store, case_id = _searching("흰 SUV")
    later = _requested_at(store, case_id, "HINT_EXTRACT") + timedelta(hours=1)

    view = service.get_view(case_id, store=store, now=later)

    assert [j["kind"] for j in view["running_jobs"]] == ["HINT_EXTRACT"]
    assert TIMED_OUT not in _codes(view)


def test_coarse_without_known_scope_has_no_deadline():
    store, case_id = _searching()
    case = store.get_case(case_id)
    record = dict(jobs.latest_job_record(case, "COARSE_SEARCH"), scope_ref="scope_unknown")
    assert case.wait_deadline(record) is None


# ── CaseView (읽기) ────────────────────────────────────────────────────────


def test_view_before_deadline_still_waits():
    store, case_id = _searching()
    just_before = _requested_at(store, case_id) + timedelta(seconds=179)

    view = service.get_view(case_id, store=store, now=just_before)

    assert [j["kind"] for j in view["running_jobs"]] == ["COARSE_SEARCH"]
    assert _coarse_state(view) == "RUNNING"
    assert TIMED_OUT not in _codes(view)


def test_view_after_deadline_stops_waiting_without_saving():
    store, case_id = _searching()
    rev = store.get_case(case_id).case_rev

    view = service.get_view(case_id, store=store, now=_requested_at(store, case_id) + timedelta(seconds=180))

    assert view["running_jobs"] == []
    assert (view["stage"], view["case_rev"], _coarse_state(view)) == ("SEARCHING", rev, "PARTIAL")
    notice = next(n for n in view["notices"] if n["code"] == TIMED_OUT)
    assert notice == {"code": TIMED_OUT, "severity": "INFO", "blocking": False,
                      "message_key": "notice.analysis_timed_out", "actions": ["RETRY_SEARCH"]}
    assert "case.analysis_stopped" not in _codes(view)
    assert store.get_case(case_id).settled_jobs == {}  # 읽기는 저장하지 않는다


# ── T2 반영 ────────────────────────────────────────────────────────────────


def test_result_before_deadline_is_applied():
    store, case_id = _searching()
    now = _requested_at(store, case_id) + timedelta(seconds=100)

    result = reflect_execution(_coarse_outcome(store, case_id), store=store, reader=Reader(),
                               timelines=FakeTimelines(), now=now)

    assert result.status == "APPLIED"
    assert store.get_case(case_id).stage == "CANDIDATE_REVIEW"


def test_result_after_deadline_is_not_applied_and_settlement_is_saved():
    store, case_id = _searching()
    outcome = _coarse_outcome(store, case_id)
    reader = Reader()

    result = reflect_execution(outcome, store=store, reader=reader, timelines=FakeTimelines(),
                               now=_requested_at(store, case_id) + timedelta(seconds=200))

    assert (result.status, result.reason, result.appended_job_records) == ("NOT_APPLIED", "STOPPED_WAITING", [])
    case = store.get_case(case_id)
    assert case.settled_jobs[outcome.job_id] == "STOPPED_WAITING"
    assert (case.stage, case.candidates) == ("SEARCHING", [])
    assert reader.calls == 0


def test_other_job_result_also_records_expired_settlement():
    # 다른 job의 T2도 case 행을 잠그므로, 그때 지난 마감을 함께 남긴다.
    store, case_id = _searching()
    coarse = jobs.latest_job_record(store.get_case(case_id), "COARSE_SEARCH")
    case = store.load_for_update(case_id)
    other = jobs.issue_plate_read(case, input_fingerprint="sha256:plate")
    store.save(case)
    outcome = ExecutionOutcome("exec_plate", other["job_id"], case_id, "PLATE_READ", 1, "SUCCEEDED")

    result = reflect_execution(outcome, store=store, reader=Reader(), timelines=FakeTimelines(),
                               now=_requested_at(store, case_id) + timedelta(seconds=200))

    assert result.status == "APPLIED"
    assert store.get_case(case_id).settled_jobs[coarse["job_id"]] == "STOPPED_WAITING"


# ── command ────────────────────────────────────────────────────────────────


def test_resume_after_timeout_issues_new_search_without_cancel():
    store, case_id = _searching()
    old = jobs.latest_job_record(store.get_case(case_id), "COARSE_SEARCH")
    later = _requested_at(store, case_id) + timedelta(seconds=200)
    request = {
        "case_id": case_id,
        "expected_case_rev": store.get_case(case_id).case_rev,
        "kind": "RUN_NOTICE_ACTION",
        "payload": {"notice_code": TIMED_OUT, "action": "RETRY_SEARCH"},
    }

    result = command.execute_command(request, store=store, now=later)

    assert result.response["ok"] is True
    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]
    assert result.cancelled_job_ids == []  # timeout은 실행을 취소하지 않는다
    case = store.get_case(case_id)
    assert case.settled_jobs[old["job_id"]] == "STOPPED_WAITING"
    view = result.response["case_view"]
    assert TIMED_OUT not in _codes(view)
    assert [j["kind"] for j in view["running_jobs"]] == ["COARSE_SEARCH"]


def test_stop_after_timeout_is_not_allowed():
    store, case_id = _searching()
    request = {"case_id": case_id, "expected_case_rev": store.get_case(case_id).case_rev,
               "kind": "STOP_ANALYSIS", "payload": {}}

    result = command.execute_command(request, store=store,
                                     now=_requested_at(store, case_id) + timedelta(seconds=200))

    assert result.response["error"]["code"] == "case.command.not_allowed"
    assert result.cancelled_job_ids == []
