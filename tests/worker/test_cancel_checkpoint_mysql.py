"""Real heartbeat → signal → checkpoint → fenced CANCELLED acceptance."""

from importlib import import_module
import json
import time
from threading import Event, enumerate as threads
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sqlalchemy import update, text

from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.schema import job_execution
from logging_faults import install_logging_fault
from test_heartbeat_mysql import resources, worker, stored, listener
from mysql_fault_proxy import CommitResponseProxy
from daesingo.common.config import DbSettings
from daesingo.common.db import create_worker_engine

pytestmark = pytest.mark.mysql


@pytest.mark.mysql_check("cancel_worker", "terminal_ack")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel_worker", "terminal_ack", parameter=s)) for s in
    ("commit_delay", "slow_logger", "lock_wait", "unknown_commit", "retry",
     "logger", "filter", "handler", "calculation")])
def test_cancel_metrics_end_at_durable_commit_ack(resources, mode, monkeypatch, capsys):
    engine, heartbeat, startup, execution, stream = resources
    startup = replace(startup, config=replace(startup.config,
        worker=startup.config.worker.model_copy(update={"heartbeat_interval_sec": 10})))
    from daesingo.common.jobs.cancel import CancellationRequested
    from daesingo.worker import composition
    checkpoint, acknowledgements, waits = [], [], []
    anchors = []
    writes, logger_calls = [], []
    active, locked = Event(), Event()
    writer_ready, writer_ids, holders = Event(), [], []
    remove = lambda: None
    original_log = startup.logger.log
    def log(level, message, *args, **kwargs):
        if kwargs.get("extra", {}).get("runtime_event") == "runtime.cancel.terminal_latency_ms":
            logger_calls.append(1)
            if mode == "slow_logger":
                time.sleep(0.4)
            elif mode == "logger":
                raise RuntimeError("private terminal logger payload")
        return original_log(level, message, *args, **kwargs)
    monkeypatch.setattr(startup.logger, "log", log)
    if mode in ("filter", "handler"):
        _, remove = install_logging_fault(startup.logger, mode,
            lambda event: event == "runtime.cancel.terminal_latency_ms")
    if mode == "calculation":
        from sqlalchemy.exc import OperationalError
        monkeypatch.setattr(composition, "float", lambda value: (_ for _ in ()).throw(
            OperationalError("private metric", {}, Exception(1213, "private payload"))), raising=False)
    def handler(ctx):
        cancel(engine)
        with engine.connect() as conn:
            before = time.monotonic()
            age = conn.scalar(text("SELECT TIMESTAMPDIFF(MICROSECOND, cancel_requested_at, NOW(6)) "
                                   "/ 1000.0 FROM job_execution"))
            anchors.append((float(age), before, time.monotonic()))
        assert ctx.cancel_signal.request() in (True, False)
        assert ctx.cancel_signal.request() is False
        with pytest.raises(CancellationRequested):
            ctx.checkpoint()
        checkpoint.append(ctx.cancel_signal.checkpoint_at)
        if mode == "lock_wait":
            assert locked.wait(10)
        active.set()
        ctx.checkpoint()
    def commit(conn):
        if not active.is_set():
            return
        driver = conn.connection.driver_connection
        original = driver.commit
        def acknowledged():
            driver.commit = original
            if mode == "commit_delay":
                time.sleep(0.4)
            original()
            acknowledgements.append(time.monotonic())
            active.clear()
        driver.commit = acknowledged
    attempts = []
    def writer(conn, cursor, sql, *args):
        if mode == "lock_wait" and sql.upper().startswith("UPDATE JOB_EXECUTION SET STATUS"):
            writer_ids.append(conn.connection.driver_connection.thread_id())
            writer_ready.set()
    def terminal(conn, cursor, sql, *args):
        if sql.upper().startswith("UPDATE JOB_EXECUTION SET STATUS"):
            writes.append(1)
            if mode == "unknown_commit":
                proxy.arm()
            if mode == "retry" and not attempts:
                from sqlalchemy.exc import OperationalError
                attempts.append(1)
                raise OperationalError("private SQL", {}, Exception(1213, "private retry"))
    def hold():
        with engine.begin() as conn:
            conn.execute(text("SELECT execution_id FROM job_execution FOR UPDATE"))
            locked.set()
            assert active.wait(10)
            assert writer_ready.wait(10)
            deadline = time.monotonic() + 5
            with engine.connect() as control:
                while time.monotonic() < deadline:
                    blocked = control.scalar(text("""SELECT COUNT(*)
                        FROM performance_schema.data_lock_waits w
                        JOIN performance_schema.threads t ON t.THREAD_ID = w.REQUESTING_THREAD_ID
                        JOIN performance_schema.data_locks l
                          ON l.ENGINE = w.ENGINE AND l.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
                        WHERE t.PROCESSLIST_ID = :writer AND l.OBJECT_SCHEMA = DATABASE()"""),
                        {"writer": writer_ids[0]})
                    if blocked:
                        break
                    Event().wait(0.005)
                else:
                    pytest.fail("terminal writer never entered this schema's InnoDB lock wait")
            # Inject the delay only after proving a real InnoDB row lock wait.
            time.sleep(0.4)
    try:
        with CommitResponseProxy(engine.url.host, engine.url.port) as proxy:
            url = engine.url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
            main = create_worker_engine(DbSettings(url=url.render_as_string(hide_password=False)))
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    # Take the lock after cancel's marker commit, before checkpoint.
                    if mode == "lock_wait":
                        original_cancel = cancel
                        def lock_after_cancel(target):
                            original_cancel(target)
                            holders.append(pool.submit(hold))
                            assert locked.wait(10)
                        monkeypatch.setitem(handler.__globals__, "cancel", lock_after_cancel)
                    with listener(main, "commit", commit), listener(main, "after_cursor_execute", terminal), \
                         listener(main, "before_cursor_execute", writer):
                        worker((main, heartbeat, startup, execution, stream), handler,
                            sleep=lambda seconds: (waits.append(seconds), time.sleep(0.05))).run()
                    for holder in holders:
                        holder.result(timeout=10)
                if mode == "unknown_commit":
                    assert proxy.commit_ok_dropped == 1 and waits == [1]
                if mode == "retry":
                    assert attempts == [1] and waits == [1]
            finally:
                main.dispose()
    finally:
        remove()
    row = stored(engine, execution)
    assert row["status"] == "CANCELLED" and row["produced"] == []
    assert len(acknowledgements) == 1
    assert len(writes) == (2 if mode == "retry" else 1)
    assert waits == ([1] if mode in ("retry", "unknown_commit") else [])
    assert len(logger_calls) == (0 if mode == "calculation" else 1)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    checkpoints = [e for e in events if e["event"] == "runtime.cancel.checkpoint_to_terminal_ms"]
    terminals = [e for e in events if e["event"] == "runtime.cancel.terminal_latency_ms"]
    metric, = checkpoints
    actual = (acknowledgements[-1] - checkpoint[0]) * 1000
    assert metric["duration_ms"] == pytest.approx(actual, abs=30)
    if mode not in ("logger", "filter", "handler", "calculation"):
        terminal_metric, = terminals
        age, before, after = anchors[0]
        # Bracket the server NOW(6) sample by client monotonic times. This
        # compares both metrics to the same independently observed COMMIT OK.
        lower = age + (acknowledgements[0] - after) * 1000
        upper = age + (acknowledgements[0] - before) * 1000
        assert lower - 30 <= terminal_metric["duration_ms"] <= upper + 30
        persisted = (row["ended_at"] - row["cancel_requested_at"]).total_seconds() * 1000
        assert terminal_metric["duration_ms"] + 0.001 >= persisted
        if mode in ("commit_delay", "lock_wait"):
            assert terminal_metric["duration_ms"] >= 380
    assert "private" not in stream.getvalue() and "private" not in capsys.readouterr().err
    print(json.dumps({"mode": mode, "ack_ms": actual,
                      "checkpoint_ms": metric["duration_ms"], "terminal": terminals}))


