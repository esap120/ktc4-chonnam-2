"""RT-06(a) real MySQL atomic stale/retry and competing owners."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module, util
from io import StringIO
import json
import time
from threading import Barrier, Event

import pytest
from sqlalchemy import event, func, select, text, update

from daesingo.common.config import WorkerSettings, DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.jobs.cancel import request_cancel
from daesingo.common.jobs.repository import claim_one, enqueue, finish
from daesingo.common.jobs.schema import job_execution as jobs
from daesingo.common.logging import configure_logging
from mysql_fault_proxy import CommitResponseProxy

pytestmark = pytest.mark.mysql


def sweep():
    assert util.find_spec("daesingo.common.jobs.sweep"), "RT-06 sweep missing"
    return import_module("daesingo.common.jobs.sweep")


@pytest.fixture
def queue(mysql_engine, mysql_schema_url):
    upgrade_all(mysql_schema_url)
    return mysql_engine


def add(engine, job="job"):
    with engine.begin() as conn:
        execution, = enqueue(conn, [{"job_id": job, "case_id": "case", "kind": "TEST"}], "trace")
    return execution


def rows(engine):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(jobs).order_by(jobs.c.job_id, jobs.c.attempt)).mappings()]


def expire(engine, execution):
    with engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.execution_id == execution).values(
            lease_expires_at=func.timestampadd(text("SECOND"), -1, func.now(6))))


@contextmanager
def listen(engine, name, callback):
    event.listen(engine, name, callback)
    try:
        yield
    finally:
        event.remove(engine, name, callback)


@pytest.mark.mysql_check("sweep", "atomicity")
@pytest.mark.parametrize("commit", [pytest.param(value, marks=pytest.mark.mysql_check(
    "sweep", "atomicity", parameter="commit" if value else "rollback")) for value in (False, True)])
def test_stale_and_new_queued_are_one_caller_transaction(queue, commit):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    with queue.connect() as conn:
        tx = conn.begin()
        result = sweep().sweep_expired(conn, execution, WorkerSettings())
        assert result is not None
        snapshot = list(conn.execute(select(jobs).order_by(jobs.c.attempt)).mappings())
        assert [r["status"] for r in snapshot] == ["STALE", "QUEUED"]
        assert snapshot[1]["attempt"] == 2 and snapshot[1]["execution_id"] != execution
        assert snapshot[0]["ended_at"] == snapshot[1]["queued_at"]
        assert snapshot[1]["available_at"] - snapshot[1]["queued_at"] == timedelta(seconds=5)
        for name in ("job_id", "case_id", "kind", "trace_id"):
            assert snapshot[1][name] == snapshot[0][name]
        assert snapshot[1]["produced"] == [] and snapshot[1]["lease_owner"] is None
        # Another connection sees neither uncommitted change.
        assert len(rows(queue)) == 1 and rows(queue)[0]["status"] == "RUNNING"
        tx.commit() if commit else tx.rollback()
    assert [r["status"] for r in rows(queue)] == (["STALE", "QUEUED"] if commit else ["RUNNING"])


@pytest.mark.mysql_check("sweep", "eligibility")
def test_sweep_only_expired_running_not_live_lease_or_terminal(queue):
    execution = add(queue)
    claim_one(queue, "owner")
    for status in ("QUEUED", "FAILED", "SUCCEEDED", "CANCELLED", "STALE"):
        other = add(queue, status)
        with queue.begin() as conn:
            conn.execute(update(jobs).where(jobs.c.execution_id == other).values(
                status=status, lease_expires_at=func.timestampadd(text("SECOND"), -1, func.now(6))))
    before = rows(queue)
    assert sweep().sweep_once(queue, WorkerSettings()) == ()
    assert rows(queue) == before
    expire(queue, execution)
    assert len(sweep().sweep_once(queue, WorkerSettings())) == 1
    assert sweep().sweep_once(queue, WorkerSettings()) == ()
    assert len(rows(queue)) == 7


@pytest.mark.mysql_check("sweep", "cap_cancel")
@pytest.mark.parametrize("reason", [pytest.param(value, marks=pytest.mark.mysql_check(
    "sweep", "cap_cancel", parameter=value)) for value in ("cancel", "exhausted", "disabled")])
def test_no_retry_for_marker_or_cap(queue, reason):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    settings = WorkerSettings(stale_retry_max=0 if reason == "disabled" else 1)
    if reason == "cancel":
        with queue.begin() as conn:
            request_cancel(conn, ["job"])
    elif reason == "exhausted":
        sweep().sweep_once(queue, settings)
        with queue.begin() as conn:
            conn.execute(update(jobs).where(jobs.c.attempt == 2).values(available_at=func.now(6)))
        execution = claim_one(queue, "next").execution_id
        expire(queue, execution)
    outcomes = sweep().sweep_once(queue, settings)
    assert len(outcomes) == 1
    assert outcomes[0].retry_execution_id is None
    assert outcomes[0].reason == ("CANCELLED" if reason == "cancel" else "EXHAUSTED")
    assert len(rows(queue)) == (2 if reason == "exhausted" else 1)
    assert rows(queue)[-1]["status"] == "STALE"


@pytest.mark.mysql_check("sweep", "backoff")
def test_backoff_does_not_claim_or_hold_other_work(queue):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    settings = WorkerSettings(stale_retry_backoff_base_sec=0.2)
    sweep().sweep_once(queue, settings)
    assert claim_one(queue, "owner") is None
    other = add(queue, "other")
    assert claim_one(queue, "owner").execution_id == other
    with queue.connect() as conn:
        conn.exec_driver_sql("SELECT SLEEP(0.25)")
    retry = claim_one(queue, "owner")
    assert retry.job_id == "job" and retry.attempt == 2
    assert retry.started_at >= rows(queue)[1]["available_at"].replace(tzinfo=retry.started_at.tzinfo)


@pytest.mark.mysql_check("sweep", "concurrent")
def test_two_sweepers_create_exactly_one_retry(queue):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    barrier = Barrier(2)
    def run():
        barrier.wait(10)
        return sweep().sweep_once(queue, WorkerSettings())
    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(run), pool.submit(run)
        outcomes = a.result(15) + b.result(15)
    assert len(outcomes) == 1
    assert [r["status"] for r in rows(queue)] == ["STALE", "QUEUED"]
    assert sweep().sweep_once(queue, WorkerSettings()) == ()


@pytest.mark.mysql_check("sweep", "recheck")
@pytest.mark.parametrize("change", [pytest.param(value, marks=pytest.mark.mysql_check(
    "sweep", "recheck", parameter=value)) for value in ("heartbeat", "finish", "cancel")])
def test_candidate_state_is_rechecked_under_lock(queue, change):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    changed = []
    def intervene(conn, cursor, sql, params, ctx, many):
        if "FOR UPDATE" in sql and not changed:
            changed.append(True)
            with queue.begin() as other:
                if change == "heartbeat":
                    other.execute(update(jobs).values(lease_expires_at=func.timestampadd(text("SECOND"), 60, func.now(6))))
                elif change == "finish":
                    assert finish(other, execution, "owner", status="SUCCEEDED") == 1
                else:
                    request_cancel(other, ["job"])
    with listen(queue, "before_cursor_execute", intervene):
        result = sweep().sweep_once(queue, WorkerSettings())
    assert changed and len(rows(queue)) == 1
    assert rows(queue)[0]["status"] == {"heartbeat": "RUNNING", "finish": "SUCCEEDED", "cancel": "STALE"}[change]
    assert len(result) == (1 if change == "cancel" else 0)


@pytest.mark.mysql_check("sweep", "rollback_retry")
def test_failed_insert_rolls_back_stale_and_b_d8_retries_whole_transaction(queue):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    failed, waits = [], []
    def fail(conn, cursor, sql, params, ctx, many):
        if sql.startswith("INSERT INTO job_execution") and not failed:
            failed.append(True)
            conn.exec_driver_sql("SIGNAL SQLSTATE '40001' SET MYSQL_ERRNO=1213, MESSAGE_TEXT='test fault'")
    def wait(seconds):
        assert len(rows(queue)) == 1 and rows(queue)[0]["status"] == "RUNNING"
        waits.append(seconds)
    with listen(queue, "before_cursor_execute", fail):
        result = sweep().sweep_once(queue, WorkerSettings(), sleep=wait)
    assert waits == [1] and len(result) == 1
    assert [r["status"] for r in rows(queue)] == ["STALE", "QUEUED"]


@pytest.mark.mysql_check("sweep", "unknown_commit")
def test_real_commit_response_loss_recovers_same_retry_without_duplicate(queue):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    with CommitResponseProxy(queue.url.host, queue.url.port) as proxy:
        url = queue.url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        engine = create_worker_engine(DbSettings(url=url.render_as_string(hide_password=False), pool_size=2, max_overflow=2))
        def arm(conn, cursor, sql, params, ctx, many):
            if sql.startswith("INSERT INTO job_execution"):
                proxy.arm()
        try:
            with listen(engine, "before_cursor_execute", arm):
                result = sweep().sweep_once(engine, WorkerSettings(), sleep=lambda s: None)
            assert len(result) == 1
            assert proxy.commit_ok_dropped == 1
        finally:
            engine.dispose()
    assert [r["status"] for r in rows(queue)] == ["STALE", "QUEUED"]
    assert rows(queue)[1]["execution_id"] == result[0].retry_execution_id


def test_requires_caller_transaction(queue):
    with queue.connect() as conn:
        with pytest.raises(ValueError, match="transaction"):
            sweep().sweep_expired(conn, "missing", WorkerSettings())


@pytest.mark.mysql_check("sweep", "expiry")
def test_no_heartbeat_naturally_expires_then_sweep_fences_old_owner(queue):
    execution = add(queue)
    claim_one(queue, "owner", lease_duration_sec=0.1)
    with queue.connect() as conn:
        conn.exec_driver_sql("SELECT SLEEP(0.15)")
    assert len(sweep().sweep_once(queue, WorkerSettings())) == 1
    with queue.begin() as conn:
        assert finish(conn, execution, "owner", status="SUCCEEDED") == 0
    assert rows(queue)[0]["status"] == "STALE"


@pytest.mark.mysql_check("sweep", "cancel_race")
@pytest.mark.parametrize("first", [pytest.param(value, marks=pytest.mark.mysql_check(
    "sweep", "cancel_race", parameter=value)) for value in ("sweep", "cancel")])
def test_real_cancel_and_sweep_transactions_serialize_marker_and_future_attempt(queue, first):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    if first == "cancel":
        with queue.begin() as conn:
            # Hold the marker uncommitted: the sweeper must skip this locked row.
            request_cancel(conn, ["job"])
            assert sweep().sweep_once(queue, WorkerSettings()) == ()
        result = sweep().sweep_once(queue, WorkerSettings())
        assert result[0].reason == "CANCELLED" and len(rows(queue)) == 1
    else:
        attempting, connection_ids = Event(), []
        def cancel():
            with queue.begin() as conn:
                connection_ids.append(conn.connection.driver_connection.thread_id())
                attempting.set()
                request_cancel(conn, ["job"])
        with ThreadPoolExecutor(1) as pool:
            with queue.begin() as conn:
                sweep().sweep_expired(conn, execution, WorkerSettings())
                cancellation = pool.submit(cancel)
                assert attempting.wait(5)
                deadline = time.monotonic() + 5
                with queue.connect() as control:
                    while time.monotonic() < deadline:
                        waiting = control.scalar(text("""SELECT COUNT(*)
                            FROM performance_schema.data_lock_waits w
                            JOIN performance_schema.threads t ON t.THREAD_ID=w.REQUESTING_THREAD_ID
                            WHERE t.PROCESSLIST_ID=:id"""), {"id": connection_ids[0]})
                        if waiting:
                            break
                        Event().wait(0.005)
                    assert waiting, "cancel did not wait on sweep's real InnoDB lock"
            cancellation.result(10)
        assert [r["status"] for r in rows(queue)] == ["STALE", "CANCELLED"]
        assert all(r["cancel_requested_at"] is not None for r in rows(queue))
    assert claim_one(queue, "owner") is None


@pytest.mark.mysql_check("sweep", "metrics")
def test_only_committed_recovery_emits_metrics_and_logging_failure_does_not_replay(queue, monkeypatch):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    stream = StringIO()
    logger = configure_logging("worker", stream=stream)
    assert len(sweep().sweep_once(queue, WorkerSettings(), logger=logger)) == 1
    assert sweep().sweep_once(queue, WorkerSettings(), logger=logger) == ()
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    names = [value["event"] for value in events]
    assert names.count("runtime.stale.count") == 1
    assert names.count("runtime.retry.auto_count") == 1
    delay = next(value for value in events if value["event"] == "runtime.stale.detect_latency_s")
    stored = rows(queue)[0]
    assert delay["duration_ms"] == pytest.approx(
        (stored["ended_at"] - stored["heartbeat_at"]).total_seconds() * 1000, abs=0.001)
    assert delay["execution_id"] == execution
    with queue.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.attempt == 2).values(available_at=func.now(6)))
    retry = claim_one(queue, "owner")
    expire(queue, retry.execution_id)
    monkeypatch.setattr(logger, "log", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("private")))
    result = sweep().sweep_once(queue, WorkerSettings(), logger=logger)
    assert result[0].reason == "EXHAUSTED" and len(rows(queue)) == 2


@pytest.mark.mysql_check("sweep", "detect_latency")
@pytest.mark.parametrize("lease,reason", [pytest.param(lease, reason, marks=pytest.mark.mysql_check(
    "sweep", "detect_latency", parameter=f"{lease}_{reason}"))
    for lease in (60, 7) for reason in ("RETRIED", "EXHAUSTED", "CANCELLED")])
def test_detect_latency_includes_lease_from_last_db_heartbeat(queue, lease, reason):
    execution = add(queue)
    claim_one(queue, "owner", lease_duration_sec=lease)
    with queue.begin() as conn:
        heartbeat = conn.scalar(select(func.timestampadd(text("SECOND"), -(lease + 1), func.now(6))))
        conn.execute(update(jobs).where(jobs.c.execution_id == execution).values(
            heartbeat_at=heartbeat, lease_expires_at=heartbeat + timedelta(seconds=lease)))
        if reason == "CANCELLED":
            request_cancel(conn, ["job"])
    stream = StringIO()
    outcome, = sweep().sweep_once(queue, WorkerSettings(stale_retry_max=0 if reason == "EXHAUSTED" else 1),
                                 logger=configure_logging("worker", stream=stream))
    stored = rows(queue)[0]
    assert outcome.reason == reason
    assert lease + 1 <= outcome.detect_latency_sec < lease + 3
    assert outcome.detect_latency_sec == (stored["ended_at"] - stored["heartbeat_at"]).total_seconds()
    metric, = [json.loads(line) for line in stream.getvalue().splitlines()
               if json.loads(line)["event"] == "runtime.stale.detect_latency_s"]
    assert metric["duration_ms"] / 1000 == pytest.approx(outcome.detect_latency_sec, abs=0.001)
    assert len(rows(queue)) == (2 if reason == "RETRIED" else 1)


@pytest.mark.mysql_check("sweep", "detect_boundary", parameter="transition_clock")
def test_stale_record_uses_update_time_even_when_transition_is_delayed(queue):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    floors = []
    def delay(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE job_execution SET") and not floors:
            conn.exec_driver_sql("SELECT SLEEP(0.2)")
            floors.append(conn.scalar(select(func.now(6))))
    with listen(queue, "before_cursor_execute", delay):
        outcome, = sweep().sweep_once(queue, WorkerSettings())
    stored = rows(queue)
    assert floors and stored[0]["ended_at"] >= floors[0]
    assert stored[0]["ended_at"] == outcome.ended_at == stored[1]["queued_at"]
    assert outcome.detect_latency_sec == (stored[0]["ended_at"] - stored[0]["heartbeat_at"]).total_seconds()


@pytest.mark.mysql_check("sweep", "detect_boundary")
@pytest.mark.parametrize("invalid", [pytest.param(mode, marks=pytest.mark.mysql_check(
    "sweep", "detect_boundary", parameter=mode)) for mode in ("null", "future")])
def test_invalid_heartbeat_omits_measurement_without_invented_fallback_or_lost_retry(queue, invalid):
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    with queue.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.execution_id == execution).values(
            heartbeat_at=None if invalid == "null" else func.timestampadd(text("HOUR"), 1, func.now(6))))
    stream = StringIO()
    outcome, = sweep().sweep_once(queue, WorkerSettings(), logger=configure_logging("worker", stream=stream))
    assert outcome.detect_latency_sec is None
    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert "runtime.stale.detect_latency_s" not in events
    assert "runtime.stale.count" in events and "runtime.retry.auto_count" in events
    assert [r["status"] for r in rows(queue)] == ["STALE", "QUEUED"]


@pytest.mark.mysql_check("sweep", "detect_fault")
@pytest.mark.parametrize("fault", [pytest.param(mode, marks=pytest.mark.mysql_check(
    "sweep", "detect_fault", parameter=mode)) for mode in ("calculation", "logger", "filter", "handler")])
def test_detect_measurement_fault_cannot_rollback_or_replay_recovery(queue, monkeypatch, fault):
    from logging_faults import install_logging_fault
    execution = add(queue)
    claim_one(queue, "owner")
    expire(queue, execution)
    stream = StringIO()
    logger = configure_logging("worker", stream=stream)
    calculations = []
    if fault == "calculation":
        def broken(outcome):
            calculations.append(outcome.execution_id)
            raise ValueError("secret /private/measurement")
        monkeypatch.setattr(sweep(), "_detect_latency", broken, raising=False)
    elif fault == "logger":
        def broken(*args, **kwargs):
            raise ValueError("secret /private/logger")
        monkeypatch.setattr(logger, "log", broken)
    else:
        _, remove = install_logging_fault(logger, fault, lambda event: event == "runtime.stale.detect_latency_s")
    try:
        outcome, = sweep().sweep_once(queue, WorkerSettings(), logger=logger)
        assert outcome.reason == "RETRIED"
        assert sweep().sweep_once(queue, WorkerSettings(), logger=logger) == ()
        assert [r["status"] for r in rows(queue)] == ["STALE", "QUEUED"]
        assert "secret" not in stream.getvalue() and "private" not in stream.getvalue()
        if fault == "calculation":
            assert calculations == [execution], "latency calculation has no isolated post-commit boundary"
    finally:
        if fault in ("filter", "handler"):
            remove()
