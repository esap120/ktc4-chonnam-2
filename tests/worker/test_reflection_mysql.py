"""T2 uses real Case-fake rows, InnoDB, connection kills and COMMIT packets."""

from io import StringIO
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, Event
import time

import pytest
import sqlalchemy as sa

from daesingo.common.config import DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.read_port import read_executions
from daesingo.common.jobs.reflection import ReflectionResult, RuntimeJobRecord
from daesingo.common.jobs.repository import enqueue
from daesingo.common.jobs.schema import job_execution
from logging_faults import install_logging_fault
from mysql_fault_proxy import CommitResponseProxy
from test_worker_mysql import queue, row, seed, composed

pytestmark = pytest.mark.mysql
OUTCOMES = ("APPLIED", "ALREADY_APPLIED", "STOPPED_WAITING", "CANCELLED", "SUPERSEDED")
ROLLBACKS = ("reflector", "enqueue", "extra", "tampered_reason", "non_applied_jobs", "cross_case", "commit", "rollback")
METRICS = ("first_stopped", "retry_stopped", "third_stopped", "cancelled", "superseded", "already", "applied", "exception")
SINKS = tuple(mode + "_" + sink for mode in ("metric", "failure", "db_retry") for sink in ("filter", "handler"))
metadata = sa.MetaData()
case = sa.Table("rt04b_case", metadata, sa.Column("case_id", sa.String(128), primary_key=True),
                sa.Column("applied", sa.Integer, nullable=False))
receipt = sa.Table("rt04b_receipt", metadata, sa.Column("execution_id", sa.String(128), primary_key=True))


@pytest.fixture
def fake_case(queue):
    with queue.begin() as conn:
        metadata.create_all(conn)
        conn.execute(case.insert().values(case_id="case", applied=0))
    return queue


class FakeReflector:
    """Test-only persistence; actual Case 8-8 need not use this schema/shape."""
    def __init__(self, engine, outcome="APPLIED", *, jobs=(), fault=None):
        self.engine, self.outcome, self.jobs, self.fault = engine, outcome, jobs, fault
        self.calls, self.applied = [], 0

    def reflect(self, conn, incoming):
        self.calls.append((conn, conn.get_transaction(), incoming))
        assert conn.in_transaction()
        conn.execute(sa.select(case).where(case.c.case_id == incoming.case_id).with_for_update()).one()
        # Another connection sees durable T1 while this Case lock is held.
        with self.engine.connect() as observer:
            stored = observer.execute(sa.select(job_execution).where(
                job_execution.c.execution_id == incoming.execution_id)).mappings().one_or_none()
        if stored is not None:
            assert stored["status"] == incoming.terminal.status and stored["ended_at"] is not None
        if conn.scalar(sa.select(receipt.c.execution_id).where(receipt.c.execution_id == incoming.execution_id)):
            return ReflectionResult("ALREADY_APPLIED")
        if self.outcome == "APPLIED" or self.fault:
            conn.execute(case.update().where(case.c.case_id == incoming.case_id).values(applied=case.c.applied + 1))
        conn.execute(receipt.insert().values(execution_id=incoming.execution_id))
        if self.fault == "reflector":
            raise RuntimeError("secret /private/path SQL provider/user payload claim_token")
        if self.fault == "commit":
            conn.commit()
        if self.fault == "rollback":
            conn.rollback()
        if self.fault == "extra":
            return {"status": "APPLIED", "claim_token": "secret /private/payload"}
        if self.fault in ("tampered_reason", "non_applied_jobs"):
            value = ReflectionResult("NOT_APPLIED", "STOPPED_WAITING")
            object.__setattr__(value, "reason" if self.fault == "tampered_reason" else "jobs",
                               "secret /private/payload" if self.fault == "tampered_reason" else self.jobs)
            return value
        if self.outcome == "APPLIED":
            return ReflectionResult("APPLIED", jobs=self.jobs)
        if self.outcome == "ALREADY_APPLIED":
            return ReflectionResult("ALREADY_APPLIED")
        return ReflectionResult("NOT_APPLIED", self.outcome)


