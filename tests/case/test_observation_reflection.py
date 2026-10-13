"""T2 관찰 kind 반영 — `PLATE_READ` · `OVERLAY_TIME_READ` · `FINE_VERIFY`(고도화 8-6 2단계 · 8-8,
`decisions/observation-storage.md` §4-5).

관찰 결과는 정산만 한다 — 내용은 case state에 복사하지 않고(CaseView는 adapter가 결과를 읽는다), job을 `REFLECTED`로
정산한 뒤 stage가 `EVIDENCE_REVIEW`면 command 뒤와 같은 READY gate를 다시 본다. 실패 terminal도 정산만 하고, 실패
notice는 view가 read port의 실행 상태로 계산한다.
"""
from __future__ import annotations

from typing import Any

import pytest

from daesingo.case import command, jobs, service
from daesingo.case.reflection import ExecutionOutcome, reflect_execution
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline

OBSERVATION_KINDS = ["PLATE_READ", "OVERLAY_TIME_READ", "FINE_VERIFY"]
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


class FakeReader:
    def __init__(self, content: dict[str, Any] | None = None):
        self.content = content or {}
        self.calls: list[str] = []

    def __call__(self, conn: Any, kind: str, produced: tuple) -> dict[str, Any]:
        self.calls.append(kind)
        return self.content


class SnapshotAdapter:
    """READY gate(`mark_ready_if_package_ready`)가 읽는 getter만 가진 스냅샷."""

    def __init__(self, *, evidence_record: dict | None = None, final: str | None = None, package: dict | None = None):
        self._evidence = evidence_record
        self._final = None if final is None else {"overall": final, "checks": []}
        self._package = package

    def get_evidence_record(self):
        return self._evidence

    def get_requirement_report(self, scope):
        return self._final if scope == "FINAL_PACKAGE" else None

    def get_report_package(self):
        return self._package

    def get_plate_read_status(self):
        return None

    def get_evidence_needs(self):
        return []

    def get_plate_readouts(self):
        return []

    def get_overlay_time_readouts(self):
        return []

    def get_visual_evidence_decision(self):
        return None

    def get_independent_facts(self):
        return None


def _store_with_observation_job(kind: str, adapter: Any) -> tuple[CaseStore, str]:
    """후보를 고른(`EVIDENCE_REVIEW`) case에 관찰 job 하나를 발주해 둔다."""
    store = CaseStore(conn=object())
    case_id = service.create_case(store=store)
    service.record_source_registered(
        case_id,
        {"source_asset_ref": "sa_0", "availability": "AVAILABLE", "duration_sec": 10.0},
        media_streams=[{"media_stream_ref": "ms_0", "media_type": "VIDEO"}],
        store=store,
    )
    start = {"case_id": case_id, "expected_case_rev": 1, "kind": "START_ANALYSIS", "payload": {"description": ""}}
    assert command.execute_command(start, store=store, timelines=FakeTimelines()).response["ok"] is True
    coarse = jobs.latest_job_record(store.get_case(case_id), "COARSE_SEARCH")
    reflect_execution(
        ExecutionOutcome("exec_coarse", coarse["job_id"], case_id, "COARSE_SEARCH", 1, "SUCCEEDED",
                         ({"kind": "analysis_run", "ref": "run_1"},)),
        store=store, reader=FakeReader({"outcome": "SUCCEEDED", "candidate_events": [EVENT]}), timelines=FakeTimelines(),
    )
    case = store.load_for_update(case_id)
    case.select_candidate("cand_1")
    jobs.issue_job(case, kind, input_fingerprint=f"sha256:{kind.lower()}")
    store.save(case)
    store.adapters.put(case_id, adapter)
    return store, case_id


def _outcome(store: CaseStore, case_id: str, kind: str, status: str = "SUCCEEDED") -> ExecutionOutcome:
    job = jobs.latest_job_record(store.get_case(case_id), kind)
    return ExecutionOutcome(
        execution_id=f"exec_{kind.lower()}",
        job_id=job["job_id"],
        case_id=case_id,
        kind=kind,
        attempt=1,
        status=status,
        produced=({"kind": "plate_readout", "ref": "pr_1"},) if status == "SUCCEEDED" else (),
        failure_kind=None if status == "SUCCEEDED" else "PROVIDER_FAILED",
    )


def _reflect(store: CaseStore, outcome: ExecutionOutcome, reader: FakeReader):
    return reflect_execution(outcome, store=store, reader=reader, timelines=FakeTimelines())


@pytest.mark.parametrize("kind", OBSERVATION_KINDS)
@pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED"])
def test_observation_result_is_settled_without_reading_content(kind, status):
    store, case_id = _store_with_observation_job(kind, SnapshotAdapter())
    outcome = _outcome(store, case_id, kind, status)
    reader = FakeReader()

    result = _reflect(store, outcome, reader)

    assert (result.status, result.reason, result.appended_job_records) == ("APPLIED", None, [])
    case = store.get_case(case_id)
    assert case.settled_jobs[outcome.job_id] == "REFLECTED"
    assert case.processed_executions[outcome.execution_id] == outcome.job_id
    assert reader.calls == []  # 내용은 CaseView 조립 때 adapter가 읽는다(§4-2)
    assert case.stage == "EVIDENCE_REVIEW"
    assert jobs.latest_job_record(case, kind)["job_id"] not in [r["job_id"] for r in case.waiting_job_records()]


@pytest.mark.parametrize("kind", OBSERVATION_KINDS)
def test_observation_result_reopens_ready_gate(kind):
    # 관찰 결과로 Package가 준비되면 command 뒤와 같은 gate로 READY가 된다(§4-5).
    evidence = {
        "record_ref": {"kind": "evidence_record", "ref": "er_1"},
        "basis": {"candidate_ref": {"kind": "candidate_event", "ref": "cand_1"}},
        "selection_rev": 1,
    }
    adapter = SnapshotAdapter(evidence_record=evidence, final="PASS", package={"package_ref": {"ref": "pkg_1"}})
    store, case_id = _store_with_observation_job(kind, adapter)

    _reflect(store, _outcome(store, case_id, kind), FakeReader())

    assert store.get_case(case_id).stage == "READY"


def test_observation_result_does_not_ready_without_package():
    store, case_id = _store_with_observation_job("PLATE_READ", SnapshotAdapter(final="UNKNOWN"))
    rev = store.get_case(case_id).case_rev

    _reflect(store, _outcome(store, case_id, "PLATE_READ"), FakeReader())

    case = store.get_case(case_id)
    assert (case.stage, case.case_rev) == ("EVIDENCE_REVIEW", rev)


def test_superseded_observation_job_is_not_applied():
    store, case_id = _store_with_observation_job("PLATE_READ", SnapshotAdapter())
    old = _outcome(store, case_id, "PLATE_READ")
    case = store.load_for_update(case_id)
    jobs.issue_job(case, "PLATE_READ", input_fingerprint="sha256:plate_read")
    store.save(case)

    result = _reflect(store, old, FakeReader())

    assert (result.status, result.reason) == ("NOT_APPLIED", "SUPERSEDED")
