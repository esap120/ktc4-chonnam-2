"""Receipts and real faults must never dispatch a second or foreign claim."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
from threading import Barrier, Event

import pytest
from sqlalchemy import event

from daesingo.common.config import DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.db import transactions
from daesingo.common.logging import configure_logging
from mysql_fault_proxy import CommitResponseProxy
from test_lifecycle_mysql import queue, repo, seed, row, listener, terminal_args

pytestmark = pytest.mark.mysql


def with_retry_hook(monkeypatch, repo, hook):
    def run(engine, operation, **kwargs):
        return transactions.run_worker_transaction(engine, operation, sleep=hook, **kwargs)
    monkeypatch.setattr(repo, "run_worker_transaction", run)


@pytest.mark.mysql_check("jobs", "claim_unknown_commit")
@pytest.mark.parametrize("mode", [pytest.param(s, marks=pytest.mark.mysql_check(
    "jobs", "claim_unknown_commit", parameter=s)) for s in
    ("recovered", "token", "owner", "terminal", "expired", "missing")])
def test_real_commit_response_loss_recovers_only_same_durable_receipt(queue, repo, monkeypatch, mode):
    ids = seed(queue, 2)
    original = []
    waits = []
    def retry(seconds):
        waits.append(seconds)
        with queue.begin() as conn:
            receipt = conn.exec_driver_sql("SELECT execution_id,claim_token FROM job_execution WHERE status='RUNNING'").one()
            original.append(receipt)
            execution_id = receipt[0]
            if mode == "token":
                conn.exec_driver_sql("UPDATE job_execution SET claim_token='other_token' WHERE execution_id=%s", (execution_id,))
            elif mode == "owner":
                conn.exec_driver_sql("UPDATE job_execution SET lease_owner='other_owner' WHERE execution_id=%s", (execution_id,))
            elif mode == "terminal":
                conn.exec_driver_sql("UPDATE job_execution SET status='SUCCEEDED',ended_at=NOW(6) WHERE execution_id=%s", (execution_id,))
            elif mode == "expired":
                conn.exec_driver_sql("UPDATE job_execution SET lease_expires_at=NOW(6) WHERE execution_id=%s", (execution_id,))
            elif mode == "missing":
                conn.exec_driver_sql("DELETE FROM job_execution WHERE execution_id=%s", (execution_id,))
    with_retry_hook(monkeypatch, repo, retry)
    with CommitResponseProxy(queue.url.host, queue.url.port) as proxy:
        url = queue.url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        engine = create_worker_engine(DbSettings(url=url.render_as_string(hide_password=False)))
        statements = []
        def arm(conn, cursor, sql, *args):
            statements.append(sql)
            if sql.lstrip().upper().startswith("UPDATE JOB_EXECUTION"):
                proxy.arm()
        try:
            with listener(engine, "before_cursor_execute", arm):
                if mode == "recovered":
                    result = repo.claim_one(engine, "worker")
                    assert result.execution_id == original[0][0]
                    assert row(queue, result.execution_id)["claim_token"] == original[0][1]
                else:
                    with pytest.raises(repo.ClaimLostError):
                        repo.claim_one(engine, "worker")
            assert waits == [1] and proxy.commit_ok_dropped == 1
            assert sum("SKIP LOCKED" in sql.upper() for sql in statements) == 1
            assert not any(sql.lstrip().upper().startswith("INSERT") for sql in statements)
            untouched, = set(ids) - {original[0][0]}
            assert row(queue, untouched)["status"] == "QUEUED"
        finally:
            engine.dispose()


@pytest.mark.mysql_check("jobs", "claim_token_identity")
@pytest.mark.mysql_check("jobs", "claim_disconnect")
def test_precommit_disconnect_then_same_worker_foreign_token_is_not_returned(queue, repo, monkeypatch):
    ids = seed(queue, 2)
    original_tokens, foreign = [], []
    def kill_after_update(conn, cursor, sql, params, *args):
        if sql.lstrip().upper().startswith("UPDATE JOB_EXECUTION") and not original_tokens:
            original_tokens.append(params["token"])
            identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with queue.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
    def retry(seconds):
        assert seconds == 1
        assert all(row(queue, i)["status"] == "QUEUED" for i in ids)
        foreign.append(repo.claim_one(queue, "same_worker"))
    with_retry_hook(monkeypatch, repo, retry)
    with listener(queue, "after_cursor_execute", kill_after_update):
        with pytest.raises(repo.ClaimLostError):
            repo.claim_one(queue, "same_worker")
    assert len(foreign) == 1
    receipt = row(queue, foreign[0].execution_id)
    assert receipt["lease_owner"] == "same_worker" and receipt["claim_token"] != original_tokens[0]
    assert sum(row(queue, i)["status"] == "RUNNING" for i in ids) == 1


@pytest.mark.mysql_check("jobs", "claim_disconnect")
def test_real_precommit_disconnect_replays_same_id_and_token(queue, repo, monkeypatch):
    ids = seed(queue, 2)
    tokens, attempts, sleeps = [], [], []
    def after_update(conn, cursor, sql, params, *args):
        if sql.lstrip().upper().startswith("UPDATE JOB_EXECUTION"):
            tokens.append(params["token"])
            attempts.append(params["execution_id"])
            if len(tokens) == 1:
                identity = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
                with queue.connect() as control:
                    control.exec_driver_sql(f"KILL CONNECTION {int(identity)}")
    def retry(seconds):
        sleeps.append(seconds)
        assert all(row(queue, i)["status"] == "QUEUED" and row(queue, i)["claim_token"] is None for i in ids)
    with_retry_hook(monkeypatch, repo, retry)
    with listener(queue, "after_cursor_execute", after_update):
        claimed = repo.claim_one(queue, "worker")
    assert sleeps == [1] and len(tokens) == 2 and len(set(tokens)) == len(set(attempts)) == 1
    assert claimed.execution_id == attempts[0]
    assert sum(row(queue, i)["status"] == "RUNNING" for i in ids) == 1


@pytest.mark.mysql_check("jobs", "finish_race")
@pytest.mark.parametrize("first,commit", [pytest.param(s, committed, marks=pytest.mark.mysql_check(
    "jobs", "finish_race", parameter=s + ("_commit" if committed else "_rollback")))
    for s in ("SUCCEEDED", "FAILED", "CANCELLED") for committed in (True, False)])
def test_competing_terminal_first_commit_wins_or_rollback_allows_second(queue, repo, first, commit):
    execution_id, = seed(queue)
    repo.claim_one(queue, "worker")
    second = "CANCELLED" if first != "CANCELLED" else "SUCCEEDED"
    updating = Event()
    second_connection = []
    def pending(conn, cursor, sql, *args):
        if sql.lstrip().upper().startswith("UPDATE JOB_EXECUTION") and second_connection and conn is second_connection[0]:
            updating.set()
    with queue.connect() as a, listener(queue, "before_cursor_execute", pending):
        tx = a.begin()
        assert repo.finish(a, execution_id, "worker", **terminal_args(first)) == 1
        def contender():
            with queue.begin() as b:
                second_connection.append(b)
                return repo.finish(b, execution_id, "worker", **terminal_args(second))
        with ThreadPoolExecutor(max_workers=1) as pool:
            b = pool.submit(contender)
            try:
                assert updating.wait(15)
                # DB lock-wait evidence, not a timer or Future.done() guess.
                with queue.connect() as control:
                    for _ in range(10000):
                        waiting = control.exec_driver_sql("SELECT COUNT(*) FROM performance_schema.data_lock_waits").scalar_one()
                        if waiting:
                            break
                    assert waiting > 0
                if commit:
                    tx.commit()
                else:
                    tx.rollback()
                assert b.result(timeout=15) == (0 if commit else 1)
            finally:
                if tx.is_active:
                    tx.rollback()
    assert row(queue, execution_id)["status"] == (first if commit else second)


@pytest.mark.mysql_check("jobs", "claim_rc_finish")
@pytest.mark.parametrize("target", [pytest.param(s, marks=pytest.mark.mysql_check(
    "jobs", "claim_rc_finish", parameter=s)) for s in ("FAILED", "CANCELLED")])
def test_rc_claim_lock_does_not_block_unrelated_terminal_commit(queue, repo, target):
    seed(queue, 2)
    running = repo.claim_one(queue, "other_worker")
    selected, release = Event(), Event()
    def hold(conn, cursor, sql, *args):
        if "SKIP LOCKED" in sql.upper():
            selected.set()
            assert release.wait(15)
    with listener(queue, "after_cursor_execute", hold), ThreadPoolExecutor(max_workers=2) as pool:
        claim = pool.submit(repo.claim_one, queue, "claim_worker")
        try:
            assert selected.wait(15)
            def complete():
                with queue.begin() as conn:
                    assert conn.get_isolation_level() == "READ COMMITTED"
                    return repo.finish(conn, running.execution_id, "other_worker", **terminal_args(target))
            assert pool.submit(complete).result(timeout=15) == 1
            assert row(queue, running.execution_id)["status"] == target
            assert not claim.done()
        finally:
            release.set()
        assert claim.result(timeout=15).execution_id != running.execution_id


@pytest.mark.mysql_check("jobs", "finish_deadlock")
def test_real_terminal_deadlock_restarts_entire_callback(queue, repo, monkeypatch):
    seed(queue, 2)
    ids = [repo.claim_one(queue, "worker").execution_id for _ in range(2)]
    barrier = Barrier(2, timeout=15)
    attempts = [0, 0]
    codes = []
    def observed(context):
        args = getattr(context.original_exception, "args", ())
        if args and args[0] == 1213:
            codes.append(1213)
    def participant(index):
        first, second = ids if index == 0 else ids[::-1]
        def operation(conn):
            attempts[index] += 1
            changed = repo.finish(conn, first, "worker", status="SUCCEEDED")
            if attempts[index] == 1:
                barrier.wait()
            changed += repo.finish(conn, second, "worker", status="SUCCEEDED")
            return changed
        return transactions.run_worker_transaction(queue, operation, sleep=lambda _: None)
    with listener(queue, "handle_error", observed), ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(participant, i) for i in range(2)]
        assert sum(f.result(timeout=20) for f in results) == 2
    assert codes == [1213] and sorted(attempts) == [1, 2]
    assert all(row(queue, i)["status"] == "SUCCEEDED" for i in ids)


@pytest.mark.mysql_check("jobs", "claim_lock_timeout")
def test_real_claim_secondary_lock_timeout_replays_same_receipt(queue, repo, monkeypatch):
    ids = seed(queue, 2)
    with queue.begin() as conn:
        conn.exec_driver_sql("UPDATE job_execution SET status='RUNNING',started_at=NOW(6),available_at=TIMESTAMPADD(DAY,1,NOW(6)),lease_owner='blocker' WHERE execution_id=%s", (ids[1],))
    blocker = queue.connect()
    blocker.exec_driver_sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    blocker.commit()
    lock = blocker.begin()
    blocker.exec_driver_sql("SELECT execution_id FROM job_execution FORCE INDEX(ix_job_execution_claim) WHERE status='RUNNING' ORDER BY available_at,execution_id LIMIT 1 FOR UPDATE")
    tokens, codes, sleeps = [], [], []
    def timeout(conn, cursor, sql, params, *args):
        if sql.lstrip().upper().startswith("UPDATE JOB_EXECUTION"):
            tokens.append(params["token"])
            conn.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
    def error(context):
        code = context.original_exception.args[0]
        if code == 1205:
            codes.append(code)
    def retry(seconds):
        sleeps.append(seconds)
        assert row(queue, ids[0])["status"] == "QUEUED"
        assert row(queue, ids[0])["claim_token"] is None
        lock.rollback()
    with_retry_hook(monkeypatch, repo, retry)
    try:
        with listener(queue, "before_cursor_execute", timeout), listener(queue, "handle_error", error):
            claimed = repo.claim_one(queue, "worker")
        assert claimed.execution_id == ids[0]
        assert codes == [1205] and sleeps == [1] and len(tokens) == 2 and len(set(tokens)) == 1
    finally:
        if lock.is_active:
            lock.rollback()
        # Do not leak an RR session into later borrowers.
        blocker.exec_driver_sql("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        blocker.close()


@pytest.mark.mysql_check("jobs", "claim_latency")
def test_claim_latency_observation_after_commit_and_broken_logger_is_not_a_retry(queue, repo):
    ids = seed(queue, 2)
    stream = StringIO()
    logger = configure_logging("worker", stream=stream)
    def before_ack(conn):
        assert stream.getvalue() == ""
    with listener(queue, "commit", before_ack):
        first = repo.claim_one(queue, "worker", logger=logger)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    latency, = [e for e in events if e["event"] == "runtime.db.claim_latency_ms"]
    assert latency["status"] == "CLAIMED" and latency["duration_ms"] >= 0
    class BrokenLogger:
        def log(self, *args, **kwargs):
            raise RuntimeError("sink failed")
    second = repo.claim_one(queue, "worker", logger=BrokenLogger())
    assert {first.execution_id, second.execution_id} == set(ids)