def worker(engine, reflector, *, terminal=None, stream=None, sleep=None, stop=None, idle_wait=None):
    value = terminal if terminal is not None else HandlerResult(produced=[{"kind": "Candidates", "ref": "cand_1"}])
    stop = stop if stop is not None else Event()
    def handler(ctx):
        assert engine.pool.checkedout() == 0
        stop.set()
        return value
    return composed(engine, {"TEST": handler}, stop=stop, stream=stream, sleep=sleep,
                    reflector=reflector, idle_wait=idle_wait or stop.wait)


def case_state(engine):
    with engine.connect() as conn:
        return conn.scalar(sa.select(case.c.applied)), conn.scalar(sa.select(sa.func.count()).select_from(receipt))


@pytest.mark.mysql_check("worker_t2", "delivery")
@pytest.mark.parametrize("outcome", [pytest.param(outcome, marks=[
    pytest.mark.mysql_check("worker_t2", "delivery", parameter=outcome),
    *([pytest.mark.mysql_check("worker_t2", "e2e0")] if outcome == "APPLIED" else []),
]) for outcome in OUTCOMES])
def test_delivery_outcomes_and_e2e0_are_one_atomic_commit(fake_case, outcome):
    engine = fake_case
    execution_id, = seed(engine)
    jobs = (RuntimeJobRecord("follow", "case", "FOLLOW"),) if outcome == "APPLIED" else ()
    reflector = FakeReflector(engine, outcome, jobs=jobs)
    statements = []
    def observe(conn, cursor, sql, *args):
        if reflector.calls and conn is reflector.calls[-1][0]:
            assert conn.get_transaction() is reflector.calls[-1][1]
            statements.append(sql.upper())
    sa.event.listen(engine, "before_cursor_execute", observe)
    try:
        worker(engine, reflector).run()
    finally:
        sa.event.remove(engine, "before_cursor_execute", observe)
    stored = row(engine, execution_id)
    assert stored["status"] == "SUCCEEDED" and stored["case_applied_at"] is not None
    assert len(reflector.calls) == 1 and case_state(engine) == (int(outcome == "APPLIED"), 1)
    with engine.connect() as conn:
        snapshots = read_executions(conn, ["job_0", "follow"])
    statuses = {snapshot["job_id"]: snapshot["status"] for snapshot in snapshots}
    assert statuses["job_0"] == "SUCCEEDED"
    if outcome == "APPLIED":
        assert statuses["follow"] == "QUEUED"
    assert len(snapshots) == (2 if outcome == "APPLIED" else 1)
    locks = [sql for sql in statements if "FOR UPDATE" in sql]
    assert "RT04B_CASE" in locks[0] and "JOB_EXECUTION" in locks[1]
    assert any("UPDATE JOB_EXECUTION" in sql for sql in statements)


@pytest.mark.mysql_check("worker_t2", "rollback")
@pytest.mark.parametrize("fault", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_t2", "rollback", parameter=s)) for s in ROLLBACKS])
def test_t2_failure_rolls_back_case_followup_and_marker(fake_case, fault):
    engine, stream = fake_case, StringIO()
    execution_id, = seed(engine)
    if fault == "enqueue":
        with engine.begin() as conn:
            enqueue(conn, [{"job_id": "follow", "case_id": "case", "kind": "FOLLOW"}], "trace")
    jobs = (RuntimeJobRecord("follow", "other" if fault == "cross_case" else "case", "FOLLOW"),)
    reflector = FakeReflector(engine, jobs=jobs, fault=fault)
    worker(engine, reflector, stream=stream).run()
    stored = row(engine, execution_id)
    assert len(reflector.calls) == 1
    assert stored["status"] == "SUCCEEDED" and stored["case_applied_at"] is None
    assert stored["produced"] == [{"kind": "Candidates", "ref": "cand_1"}] and case_state(engine) == (0, 0)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution)) == (2 if fault == "enqueue" else 1)
    assert "runtime.reflect.failed" in stream.getvalue()
    assert all(word not in stream.getvalue() for word in ("secret", "private", "payload", "claim_token", "INSERT INTO"))


