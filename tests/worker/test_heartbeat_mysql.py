"""RT-05(a) real lease renewal, ownership races and lifecycle acceptance."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from importlib import import_module
from io import StringIO
from threading import Event, current_thread, enumerate as threads
from types import MappingProxyType

import pytest
from sqlalchemy import event, select, update

from daesingo.common.bootstrap import Startup
from daesingo.common.config import RuntimeConfig, DbSettings
from daesingo.common.db import create_worker_engine, create_heartbeat_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.repository import enqueue, claim_one
from daesingo.common.jobs.schema import job_execution
from daesingo.common.logging import configure_logging
from logging_faults import install_logging_fault

pytestmark = pytest.mark.mysql


@pytest.fixture
def resources(mysql_schema_url):
    upgrade_all(mysql_schema_url)
    config = RuntimeConfig.from_mapping("worker", {
        "DAESINGO_RUNTIME_DB_URL": mysql_schema_url.render_as_string(hide_password=False),
        "DAESINGO_RUNTIME_MEDIA_ROOT": "/private/media",
        "DAESINGO_RUNTIME_WORKER_TEMP_ROOT": "/private/temp",
    })
    config = replace(config, worker=config.worker.model_copy(update={"heartbeat_interval_sec": 0.05}))
    engine = create_worker_engine(config.db)
    heartbeat = create_heartbeat_engine(config.db, config.heartbeat)
    stream = StringIO()
    startup = Startup(config, MappingProxyType({}), configure_logging("worker", stream=stream))
    with engine.begin() as conn:
        execution_id, = enqueue(conn, [{"job_id": "job", "case_id": "case", "kind": "TEST"}], "trace")
    try:
        yield engine, heartbeat, startup, execution_id, stream
    finally:
        heartbeat.dispose()
        engine.dispose()


def stored(engine, execution_id):
    with engine.connect() as conn:
        return dict(conn.execute(select(job_execution).where(
            job_execution.c.execution_id == execution_id)).mappings().one())


@contextmanager
def listener(engine, name, callback):
    event.listen(engine, name, callback)
    try:
        yield
    finally:
        event.remove(engine, name, callback)


def worker(resources, handler, *, owned=False, **kwargs):
    engine, heartbeat, startup, execution_id, stream = resources
    composition = import_module("daesingo.worker.composition")
    assert "heartbeat_engine" in __import__("inspect").signature(composition.compose_worker).parameters, \
        "RT-05 dedicated heartbeat composition is missing"
    stop = Event()
    from daesingo.worker.registry import KindRegistry
    if not owned:
        kwargs["heartbeat_engine"] = heartbeat
    return composition.compose_worker(engine=engine,
        startup=startup, registry=KindRegistry({"TEST": handler}), worker_id="owner",
        stop=stop, idle_wait=lambda seconds: stop.set(), **kwargs)


@pytest.mark.mysql_check("heartbeat_lifecycle", "renewal")
def test_db_clock_lease_renewal_and_persistent_dedicated_connection(resources):
    engine, heartbeat, startup, execution_id, stream = resources
    renewed, connections, observations = Event(), [], []
    def observed(conn):
        connections.append(conn.connection.driver_connection.thread_id())
    def observe(value):
        if value.outcome == "RENEWED":
            observations.append(value)
            if len(observations) >= 2:
                renewed.set()
    def handler(context):
        before = stored(engine, execution_id)
        assert renewed.wait(10)
        after = stored(engine, execution_id)
        assert after["lease_expires_at"] > before["lease_expires_at"]
        assert after["heartbeat_at"] > before["heartbeat_at"]
        assert engine.pool.checkedout() == 0
        return HandlerResult()
    with listener(heartbeat, "commit", observed):
        worker(resources, handler, heartbeat_observe=observe).run()
    assert stored(engine, execution_id)["status"] == "SUCCEEDED"
    assert len(connections) >= 2 and len(set(connections)) == 1
    assert not any(t.name.startswith("runtime-heartbeat-") for t in threads())


@pytest.mark.mysql_check("heartbeat_lifecycle", "zero_rows")
@pytest.mark.parametrize("sink", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "zero_rows", parameter=s)) for s in ("healthy", "logger", "filter", "handler", "observer")])
def test_zero_rows_fences_handler_result(resources, sink, monkeypatch):
    engine, heartbeat, startup, execution_id, stream = resources
    observations = []
    def observe(value):
        observations.append(value)
        if sink == "observer":
            raise RuntimeError("private observer")
    remove = lambda: None
    if sink in ("filter", "handler"):
        seen, remove = install_logging_fault(startup.logger, sink, lambda event: True)
    elif sink == "logger":
        def fail(*args, **kwargs):
            raise RuntimeError("private logger")
        monkeypatch.setattr(startup.logger, "log", fail)
    def handler(context):
        with engine.begin() as conn:
            conn.execute(update(job_execution).values(lease_owner="other"))
        assert context.ownership.wait_lost(10)
        return HandlerResult(produced=[{"kind": "Candidates", "ref": "stale"}])
    try:
        worker(resources, handler, heartbeat_observe=observe).run()
    finally:
        remove()
    assert stored(engine, execution_id)["status"] == "RUNNING"
    assert stored(engine, execution_id)["produced"] == []
    assert observations[0].outcome == "OWNERSHIP_LOST"
    if sink in ("healthy", "observer"):
        assert "runtime.execution.finish_rejected" in stream.getvalue()


@pytest.mark.mysql_check("heartbeat_lifecycle", "owned_cleanup")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "owned_cleanup", parameter=s)) for s in
    ("success", "heartbeat_interrupt", "handler_interrupt")])
def test_owned_engine_is_disposed_and_heartbeat_baseexception_returns_to_owner(resources, mode, monkeypatch):
    engine, heartbeat, startup, execution_id, stream = resources
    module = import_module("daesingo.worker.composition")
    original = module.create_heartbeat_engine
    opened, closed, disposed, renewed = [], [], [], Event()
    def factory(db, settings):
        dedicated = original(db, settings)
        event.listen(dedicated, "connect", lambda conn, record: opened.append(conn))
        event.listen(dedicated, "close", lambda conn, record: closed.append(conn))
        event.listen(dedicated, "engine_disposed", lambda eng: disposed.append(eng))
        return dedicated
    monkeypatch.setattr(module, "create_heartbeat_engine", factory)
    def observe(value):
        renewed.set()
        if mode == "heartbeat_interrupt":
            raise KeyboardInterrupt()
    def handler(context):
        assert renewed.wait(10)
        if mode == "heartbeat_interrupt":
            assert context.ownership.wait_lost(10)
        elif mode == "handler_interrupt":
            raise KeyboardInterrupt()
        return HandlerResult()
    loop = worker(resources, handler, owned=True, heartbeat_observe=observe)
    if mode == "success":
        loop.run()
    else:
        with pytest.raises(KeyboardInterrupt):
            loop.run()
    assert len(disposed) == 1 and opened and opened == closed
    assert not any(t.name.startswith("runtime-heartbeat-") for t in threads())
    assert engine.pool.checkedout() == 0
    assert stored(engine, execution_id)["status"] == ("SUCCEEDED" if mode == "success" else "RUNNING")


@pytest.mark.mysql_check("heartbeat_lifecycle", "commit_race")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "commit_race", parameter=s)) for s in ("local_loss", "db_transfer")])
def test_loss_between_terminal_update_and_commit_rolls_back(resources, mode):
    engine, heartbeat, startup, execution_id, stream = resources
    ready, release, contexts = Event(), Event(), []
    def handler(context):
        contexts.append(context)
        return HandlerResult()
    def pause(conn, cursor, sql, params, ctx, many):
        if sql.startswith("UPDATE job_execution SET status="):
            ready.set()
            assert release.wait(10)
    with listener(engine, "before_cursor_execute" if mode == "db_transfer" else "after_cursor_execute", pause):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker(resources, handler).run)
            try:
                assert ready.wait(10)
                if mode == "db_transfer":
                    with engine.begin() as conn:
                        conn.execute(update(job_execution).values(lease_owner="other"))
                    assert contexts[0].ownership.wait_lost(10)
                else:
                    contexts[0].ownership.mark_lost()
            finally:
                release.set()
            future.result(timeout=15)
    assert stored(engine, execution_id)["status"] == "RUNNING"


@pytest.mark.mysql_check("heartbeat_lifecycle", "retry_fence")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "retry_fence", parameter=s)) for s in ("transaction", "loop")])
def test_loss_during_transaction_retry_wait_blocks_next_attempt(resources, mode):
    engine, heartbeat, startup, execution_id, stream = resources
    contexts, calls, waits = [], [], []
    def handler(context):
        contexts.append(context)
        return HandlerResult()
    def fail(conn, cursor, sql, params, ctx, many):
        if sql.startswith("UPDATE job_execution SET status="):
            calls.append(sql)
            # Real MySQL SIGNAL is a retryable 1213, not a mocked transaction.
            conn.exec_driver_sql("SIGNAL SQLSTATE '40001' SET MYSQL_ERRNO=1213, MESSAGE_TEXT='test fault'")
    def sleep(seconds):
        waits.append(seconds)
        if mode == "loop" and seconds == 1:
            return
        with engine.begin() as conn:
            conn.execute(update(job_execution).values(lease_owner="other"))
        assert contexts[0].ownership.wait_lost(10)
    with listener(engine, "before_cursor_execute", fail):
        worker(resources, handler, sleep=sleep).run()
    assert len(calls) == (1 if mode == "transaction" else 3)
    assert waits == ([1] if mode == "transaction" else [1, 1, 5])
    assert stored(engine, execution_id)["status"] == "RUNNING"


@pytest.mark.mysql_check("heartbeat_lifecycle", "cleanup")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "cleanup", parameter=s)) for s in ("success", "failure", "exception", "interrupt", "exit", "signal")])
def test_all_handler_exit_paths_close_connection_and_join_thread(resources, mode):
    engine, heartbeat, startup, execution_id, stream = resources
    renewed, live, closed = Event(), [], []
    def opened(conn, record):
        live.append(conn)
    def close(conn, record):
        closed.append(conn)
    def committed(conn):
        renewed.set()
    loop = None
    def handler(context):
        assert renewed.wait(10)
        if mode == "signal":
            loop.stop.set()
        if mode == "interrupt":
            raise KeyboardInterrupt()
        if mode == "exit":
            raise SystemExit(7)
        if mode == "exception":
            raise RuntimeError("private payload")
        return HandlerResult(status="FAILED", failure_kind="MODULE_ERROR") if mode == "failure" else HandlerResult()
    with listener(heartbeat, "connect", opened), listener(heartbeat, "close", close), listener(heartbeat, "commit", committed):
        loop = worker(resources, handler)
        if mode in ("interrupt", "exit"):
            with pytest.raises(KeyboardInterrupt if mode == "interrupt" else SystemExit):
                loop.run()
        else:
            loop.run()
    assert live and closed == live
    assert not any(t.name.startswith("runtime-heartbeat-") for t in threads())
    assert engine.pool.checkedout() == 0


@pytest.mark.mysql_check("heartbeat_lifecycle", "slow_attempt")
def test_slow_db_call_has_no_overlap_and_records_skipped_ticks(resources):
    engine, heartbeat, startup, execution_id, stream = resources
    calls, active, max_active = [], [], []
    finished = Event()
    def delay(conn, cursor, sql, params, ctx, many):
        if sql.startswith("UPDATE job_execution"):
            active.append(True)
            max_active.append(len(active))
            calls.append(current_thread().ident)
            conn.exec_driver_sql("SELECT SLEEP(0.18)")
    def after(conn, cursor, sql, params, ctx, many):
        if sql.startswith("UPDATE job_execution"):
            active.pop()
    def observation(value):
        if value.skipped_tick_count:
            finished.set()
    def handler(context):
        assert finished.wait(10)
        return HandlerResult()
    with listener(heartbeat, "before_cursor_execute", delay), listener(heartbeat, "after_cursor_execute", after):
        worker(resources, handler, heartbeat_observe=observation).run()
    assert max(max_active) == 1 and len(set(calls)) == 1
    assert "runtime.heartbeat.skipped_tick_count" in stream.getvalue()


@pytest.mark.mysql_check("heartbeat_lifecycle", "error_isolation")
@pytest.mark.parametrize("sink", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "error_isolation", parameter=s)) for s in ("healthy", "logger", "filter", "handler", "observer")])
def test_heartbeat_db_error_reconnects_without_retry_or_handler_failure(resources, sink, monkeypatch):
    engine, heartbeat, startup, execution_id, stream = resources
    attempts, connects, recovered = [], [], Event()
    def opened(conn, record):
        connects.append(conn)
    def fail(conn, cursor, sql, params, ctx, many):
        if sql.startswith("UPDATE job_execution"):
            attempts.append(current_thread().ident)
            if len(attempts) == 1:
                conn.exec_driver_sql("SIGNAL SQLSTATE '40001' SET MYSQL_ERRNO=1213, MESSAGE_TEXT='test fault'")
    def observe(value):
        if value.outcome == "RENEWED":
            recovered.set()
        if sink == "observer":
            raise RuntimeError("private observer")
    if sink in ("filter", "handler"):
        seen, remove = install_logging_fault(startup.logger, sink, lambda event: True)
    elif sink == "logger":
        monkeypatch.setattr(startup.logger, "log", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("private logger")))
    def handler(context):
        assert recovered.wait(10)
        assert not context.ownership.lost
        return HandlerResult()
    try:
        with listener(heartbeat, "before_cursor_execute", fail), listener(heartbeat, "connect", opened):
            worker(resources, handler, heartbeat_observe=observe).run()
    finally:
        if sink in ("filter", "handler"):
            remove()
    assert len(attempts) >= 2 and len(connects) == 2
    assert stored(engine, execution_id)["status"] == "SUCCEEDED"
    assert "private" not in stream.getvalue()


@pytest.mark.mysql_check("heartbeat_lifecycle", "connection_fault")
@pytest.mark.parametrize("fault", [pytest.param(s, marks=pytest.mark.mysql_check(
    "heartbeat_lifecycle", "connection_fault", parameter=s)) for s in ("disconnect", "timeout")])
def test_real_disconnect_and_read_timeout_recover_next_tick(resources, fault):
    engine, heartbeat, startup, execution_id, stream = resources
    attempts, observations, recovered, connections = [], [], Event(), []
    def opened(conn, record):
        connections.append(conn)
    def fail(conn, cursor, sql, params, ctx, many):
        if sql.startswith("UPDATE job_execution"):
            attempts.append(current_thread().ident)
            if len(attempts) == 1:
                if fault == "disconnect":
                    connection_id = conn.connection.driver_connection.thread_id()
                    with engine.connect() as killer:
                        killer.exec_driver_sql(f"KILL CONNECTION {connection_id}")
                else:
                    conn.exec_driver_sql("SELECT SLEEP(6)")  # B-D9 read timeout is 5s.
    def observe(value):
        observations.append(value)
        if value.outcome == "RENEWED":
            recovered.set()
    def handler(context):
        assert recovered.wait(20)
        return HandlerResult()
    with listener(heartbeat, "connect", opened), listener(heartbeat, "before_cursor_execute", fail):
        worker(resources, handler, heartbeat_observe=observe).run()
    assert [o.outcome for o in observations[:2]] == ["FAILED", "RENEWED"]
    assert observations[0].consecutive_failures == 1 and observations[1].consecutive_failures == 0
    assert len(connections) == 2
    assert stored(engine, execution_id)["status"] == "SUCCEEDED"


@pytest.mark.mysql_check("heartbeat_lifecycle", "zero_commit_failure")
def test_zero_rows_fences_even_if_empty_commit_fails(resources):
    engine, heartbeat, startup, execution_id, stream = resources
    contexts, observations = [], []
    def fail_commit(conn):
        conn.exec_driver_sql("SIGNAL SQLSTATE '40001' SET MYSQL_ERRNO=1213, MESSAGE_TEXT='test commit fault'")
    def handler(context):
        contexts.append(context)
        with engine.begin() as conn:
            conn.execute(update(job_execution).values(lease_owner="other"))
        assert context.ownership.wait_lost(3)
        return HandlerResult()
    with listener(heartbeat, "commit", fail_commit):
        worker(resources, handler, heartbeat_observe=observations.append).run()
    assert contexts[0].ownership.lost
    assert observations[0].outcome == "OWNERSHIP_LOST"
    assert len(observations) == 1
    assert stored(engine, execution_id)["status"] == "RUNNING"
