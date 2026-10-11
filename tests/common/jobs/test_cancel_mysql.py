"""Case-approved RT-05(b) locking races on real InnoDB READ COMMITTED.

RT-06 is not implemented: sweep_boundary models only its locked STALE marker
predicate and atomic attempt INSERT. It is test scaffolding, not a scheduler.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module, util
from threading import Barrier, Event
import time

import pytest
from sqlalchemy import event, func, insert, select, text, update

from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.repository import enqueue, claim_one, finish
from daesingo.common.jobs.schema import job_execution as jobs

pytestmark = pytest.mark.mysql


def cancel(conn, ids):
    assert util.find_spec("daesingo.common.jobs.cancel"), "RT-05(b) cancel port is missing"
    return import_module("daesingo.common.jobs.cancel").request_cancel(conn, ids)


@pytest.fixture
def queue(mysql_engine, mysql_schema_url):
    upgrade_all(mysql_schema_url)
    return mysql_engine


def add(engine, ids=("job",)):
    with engine.begin() as conn:
        return enqueue(conn, [{"job_id": job, "case_id": "case", "kind": "UNREGISTERED"}
                              for job in ids], "trace")


def rows(engine):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(jobs).order_by(
            jobs.c.job_id, jobs.c.attempt, jobs.c.execution_id)).mappings()]


def assert_lock_wait(engine, connection_id):
    """Prove this contender is blocked on this test's schema, not a timer."""
    deadline = time.monotonic() + 5
    with engine.connect() as control:
        while time.monotonic() < deadline:
            waiting = control.scalar(text("""SELECT COUNT(*)
                FROM performance_schema.data_lock_waits w
                JOIN performance_schema.threads t ON t.THREAD_ID = w.REQUESTING_THREAD_ID
                JOIN performance_schema.data_locks l
                  ON l.ENGINE = w.ENGINE AND l.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
                WHERE t.PROCESSLIST_ID = :connection_id AND l.OBJECT_SCHEMA = DATABASE()"""),
                {"connection_id": connection_id})
            if waiting:
                return
            Event().wait(0.005)
    pytest.fail("contender never entered a MySQL row lock wait")


def sweep_boundary(conn, execution_id):
    row = dict(conn.execute(select(jobs).where(jobs.c.execution_id == execution_id)
                            .with_for_update()).mappings().one())
    if row["status"] != "STALE" or row["cancel_requested_at"] is not None:
        return False
    row.update(execution_id="attempt2_" + execution_id, attempt=2, status="QUEUED",
               available_at=conn.scalar(select(func.now(6))) + timedelta(seconds=5),
               started_at=None, ended_at=None, lease_owner=None, lease_expires_at=None,
               heartbeat_at=None, claim_token=None)
    conn.execute(insert(jobs).values(row))
    return True


@pytest.mark.mysql_check("cancel", "states")
@pytest.mark.parametrize("state", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel", "states", parameter=s)) for s in
    ("QUEUED", "RUNNING", "STALE", "SUCCEEDED", "FAILED", "CANCELLED")])
def test_all_states_first_marker_terminal_noop_and_usage_zero(queue, state):
    execution, = add(queue)
    with queue.begin() as conn:
        conn.execute(update(jobs).values(status=state))
    before = rows(queue)[0]
    with queue.begin() as conn:
        now = conn.scalar(select(func.now(6)))
        assert cancel(conn, ["missing", "job", "job"]) is None
        after = dict(conn.execute(select(jobs)).mappings().one())
        end = conn.scalar(select(func.now(6)))
    if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
        assert after == before
    else:
        assert now <= after["cancel_requested_at"] <= end
        assert after["status"] == ("CANCELLED" if state == "QUEUED" else state)
        if state == "QUEUED":
            assert after["ended_at"] == after["cancel_requested_at"] and after["produced"] == []
            assert claim_one(queue, "owner") is None
        else:
            assert after["ended_at"] is None
        with queue.begin() as conn:
            cancel(conn, ["job"])
        assert rows(queue)[0] == after
    # RT-07 ledger is not implemented. QUEUED cancellation cannot be claimed,
    # so no handler/provider invocation or UsageRecord production can occur.
    if state == "QUEUED":
        assert rows(queue)[0]["started_at"] is None