@pytest.mark.mysql_check("worker_t2", "t1_gap")
@pytest.mark.parametrize("status", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_t2", "t1_gap", parameter=s)) for s in ("SUCCEEDED", "FAILED")])
def test_t1_remains_terminal_when_t2_fails_before_reflection(fake_case, status):
    execution_id, = seed(fake_case)
    reflector = FakeReflector(fake_case, fault="reflector")
    terminal = HandlerResult(status=status, failure_kind="SEARCH_FAILURE" if status == "FAILED" else None)
    worker(fake_case, reflector, terminal=terminal).run()
    stored = row(fake_case, execution_id)
    assert len(reflector.calls) == 1 and stored["status"] == status
    assert stored["failure_kind"] == terminal.failure_kind and stored["case_applied_at"] is None


@pytest.mark.mysql_check("worker_t2", "commit_recovery")
@pytest.mark.parametrize("outcome", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_t2", "commit_recovery", parameter=s)) for s in ("APPLIED", "STOPPED_WAITING")])
def test_lost_t2_commit_replays_case_idempotently_without_duplicate_execution(fake_case, outcome):
    execution_id, = seed(fake_case)
    waits, stream = [], StringIO()
    with CommitResponseProxy(fake_case.url.host, fake_case.url.port) as proxy:
        url = fake_case.url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        engine = create_worker_engine(DbSettings(url=url.render_as_string(hide_password=False)))
        reflector = FakeReflector(fake_case, outcome, jobs=(RuntimeJobRecord("follow", "case", "FOLLOW"),) if outcome == "APPLIED" else ())
        def arm(conn, cursor, sql, *args):
            if sql.upper().startswith("UPDATE JOB_EXECUTION SET CASE_APPLIED_AT"):
                proxy.arm()
        sa.event.listen(engine, "after_cursor_execute", arm)
        try:
            worker(engine, reflector, stream=stream, sleep=waits.append).run()
            assert proxy.commit_ok_dropped == 1 and waits == [1]
        finally:
            sa.event.remove(engine, "after_cursor_execute", arm)
            engine.dispose()
    assert row(fake_case, execution_id)["case_applied_at"] is not None
    assert len(reflector.calls) == 2 and case_state(fake_case) == (int(outcome == "APPLIED"), 1)
    with fake_case.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution)) == (2 if outcome == "APPLIED" else 1)
    assert "runtime.reflect.failed" not in stream.getvalue()


@pytest.mark.mysql_check("worker_t2", "metric")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_t2", "metric", parameter=s)) for s in METRICS])
def test_after_case_stopped_metric_includes_only_committed_retry_stopped(fake_case, mode):
    execution_id, = seed(fake_case)
    attempt = 1 if mode == "first_stopped" else 3 if mode == "third_stopped" else 2
    outcome = {"cancelled": "CANCELLED", "superseded": "SUPERSEDED", "already": "ALREADY_APPLIED", "applied": "APPLIED"}.get(mode, "STOPPED_WAITING")
    with fake_case.begin() as conn:
        conn.execute(job_execution.update().where(job_execution.c.execution_id == execution_id).values(attempt=attempt))
    stream = StringIO()
    reflector = FakeReflector(fake_case, outcome, fault="reflector" if mode == "exception" else None)
    worker(fake_case, reflector, stream=stream).run()
    assert len(reflector.calls) == 1
    assert (row(fake_case, execution_id)["case_applied_at"] is not None) == (mode != "exception")
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    counts = [event for event in events if event["event"] == "runtime.retry.after_case_stopped_count"]
    assert len(counts) == int(mode in ("retry_stopped", "third_stopped"))
    if counts:
        assert [counts[0][key] for key in ("trace_id", "case_id", "job_id", "execution_id")] == ["trace", "case", "job_0", execution_id]


