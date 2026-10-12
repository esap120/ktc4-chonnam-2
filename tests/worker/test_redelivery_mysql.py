"""RT-06(b): real Case/Runtime T2, concurrent locks, COMMIT loss and OS kills."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from io import StringIO
import json
import multiprocessing
from threading import Barrier, Event
from types import MappingProxyType

import pytest
import sqlalchemy as sa

from daesingo.common.bootstrap import Startup
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.schema import job_execution as jobs
from daesingo.common.logging import configure_logging
from daesingo.worker.composition import compose_worker
from daesingo.worker.registry import KindRegistry
from logging_faults import install_logging_fault
from mysql_fault_proxy import CommitResponseProxy
from redelivery_support import adapter, config, row, seed, snapshot, spawned_worker, store

pytestmark = pytest.mark.mysql


def parameters(scenario, modes):
    return [pytest.param(mode, marks=pytest.mark.mysql_check(
        "redelivery", scenario, parameter=mode)) for mode in modes]


@pytest.fixture
def resources(mysql_schema_url):
    upgrade_all(mysql_schema_url)
    cfg = config(mysql_schema_url.render_as_string(hide_password=False))
    engine = create_worker_engine(cfg.db)
    try:
        yield engine, cfg
    finally:
        engine.dispose()


def deliver(engine, reflector=None, **kwargs):
    return import_module("daesingo.common.jobs.redelivery").redeliver_once(
        engine, reflector or adapter(), sleep=lambda seconds: None, **kwargs)


@pytest.mark.mysql_check("redelivery", "eligibility")
@pytest.mark.parametrize("mode", parameters("eligibility", (
    "SUCCEEDED", "FAILED", "CANCELLED", "STALE", "QUEUED", "RUNNING", "receipt")))
def test_only_supported_unapplied_terminal_is_delivered(resources, mode):
    engine, _ = resources
    case_id, execution_id = seed(engine)
    with engine.begin() as conn:
        if mode != "receipt":
            conn.execute(jobs.update().where(jobs.c.execution_id == execution_id).values(
                status=mode, failure_kind="TEST_FAILED" if mode == "FAILED" else None))
        else:
            conn.execute(jobs.update().values(case_applied_at=sa.func.now(6)))
    calls = []
    actual = adapter()

    class Spy:
        def reflect(self, conn, incoming):
            calls.append(incoming)
            return actual.reflect(conn, incoming)
    deliver(engine, Spy())
    assert len(calls) == int(mode in ("SUCCEEDED", "FAILED"))
    assert bool(snapshot(engine, case_id).processed_executions) == bool(calls)
    assert (row(engine, execution_id)["case_applied_at"] is not None) == (bool(calls) or mode == "receipt")
    deliver(engine, Spy())
    assert len(calls) == int(mode in ("SUCCEEDED", "FAILED"))


@pytest.mark.mysql_check("redelivery", "atomicity")
@pytest.mark.parametrize("mode", parameters("atomicity", ("success", "failed_hint", "enqueue", "marker")))
def test_case_followup_enqueue_and_receipt_are_one_commit(resources, mode):
    engine, _ = resources
    case_id, execution_id = seed(engine, description="test description",
        status="FAILED" if mode == "failed_hint" else "SUCCEEDED")

    def fail(conn, cursor, sql, *args):
        target = "INSERT INTO JOB_EXECUTION" if mode == "enqueue" else "UPDATE JOB_EXECUTION SET CASE_APPLIED_AT"
        if mode in ("enqueue", "marker") and sql.upper().startswith(target):
            raise RuntimeError("secret SQL payload")
    sa.event.listen(engine, "before_cursor_execute", fail)
    try:
        deliver(engine)
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail)
    applied = mode in ("success", "failed_hint")
    case = snapshot(engine, case_id)
    assert len(case.processed_executions) == int(applied)
    assert len(case.job_records) == 1 + int(applied)
    assert (row(engine, execution_id)["case_applied_at"] is not None) == applied
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(jobs)) == 1 + int(applied)
    if not applied:
        deliver(engine)
        assert len(snapshot(engine, case_id).job_records) == 2


@pytest.mark.mysql_check("redelivery", "concurrent")
@pytest.mark.mysql_check("redelivery", "concurrent", parameter="case_first")
def test_concurrent_sweeper_locks_case_before_runtime_and_enqueues_once(resources):
    engine, _ = resources
    case_id, execution_id = seed(engine, description="test")
    barrier = Barrier(2)
    actual = adapter()

    class Concurrent:
        def reflect(self, conn, incoming):
            # Both scans/rechecks entered before either Case reflection.
            barrier.wait(10)
            return actual.reflect(conn, incoming)
    statements = []

    def observe(conn, cursor, sql, *args):
        if "FOR UPDATE" in sql.upper():
            statements.append((id(conn), sql.upper()))
    sa.event.listen(engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(deliver, engine, Concurrent()) for _ in range(2)]
            for future in futures:
                future.result(20)
    finally:
        sa.event.remove(engine, "before_cursor_execute", observe)
    for connection in {identity for identity, _ in statements}:
        ordered = [sql for identity, sql in statements if identity == connection]
        assert "CASES" in ordered[0]
        assert any("JOB_EXECUTION" in sql for sql in ordered[1:])
    case = snapshot(engine, case_id)
    assert case.processed_executions == {execution_id: row(engine, execution_id)["job_id"]}
    assert len(case.job_records) == 2
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(jobs)) == 2


@pytest.mark.mysql_check("redelivery", "commit_unknown")
@pytest.mark.parametrize("mode", parameters("commit_unknown", ("followup", "stopped")))
def test_commit_ack_loss_recovers_receipt_without_duplicate_effect(resources, mode):
    engine, cfg = resources
    case_id, execution_id = seed(engine, description="test" if mode == "followup" else "", attempt=2)
    if mode == "stopped":
        with engine.begin() as conn:
            case = store(conn).load_for_update(case_id)
            case.settle_job(row(engine, execution_id)["job_id"], reason="STOPPED_WAITING")
            store(conn).save(case)
    stream = StringIO()
    with CommitResponseProxy(engine.url.host, engine.url.port) as proxy:
        url = engine.url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        proxied = create_worker_engine(config(url.render_as_string(hide_password=False)).db)

        def arm(conn, cursor, sql, *args):
            if sql.upper().startswith("UPDATE JOB_EXECUTION SET CASE_APPLIED_AT"):
                proxy.arm()
        sa.event.listen(proxied, "after_cursor_execute", arm)
        try:
            deliver(proxied, logger=configure_logging("worker", stream=stream))
            assert proxy.commit_ok_dropped == 1
        finally:
            sa.event.remove(proxied, "after_cursor_execute", arm)
            proxied.dispose()
    assert row(engine, execution_id)["case_applied_at"] is not None
    assert len(snapshot(engine, case_id).job_records) == (2 if mode == "followup" else 1)
    assert "runtime.retry.after_case_stopped_count" not in stream.getvalue()
    assert "runtime.reflect.failed" not in stream.getvalue()


@pytest.mark.mysql_check("redelivery", "isolation")
@pytest.mark.parametrize("mode", parameters("isolation", ("reflector", "db", "logger", "filter", "handler", "scan")))
def test_fault_isolation_next_candidate_and_next_cycle(resources, mode, monkeypatch):
    engine, _ = resources
    case_a, first = seed(engine)
    case_b, second = seed(engine)
    stream = StringIO()
    logger = configure_logging("worker", stream=stream)
    actual = adapter()
    attempts = []

    class Fault:
        def reflect(self, conn, incoming):
            attempts.append(incoming.execution_id)
            if incoming.execution_id == first and mode in ("reflector", "db"):
                if mode == "db":
                    identity = conn.scalar(sa.text("SELECT CONNECTION_ID()"))
                    with engine.connect() as control:
                        control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
                    conn.execute(sa.text("SELECT 1"))  # real disconnect, three B-D8 attempts
                    pytest.fail("killed connection unexpectedly usable")
                raise ValueError("secret reflector")
            return actual.reflect(conn, incoming)
    remove = lambda: None
    if mode in ("filter", "handler"):
        _, remove = install_logging_fault(logger, mode, lambda e: True)
    if mode == "logger":
        monkeypatch.setattr(logger, "log", lambda *a, **k: (_ for _ in ()).throw(ValueError("secret logger")))
    scan_fault = []

    def fail_scan(conn, cursor, sql, *args):
        if mode == "scan" and not scan_fault and sql.upper().startswith("SELECT"):
            scan_fault.append(True)
            raise sa.exc.OperationalError("secret SQL", {}, Exception(2003, "secret scan"))
    sa.event.listen(engine, "before_cursor_execute", fail_scan)
    try:
        if mode == "scan":
            with pytest.raises(sa.exc.OperationalError):
                deliver(engine, Fault(), logger=logger)
        else:
            deliver(engine, Fault(), logger=logger)
    finally:
        remove()
        sa.event.remove(engine, "before_cursor_execute", fail_scan)
    if mode != "scan":
        assert row(engine, second)["case_applied_at"] is not None
        assert (row(engine, first)["case_applied_at"] is None) == (mode in ("reflector", "db"))
        if mode == "db":
            assert attempts.count(first) == 3
    deliver(engine, logger=logger)
    assert all(row(engine, execution)["case_applied_at"] is not None for execution in (first, second))
    assert len(snapshot(engine, case_a).processed_executions) == len(snapshot(engine, case_b).processed_executions) == 1
    assert "secret" not in stream.getvalue()


@pytest.mark.mysql_check("redelivery", "unsupported")
@pytest.mark.parametrize("mode", parameters("unsupported", ("PLATE_READ", "UNKNOWN")))
def test_unsupported_kind_failed_t1_remains_unreceipted_and_other_case_progresses(resources, mode):
    engine, cfg = resources
    if mode == "PLATE_READ":
        from daesingo.case import jobs as case_jobs, service
        from daesingo.common.jobs.repository import enqueue
        with engine.begin() as conn:
            case_id = service.create_case(store=store(conn))
            case = store(conn).load_for_update(case_id)
            record = case_jobs.issue_plate_read(case, input_fingerprint="test_plate")
            store(conn).save(case)
            execution_id, = enqueue(conn, [record], "trace_redelivery")
        assert snapshot(engine, case_id).job_records[0]["kind"] == mode
    else:
        # UNKNOWN is not a Case JobRecord kind: exercise the distinct wiring
        # mismatch without extending Case's accepted kind vocabulary.
        case_id, execution_id = seed(engine, terminal=False)
        with engine.begin() as conn:
            conn.execute(jobs.update().where(jobs.c.execution_id == execution_id).values(kind=mode))
        assert snapshot(engine, case_id).job_records[0]["kind"] == "COARSE_SEARCH"
    reasons = []
    actual = adapter()

    class FailClosed:
        def reflect(self, conn, incoming):
            try:
                return actual.reflect(conn, incoming)
            except ValueError as error:
                reasons.append(str(error))
                raise
    stop = Event()
    stream = StringIO()
    startup = Startup(cfg, MappingProxyType({}), configure_logging("worker", stream=stream))
    worker = compose_worker(engine=engine, startup=startup, registry=KindRegistry({}), stop=stop,
        reflector=FailClosed(), idle_wait=lambda seconds: stop.set())
    worker.run()  # Unregistered kind really reaches T1 FAILED and T2.
    assert row(engine, execution_id)["failure_kind"] == "RUNTIME_UNREGISTERED_KIND"
    assert row(engine, execution_id)["case_applied_at"] is None
    assert reasons and all(("반영기가 없는 kind" if mode == "PLATE_READ" else "kind가 다르다") in reason
                           for reason in reasons)
    other_case, other = seed(engine)
    for _ in range(2):
        deliver(engine, logger=startup.logger)
    assert row(engine, other)["case_applied_at"] is not None
    assert row(engine, execution_id)["case_applied_at"] is None
    assert snapshot(engine, case_id).processed_executions == {}
    assert len(snapshot(engine, other_case).processed_executions) == 1
    assert "runtime.reflect.failed" in stream.getvalue()


@pytest.mark.mysql_check("redelivery", "metric")
@pytest.mark.parametrize("mode", parameters("metric", (
    "first_stopped", "retry_stopped", "third_stopped", "CANCELLED", "SUPERSEDED", "APPLIED")))
def test_redelivery_metrics_preserve_after_case_stopped_meaning(resources, mode):
    engine, _ = resources
    case_id, execution_id = seed(engine, attempt=1 if mode == "first_stopped" else 3 if mode == "third_stopped" else 2)
    if mode != "APPLIED":
        with engine.begin() as conn:
            case = store(conn).load_for_update(case_id)
            case.settle_job(row(engine, execution_id)["job_id"], reason=mode if mode in ("CANCELLED", "SUPERSEDED") else "STOPPED_WAITING")
            store(conn).save(case)
    stream = StringIO()
    logger = configure_logging("worker", stream=stream)
    deliver(engine, logger=logger)
    deliver(engine, logger=logger)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    count = [e for e in events if e["event"] == "runtime.retry.after_case_stopped_count"]
    assert len(count) == int(mode in ("retry_stopped", "third_stopped"))
    redelivery = [e for e in events if e["event"] == "runtime.reflect.redelivery_count"]
    assert len(redelivery) == 1
    assert redelivery[0]["execution_id"] == execution_id


@pytest.mark.mysql_check("redelivery", "startup_periodic")
@pytest.mark.parametrize("mode", parameters("startup_periodic", ("startup", "periodic")))
def test_composition_redelivers_before_first_claim_and_during_blocked_handler(resources, mode):
    engine, cfg = resources
    old_case, old = seed(engine, terminal=mode == "startup")
    if mode == "periodic":
        from daesingo.common.jobs.repository import claim_one, finish
        assert claim_one(engine, "old").execution_id == old
    current_case, current = seed(engine, terminal=False)
    stop = Event()
    startup = Startup(cfg, MappingProxyType({}), configure_logging("worker", stream=StringIO()))
    actual = adapter()
    applied = Event()

    class Observe:
        def reflect(self, conn, incoming):
            value = actual.reflect(conn, incoming)
            if incoming.execution_id == old:
                applied.set()
            return value

    def handler(context):
        assert context.execution_id == current
        if mode == "startup":
            assert row(engine, old)["case_applied_at"] is not None
        else:
            with engine.begin() as conn:
                assert finish(conn, old, "old", status="SUCCEEDED") == 1
            assert applied.wait(10)
        stop.set()
        return HandlerResult()
    worker = compose_worker(engine=engine, startup=startup, registry=KindRegistry({"COARSE_SEARCH": handler}),
        stop=stop, reflector=Observe())
    original_claim = worker.claim

    def claim():
        if mode == "startup":
            assert row(engine, old)["case_applied_at"] is not None
        return original_claim()
    worker.claim = claim
    worker.run()
    assert row(engine, old)["case_applied_at"] is not None
    assert len(snapshot(engine, old_case).processed_executions) == 1


@pytest.mark.mysql_check("redelivery", "process_kill")
@pytest.mark.parametrize("mode", parameters("process_kill", ("gap", "running")))
def test_actual_process_kill_recovers_durable_case_exactly_once(resources, mode):
    engine, cfg = resources
    case_id, execution_id = seed(engine, terminal=False)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=spawned_worker, args=(
        engine.url.render_as_string(hide_password=False), mode, child))
    replacement = receiver = sender = None
    try:
        process.start()
        child.close()
        assert parent.poll(30), "child did not reach the kill barrier"
        phase, observed = parent.recv()
        assert (phase, observed) == ("T1" if mode == "gap" else "RUNNING", execution_id)
        before = row(engine, execution_id)  # independent connection proves durable state
        assert before["status"] == ("SUCCEEDED" if mode == "gap" else "RUNNING")
        assert before["case_applied_at"] is None
        assert snapshot(engine, case_id).processed_executions == {}
        process.kill()
        process.join(10)
        assert not process.is_alive() and process.exitcode not in (None, 0)
        if mode == "gap":
            # No remaining claimable work: startup must still perform T2.
            stop = Event()
            startup = Startup(cfg, MappingProxyType({}), configure_logging("worker", stream=StringIO()))
            worker = compose_worker(engine=engine, startup=startup, registry=KindRegistry({}), stop=stop,
                reflector=adapter(), idle_wait=lambda seconds: stop.set())
            original = worker.claim

            def claim():
                assert row(engine, execution_id)["case_applied_at"] is not None
                return original()
            worker.claim = claim
            worker.run()
        else:
            receiver, sender = context.Pipe()
            replacement = context.Process(target=spawned_worker, args=(
                engine.url.render_as_string(hide_password=False), "recover", sender))
            replacement.start()
            sender.close()
            assert receiver.poll(30), "replacement did not finish lease recovery"
            assert receiver.recv() == ("DONE", None)
            replacement.join(10)
            receiver.close()
            assert not replacement.is_alive() and replacement.exitcode == 0
        with engine.connect() as conn:
            executions = list(conn.execute(sa.select(jobs).where(jobs.c.case_id == case_id)
                .order_by(jobs.c.attempt)).mappings())
        assert [r["status"] for r in executions] == (["SUCCEEDED"] if mode == "gap" else ["STALE", "SUCCEEDED"])
        assert [r["attempt"] for r in executions] == ([1] if mode == "gap" else [1, 2])
        final = executions[-1]
        assert final["case_applied_at"] is not None
        if mode == "running":
            assert executions[0]["case_applied_at"] is None
            assert executions[0]["ended_at"] > before["lease_expires_at"]
            assert final["started_at"] >= final["available_at"]
        case = snapshot(engine, case_id)
        assert case.processed_executions == {final["execution_id"]: final["job_id"]}
        assert case.stage == "CANDIDATE_REVIEW"
        assert len(case.candidates) == 1
        deliver(engine)
        assert snapshot(engine, case_id).processed_executions == case.processed_executions
    finally:
        for owned in (process, replacement):
            if owned is not None and owned.pid is not None:
                if owned.is_alive():
                    owned.kill()
                owned.join(10)
                assert not owned.is_alive()
                owned.close()
        parent.close()
        child.close()
        if receiver is not None:
            receiver.close()
        if sender is not None:
            sender.close()
