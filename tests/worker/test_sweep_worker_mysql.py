"""Production composition: startup recovery and sweep alongside heartbeat."""

from io import StringIO
from threading import Event, enumerate as threads
from types import MappingProxyType

import pytest
from sqlalchemy import func, select, text, update

from daesingo.common.bootstrap import Startup
from daesingo.common.config import RuntimeConfig
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.repository import claim_one, enqueue
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.schema import job_execution as jobs
from daesingo.common.jobs.sweep import sweep_once
from daesingo.common.logging import configure_logging
from daesingo.worker.composition import compose_worker
from daesingo.worker.registry import KindRegistry

pytestmark = pytest.mark.mysql


@pytest.fixture
def resources(mysql_schema_url):
    upgrade_all(mysql_schema_url)
    config = RuntimeConfig.from_mapping("worker", {
        "DAESINGO_RUNTIME_DB_URL": mysql_schema_url.render_as_string(hide_password=False),
        "DAESINGO_RUNTIME_MEDIA_ROOT": "/test/media",
        "DAESINGO_RUNTIME_WORKER_TEMP_ROOT": "/test/temp",
        "DAESINGO_RUNTIME_DB_LOCK_WAIT_TIMEOUT_SEC": "1",
        "DAESINGO_RUNTIME_HEARTBEAT_INTERVAL_SEC": "2",
        "DAESINGO_RUNTIME_LEASE_DURATION_SEC": "3",
        "DAESINGO_RUNTIME_STALE_SWEEP_INTERVAL_SEC": "0.05",
    })
    engine = create_worker_engine(config.db)
    startup = Startup(config, MappingProxyType({}), configure_logging("worker", stream=StringIO()))
    try:
        yield engine, startup
    finally:
        engine.dispose()


def add(engine, job):
    with engine.begin() as conn:
        execution, = enqueue(conn, [{"job_id": job, "case_id": "case", "kind": "TEST"}], "trace")
    return execution


def expire(engine, execution):
    with engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.execution_id == execution).values(
            lease_expires_at=func.timestampadd(text("SECOND"), -1, func.now(6))))


def rows(engine):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(jobs).order_by(jobs.c.job_id, jobs.c.attempt)).mappings()]


@pytest.mark.mysql_check("sweep_worker", "startup")
def test_startup_recovers_expired_row_before_first_handler_preserves_live_lease(resources):
    engine, startup = resources
    expired = add(engine, "expired")
    assert claim_one(engine, "dead").execution_id == expired
    expire(engine, expired)
    live = add(engine, "live")
    assert claim_one(engine, "alive").execution_id == live
    current = add(engine, "work")
    stop = Event()
    def handler(context):
        stop.set()
        snapshot = rows(engine)
        assert [r["status"] for r in snapshot] == ["STALE", "QUEUED", "RUNNING", "RUNNING"]
        assert context.execution_id == current
        return HandlerResult()
    assert "sweep_hooks" in __import__("inspect").signature(compose_worker).parameters, "RT-06 composition missing"
    compose_worker(engine=engine, startup=startup, stop=stop, registry=KindRegistry({"TEST": handler})).run()
    assert rows(engine)[2]["status"] == "RUNNING"
    assert rows(engine)[-1]["status"] == "SUCCEEDED"
    assert not any(t.name.startswith(("runtime-sweep", "runtime-heartbeat")) for t in threads())


@pytest.mark.mysql_check("sweep_worker", "independent")
def test_periodic_sweep_recovers_other_row_while_handler_is_blocked(resources):
    engine, startup = resources
    other = add(engine, "other")
    claim_one(engine, "dead")
    add(engine, "work")
    stop, periodic = Event(), Event()
    snapshots = []
    def hook():
        snapshots.append(rows(engine))
        if any(r["status"] == "STALE" for r in snapshots[-1]):
            periodic.set()
    def handler(context):
        try:
            expire(engine, other)  # expiry occurs AFTER startup sweep
            assert periodic.wait(10)
            assert any(r["attempt"] == 2 and r["status"] == "QUEUED" for r in rows(engine))
        finally:
            stop.set()
        return HandlerResult()
    assert "sweep_hooks" in __import__("inspect").signature(compose_worker).parameters, "RT-07 sweep registration missing"
    compose_worker(engine=engine, startup=startup, stop=stop, registry=KindRegistry({"TEST": handler}),
                   sweep_hooks=(hook,)).run()
    assert snapshots[0][0]["status"] == "RUNNING"
    assert rows(engine)[-1]["status"] == "SUCCEEDED"
    assert engine.pool.checkedout() == 0