@pytest.mark.mysql_check("worker_t2", "zero_guard")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_t2", "zero_guard", parameter=s)) for s in ("missing", "mismatch", "zero", "already", "insert_then_marker_failure")])
def test_terminal_marker_zero_or_mismatch_requires_durable_confirmation(fake_case, mode):
    execution_id, = seed(fake_case)
    reflector = FakeReflector(fake_case)
    current = worker(fake_case, reflector)
    current.run()
    assert callable(current.reflect) and len(reflector.calls) == 1
    context = reflector.calls[0][2]
    from daesingo.common.jobs.execution import ExecutionContext
    ctx = ExecutionContext(context.execution_id, context.job_id, context.case_id, context.kind, context.attempt, "trace")
    if mode == "already":
        assert current.reflect(ctx, context.terminal).status == "ALREADY_APPLIED"
        assert case_state(fake_case) == (1, 1)
        return
    with fake_case.begin() as conn:
        conn.execute(receipt.delete())
        conn.execute(case.update().values(applied=0))
        conn.execute(job_execution.update().where(job_execution.c.execution_id == execution_id).values(case_applied_at=None))
        if mode == "missing":
            conn.execute(job_execution.delete().where(job_execution.c.execution_id == execution_id))
        elif mode == "mismatch":
            conn.execute(job_execution.update().where(job_execution.c.execution_id == execution_id).values(failure_kind="secret"))
    inserted = []
    if mode == "insert_then_marker_failure":
        reflector.jobs = (RuntimeJobRecord("follow", "case", "FOLLOW"),)
    if mode in ("zero", "insert_then_marker_failure"):
        def no_update(conn, cursor, sql, parameters, context, many):
            if sql.upper().startswith("UPDATE JOB_EXECUTION SET CASE_APPLIED_AT"):
                if mode == "insert_then_marker_failure":
                    assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution).where(
                        job_execution.c.job_id == "follow")) == 1
                    inserted.append(True)
                return sql + " AND 1=0", parameters
            return sql, parameters
        sa.event.listen(fake_case, "before_cursor_execute", no_update, retval=True)
    try:
        with pytest.raises(ValueError) as error:
            current.reflect(ctx, context.terminal)
        assert "secret" not in str(error.value)
    finally:
        if mode in ("zero", "insert_then_marker_failure"):
            sa.event.remove(fake_case, "before_cursor_execute", no_update)
    assert case_state(fake_case) == (0, 0)
    if mode == "insert_then_marker_failure":
        assert inserted == [True] and row(fake_case, execution_id)["case_applied_at"] is None
        with fake_case.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution).where(
                job_execution.c.job_id == "follow")) == 0


@pytest.mark.mysql_check("worker_t2", "sink_isolation")
@pytest.mark.parametrize("mode,sink", [pytest.param(*entry.rsplit("_", 1),
    marks=pytest.mark.mysql_check("worker_t2", "sink_isolation", parameter=entry)) for entry in SINKS])
def test_logger_and_observer_do_not_change_t2_result_or_retry(fake_case, mode, sink, monkeypatch, capsys):
    from daesingo.worker import composition
    execution_id, = seed(fake_case)
    observed, waits, kills = [], [], []
    original = composition.run_worker_transaction
    def observer(attempt):
        observed.append(attempt.outcome)
        raise sa.exc.OperationalError("private SQL", {}, Exception(1213, "secret observer"))
    def transaction(engine, operation, **kwargs):
        return original(engine, operation, **kwargs, observe=observer)
    monkeypatch.setattr(composition, "run_worker_transaction", transaction)
    with fake_case.begin() as conn:
        conn.execute(job_execution.update().values(attempt=2))
    reflector = FakeReflector(fake_case, "STOPPED_WAITING" if mode == "metric" else "APPLIED", fault="reflector" if mode == "failure" else None)
    current = worker(fake_case, reflector, sleep=waits.append)
    name = "runtime.retry.after_case_stopped_count" if mode == "metric" else "runtime.reflect.failed"
    seen, remove = install_logging_fault(current.logger, sink,
                                         lambda event: event.startswith("runtime.db.") if mode == "db_retry" else event == name)
    def kill(conn, cursor, sql, *args):
        if mode == "db_retry" and sql.upper().startswith("UPDATE RT04B_CASE") and not kills:
            identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with fake_case.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
            kills.append(identity)
    sa.event.listen(fake_case, "before_cursor_execute", kill)
    try:
        current.run()
    finally:
        remove()
        sa.event.remove(fake_case, "before_cursor_execute", kill)
    assert seen and len(reflector.calls) == (2 if mode == "db_retry" else 1)
    stored = row(fake_case, execution_id)
    assert stored["status"] == "SUCCEEDED" and (stored["case_applied_at"] is not None) == (mode != "failure")
    assert waits == ([1] if mode == "db_retry" else [])
    assert observed == (["COMMITTED", "DISCONNECT", "COMMITTED"] if mode == "db_retry" else ["COMMITTED", "FAILED"] if mode == "failure" else ["COMMITTED", "COMMITTED"])
    assert capsys.readouterr().err == ""


