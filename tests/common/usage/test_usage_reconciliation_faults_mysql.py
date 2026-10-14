"""Actual InnoDB 1205/1213, consumed COMMIT OK packets and forward migration."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Barrier

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa

from daesingo.common.config import DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.usage.port import UsagePersistenceError, UsageValidationError, UsageConflictError
from migration_support import ROOT
from mysql_fault_proxy import CommitResponseProxy
from usage_reconciliation_support import RUN, begin, facts, job, module, reconcile, rows, sink

pytestmark = pytest.mark.mysql


@pytest.fixture
def ledger(mysql_schema_url, mysql_engine):
    upgrade_all(mysql_schema_url)
    yield mysql_engine
    assert mysql_engine.pool.checkedout() == 0


@pytest.mark.parametrize("stage,drops", [
    pytest.param(stage, drops, marks=pytest.mark.mysql_check("usage_reconciliation", "commit_unknown",
        parameter=stage + ("_exhausted" if drops == 3 else "")))
    for stage in ("recovery", "late") for drops in (1, 3)])
def test_commit_ack_loss_and_exhaustion_recover_durable_fixed_facts(ledger, mysql_schema_url, monkeypatch, stage, drops):
    job(ledger, "STALE")
    s = sink(ledger)
    identity = begin(s)
    calls = [identity]
    if stage == "recovery": s.finish(identity, **facts())
    else: reconcile(ledger)
    final_before = rows(ledger)[1]
    with CommitResponseProxy(mysql_schema_url.host, mysql_schema_url.port or 3306, drop_commits=drops) as proxy:
        fault = create_worker_engine(DbSettings(url=mysql_schema_url.set(host="127.0.0.1", port=proxy.port)
            .update_query_dict({"ssl_disabled": "true"}).render_as_string(hide_password=False)))
        try:
            def transaction(callback):
                def operation(conn):
                    proxy.arm()
                    return callback(conn)
                return run_worker_transaction(fault, operation, sleep=lambda _: None)
            original = module().run_worker_transaction
            if stage == "recovery":
                monkeypatch.setattr(module(), "run_worker_transaction", lambda engine, cb, **kw: transaction(cb))
            late_sink = sink(fault, transaction=transaction)
            def invoke():
                if stage == "recovery": return reconcile(fault)
                return late_sink.finish(identity, **facts())
            if drops == 3:
                with pytest.raises(UsagePersistenceError): invoke()
                before = rows(ledger)
                invoke()
                assert rows(ledger) == before
            else:
                invoke()
            assert proxy.commit_ok_dropped == drops
        finally:
            monkeypatch.setattr(module(), "run_worker_transaction", original)
            fault.dispose()
    tracker, final = rows(ledger)
    assert calls == [identity] and len(final) == 1 and final[0]["usage_id"] == identity
    assert tracker[0]["state"] == "FINALIZED" and tracker[0]["recovered_at"] is not None
    if stage == "late":
        assert final == final_before and tracker[0]["late_observed_at"] is not None
        assert tracker[0]["input_tokens"] == 2
    else:
        assert final[0]["input_tokens"] == 2


@pytest.mark.parametrize("stage,code", [
    pytest.param(stage, code, marks=pytest.mark.mysql_check("usage_reconciliation", "retry", parameter=f"{stage}_{code}"))
    for stage in ("recovery", "late") for code in (1205, 1213)])
def test_real_lock_errors_retry_entire_transaction_without_provider_repeat(ledger, monkeypatch, stage, code):
    with ledger.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE retry_probe (id INT PRIMARY KEY, value INT NOT NULL) ENGINE=InnoDB")
        conn.exec_driver_sql("INSERT INTO retry_probe VALUES (1,0),(2,0)")
    count = 1 if code == 1205 else 2
    identities = []
    for index in range(count):
        execution = f"exec{index}"
        job(ledger, "STALE", execution=execution)
        s = sink(ledger, execution)
        identities.append(begin(s))
        if stage == "recovery": s.finish(identities[-1], **facts())
    if stage == "late": reconcile(ledger)
    calls = list(identities)
    errors, attempts, final_snapshots = [], [], []
    barrier = Barrier(2)
    blocked = None
    original = module().run_worker_transaction
    def participant(index):
        local_attempts = []
        first, second = (1, 2) if index == 0 else (2, 1)
        def transaction(callback):
            def operation(conn):
                local_attempts.append(1)
                if code == 1205: conn.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
                conn.exec_driver_sql("UPDATE retry_probe SET value=value+1 WHERE id=%s", (first,))
                if code == 1213 and len(local_attempts) == 1: barrier.wait(timeout=10)
                try:
                    result = callback(conn)
                    snapshot = conn.exec_driver_sql(
                        "SELECT r.usage_id,r.input_tokens,r.latency_ms,t.finalized_at,t.late_observed_at "
                        "FROM usage_record r JOIN usage_inflight t USING (usage_id) WHERE r.execution_ref=%s",
                        (f"exec{index}",)).all()
                    final_snapshots.append(snapshot)
                    conn.exec_driver_sql("UPDATE retry_probe SET value=value+1 WHERE id=%s", (second,))
                    return result
                except sa.exc.DBAPIError as error:
                    errors.append(error.orig.args[0])
                    raise
            def wait(seconds):
                assert seconds == 1
                if code == 1205: blocked.rollback()
            result = original(ledger, operation, sleep=wait)
            attempts.append(len(local_attempts))
            return result
        if stage == "recovery":
            # A thread-local runner avoids test interference between participants.
            __import__("threading").current_thread().usage_transaction = transaction
            reconcile(ledger, execution_ref=f"exec{index}")
        else:
            sink(ledger, f"exec{index}", transaction=transaction).finish(identities[index], **facts())
    def dispatch_runner(engine, callback, **kwargs):
        return __import__("threading").current_thread().usage_transaction(callback)
    if stage == "recovery": monkeypatch.setattr(module(), "run_worker_transaction", dispatch_runner)
    try:
        if code == 1205:
            with ledger.connect() as blocker:
                blocked = blocker.begin()
                blocker.exec_driver_sql("SELECT id FROM retry_probe WHERE id=2 FOR UPDATE")
                try: participant(0)
                finally:
                    if blocked.is_active: blocked.rollback()
        else:
            with ThreadPoolExecutor(2) as pool: list(pool.map(participant, range(2)))
    finally:
        monkeypatch.setattr(module(), "run_worker_transaction", original)
        current = __import__("threading").current_thread()
        if hasattr(current, "usage_transaction"): del current.usage_transaction
    assert errors == [code] and max(attempts) == 2
    tracker, final = rows(ledger)
    for identity in identities:
        snapshots = [r for batch in final_snapshots for r in batch if r[0] == identity]
        assert snapshots and all(r == snapshots[0] for r in snapshots)
    assert len(final) == count and calls == identities
    assert all(r["state"] == "FINALIZED" for r in tracker)
    if stage == "recovery":
        assert all(r["input_tokens"] == 2 for r in final)
    else:
        assert all(r["input_tokens"] is None for r in final)
        assert all(r["input_tokens"] == 2 and r["late_observed_at"] is not None for r in tracker)
    with ledger.connect() as conn:
        assert sum(conn.exec_driver_sql("SELECT value FROM retry_probe").scalars()) == 2 * count


@pytest.mark.mysql_check("usage_reconciliation", "migration", parameter="legacy")
def test_upgrade_0003_preserves_pending_and_final_rows_without_inventing_intent(mysql_schema_url):
    engine = create_worker_engine(DbSettings(url=mysql_schema_url.render_as_string(hide_password=False)))
    cfg = Config(str(ROOT / "migrations/runtime/alembic.ini"))
    try:
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "runtime_0003")
            pending = sa.Table("usage_inflight", sa.MetaData(), autoload_with=conn)
            conn.execute(pending.insert().values(usage_id="legacy", execution_ref="exec", case_id="case",
                occurred_at=datetime(2026, 10, 14), provider_label="fake", operation="SEARCH_COARSE",
                state="OBSERVED", outcome="SUCCEEDED", observed_at=datetime(2026, 10, 14),
                pricing_id="price", unit="opaque", currency="KRW", input_tokens=2, output_tokens=3, total_tokens=5))
            final = sa.Table("usage_record", sa.MetaData(), autoload_with=conn)
            conn.execute(final.insert().values(usage_id="already_final", execution_ref="exec", case_id="case",
                occurred_at=datetime(2026, 10, 14), provider_label="fake", operation="SEARCH_COARSE",
                run_kind="analysis_run", run_ref="actual_run", pricing_id="price", unit="opaque", currency="KRW"))
            before = [dict(r) for r in conn.execute(sa.select(pending)).mappings()]
            final_before = conn.execute(sa.select(final)).all()
        upgrade_all(mysql_schema_url)
        job(engine, "STALE")
        reconcile(engine)
        tracker, finals = rows(engine)
        assert len(finals) == 1
        assert all(tracker[0][k] == v for k, v in before[0].items())
        assert tracker[0]["planned_run_ref"] is None and not tracker[0]["direct_no_run"]
        with engine.connect() as conn:
            assert conn.execute(sa.select(final)).all() == final_before
            assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "runtime_0004"
        upgrade_all(mysql_schema_url)
        assert rows(engine) == (tracker, finals)
    finally:
        engine.dispose()


@pytest.mark.mysql_check("usage_reconciliation", "direct", parameter="explicit_finalize")
def test_execution_sink_accepts_explicit_direct_no_run_without_inference(ledger):
    s = sink(ledger)
    identity = begin(s, run=None, reason="DIRECT_NO_RUN")
    s.finish(identity, **facts())
    s.finalize(identity, run_ref=None, run_ref_reason="DIRECT_NO_RUN")
    assert rows(ledger)[1][0]["run_ref_reason"] == "DIRECT_NO_RUN"
    with pytest.raises(UsageConflictError):
        s.finalize(identity, run_ref=None, run_ref_reason="RUN_NOT_PRODUCED")


@pytest.mark.parametrize("mode", [
    pytest.param(m, marks=pytest.mark.mysql_check("usage_reconciliation", "intent", parameter=m))
    for m in ("planned_replay", "direct_replay", "different_run", "different_reason", "premature_not_produced")])
def test_begin_replay_preserves_intent_and_rejects_conflicts(ledger, mode):
    s = sink(ledger)
    direct = mode in ("direct_replay", "different_reason")
    identity = begin(s, run=None if direct else RUN, reason="DIRECT_NO_RUN" if direct else None)
    before = rows(ledger)
    if mode in ("planned_replay", "direct_replay"):
        assert s.begin("SEARCH_COARSE", "fake", {"pricing_id": "price", "unit": "opaque"}, usage_id=identity,
            run_ref=None if direct else RUN, run_ref_reason="DIRECT_NO_RUN" if direct else None) == identity
    elif mode == "premature_not_produced":
        with pytest.raises(UsageValidationError):
            s.begin("SEARCH_COARSE", "fake", {"pricing_id": "price", "unit": "opaque"},
                run_ref=None, run_ref_reason="RUN_NOT_PRODUCED")
    else:
        with pytest.raises(UsageConflictError):
            s.begin("SEARCH_COARSE", "fake", {"pricing_id": "price", "unit": "opaque"}, usage_id=identity,
                run_ref={"kind": "analysis_run", "ref": "different"}, run_ref_reason=None)
    assert rows(ledger) == before
