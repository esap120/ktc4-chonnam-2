"""RT-04(a) uses real InnoDB, disconnects and a real lost COMMIT response."""

from importlib import import_module
from io import StringIO
import json
from threading import Event
from types import MappingProxyType

import pytest
from sqlalchemy import event, select

from daesingo.common.bootstrap import Startup
from daesingo.common.config import RuntimeConfig, DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.repository import enqueue
from daesingo.common.jobs.read_port import read_executions
from daesingo.common.jobs.schema import job_execution
from daesingo.common.logging import configure_logging
from mysql_fault_proxy import CommitResponseProxy
from logging_faults import install_logging_fault

pytestmark = pytest.mark.mysql


@pytest.fixture
def queue(mysql_schema_url):
    upgrade_all(mysql_schema_url)
    engine = create_worker_engine(DbSettings(url=mysql_schema_url.render_as_string(hide_password=False)))
    try:
        yield engine
    finally:
        engine.dispose()


def seed(queue, kinds=("TEST",)):
    with queue.begin() as conn:
        return enqueue(conn, [{"job_id": f"job_{i}", "case_id": "case", "kind": kind}
                              for i, kind in enumerate(kinds)], "trace")


def row(queue, execution_id):
    with queue.connect() as conn:
        return dict(conn.execute(select(job_execution).where(
            job_execution.c.execution_id == execution_id)).mappings().one())


def composed(queue, handlers, *, stop=None, stream=None, idle_wait=None, sleep=None, reflector=None):
    module = import_module("daesingo.worker.composition")
    registry = import_module("daesingo.worker.registry")
    stop = stop if stop is not None else Event()
    stream = stream if stream is not None else StringIO()
    config = RuntimeConfig.from_mapping("worker", {
        "DAESINGO_RUNTIME_DB_URL": queue.url.render_as_string(hide_password=False),
        "DAESINGO_RUNTIME_MEDIA_ROOT": "/private/media",
        "DAESINGO_RUNTIME_WORKER_TEMP_ROOT": "/private/temp",
    })
    startup = Startup(config, MappingProxyType({}), configure_logging("worker", stream=stream))
    def default_idle(seconds):
        assert seconds == 2
        stop.set()
    kwargs = dict(engine=queue, startup=startup, registry=registry.KindRegistry(handlers),
                  stop=stop, worker_id="worker", idle_wait=idle_wait or default_idle)
    if sleep is not None:
        kwargs["sleep"] = sleep
    if reflector is not None:
        kwargs["reflector"] = reflector
    return module.compose_worker(**kwargs)


@pytest.mark.mysql_check("worker_core", "success")
def test_worker_claim_dispatch_terminal_and_read_port_without_handler_transaction(queue):
    ids, called, stream = seed(queue, ("TEST", "TEST")), [], StringIO()
    from daesingo.common.jobs.execution import HandlerResult
    def handler(context):
        assert queue.pool.checkedout() == 0
        called.append(context)
        stored = row(queue, context.execution_id)
        assert stored["status"] == "RUNNING" and stored["claim_token"]
        return HandlerResult(produced=[{"kind": "Candidates", "ref": "cand_" + context.job_id}])
    composed(queue, {"TEST": handler}, stream=stream).run()
    assert {c.execution_id for c in called} == set(ids) and len(called) == 2
    for context in called:
        stored = row(queue, context.execution_id)
        assert stored["status"] == "SUCCEEDED"
        assert stored["produced"] == [{"kind": "Candidates", "ref": "cand_" + context.job_id}]
        assert stored["case_applied_at"] is None
    with queue.connect() as conn:
        snapshots = read_executions(conn, [c.job_id for c in called])
    assert all(s["status"] == "SUCCEEDED" and s["usage_refs"] == [] for s in snapshots)
    events = [json.loads(s) for s in stream.getvalue().splitlines()]
    executions = [e for e in events if e["event"].startswith("runtime.execution.")]
    assert [e["event"] for e in executions] == ["runtime.execution.started", "runtime.execution.completed"] * 2
    for context in called:
        for e in (e for e in executions if e["execution_id"] == context.execution_id):
            assert (e["trace_id"], e["case_id"], e["job_id"]) == ("trace", "case", context.job_id)
    assert all(word not in stream.getvalue() for word in ("claim_token", "private", "cand_"))


