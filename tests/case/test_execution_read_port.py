"""JobExecution read port 연결(8-10) — `decisions/jobexecution-read-port.md`.

composition root가 `CaseStore(executions=read_executions)`로 Runtime read port를 꽂으면, case가 로드한 case의
`job_id`로 직접 조회해 `running_jobs` · Fine 실행 실패 notice를 만든다. 호출자가 실행 기록을 넘기는 인자는 없다.
"""
from __future__ import annotations

from typing import Any

from daesingo.case import command, jobs, service
from daesingo.case.domain import CaseAggregate
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline


class FakeTimelines:
    def timeline_for(self, sources):
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


class FakeReader:
    """Runtime `read_executions(conn, job_ids)`와 같은 모양. 요청받은 job만 돌려준다."""

    def __init__(self, executions: list[dict[str, Any]] | None = None, default: str | None = None):
        self.executions = executions or []
        self.default = default
        self.calls: list[tuple[Any, list[str]]] = []

    def __call__(self, conn: Any, job_ids: list[str]) -> list[dict[str, Any]]:
        self.calls.append((conn, list(job_ids)))
        found = [e for e in self.executions if e["job_id"] in job_ids]
        if self.default is not None:
            known = {e["job_id"] for e in found}
            found += [{"job_id": j, "attempt": 1, "status": self.default} for j in job_ids if j not in known]
        return found


def _searching_case(case_id: str = "case_rp") -> CaseAggregate:
    case = CaseAggregate.intake(case_id=case_id, hints={}, manifest_summary={})
    case.start_search()
    return case


def test_get_view_reads_executions_through_injected_port():
    case = _searching_case()
    job = jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f")
    conn = object()
    reader = FakeReader([
        {"job_id": job["job_id"], "attempt": 1, "status": "STALE"},
        {"job_id": job["job_id"], "attempt": 2, "status": "RUNNING"},
    ])
    store = CaseStore(conn=conn, executions=reader)
    store.register(case)

    view = service.get_view(case.case_id, store=store)

    assert [(j["job_id"], j["status"]) for j in view["running_jobs"]] == [(job["job_id"], "RUNNING")]
    assert reader.calls == [(conn, [job["job_id"]])]


def test_reader_is_asked_only_for_this_case_jobs():
    store = CaseStore(executions=(reader := FakeReader()))
    mine, other = _searching_case("case_mine"), _searching_case("case_other")
    mine_job = jobs.issue_plate_read(mine, input_fingerprint="p")
    jobs.issue_plate_read(other, input_fingerprint="p")
    store.register(mine)
    store.register(other)

    service.get_view("case_mine", store=store)

    assert reader.calls[-1][1] == [mine_job["job_id"]]


def test_without_reader_jobs_stay_pending():
    case = _searching_case()
    jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f")
    store = CaseStore()
    store.register(case)

    view = service.get_view(case.case_id, store=store)

    assert [j["status"] for j in view["running_jobs"]] == ["PENDING"]


def test_case_without_jobs_does_not_call_reader():
    store = CaseStore(executions=(reader := FakeReader()))
    store.register(_searching_case())

    service.get_view("case_rp", store=store)

    assert reader.calls == []


def test_command_response_view_uses_reader():
    store, case_id = _store_with_sources(1)
    store.executions = FakeReader(default="RUNNING")

    result = command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=FakeTimelines())

    assert [(j["kind"], j["status"]) for j in result.response["case_view"]["running_jobs"]] == [
        ("HINT_EXTRACT", "RUNNING")
    ]


def test_rejected_command_view_uses_reader():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    store.executions = FakeReader(default="RUNNING")

    result = command.execute_command(_start(case_id, "y", rev=1), store=store, timelines=FakeTimelines())

    assert result.response["ok"] is False
    assert [j["status"] for j in result.response["case_view"]["running_jobs"]] == ["RUNNING"]