@pytest.mark.mysql_check("sweep_worker", "heartbeat")
def test_successful_heartbeat_keeps_handler_live_beyond_lease(resources):
    engine, startup = resources
    execution = add(engine, "work")
    stop, renewed = Event(), Event()
    # Valid short interval configuration, including lock_wait < heartbeat.
    # Duration exceeds the original lease; later renewals must protect it.
    def observe(value):
        if value.outcome == "RENEWED":
            renewed.set()
    checked = []
    def hook():
        checked.append(rows(engine)[0]["status"])
    def handler(context):
        try:
            assert renewed.wait(10)
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT SLEEP(3.5)")
            assert rows(engine)[0]["status"] == "RUNNING" and not context.ownership.lost
            assert checked.count("RUNNING") >= 2
        finally:
            stop.set()
        return HandlerResult()
    assert "sweep_hooks" in __import__("inspect").signature(compose_worker).parameters, "RT-07 sweep registration missing"
    compose_worker(engine=engine, startup=startup, stop=stop, registry=KindRegistry({"TEST": handler}),
                   heartbeat_observe=observe, sweep_hooks=(hook,)).run()
    assert rows(engine)[0]["status"] == "SUCCEEDED" and len(rows(engine)) == 1
    assert not any(t.name.startswith(("runtime-sweep", "runtime-heartbeat")) for t in threads())


@pytest.mark.mysql_check("sweep_worker", "queue_wait")
@pytest.mark.parametrize("attempt", [pytest.param(value, marks=pytest.mark.mysql_check(
    "sweep_worker", "queue_wait", parameter=str(value))) for value in (1, 2)])
def test_claim_logs_queue_wait_with_retry_backoff_and_attempt_group(resources, attempt):
    import json
    from daesingo.common.config import WorkerSettings
    engine, startup = resources
    execution = add(engine, "work")
    if attempt == 2:
        claim_one(engine, "dead")
        expire(engine, execution)
        sweep_once(engine, WorkerSettings(stale_retry_backoff_base_sec=0.2))
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT SLEEP(0.25)")
    stop = Event()
    def handler(context):
        stop.set()
        return HandlerResult()
    stream = StringIO()
    startup = Startup(startup.config, startup.modules, configure_logging("worker", stream=stream))
    compose_worker(engine=engine, startup=startup, stop=stop, registry=KindRegistry({"TEST": handler})).run()
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    wait = [value for value in events if value["event"] == "runtime.queue.wait_ms"]
    assert len(wait) == 1, "queue wait measurement missing"
    assert wait[0]["status"] == ("RETRY" if attempt == 2 else "INITIAL")
    row = rows(engine)[-1]
    expected_ms = (row["started_at"] - row["queued_at"]).total_seconds() * 1000
    assert wait[0]["duration_ms"] == pytest.approx(expected_ms)
    if attempt == 2:
        assert wait[0]["duration_ms"] >= 200


@pytest.mark.mysql_check("sweep_worker", "slow_queue_logger")
def test_queue_wait_logging_longer_than_lease_is_protected_by_heartbeat(resources, monkeypatch):
    engine, startup = resources
    execution = add(engine, "work")
    original_log = startup.logger.log
    renewed, logger_calls = Event(), []
    def log(level, message, *args, **kwargs):
        if kwargs.get("extra", {}).get("runtime_event") == "runtime.queue.wait_ms":
            logger_calls.append(True)
            Event().wait(3.5)  # validated lease=3, heartbeat=2, sweep=0.05
        return original_log(level, message, *args, **kwargs)
    monkeypatch.setattr(startup.logger, "log", log)
    def observe(value):
        if value.outcome == "RENEWED":
            renewed.set()
    stop = Event()
    def handler(context):
        stop.set()
        return HandlerResult()
    compose_worker(engine=engine, startup=startup, stop=stop, registry=KindRegistry({"TEST": handler}),
                   heartbeat_observe=observe).run()
    assert logger_calls == [True] and renewed.is_set()
    assert len(rows(engine)) == 1 and rows(engine)[0]["status"] == "SUCCEEDED"


@pytest.mark.mysql_check("sweep_worker", "hook_fatal")
@pytest.mark.parametrize("phase,kind,sink", [pytest.param(phase, kind, sink,
    marks=pytest.mark.mysql_check("sweep_worker", "hook_fatal", parameter=f"{phase}_{kind}_{sink}"))
    for phase in ("startup", "periodic") for kind in ("exit", "interrupt", "base")
    for sink in ("healthy", "logger", "filter", "handler")])