@pytest.mark.mysql_check("worker_t2", "recovery")
@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.mysql_check(
    "worker_t2", "recovery", parameter=mode)) for mode in ("exhausted", "next_job", "concurrent")])
def test_t2_exhaustion_continuation_and_concurrent_delivery(fake_case, mode):
    waits, stream = [], StringIO()
    ids = seed(fake_case, ("TEST", "TEST") if mode == "next_job" else ("TEST",))
    reflector = FakeReflector(fake_case)
    if mode == "exhausted":
        def kill(conn, cursor, sql, *args):
            if sql.upper().startswith("UPDATE RT04B_CASE"):
                identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
                with fake_case.connect() as control:
                    control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
        sa.event.listen(fake_case, "before_cursor_execute", kill)
        try:
            worker(fake_case, reflector, sleep=waits.append, idle_wait=waits.append, stream=stream).run()
        finally:
            sa.event.remove(fake_case, "before_cursor_execute", kill)
        assert len(reflector.calls) == 3 and waits == [1, 1, 5]
        assert case_state(fake_case) == (0, 0)
        assert row(fake_case, ids[0])["status"] == "SUCCEEDED"
        assert row(fake_case, ids[0])["case_applied_at"] is None
        assert "runtime.db.tx_retry_exhausted_count" in stream.getvalue() and "runtime.reflect.failed" in stream.getvalue()
    elif mode == "next_job":
        original = reflector.reflect
        def fail_once(conn, incoming):
            reflector.fault = "reflector" if not reflector.calls else None
            return original(conn, incoming)
        reflector.reflect = fail_once
        composed(fake_case, {"TEST": lambda ctx: HandlerResult()}, reflector=reflector,
                 sleep=waits.append, stream=stream).run()
        assert len(reflector.calls) == 2 and waits == []
        assert all(row(fake_case, identity)["status"] == "SUCCEEDED" for identity in ids)
        assert [row(fake_case, call[2].execution_id)["case_applied_at"] is not None
                for call in reflector.calls] == [False, True]
        assert case_state(fake_case) == (1, 1)
    else:
        current = worker(fake_case, reflector)
        current.run()
        incoming = reflector.calls[0][2]
        from daesingo.common.jobs.execution import ExecutionContext
        context = ExecutionContext(incoming.execution_id, incoming.job_id, incoming.case_id,
                                   incoming.kind, incoming.attempt, "trace")
        with fake_case.begin() as conn:
            conn.execute(receipt.delete())
            conn.execute(case.update().values(applied=0))
            conn.execute(job_execution.update().values(case_applied_at=None))
        reflector.jobs = (RuntimeJobRecord("follow", "case", "FOLLOW"),)
        arrived = Barrier(3, timeout=10)
        def before_case_lock(conn, cursor, sql, *args):
            if "FROM RT04B_CASE" in sql.upper() and "FOR UPDATE" in sql.upper():
                arrived.wait()
        # Force both deliveries to wait on an external Case lock, rather than
        # relying on the scheduler to overlap two fast transactions.
        with fake_case.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(sa.select(case).with_for_update()).one()
            sa.event.listen(fake_case, "before_cursor_execute", before_case_lock)
            with ThreadPoolExecutor(max_workers=2) as threads:
                futures = [threads.submit(current.reflect, context, incoming.terminal) for _ in range(2)]
                try:
                    arrived.wait()
                    deadline = time.monotonic() + 10
                    with fake_case.connect() as observer:
                        while True:
                            waiting = observer.exec_driver_sql("""
                                SELECT COUNT(DISTINCT w.REQUESTING_THREAD_ID) FROM performance_schema.data_lock_waits w
                                JOIN performance_schema.data_locks l
                                  ON l.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
                                WHERE l.OBJECT_SCHEMA = DATABASE() AND l.OBJECT_NAME = 'rt04b_case'
                            """).scalar_one()
                            if waiting == 2:
                                break
                            assert time.monotonic() < deadline, f"Case lock waiting thread count: {waiting}"
                            time.sleep(0.01)
                finally:
                    transaction.rollback()
                    sa.event.remove(fake_case, "before_cursor_execute", before_case_lock)
                assert sorted(future.result(timeout=20).status for future in futures) == ["ALREADY_APPLIED", "APPLIED"]
        assert case_state(fake_case) == (1, 1) and row(fake_case, ids[0])["case_applied_at"] is not None
        with fake_case.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution)) == 2