@pytest.mark.mysql_check("worker_core", "failure")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_core", "failure", parameter=s)) for s in ("unknown", "module", "exception", "invalid")])
def test_worker_failure_preserves_module_taxonomy_and_never_logs_input(queue, mode):
    execution_id, = seed(queue, ("TEST" if mode != "unknown" else "UNREGISTERED",))
    from daesingo.common.jobs.execution import HandlerResult
    stream, calls = StringIO(), []
    def handler(context):
        calls.append(context)
        assert queue.pool.checkedout() == 0
        if mode == "module":
            return HandlerResult(status="FAILED", failure_kind="SEARCH_ACCOUNT_BLOCKED",
                                 produced=[{"kind": "Partial", "ref": "partial_1"}])
        if mode == "exception":
            raise RuntimeError("/private/path secret user/provider payload")
        return {"payload": "secret"}
    composed(queue, {"TEST": handler}, stream=stream).run()
    stored = row(queue, execution_id)
    assert stored["status"] == "FAILED"
    assert len(calls) == (0 if mode == "unknown" else 1)
    assert stored["failure_kind"] == ("SEARCH_ACCOUNT_BLOCKED" if mode == "module" else
                                      "RUNTIME_UNREGISTERED_KIND" if mode == "unknown" else
                                      "RUNTIME_HANDLER_ERROR" if mode == "exception" else "RUNTIME_INVALID_RESULT")
    assert stored["produced"] == ([{"kind": "Partial", "ref": "partial_1"}] if mode == "module" else [])
    assert stored["case_applied_at"] is None
    assert all(word not in stream.getvalue() for word in ("private", "secret", "payload", "SEARCH_ACCOUNT_BLOCKED", stored["claim_token"]))


@pytest.mark.mysql_check("worker_core", "claim_db_recovery")
def test_real_claim_disconnect_exhaustion_keeps_process_alive_and_recovers(queue):
    execution_id, = seed(queue)
    waits, kills = [], []
    from daesingo.common.jobs.execution import HandlerResult
    def kill(conn, cursor, sql, *args):
        if "SKIP LOCKED" in sql.upper() and len(kills) < 3:
            identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with queue.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
            kills.append(identity)
    stop = Event()
    def idle(seconds):
        waits.append(seconds)
        assert queue.pool.checkedout() == 0
        if seconds == 2:
            stop.set()
    event.listen(queue, "before_cursor_execute", kill)
    try:
        composed(queue, {"TEST": lambda ctx: HandlerResult()}, stop=stop, idle_wait=idle).run()
    finally:
        event.remove(queue, "before_cursor_execute", kill)
    assert len(kills) == 3 and waits == [5, 2]
    assert row(queue, execution_id)["status"] == "SUCCEEDED"


@pytest.mark.mysql_check("worker_core", "terminal_db_recovery")
def test_real_terminal_retry_exhaustion_keeps_result_and_finishes_after_signal(queue):
    execution_id, = seed(queue)
    from daesingo.common.jobs.execution import HandlerResult
    calls, kills, waits, stream, stop = [], [], [], StringIO(), Event()
    def handler(ctx):
        calls.append(ctx)
        stop.set()
        return HandlerResult(produced=[{"kind": "Candidates", "ref": "cand_1"}])
    def kill(conn, cursor, sql, *args):
        if sql.upper().startswith("UPDATE JOB_EXECUTION SET STATUS") and len(kills) < 3:
            identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with queue.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
            kills.append(identity)
    def sleep(seconds):
        assert queue.pool.checkedout() == 0
        waits.append(seconds)
    event.listen(queue, "before_cursor_execute", kill)
    try:
        composed(queue, {"TEST": handler}, stop=stop, sleep=sleep, stream=stream).run()
    finally:
        event.remove(queue, "before_cursor_execute", kill)
    assert len(calls) == 1 and len(kills) == 3 and waits == [1, 1, 5]
    assert row(queue, execution_id)["produced"] == [{"kind": "Candidates", "ref": "cand_1"}]
    assert row(queue, execution_id)["status"] == "SUCCEEDED"
    events = [json.loads(s) for s in stream.getvalue().splitlines()]
    errors = [e for e in events if e["event"].startswith("runtime.db.") and e["event"] != "runtime.db.claim_latency_ms"]
    assert errors and all(e["execution_id"] == execution_id and e["job_id"] == "job_0" for e in errors)
    assert sum(e["event"] == "runtime.execution.completed" for e in events) == 1