@pytest.mark.mysql_check("cancel_worker", "terminal_ack", parameter="zero_rows")
def test_rejected_terminal_update_never_emits_cancel_metrics(resources, monkeypatch):
    engine, heartbeat, startup, execution, stream = resources
    from daesingo.worker import composition
    monkeypatch.setattr(composition, "finish", lambda *args, **kwargs: 0)
    def handler(ctx):
        cancel(engine)
        ctx.cancel_signal.request()
        ctx.checkpoint()
    worker(resources, handler).run()
    assert stored(engine, execution)["status"] == "RUNNING"
    assert "terminal_latency_ms" not in stream.getvalue()
    assert "checkpoint_to_terminal_ms" not in stream.getvalue()


def cancel(engine):
    module = import_module("daesingo.common.jobs.cancel")
    with engine.begin() as conn:
        module.request_cancel(conn, ["job"])


@pytest.mark.mysql_check("cancel_worker", "observe")
@pytest.mark.parametrize("sink", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel_worker", "observe", parameter=s)) for s in
    ("healthy", "logger", "filter", "handler", "observer")])
def test_marker_signal_once_checkpoint_cancelled_metrics_and_sink_isolation(resources, sink, monkeypatch, capsys):
    engine, heartbeat, startup, execution, stream = resources
    seen, observations, renewals, signal_calls = Event(), [], [], []
    def observe(value):
        observations.append(value)
        seen.set()
        if sink == "observer":
            raise RuntimeError("private observer payload")
    def heartbeat_observe(value):
        if value.outcome == "RENEWED":
            renewals.append(value)
    remove = lambda: None
    if sink in ("filter", "handler"):
        _, remove = install_logging_fault(startup.logger, sink, lambda event: True)
    elif sink == "logger":
        monkeypatch.setattr(startup.logger, "log", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("private logger payload")))
    def handler(ctx):
        ctx.checkpoint()
        original = ctx.cancel_signal.request
        def request():
            first = original()
            signal_calls.append(first)
            return first
        monkeypatch.setattr(ctx.cancel_signal, "request", request)
        cancel(engine)
        assert seen.wait(10)
        assert ctx.cancel_signal.requested and not ctx.ownership.lost
        # Keep the handler alive for another tick; observation remains once.
        twice = Event()
        def count(conn):
            if len(renewals) >= 2:
                twice.set()
        with listener(heartbeat, "commit", count):
            assert twice.wait(10)
        ctx.checkpoint()
        pytest.fail("checkpoint returned after cancel")
    try:
        worker(resources, handler, heartbeat_observe=heartbeat_observe, cancel_observe=observe).run()
    finally:
        remove()
    row = stored(engine, execution)
    assert row["status"] == "CANCELLED" and row["produced"] == [] and row["failure_kind"] is None
    assert len(observations) == 1 and signal_calls == [True]
    assert observations[0].duration_ms >= 0
    assert observations[0].duration_ms < 20_000  # test cadence only; B-X1 is a target
    assert not any(t.name.startswith("runtime-heartbeat-") for t in threads())
    assert engine.pool.checkedout() == 0
    assert "private" not in stream.getvalue() and "payload" not in stream.getvalue()
    assert "private" not in capsys.readouterr().err
    if sink in ("healthy", "observer"):
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        for name in ("observe", "terminal"):
            metric, = [e for e in events if e["event"] == "runtime.cancel." + name + "_latency_ms"]
            assert metric["duration_ms"] >= 0 and metric["execution_id"] == execution
        terminal, = [e for e in events if e["event"] == "runtime.cancel.terminal_latency_ms"]
        assert terminal["duration_ms"] >= (
            (row["ended_at"] - row["cancel_requested_at"]).total_seconds() * 1000) - 0.001
        assert any(e["event"] == "runtime.cancel.checkpoint_to_terminal_ms" for e in events)