@pytest.mark.mysql_check("worker_t2", "recovery", parameter="exhausted_next_job")
def test_exhausted_t2_waits_before_next_job_and_rolls_back_inserted_followup(fake_case):
    ids = seed(fake_case, ("TEST", "TEST"))
    stop, waits, handled, kills, inserted, at_second, stream = Event(), [], [], [], [], [], StringIO()
    terminal = HandlerResult(produced=[{"kind": "Candidates", "ref": "cand_1"}])
    reflector = FakeReflector(fake_case)
    original = reflector.reflect
    def reflect(conn, incoming):
        reflector.jobs = (RuntimeJobRecord("follow", "case", "FOLLOW"),) if incoming.execution_id == handled[0] else ()
        return original(conn, incoming)
    reflector.reflect = reflect
    def handler(ctx):
        assert fake_case.pool.checkedout() == 0
        handled.append(ctx.execution_id)
        if len(handled) == 2:
            at_second.extend(waits)
            stop.set()
        return terminal
    def kill(conn, cursor, sql, *args):
        if sql.upper().startswith("UPDATE JOB_EXECUTION SET CASE_APPLIED_AT") and len(kills) < 3:
            assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution).where(
                job_execution.c.job_id == "follow")) == 1
            inserted.append(True)
            identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with fake_case.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
            kills.append(identity)
    def idle(seconds):
        assert seconds == 5 and handled == [handled[0]]
        waits.append(seconds)
        first = row(fake_case, handled[0])
        assert first["status"] == "SUCCEEDED" and first["produced"] == terminal.model_dump(mode="json")["produced"]
        assert first["case_applied_at"] is None and case_state(fake_case) == (0, 0)
        with fake_case.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution)) == 2
    sa.event.listen(fake_case, "before_cursor_execute", kill)
    try:
        composed(fake_case, {"TEST": handler}, reflector=reflector, stop=stop,
                 sleep=waits.append, idle_wait=idle, stream=stream).run()
    finally:
        sa.event.remove(fake_case, "before_cursor_execute", kill)
    assert set(handled) == set(ids) and waits == [1, 1, 5]
    assert at_second == [1, 1, 5]
    assert len(kills) == len(inserted) == 3 and len(reflector.calls) == 4
    assert row(fake_case, handled[0])["status"] == row(fake_case, handled[1])["status"] == "SUCCEEDED"
    assert row(fake_case, handled[0])["case_applied_at"] is None
    assert row(fake_case, handled[1])["case_applied_at"] is not None and case_state(fake_case) == (1, 1)
    with fake_case.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(job_execution)) == 2
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    failure = next(event for event in events if event["event"] == "runtime.reflect.failed")
    assert failure["execution_id"] == handled[0]
    assert any(event["event"] == "runtime.db.error_count" for event in events)
