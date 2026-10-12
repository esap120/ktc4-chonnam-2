"""MySQL 전용 — case가 Runtime의 실제 read port로 실행 상태를 읽는다(8-10, `decisions/jobexecution-read-port.md`).

`DAESINGO_MYSQL_URL`이 있을 때만 돈다. case · runtime 두 migration을 새 schema에 올리고, Runtime `enqueue` ·
`claim_one`이 남긴 행을 `CaseStore(executions=read_executions)`로 읽는다.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from daesingo.case import jobs, service  # noqa: E402
from daesingo.case.domain import CaseAggregate  # noqa: E402
from daesingo.case.store import CaseStore  # noqa: E402

pytestmark = pytest.mark.mysql


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


def _case_with_coarse(case_id: str) -> tuple[CaseAggregate, dict]:
    case = CaseAggregate.intake(case_id=case_id, hints={}, manifest_summary={})
    case.start_search()
    job = jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f")
    return case, job


def _statuses(view: dict) -> list[tuple[str, str]]:
    return [(j["job_id"], j["status"]) for j in view["running_jobs"]]


def test_view_follows_runtime_rows_from_queued_to_running(engine):
    from daesingo.common.jobs.repository import claim_one, enqueue

    case, job = _case_with_coarse("case_rp_mysql")
    with engine.begin() as conn:
        _store(conn).register(case)
        enqueue(conn, case.job_records, "trace_rp")

    with engine.begin() as conn:
        assert _statuses(service.get_view(case.case_id, store=_store(conn))) == [(job["job_id"], "PENDING")]

    assert claim_one(engine, "worker_rp") is not None

    with engine.begin() as conn:
        assert _statuses(service.get_view(case.case_id, store=_store(conn))) == [(job["job_id"], "RUNNING")]


def test_view_in_same_transaction_sees_uncommitted_enqueue(engine):
    """command 응답은 enqueue와 같은 tx에서 조립된다 — 그 tx의 `conn`으로 읽으므로 방금 넣은 행이 보인다."""
    from daesingo.common.jobs.repository import enqueue

    case, _ = _case_with_coarse("case_rp_tx")
    with engine.connect() as conn:
        tx = conn.begin()
        store = _store(conn)
        store.register(case)
        enqueue(conn, case.job_records, "trace_rp")
        execution_ids = [e["execution_id"] for e in store.read_executions(case)]
        assert len(execution_ids) == 1
        assert conn.in_transaction()
        tx.rollback()