@pytest.mark.mysql_check("cancel_worker", "queued_no_usage")
def test_queued_cancel_never_invokes_handler_provider_or_usage_sink(resources):
    engine, heartbeat, startup, execution, stream = resources
    handler_calls, provider_calls, usage_records = [], [], []
    def handler(ctx):
        handler_calls.append(ctx)
        provider_calls.append("attempt")
        usage_records.append("UsageRecord")
        return HandlerResult()
    cancel(engine)
    worker(resources, handler).run()
    assert handler_calls == provider_calls == usage_records == []
    row = stored(engine, execution)
    assert row["status"] == "CANCELLED" and row["produced"] == [] and row["started_at"] is None
    assert "runtime.execution.started" not in stream.getvalue()
    assert "runtime.heartbeat" not in stream.getvalue()


@pytest.mark.mysql_check("cancel_worker", "late_success")
def test_cancel_after_last_checkpoint_preserves_success(resources):
    engine, heartbeat, startup, execution, stream = resources
    observed = Event()
    def handler(ctx):
        ctx.checkpoint()
        cancel(engine)
        assert observed.wait(10)
        assert ctx.cancel_signal.requested
        return HandlerResult(produced=[{"kind": "Candidates", "ref": "result"}])
    worker(resources, handler, cancel_observe=lambda value: observed.set()).run()
    row = stored(engine, execution)
    assert row["status"] == "SUCCEEDED" and row["produced"]
    assert "terminal_latency_ms" not in stream.getvalue()
    assert "checkpoint_to_terminal_ms" not in stream.getvalue()