@pytest.mark.mysql_check("cancel", "validation")
def test_invalid_later_id_writes_nothing_even_when_caller_commits(queue):
    add(queue)
    with queue.begin() as conn:
        with pytest.raises(ValueError, match="invalid cancel job_ids"):
            cancel(conn, ["job", None])
    assert rows(queue)[0]["status"] == "QUEUED"
    assert rows(queue)[0]["cancel_requested_at"] is None


@pytest.mark.mysql_check("cancel", "transaction")
@pytest.mark.parametrize("outcome", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel", "transaction", parameter=s)) for s in ("commit", "rollback")])
def test_case_marker_and_runtime_same_connection_atomicity(queue, outcome):
    from daesingo.case.domain import CaseAggregate
    from daesingo.case.jobs import issue_job
    from daesingo.case.store_mysql import MySQLCaseRepository
    repo = MySQLCaseRepository()
    case = CaseAggregate.empty("case")
    job = issue_job(case, "COARSE_SEARCH", input_fingerprint="test")
    with queue.begin() as conn:
        repo.insert(conn, case)
        enqueue(conn, [job], "trace")
    with queue.connect() as conn:
        tx = conn.begin()
        case = repo.load(conn, "case", lock="update")
        assert case.settle_job(job["job_id"], "CANCELLED")
        repo.save(conn, case)
        cancel(conn, [job["job_id"]])
        assert conn.in_transaction()
        getattr(tx, outcome)()
    with queue.connect() as conn:
        case = repo.load(conn, "case")
        assert (case.settled_jobs.get(job["job_id"]) == "CANCELLED") == (outcome == "commit")
    assert rows(queue)[0]["status"] == ("CANCELLED" if outcome == "commit" else "QUEUED")


@pytest.mark.mysql_check("cancel", "claim_race")
@pytest.mark.parametrize("first", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel", "claim_race", parameter=s)) for s in ("cancel", "claim", "concurrent")])
def test_claim_cancel_race_cannot_miss(queue, first):
    execution, = add(queue)
    if first == "cancel":
        with queue.begin() as conn:
            cancel(conn, ["job"])
            with ThreadPoolExecutor() as pool:
                assert pool.submit(claim_one, queue, "owner").result(10) is None
    elif first == "claim":
        locked, release, cancelling = Event(), Event(), Event()
        contender = []
        def hold_claim(conn):
            if not locked.is_set():
                locked.set()
                assert release.wait(10)
        event.listen(queue, "commit", hold_claim)
        def request():
            with queue.begin() as conn:
                contender.append(conn.connection.driver_connection.thread_id())
                cancelling.set()
                cancel(conn, ["job"])
        with ThreadPoolExecutor() as pool:
            claimant = pool.submit(claim_one, queue, "owner")
            assert locked.wait(10)
            cancellation = pool.submit(request)
            assert cancelling.wait(10)
            try:
                assert_lock_wait(queue, contender[0])
            finally:
                release.set()
            assert claimant.result(10).execution_id == execution
            cancellation.result(10)
        event.remove(queue, "commit", hold_claim)
    else:
        barrier = Barrier(2)
        def request():
            barrier.wait(10)
            with queue.begin() as conn:
                cancel(conn, ["job"])
        def claim():
            barrier.wait(10)
            return claim_one(queue, "owner")
        with ThreadPoolExecutor() as pool:
            a, b = pool.submit(request), pool.submit(claim)
            a.result(10)
            b.result(10)
    row = rows(queue)[0]
    assert row["status"] in ("CANCELLED", "RUNNING") and row["cancel_requested_at"] is not None


@pytest.mark.mysql_check("cancel", "sweep_race")
@pytest.mark.parametrize("first", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel", "sweep_race", parameter=s)) for s in ("sweep", "cancel")])
def test_sweep_future_attempt_and_cancel_locked_stale(queue, first):
    execution, = add(queue)
    with queue.begin() as conn:
        conn.execute(update(jobs).values(status="STALE"))
    waiting = Event()
    if first == "sweep":
        with queue.begin() as conn:
            assert sweep_boundary(conn, execution)
        with queue.begin() as conn:
            cancel(conn, ["job"])
        stored = rows(queue)
        assert len(stored) == 2 and stored[1]["status"] == "CANCELLED"
        assert stored[1]["available_at"] > stored[1]["ended_at"]
    else:
        contender = []
        def sweep():
            with queue.begin() as conn:
                contender.append(conn.connection.driver_connection.thread_id())
                waiting.set()
                return sweep_boundary(conn, execution)
        with ThreadPoolExecutor() as pool:
            with queue.begin() as conn:
                cancel(conn, ["job"])
                future = pool.submit(sweep)
                assert waiting.wait(10)
                assert_lock_wait(queue, contender[0])
            assert future.result(10) is False
        assert len(rows(queue)) == 1
    assert rows(queue)[0]["cancel_requested_at"] is not None


@pytest.mark.mysql_check("cancel", "sweep_pending")
def test_cancel_waiting_on_uncommitted_sweep_sees_inserted_attempt(queue):
    execution, = add(queue)
    with queue.begin() as conn:
        conn.execute(update(jobs).values(status="STALE"))
    entered = Event()
    contender = []
    def request():
        with queue.begin() as conn:
            contender.append(conn.connection.driver_connection.thread_id())
            entered.set()
            cancel(conn, ["job"])
    with ThreadPoolExecutor() as pool:
        with queue.begin() as conn:
            assert sweep_boundary(conn, execution)
            future = pool.submit(request)
            assert entered.wait(10)
            assert_lock_wait(queue, contender[0])
        future.result(10)
    assert [row["status"] for row in rows(queue)] == ["STALE", "CANCELLED"]


@pytest.mark.mysql_check("cancel", "finish_race")
@pytest.mark.parametrize("first", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel", "finish_race", parameter=s)) for s in ("SUCCEEDED", "CANCELLED", "marker")])
def test_finish_first_terminal_commit_wins(queue, first):
    execution, = add(queue)
    claim_one(queue, "owner")
    if first == "marker":
        with queue.begin() as conn:
            cancel(conn, ["job"])
        with queue.begin() as conn:
            assert finish(conn, execution, "owner", status="SUCCEEDED") == 1
        assert rows(queue)[0]["status"] == "SUCCEEDED"
        return
    waiting = Event()
    contender = []
    other = "CANCELLED" if first == "SUCCEEDED" else "SUCCEEDED"
    def late():
        with queue.begin() as conn:
            contender.append(conn.connection.driver_connection.thread_id())
            waiting.set()
            return finish(conn, execution, "owner", status=other)
    with ThreadPoolExecutor() as pool:
        with queue.begin() as conn:
            if first == "CANCELLED":
                cancel(conn, ["job"])
            assert finish(conn, execution, "owner", status=first) == 1
            future = pool.submit(late)
            assert waiting.wait(10)
            assert_lock_wait(queue, contender[0])
        assert future.result(10) == 0
    with queue.begin() as conn:
        cancel(conn, ["job"])
    assert rows(queue)[0]["status"] == first


@pytest.mark.mysql_check("cancel", "lock_order")
def test_multiple_jobs_attempts_opposite_input_order_no_deadlock(queue):
    ids = add(queue, ("b", "a", "c"))
    with queue.begin() as conn:
        conn.execute(update(jobs).values(status="STALE"))
        for execution in ids:
            assert sweep_boundary(conn, execution)
        plan = conn.execute(text("EXPLAIN SELECT execution_id, status FROM job_execution "
            "FORCE INDEX (uq_job_execution_job_attempt) WHERE job_id='a' "
            "ORDER BY job_id, attempt, execution_id FOR UPDATE")).mappings().one()
        assert plan["key"] == "uq_job_execution_job_attempt"
        assert "filesort" not in (plan["Extra"] or "").lower()
    barrier, statements = Barrier(2), []
    def before(conn, cursor, statement, parameters, context, many):
        if "FOR UPDATE" in statement:
            statements.append((statement, parameters))
    event.listen(queue, "before_cursor_execute", before)
    def request(order):
        barrier.wait(10)
        with queue.begin() as conn:
            cancel(conn, order)
    try:
        with ThreadPoolExecutor() as pool:
            a = pool.submit(request, ["c", "b", "a", "a"])
            b = pool.submit(request, ["a", "b", "c"])
            a.result(10)
            b.result(10)
    finally:
        event.remove(queue, "before_cursor_execute", before)
    assert len(rows(queue)) == 6
    assert all(row["cancel_requested_at"] is not None for row in rows(queue))
    assert [r["status"] for r in rows(queue)] == ["STALE", "CANCELLED"] * 3
    assert statements and all("uq_job_execution_job_attempt" in s and
        "ORDER BY job_id, attempt, execution_id" in s for s, _ in statements)