def test_fatal_hook_process_boundary_preserves_db_cleanup_and_hides_original(resources, tmp_path, phase, kind, sink):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    import textwrap
    engine, _ = resources
    execution = add(engine, "dead")
    claim_one(engine, "dead")
    if phase == "startup":
        expire(engine, execution)
    receipt = tmp_path / "cleanup.json"
    code = textwrap.dedent('''
        import io, json, os, signal, sys
        from pathlib import Path
        from threading import enumerate as threads
        from types import MappingProxyType
        from sqlalchemy import func, text, update
        import daesingo.worker.__main__ as module
        from daesingo.common.bootstrap import Startup
        from daesingo.common.config import RuntimeConfig
        from daesingo.common.jobs.schema import job_execution as jobs
        from daesingo.common.jobs.sweep import SweepService
        from daesingo.common.logging import configure_logging
        from daesingo.worker.composition import compose_worker as real_compose
        from logging_faults import install_logging_fault
        phase, kind, sink, receipt = sys.argv[1:]
        class Fatal(BaseException):
            pass
        stream = io.StringIO()
        logger = configure_logging("worker", stream=stream)
        if sink == "logger":
            original_log = logger.log
            def log(level, message, *args, **kwargs):
                if kwargs.get("extra", {}).get("runtime_event", "").startswith("runtime.worker."):
                    raise Fatal("secret /private/logger payload")
                return original_log(level, message, *args, **kwargs)
            logger.log = log
        elif sink != "healthy":
            install_logging_fault(logger, sink, lambda event: event.startswith("runtime.worker."),
                                  error=Fatal("secret /private/sink payload"))
        config = RuntimeConfig.from_mapping("worker", {
            "DAESINGO_RUNTIME_DB_URL": os.environ["P2_MYSQL_URL"],
            "DAESINGO_RUNTIME_MEDIA_ROOT": "/test/media",
            "DAESINGO_RUNTIME_WORKER_TEMP_ROOT": "/test/temp",
            "DAESINGO_RUNTIME_STALE_SWEEP_INTERVAL_SEC": "0.01",
        })
        module.bootstrap = lambda **kwargs: Startup(config, MappingProxyType({}), logger)
        calls, later, state = [], [], {}
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        original_join = SweepService.stop_and_join
        def join(self):
            try:
                return original_join(self)
            finally:
                state["joined"] = self.thread is None or not self.thread.is_alive()
        SweepService.stop_and_join = join
        def compose(**kwargs):
            engine, stop = kwargs["engine"], kwargs["stop"]
            original_dispose = engine.dispose
            def dispose():
                state["checkedout"] = engine.pool.checkedout()
                original_dispose()
                state["disposed"] = True
                state["stop"] = stop.is_set()
                state["threads"] = [t.name for t in threads() if t.name.startswith("runtime-")]
                Path(receipt).write_text(json.dumps(state))
            engine.dispose = dispose
            def hook():
                calls.append("hook")
                if phase == "periodic" and len(calls) == 1:
                    with engine.begin() as conn:
                        conn.execute(update(jobs).where(jobs.c.status == "RUNNING").values(
                            lease_expires_at=func.timestampadd(text("SECOND"), -1, func.now(6))))
                    return
                error = {"exit": SystemExit, "interrupt": KeyboardInterrupt, "base": Fatal}[kind]
                raise error("secret /private/hook payload")
            return real_compose(**kwargs, sweep_hooks=(hook, lambda: later.append("later")))
        module.compose_worker = compose
        result = module.main()
        assert all(value not in stream.getvalue() for value in ("Traceback", "secret", "/private/", "payload"))
        print(json.dumps({"code": result, "hook_calls": len(calls), "later_calls": len(later),
                          "signals_restored": all(signal.getsignal(sig) == value for sig, value in previous.items()),
                          "events": [json.loads(line)["event"] for line in stream.getvalue().splitlines()]}))
        raise SystemExit(result)
    ''')
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, P2_MYSQL_URL=engine.url.render_as_string(hide_password=False),
               PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=os.pathsep.join([str(root / "src"), str(root / "tests")]))
    child = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code, phase, kind, sink, str(receipt)],
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert child.stderr == ""
    assert all(value not in child.stdout + child.stderr for value in ("Traceback", "secret", "/private/", "payload"))
    assert child.returncode == 1
    result = json.loads(child.stdout)
    assert result["code"] == 1 and result["signals_restored"]
    assert result["hook_calls"] == (1 if phase == "startup" else 2)
    assert result["later_calls"] == (0 if phase == "startup" else 1)
    if sink == "healthy":
        assert "runtime.worker.failed" in result["events"]
    assert json.loads(receipt.read_text()) == {
        "joined": True, "checkedout": 0, "disposed": True, "stop": True, "threads": []}
    snapshot = rows(engine)
    assert [r["status"] for r in snapshot] == ["STALE", "QUEUED"]
    assert snapshot[0]["execution_id"] == execution and snapshot[1]["attempt"] == 2


@pytest.mark.mysql_check("sweep_worker", "hook_exception", parameter="startup_periodic")
def test_ordinary_hook_exception_isolated_in_startup_and_next_periodic_pass(resources):
    import json
    engine, startup = resources
    execution = add(engine, "dead")
    claim_one(engine, "dead")
    expire(engine, execution)
    stop, calls = Event(), []
    stream = StringIO()
    startup = Startup(startup.config, startup.modules, configure_logging("worker", stream=stream))
    def bad():
        calls.append("bad")
        raise RuntimeError("secret /private/ordinary payload")
    def later():
        calls.append("later")
        if calls.count("later") == 2:
            stop.set()
    compose_worker(engine=engine, startup=startup, stop=stop, registry=KindRegistry({}),
                   sweep_hooks=(bad, later)).run()
    assert calls == ["bad", "later", "bad", "later"]
    assert [r["status"] for r in rows(engine)] == ["STALE", "QUEUED"]
    assert engine.pool.checkedout() == 0
    assert not any(t.name.startswith("runtime-sweep") for t in threads())
    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert events.count("runtime.sweep.hook_failed") == 2
    assert "secret" not in stream.getvalue() and "private" not in stream.getvalue()