@pytest.mark.mysql_check("cancel_worker", "ownership")
@pytest.mark.parametrize("first", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel_worker", "ownership", parameter=s)) for s in ("ownership", "cancel")])
def test_ownership_loss_and_cancel_are_distinct_and_no_stale_terminal(resources, first):
    engine, heartbeat, startup, execution, stream = resources
    observed = Event()
    def transfer():
        with engine.begin() as conn:
            conn.execute(update(job_execution).values(lease_owner="other"))
    def handler(ctx):
        if first == "cancel":
            cancel(engine)
            assert observed.wait(10)
            transfer()
        else:
            transfer()
            cancel(engine)
        assert ctx.ownership.wait_lost(10)
        assert ctx.cancel_signal.requested == (first == "cancel")
        ctx.checkpoint()
        return HandlerResult()
    worker(resources, handler, cancel_observe=lambda value: observed.set()).run()
    assert stored(engine, execution)["status"] == "RUNNING"
    assert "terminal_latency_ms" not in stream.getvalue()
    assert "checkpoint_to_terminal_ms" not in stream.getvalue()
    assert not any(t.name.startswith("runtime-heartbeat-") for t in threads())


@pytest.mark.mysql_check("cancel_worker", "heartbeat_error")
def test_heartbeat_error_neither_kills_handler_nor_requests_cancel(resources):
    engine, heartbeat, startup, execution, stream = resources
    failed = Event()
    def fail(conn, cursor, statement, params, context, many):
        raise RuntimeError("private SQL payload")
    def handler(ctx):
        assert failed.wait(10)
        assert not ctx.cancel_signal.requested and not ctx.ownership.lost
        ctx.checkpoint()
        return HandlerResult()
    with listener(heartbeat, "before_cursor_execute", fail):
        worker(resources, handler, heartbeat_observe=lambda value: failed.set()).run()
    assert stored(engine, execution)["status"] == "SUCCEEDED"
    assert "private" not in stream.getvalue()


@pytest.mark.mysql_check("cancel_worker", "db_clock")
def test_observe_latency_uses_database_clock(resources):
    engine, heartbeat, startup, execution, stream = resources
    seen, values = Event(), []
    def observe(value):
        values.append(value)
        seen.set()
    def handler(ctx):
        with engine.begin() as conn:
            conn.execute(text("UPDATE job_execution SET cancel_requested_at = "
                              "TIMESTAMPADD(SECOND, -7, NOW(6))"))
        assert seen.wait(10)
        assert 7000 <= values[0].duration_ms < 17000
        ctx.checkpoint()
    worker(resources, handler, cancel_observe=observe).run()
    assert stored(engine, execution)["status"] == "CANCELLED"


@pytest.mark.mysql_check("cancel_worker", "observe_commit")
def test_observe_latency_includes_successful_commit_acknowledgement_delay(resources):
    engine, heartbeat, startup, execution, stream = resources
    observed, values = Event(), []
    def commit(conn):
        time.sleep(0.2)
    def observe(value):
        values.append(value)
        observed.set()
    def handler(ctx):
        with listener(heartbeat, "commit", commit):
            cancel(engine)
            assert observed.wait(10)
            assert ctx.cancel_signal.requested
            assert values[0].duration_ms >= 200
        ctx.checkpoint()
    worker(resources, handler, cancel_observe=observe).run()
    assert stored(engine, execution)["status"] == "CANCELLED"


@pytest.mark.mysql_check("cancel_worker", "observation_fault")
@pytest.mark.parametrize("fault", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel_worker", "observation_fault", parameter=s)) for s in ("read", "commit")])
def test_failed_marker_read_or_heartbeat_commit_never_delivers_signal(resources, fault):
    engine, heartbeat, startup, execution, stream = resources
    failed, seen = Event(), Event()
    def read_fault(conn, cursor, statement, params, context, many):
        if statement.startswith("SELECT cancel_requested_at"):
            raise RuntimeError("private marker query")
    def commit_fault(conn):
        raise RuntimeError("private heartbeat commit")
    def handler(ctx):
        with listener(heartbeat, "before_cursor_execute" if fault == "read" else "commit",
                      read_fault if fault == "read" else commit_fault):
            cancel(engine)
            assert failed.wait(10)
            assert not ctx.cancel_signal.requested and not ctx.ownership.lost
            ctx.checkpoint()
        assert seen.wait(10)
        ctx.checkpoint()
    worker(resources, handler,
        heartbeat_observe=lambda value: failed.set() if value.outcome == "FAILED" else None,
        cancel_observe=lambda value: seen.set()).run()
    assert stored(engine, execution)["status"] == "CANCELLED"
    assert "private" not in stream.getvalue()


@pytest.mark.mysql_check("cancel_worker", "cleanup")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "cancel_worker", "cleanup", parameter=s)) for s in
    ("success", "failure", "exception", "interrupt", "exit", "cancel")])