@pytest.mark.mysql_check("worker_core", "terminal_unknown_commit")
@pytest.mark.parametrize("status", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_core", "terminal_unknown_commit", parameter=s)) for s in ("SUCCEEDED", "FAILED")])
def test_lost_terminal_commit_response_is_reread_and_completed_once(queue, status):
    execution_id, = seed(queue)
    from daesingo.common.jobs.execution import HandlerResult
    calls, waits, stream = [], [], StringIO()
    result = HandlerResult(status=status, failure_kind="SEARCH_FAILURE" if status == "FAILED" else None,
                           produced=[{"kind": "Candidates", "ref": "cand_1"}])
    def handler(ctx):
        calls.append(ctx)
        return result
    with CommitResponseProxy(queue.url.host, queue.url.port) as proxy:
        url = queue.url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        engine = create_worker_engine(DbSettings(url=url.render_as_string(hide_password=False)))
        def arm(conn, cursor, sql, *args):
            if sql.upper().startswith("UPDATE JOB_EXECUTION SET STATUS"):
                proxy.arm()
        event.listen(engine, "after_cursor_execute", arm)
        try:
            composed(engine, {"TEST": handler}, sleep=waits.append, stream=stream).run()
            assert proxy.commit_ok_dropped == 1 and waits == [1]
        finally:
            event.remove(engine, "after_cursor_execute", arm)
            engine.dispose()
    assert len(calls) == 1
    stored = row(queue, execution_id)
    assert stored["status"] == status and stored["failure_kind"] == result.failure_kind
    assert stored["produced"] == [r.model_dump() for r in result.produced]
    assert sum(json.loads(s)["event"] == "runtime.execution.completed" for s in stream.getvalue().splitlines()) == 1


@pytest.mark.mysql_check("worker_core", "finish_rejected")
def test_changed_owner_cannot_commit_handler_result(queue):
    execution_id, = seed(queue)
    from daesingo.common.jobs.execution import HandlerResult
    stream = StringIO()
    def handler(ctx):
        with queue.begin() as conn:
            conn.exec_driver_sql("UPDATE job_execution SET lease_owner='other' WHERE execution_id=%s", (execution_id,))
        return HandlerResult()
    composed(queue, {"TEST": handler}, stream=stream).run()
    stored = row(queue, execution_id)
    assert stored["status"] == "RUNNING" and stored["produced"] == []
    assert "runtime.execution.completed" not in stream.getvalue()
    assert "runtime.execution.finish_rejected" in stream.getvalue()


@pytest.mark.mysql_check("worker_core", "correlation")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "worker_core", "correlation", parameter=s)) for s in ("max_job_id", "path_id")])
def test_real_queue_storage_ids_preserve_correlation_without_disclosing_paths(queue, mode):
    from daesingo.common.jobs.execution import HandlerResult
    raw = "job_" + "a" * 187 if mode == "max_job_id" else "/private/path-secret\nuser payload"
    with queue.begin() as conn:
        execution_id, = enqueue(conn, [{"job_id": raw, "case_id": "case", "kind": "TEST"}], "trace")
    stream, calls = StringIO(), []
    def handler(ctx):
        calls.append(ctx.job_id)
        return HandlerResult()
    composed(queue, {"TEST": handler}, stream=stream).run()
    assert calls == [raw] and row(queue, execution_id)["status"] == "SUCCEEDED"
    events = [json.loads(s) for s in stream.getvalue().splitlines() if "runtime.execution." in s]
    assert len(events) == 2 and events[0]["job_id"] == events[1]["job_id"]
    if mode == "max_job_id":
        assert events[0]["job_id"] == raw
    else:
        assert events[0]["job_id"].startswith("id_")
        assert all(word not in stream.getvalue() for word in ("private", "secret", "payload"))


