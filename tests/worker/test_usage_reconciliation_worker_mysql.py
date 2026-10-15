"""Real Worker startup/periodic/T1 integration and OS process-kill recovery."""

from datetime import timedelta
import multiprocessing
from threading import Event, enumerate as threads

import pytest
import sqlalchemy as sa

from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.schema import job_execution as jobs
from daesingo.common.db.transactions import run_worker_transaction
from usage_reconciliation_support import (
    RUN, begin, facts, job, rows, sink, spawned_usage_worker, worker, worker_config,
)

pytestmark = pytest.mark.mysql


@pytest.fixture
def resources(mysql_schema_url):
    upgrade_all(mysql_schema_url)
    cfg = worker_config(mysql_schema_url.render_as_string(hide_password=False))
    engine = create_worker_engine(cfg.db)
    try:
        yield engine, cfg
    finally:
        assert engine.pool.checkedout() == 0
        assert not any(t.name.startswith(("runtime-sweep", "runtime-heartbeat")) for t in threads())
        engine.dispose()


@pytest.mark.mysql_check("usage_reconciliation", "worker", parameter="normal_t1")
def test_normal_t1_finalizes_from_committed_produced_without_third_search_call(resources):
    engine, cfg = resources
    job(engine, "QUEUED")
    stop, calls = Event(), []
    def handler(context):
        try:
            identity = begin(context.usage_sink)
            assert engine.pool.checkedout() == 0
            calls.append(identity)
            context.usage_sink.finish(identity, **facts())
            assert rows(engine)[1] == []
            return HandlerResult(produced=(RUN,))
        finally:
            # Worker converts ordinary handler exceptions into terminal facts;
            # a failed test assertion must still stop this one-job fixture.
            stop.set()
    loop = worker(engine, cfg, stop, handler)
    # This test selects post-T1 finalization. A periodic pass already in flight
    # may legitimately win recovery and owns its own pooled connection. Keep
    # startup reconciliation and real DB transactions, but park periodic work
    # until cleanup. The startup/periodic tests below exercise those paths.
    loop.sweeper.wait = lambda _: loop.sweeper.stop.wait()
    loop.run()
    tracker, final = rows(engine)
    assert len(calls) == len(final) == 1
    assert final[0]["run_ref"] == RUN["ref"]
    assert tracker[0]["recovered_at"] is None


@pytest.mark.mysql_check("usage_reconciliation", "worker", parameter="finish_persistence_replay")
def test_failed_finish_then_normal_failed_t1_allows_persistence_replay(resources):
    engine, cfg = resources
    job(engine, "QUEUED")
    stop, calls, saved = Event(), [], []
    def handler(context):
        s = context.usage_sink
        identity = begin(s)
        calls.append(identity)
        saved.append((s, identity))
        original = s._transaction
        def failed_transaction(callback):
            def operation(conn):
                callback(conn)
                raise RuntimeError("private SQL")
            return run_worker_transaction(engine, operation)
        s._transaction = failed_transaction
        try:
            s.finish(identity, **facts())
        finally:
            s._transaction = original
            stop.set()
        raise AssertionError("finish must fail")
    worker(engine, cfg, stop, handler).run()
    before = rows(engine)[1]
    assert len(before) == 1 and before[0]["input_tokens"] is None
    with engine.connect() as conn:
        assert conn.scalar(sa.select(jobs.c.failure_kind)) == "RUNTIME_USAGE_PERSISTENCE"
    s, identity = saved[0]
    s.finish(identity, **facts())
    tracker, final = rows(engine)
    assert final == before and calls == [identity]
    assert tracker[0]["input_tokens"] == 2 and tracker[0]["late_observed_at"] is not None


@pytest.mark.parametrize("mode", [
    pytest.param(m, marks=pytest.mark.mysql_check("usage_reconciliation", "worker", parameter=m))
    for m in ("startup", "periodic")])
def test_hooks_run_after_stale_transactions_and_preserve_live_execution(resources, mode):
    engine, cfg = resources
    job(engine, "RUNNING", execution="live")
    live_identity = begin(sink(engine, "live"))
    live_before = rows(engine)[0]
    stop, completed, calls = Event(), Event(), []
    job(engine, "QUEUED", execution="work")
    def add_terminal():
        job(engine, "STALE", execution="dead")
        s = sink(engine, "dead")
        identity = begin(s)
        calls.append(identity)
        s.finish(identity, **facts())
    if mode == "startup": add_terminal()
    def hook():
        # Connections used by sweep/reconciliation must already be returned.
        assert engine.pool.checkedout() == 0
        if rows(engine)[1]: completed.set()
    def handler(context):
        if mode == "periodic": add_terminal()
        try:
            assert completed.wait(10)
        finally:
            stop.set()
        return HandlerResult()
    worker(engine, cfg, stop, handler, (hook,)).run()
    tracker, final = rows(engine)
    assert len(final) == len(calls) == 1 and final[0]["input_tokens"] == 2
    assert final[0]["run_ref_reason"] == "RUN_NOT_PRODUCED"
    assert [r for r in tracker if r["usage_id"] == live_identity] == live_before


@pytest.mark.parametrize("mode", [
    pytest.param(m, marks=pytest.mark.mysql_check("usage_reconciliation", "process_kill", parameter=m))
    for m in ("startup", "periodic")])
def test_kill_after_finish_before_t1_recovers_exactly_one_final(resources, mode):
    engine, cfg = resources
    job(engine, "QUEUED")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=spawned_usage_worker,
        args=(engine.url.render_as_string(hide_password=False), child))
    process.start()
    child.close()
    try:
        assert parent.poll(20), "Worker did not reach durable finish"
        stage, execution, identity, provider_calls = parent.recv()
        assert stage == "OBSERVED" and provider_calls == 1
        assert rows(engine)[1] == []
        process.kill()
        process.join(10)
        assert not process.is_alive() and process.exitcode != 0
        stop, recovered = Event(), Event()
        def expire():
            with engine.begin() as conn:
                conn.execute(jobs.update().where(jobs.c.execution_id == execution).values(
                    lease_expires_at=sa.func.now(6) - sa.text("INTERVAL 1 SECOND")))
        if mode == "startup": expire()
        def hook():
            if rows(engine)[1]: recovered.set()
        loop = worker(engine, cfg, stop, hooks=(hook,))
        try:
            loop.sweeper.start()
            if mode == "periodic":
                assert rows(engine)[1] == []
                expire()
            assert recovered.wait(10)
        finally:
            stop.set()
            loop.sweeper.stop_and_join()
        tracker, final = rows(engine)
        assert len(final) == 1 and final[0]["usage_id"] == identity
        assert final[0]["input_tokens"] == 2 and final[0]["latency_ms"] == 17
        assert final[0]["run_ref"] is None and final[0]["run_ref_reason"] == "RUN_NOT_PRODUCED"
        assert tracker[0]["state"] == "FINALIZED"
        assert provider_calls == 1
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        parent.close()
        process.close()