def test_all_handler_paths_cleanup_heartbeat(resources, mode):
    engine, heartbeat, startup, execution, stream = resources
    observed = Event()
    def handler(ctx):
        if mode == "cancel":
            cancel(engine)
            assert observed.wait(10)
            ctx.checkpoint()
        if mode in ("interrupt", "exit", "exception"):
            raise {"interrupt": KeyboardInterrupt, "exit": SystemExit, "exception": RuntimeError}[mode]("private payload")
        return HandlerResult(status="FAILED", failure_kind="MODULE_FAILURE") if mode == "failure" else HandlerResult()
    loop = worker(resources, handler, cancel_observe=lambda value: observed.set())
    if mode in ("interrupt", "exit"):
        with pytest.raises(KeyboardInterrupt if mode == "interrupt" else SystemExit):
            loop.run()
    else:
        loop.run()
    assert stored(engine, execution)["status"] == {
        "success": "SUCCEEDED", "failure": "FAILED", "exception": "FAILED",
        "interrupt": "RUNNING", "exit": "RUNNING", "cancel": "CANCELLED"}[mode]
    assert not any(t.name.startswith("runtime-heartbeat-") for t in threads())
    assert heartbeat.pool.checkedout() == 0 if hasattr(heartbeat.pool, "checkedout") else True
    assert "private" not in stream.getvalue()