@pytest.mark.mysql_check("worker_core", "logger_isolation")
@pytest.mark.parametrize("scenario,sink", [pytest.param(scenario, sink, marks=pytest.mark.mysql_check(
    "worker_core", "logger_isolation", parameter=scenario + "_" + sink))
    for scenario in ("started", "completed", "claim_db", "terminal_db")
    for sink in ("filter", "handler")])
def test_logger_failure_preserves_real_terminal_and_retry_counts(queue, scenario, sink, capsys, monkeypatch):
    from daesingo.common.jobs.execution import HandlerResult
    from sqlalchemy.exc import OperationalError
    composition = import_module("daesingo.worker.composition")
    transaction = composition.run_worker_transaction
    observed = []

    def broken_observer(attempt):
        observed.append(attempt.outcome)
        # A DB-shaped sink failure must not become an extra transaction attempt.
        raise OperationalError("private SQL", {}, Exception(1213, "secret observer"))

    def record_transaction(engine, operation, **kwargs):
        return transaction(engine, operation, **kwargs, observe=broken_observer)

    monkeypatch.setattr(composition, "run_worker_transaction", record_transaction)
    execution_id, = seed(queue)
    calls, kills, sleeps, idles, stop = [], [], [], [], Event()

    def handler(ctx):
        calls.append(ctx)
        assert row(queue, execution_id)["status"] == "RUNNING"
        if scenario == "terminal_db":
            stop.set()
        return HandlerResult(produced=[{"kind": "Candidates", "ref": "cand_1"}])

    def kill(conn, cursor, sql, *args):
        target = ("SKIP LOCKED" in sql.upper() if scenario == "claim_db" else
                  sql.upper().startswith("UPDATE JOB_EXECUTION SET STATUS") if scenario == "terminal_db" else False)
        if target and len(kills) < 3:
            identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with queue.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
            kills.append(identity)

    def idle(seconds):
        assert queue.pool.checkedout() == 0
        idles.append(seconds)
        if seconds == 2:
            stop.set()

    def sleep(seconds):
        assert queue.pool.checkedout() == 0
        sleeps.append(seconds)

    worker = composed(queue, {"TEST": handler}, stop=stop, sleep=sleep, idle_wait=idle)
    wanted = ("runtime.execution." + scenario if scenario in ("started", "completed") else "runtime.db.")
    seen, remove = install_logging_fault(worker.logger, sink,
                                         lambda name: name == wanted if scenario in ("started", "completed") else name.startswith(wanted))
    event.listen(queue, "before_cursor_execute", kill)
    try:
        worker.run()
    finally:
        remove()
        event.remove(queue, "before_cursor_execute", kill)
    assert seen and len(calls) == 1
    stored = row(queue, execution_id)
    assert stored["status"] == "SUCCEEDED" and stored["produced"] == [{"kind": "Candidates", "ref": "cand_1"}]
    assert len(kills) == (3 if scenario in ("claim_db", "terminal_db") else 0)
    assert sleeps == ([1, 1, 5] if scenario == "terminal_db" else [])
    assert idles == ([5, 2] if scenario == "claim_db" else [] if scenario == "terminal_db" else [2])
    assert observed == (["DISCONNECT"] * 3 + ["COMMITTED"] if scenario == "terminal_db" else ["COMMITTED"])
    assert capsys.readouterr().err == ""
