"""MySQL 전용 — Runtime `reflect_terminal`에 case `reflect_execution`을 꽂아 T2 한 transaction을 확인한다(8-8).

`DAESINGO_MYSQL_URL`이 있을 때만 돈다. 아래 `_CaseReflector`는 composition root가 쓸 어댑터의 예시다 — case는 Runtime
타입을 모르고, 이 어댑터가 `ReflectionInput` ↔ `ExecutionOutcome`, `ReflectionOutcome` ↔ `ReflectionResult`를 옮긴다.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from daesingo.case import command, service  # noqa: E402
from daesingo.case.reflection import ExecutionOutcome, reflect_execution  # noqa: E402
from daesingo.case.store import CaseStore  # noqa: E402
from daesingo.case.timeline_source import CaseTimeline  # noqa: E402

pytestmark = pytest.mark.mysql

EVENT = {
    "candidate_id": "cand_1",
    "summary": "흰 SUV",
    "thumbnail_ref": "fr_thumb_1",
    "rank": 1,
    "span": {"representative_ms": 4_000, "timeline_revision": 1},
}


class FakeTimelines:
    def timeline_for(self, sources):
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=10_000)


@pytest.fixture
def engine(mysql_schema_url):
    from daesingo.common.config import DbSettings
    from daesingo.common.db import create_worker_engine
    from daesingo.common.db.migrate import upgrade_all

    upgrade_all(mysql_schema_url)
    engine = create_worker_engine(
        DbSettings(url=mysql_schema_url.render_as_string(hide_password=False), pool_size=2, max_overflow=2)
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _store(conn) -> CaseStore:
    from daesingo.case.store_mysql import MySQLCaseRepository
    from daesingo.common.jobs.read_port import read_executions

    return CaseStore(repository=MySQLCaseRepository(), conn=conn, executions=read_executions)


class _CaseReflector:
    def __init__(self, reader):
        self.reader = reader

    def reflect(self, conn, incoming):
        from daesingo.common.jobs.reflection import ReflectionResult, RuntimeJobRecord

        outcome = ExecutionOutcome(
            execution_id=incoming.execution_id,
            job_id=incoming.job_id,
            case_id=incoming.case_id,
            kind=incoming.kind,
            attempt=incoming.attempt,
            status=incoming.terminal.status,
            produced=tuple(ref.model_dump() for ref in incoming.terminal.produced),
            failure_kind=incoming.terminal.failure_kind,
        )
        result = reflect_execution(outcome, store=_store(conn), reader=self.reader, timelines=FakeTimelines())
        jobs = tuple(RuntimeJobRecord(r["job_id"], r["case_id"], r["kind"]) for r in result.appended_job_records)
        return ReflectionResult(result.status, result.reason, jobs)


def _searching_case(engine) -> str:
    from daesingo.common.jobs.repository import enqueue

    with engine.begin() as conn:
        store = _store(conn)
        case_id = service.create_case(store=store)
        service.record_source_registered(
            case_id,
            {"source_asset_ref": "sa_0", "availability": "AVAILABLE", "duration_sec": 10.0},
            media_streams=[{"media_stream_ref": "ms_0", "media_type": "VIDEO"}],
            store=store,
        )
        request = {"case_id": case_id, "expected_case_rev": 1, "kind": "START_ANALYSIS", "payload": {"description": ""}}
        result = command.execute_command(request, store=store, timelines=FakeTimelines())
        enqueue(conn, result.appended_job_records, "trace_rf")
    return case_id


def _terminal(engine):
    from daesingo.common.jobs.execution import HandlerResult
    from daesingo.common.jobs.reflection import ReflectionInput
    from daesingo.common.jobs.repository import claim_one, finish
    from daesingo.common.job_execution import RuntimeContractRef

    claimed = claim_one(engine, "worker_rf")
    produced = (RuntimeContractRef(kind="analysis_run", ref="run_1"),)
    with engine.begin() as conn:
        assert finish(conn, claimed.execution_id, claimed.lease_owner, status="SUCCEEDED", produced=produced) == 1
    terminal = HandlerResult(status="SUCCEEDED", produced=produced)
    return ReflectionInput(claimed.execution_id, claimed.job_id, claimed.case_id, claimed.kind, claimed.attempt, terminal)


def test_t2_applies_case_and_marks_runtime_receipt_once(engine):
    from daesingo.common.jobs.reflection import reflect_terminal

    case_id = _searching_case(engine)
    incoming = _terminal(engine)
    reflector = _CaseReflector(lambda conn, kind, produced: {"outcome": "SUCCEEDED", "candidate_events": [EVENT]})

    with engine.begin() as conn:
        assert reflect_terminal(conn, incoming, reflector, "trace_rf").status == "APPLIED"
    with engine.begin() as conn:
        # 같은 execution 재전달 — case는 처리 기록으로 ALREADY_APPLIED, Runtime 표식과도 일치한다.
        assert reflect_terminal(conn, incoming, reflector, "trace_rf").status == "ALREADY_APPLIED"

    with engine.begin() as conn:
        view = service.get_view(case_id, store=_store(conn))
        case = _store(conn).get_case(case_id)
        applied = conn.exec_driver_sql(
            "SELECT case_applied_at FROM job_execution WHERE execution_id = %s", (incoming.execution_id,)
        ).scalar_one()
    assert view["stage"] == "CANDIDATE_REVIEW"
    assert view["running_jobs"] == []
    assert case.processed_executions == {incoming.execution_id: incoming.job_id}
    assert applied is not None


def test_t2_rollback_leaves_case_and_receipt_untouched(engine):
    from daesingo.common.jobs.reflection import reflect_terminal

    case_id = _searching_case(engine)
    incoming = _terminal(engine)
    reflector = _CaseReflector(lambda conn, kind, produced: {"outcome": "SUCCEEDED", "candidate_events": [EVENT]})

    with engine.connect() as conn:
        tx = conn.begin()
        assert reflect_terminal(conn, incoming, reflector, "trace_rf").status == "APPLIED"
        tx.rollback()

    with engine.begin() as conn:
        case = _store(conn).get_case(case_id)
        applied = conn.exec_driver_sql(
            "SELECT case_applied_at FROM job_execution WHERE execution_id = %s", (incoming.execution_id,)
        ).scalar_one()
    assert case.stage == "SEARCHING"
    assert case.processed_executions == {}
    assert applied is None
