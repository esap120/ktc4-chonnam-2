"""Real queue/terminal acceptance. Events prove ordering, timeouts only bound hangs."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
from threading import Barrier, Event, Lock

import pytest
from sqlalchemy import event, select

from daesingo.common.config import DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.job_execution import JobExecution
from daesingo.common.jobs.read_port import read_executions
from daesingo.common.jobs.schema import job_execution

pytestmark = pytest.mark.mysql


@pytest.fixture
def queue(mysql_schema_url):
    upgrade_all(mysql_schema_url)
    engine = create_worker_engine(DbSettings(url=mysql_schema_url.render_as_string(hide_password=False),
                                             pool_size=8, max_overflow=0))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def repo():
    return import_module("daesingo.common.jobs.repository")


def seed(queue, count=1):
    from daesingo.common.jobs.repository import enqueue
    with queue.begin() as conn:
        return enqueue(conn, [{"job_id": f"job_{i}", "case_id": "case", "kind": "TEST"}
                              for i in range(count)], "trace")


def row(queue, execution_id):
    with queue.connect() as conn:
        return dict(conn.execute(select(job_execution).where(
            job_execution.c.execution_id == execution_id)).mappings().one())


@contextmanager
def listener(engine, name, callback):
    event.listen(engine, name, callback)
    try:
        yield
    finally:
        event.remove(engine, name, callback)


def terminal_args(status):
    return {"status": status, "failure_kind": "RUNTIME_TEST" if status == "FAILED" else None}


@pytest.mark.mysql_check("jobs", "claim_basic")
def test_claim_commits_one_row_with_db_lease_and_contract_snapshot(queue, repo):
    ids = seed(queue, 2)
    with queue.connect() as conn:
        before = conn.exec_driver_sql("SELECT NOW(6)").scalar_one()
    claimed = repo.claim_one(queue, "worker", lease_duration_sec=60)
    assert claimed.execution_id in ids
    stored = row(queue, claimed.execution_id)
    with queue.connect() as conn:
        after = conn.exec_driver_sql("SELECT NOW(6)").scalar_one()
        payload = read_executions(conn, [stored["job_id"]])[0]
    assert stored["status"] == "RUNNING" and stored["lease_owner"] == "worker"
    assert before <= stored["started_at"] <= after
    assert stored["heartbeat_at"] == stored["started_at"]
    assert stored["lease_expires_at"] - stored["started_at"] == timedelta(seconds=60)
    assert stored["claim_token"] and stored["ended_at"] is None
    assert (claimed.kind, claimed.case_id, claimed.trace_id, claimed.lease_owner) == ("TEST", "case", "trace", "worker")
    assert claimed.lease_expires_at.replace(tzinfo=None) == stored["lease_expires_at"]
    assert "claim_token" not in payload
    JobExecution.model_validate_json(__import__("json").dumps(payload))
    assert sum(row(queue, i)["status"] == "RUNNING" for i in ids) == 1


@pytest.mark.mysql_check("jobs", "claim_eligibility")
@pytest.mark.parametrize("offset,eligible", [
    pytest.param(-1, True, marks=pytest.mark.mysql_check("jobs", "claim_eligibility", parameter="past")),
    pytest.param(0, True, marks=pytest.mark.mysql_check("jobs", "claim_eligibility", parameter="equal")),
    pytest.param(1, False, marks=pytest.mark.mysql_check("jobs", "claim_eligibility", parameter="future")),
])
def test_db_now_eligibility_at_exact_boundary(queue, repo, offset, eligible):
    execution_id, = seed(queue)
    # Test-only frozen DB session clock, not an application clock or wall sleep.
    stamp = 1800000000
    with queue.begin() as conn:
        conn.exec_driver_sql("UPDATE job_execution SET queued_at=FROM_UNIXTIME(%s), available_at=FROM_UNIXTIME(%s)",
                             (stamp - 2, stamp + offset))
    def freeze(conn, *args):
        with conn.cursor() as cursor:
            cursor.execute(f"SET timestamp = {stamp}")
    with listener(queue, "checkout", freeze):
        result = repo.claim_one(queue, "worker")
    # Session SET timestamp survives rollback, reset every pooled connection.
    def unfreeze(conn, *args):
        with conn.cursor() as cursor:
            cursor.execute("SET timestamp = 0")
    with listener(queue, "checkout", unfreeze):
        assert (result is not None) is eligible
        assert row(queue, execution_id)["status"] == ("RUNNING" if eligible else "QUEUED")
    queue.dispose()


@pytest.mark.mysql_check("jobs", "claim_empty")
@pytest.mark.parametrize("locked", [
    pytest.param(False, marks=pytest.mark.mysql_check("jobs", "claim_empty", parameter="empty")),
    pytest.param(True, marks=pytest.mark.mysql_check("jobs", "claim_empty", parameter="all_locked")),
])
def test_empty_or_fully_locked_queue_returns_none(queue, repo, locked):
    if locked:
        seed(queue, 2)
    with queue.begin() as blocker:
        blocker.exec_driver_sql("SELECT execution_id FROM job_execution FOR UPDATE")
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(repo.claim_one, queue, "worker").result(timeout=15) is None


@pytest.mark.mysql_check("jobs", "claim_concurrent")
def test_concurrent_claim_ids_are_unique_and_queue_drains(queue, repo):
    ids = seed(queue, 24)
    barrier = Barrier(4, timeout=15)
    def participant(worker):
        barrier.wait()
        own = []
        while (claimed := repo.claim_one(queue, worker)) is not None:
            own.append(claimed.execution_id)
        return own
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(participant, f"worker_{i}") for i in range(4)]
        claimed = [item for f in futures for item in f.result(timeout=30)]
    assert len(claimed) == len(set(claimed)) == len(ids)
    assert set(claimed) == set(ids)
    assert all(row(queue, i)["status"] == "RUNNING" for i in ids)


@pytest.mark.mysql_check("jobs", "claim_skip_locked")
def test_locked_first_row_is_skipped_before_first_claim_commits(queue, repo):
    ids = seed(queue, 2)
    selected, release = Event(), Event()
    guard = Lock()
    held = []
    def pause(conn, cursor, statement, params, context, many):
        if "SKIP LOCKED" in statement.upper():
            with guard:
                first = not held
                if first:
                    held.append(conn)
            if first:
                selected.set()
                assert release.wait(15)
    with listener(queue, "after_cursor_execute", pause), ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(repo.claim_one, queue, "a")
        try:
            assert selected.wait(15)
            b = pool.submit(repo.claim_one, queue, "b").result(timeout=15)
            assert b is not None and not a.done()
            assert row(queue, b.execution_id)["status"] == "RUNNING"
        finally:
            release.set()
        assert {a.result(timeout=15).execution_id, b.execution_id} == set(ids)


@pytest.mark.mysql_check("jobs", "claim_commit_boundary")
@pytest.mark.mysql_check("jobs", "claim_no_insert")
def test_no_return_before_commit_no_insert_and_locks_release(queue, repo):
    execution_id, = seed(queue)
    committing, release = Event(), Event()
    statements = []
    def record(conn, cursor, sql, *args):
        statements.append(sql)
    def pause(conn):
        committing.set()
        assert release.wait(15)
    with listener(queue, "before_cursor_execute", record), listener(queue, "commit", pause):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(repo.claim_one, queue, "worker")
            try:
                assert committing.wait(15)
                assert not future.done()
                assert row(queue, execution_id)["status"] == "QUEUED"
            finally:
                release.set()
            assert future.result(timeout=15).execution_id == execution_id
    assert not any(sql.lstrip().upper().startswith("INSERT") for sql in statements)
    with queue.begin() as conn:
        assert conn.exec_driver_sql("SELECT status FROM job_execution WHERE execution_id=%s FOR UPDATE NOWAIT",
                                    (execution_id,)).scalar_one() == "RUNNING"


@pytest.mark.mysql_check("jobs", "claim_index")
def test_final_claim_select_uses_covering_ordered_index(queue, repo):
    seed(queue, 32)
    captured = []
    def record(conn, cursor, sql, params, *args):
        if "SKIP LOCKED" in sql.upper():
            captured.append((sql, params))
    with listener(queue, "before_cursor_execute", record):
        repo.claim_one(queue, "worker")
    sql, params = captured[0]
    assert "LIMIT 1" in sql.upper() and "FOR UPDATE SKIP LOCKED" in sql.upper()
    with queue.connect() as conn:
        plan = conn.exec_driver_sql("EXPLAIN " + sql, params).mappings().one()
    assert plan["key"] == "ix_job_execution_claim"
    assert "Using index" in plan["Extra"] and "filesort" not in plan["Extra"].lower()


@pytest.mark.mysql_check("jobs", "finish_targets")
@pytest.mark.parametrize("status", [pytest.param(s, marks=pytest.mark.mysql_check(
    "jobs", "finish_targets", parameter=s)) for s in ("SUCCEEDED", "FAILED", "CANCELLED")])
def test_finish_targets_follow_caller_commit_and_read_contract(queue, repo, status):
    execution_id, = seed(queue)
    repo.claim_one(queue, "worker")
    produced = [{"kind": "analysis_run", "ref": "run"}] if status == "SUCCEEDED" else []
    with queue.begin() as conn:
        assert repo.finish(conn, execution_id, "worker", produced=produced, **terminal_args(status)) == 1
        assert row(queue, execution_id)["status"] == "RUNNING"
    stored = row(queue, execution_id)
    assert stored["status"] == status and stored["ended_at"] >= stored["started_at"]
    with queue.connect() as conn:
        payload = read_executions(conn, [stored["job_id"]])[0]
    assert payload["produced"] == produced and "claim_token" not in payload
    JobExecution.model_validate_json(__import__("json").dumps(payload))


@pytest.mark.mysql_check("jobs", "finish_guard")
@pytest.mark.parametrize("state", [pytest.param(s, marks=pytest.mark.mysql_check(
    "jobs", "finish_guard", parameter=s)) for s in
    ("missing", "other_owner", "QUEUED", "SUCCEEDED", "FAILED", "CANCELLED", "STALE")])
def test_finish_non_running_missing_or_other_owner_is_zero(queue, repo, state):
    execution_id, = seed(queue)
    if state != "QUEUED":
        repo.claim_one(queue, "worker")
    if state in {"SUCCEEDED", "FAILED", "CANCELLED", "STALE"}:
        with queue.begin() as conn:
            conn.exec_driver_sql("UPDATE job_execution SET status=%s,ended_at=NOW(6),failure_kind=%s",
                                 (state, "RUNTIME_TEST" if state == "FAILED" else None))
    before = row(queue, execution_id)
    with queue.begin() as conn:
        assert repo.finish(conn, "missing" if state == "missing" else execution_id,
                           "other" if state == "other_owner" else "worker", status="SUCCEEDED") == 0
    assert row(queue, execution_id) == before


@pytest.mark.mysql_check("jobs", "finish_rollback")
def test_finish_does_not_end_or_retry_caller_transaction(queue, repo):
    execution_id, = seed(queue)
    repo.claim_one(queue, "worker")
    with queue.connect() as conn:
        tx = conn.begin()
        boundaries = []
        with listener(conn, "commit", lambda c: boundaries.append("commit")), listener(
                conn, "rollback", lambda c: boundaries.append("rollback")):
            assert repo.finish(conn, execution_id, "worker", status="SUCCEEDED") == 1
            assert conn.in_transaction() and not conn.closed and boundaries == []
        tx.rollback()
    assert row(queue, execution_id)["status"] == "RUNNING"


@pytest.mark.mysql_check("jobs", "finish_rejection")
@pytest.mark.parametrize("target", [pytest.param(s, marks=pytest.mark.mysql_check(
    "jobs", "finish_rejection", parameter=s)) for s in ("STALE", "QUEUED", "RUNNING", "UNKNOWN")])
def test_finish_rejects_non_worker_targets_without_write(queue, repo, target):
    execution_id, = seed(queue)
    repo.claim_one(queue, "worker")
    before = row(queue, execution_id)
    with queue.begin() as conn:
        with pytest.raises((ValueError, import_module("daesingo.common.job_execution").JobExecutionError)):
            repo.finish(conn, execution_id, "worker", status=target)
    assert row(queue, execution_id) == before


@pytest.mark.mysql_check("jobs", "finish_validation")
def test_finish_rejects_cancelled_produced_and_invalid_refs(queue, repo):
    execution_id, = seed(queue)
    repo.claim_one(queue, "worker")
    with queue.begin() as conn:
        for status, produced in [("CANCELLED", [{"kind": "analysis_run", "ref": "run"}]),
                                 ("SUCCEEDED", [{"kind": "", "ref": "run"}]),
                                 ("SUCCEEDED", [{"kind": "run", "ref": "a"}] * 2)]:
            with pytest.raises(ValueError):
                repo.finish(conn, execution_id, "worker", status=status, produced=produced)
    assert row(queue, execution_id)["status"] == "RUNNING"
