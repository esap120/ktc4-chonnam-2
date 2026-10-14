"""Real InnoDB tracker/Final atomicity and fixed-identity replay."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib import import_module

import pytest
import sqlalchemy as sa

from daesingo.common.config import DbSettings
from daesingo.common.db import create_worker_engine
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.db.transactions import run_worker_transaction
from mysql_fault_proxy import CommitResponseProxy
from usage_sink_support import begin, facts

pytestmark = pytest.mark.mysql


def mod():
    return import_module("daesingo.common.usage.sink")


@pytest.fixture
def ledger(mysql_schema_url, mysql_engine):
    upgrade_all(mysql_schema_url)
    return mysql_engine


def sink(engine, execution="exec", transaction=None):
    return mod().DurableUsageSink(execution_ref=execution, case_id="case",
        transaction=transaction or (lambda cb: run_worker_transaction(engine, cb, sleep=lambda _: None)))


def rows(engine):
    from daesingo.common.usage.schema import usage_inflight, usage_record
    with engine.connect() as conn:
        return ([dict(r) for r in conn.execute(sa.select(usage_inflight)).mappings()],
                [dict(r) for r in conn.execute(sa.select(usage_record)).mappings()])


def finalize(s, identity, run="run"):
    s.finalize(identity, run_ref={"kind": "analysis_run", "ref": run} if run else None,
               run_ref_reason=None if run else "RUN_NOT_PRODUCED")


@pytest.mark.mysql_check("usage_sink", "invocations")
def test_each_http_attempt_has_durable_identity_including_failed_and_parsing(ledger):
    s, ids, calls = sink(ledger), [], []
    for index in range(5):
        identity = begin(s)
        ids.append(identity)
        trackers, finals = rows(ledger)
        assert any(r["usage_id"] == identity and r["state"] == "STARTED" for r in trackers)
        calls.append(identity)
        value = facts()
        if index < 3:
            value.update(outcome="FAILED", failure_kind="PARSING" if index == 2 else "PROVIDER_FAILURE",
                         token_usage=None, cost={"amount": None, "currency": "KRW"})
        s.finish(identity, **value)
        assert rows(ledger)[1] == []
    for identity in ids:
        finalize(s, identity)
    trackers, finals = rows(ledger)
    assert len(set(ids)) == len(calls) == len(trackers) == len(finals) == 5
    assert all(r["state"] == "FINALIZED" for r in trackers)
    assert all(r["run_ref"] == "run" for r in finals)


@pytest.mark.parametrize("stage", [pytest.param(m, marks=pytest.mark.mysql_check("usage_sink", "replay", parameter=m))
    for m in ("begin", "finish", "finalize")])
def test_identical_replay_preserves_every_stored_field(ledger, stage):
    s = sink(ledger)
    identity = begin(s)
    if stage != "begin": s.finish(identity, **facts())
    if stage == "finalize": finalize(s, identity)
    before = rows(ledger)
    for _ in range(2):
        if stage == "begin": assert begin(s, usage_id=identity) == identity
        elif stage == "finish": s.finish(identity, **facts())
        else: finalize(s, identity)
    assert rows(ledger) == before


@pytest.mark.parametrize("mode", [pytest.param(m, marks=pytest.mark.mysql_check("usage_sink", "conflict", parameter=m))
    for m in ("token", "cost", "pricing", "outcome", "duration", "latency", "failure", "run", "null_run")])
def test_different_snapshots_conflict_without_overwriting(ledger, mode):
    s, value = sink(ledger), facts()
    identity = begin(s)
    value.update(outcome="FAILED", failure_kind="PROVIDER_FAILURE")
    s.finish(identity, **value)
    finalize(s, identity)
    before = rows(ledger)
    changed = deepcopy(value)
    if mode == "token": changed["token_usage"] = None
    if mode == "cost": changed["cost"]["amount"] = None
    if mode == "pricing": changed["pricing_context"]["pricing_id"] = "other"
    if mode == "outcome": changed.update(outcome="SUCCEEDED", failure_kind=None)
    if mode == "duration": changed["processed_duration_sec"] = None
    if mode == "latency": changed["latency_ms"] = None
    if mode == "failure": changed["failure_kind"] = "OTHER"
    with pytest.raises(mod().UsageConflictError):
        if mode in ("run", "null_run"): finalize(s, identity, "other" if mode == "run" else None)
        else: s.finish(identity, **changed)
    assert rows(ledger) == before


@pytest.mark.parametrize("mode", [pytest.param(m, marks=pytest.mark.mysql_check("usage_sink", "atomicity", parameter=m))
    for m in ("append", "marker", "commit", "rollback")])
def test_final_append_and_marker_share_one_transaction(ledger, monkeypatch, mode):
    s = sink(ledger)
    identity = begin(s)
    s.finish(identity, **facts())
    before = rows(ledger)
    if mode in ("append", "marker"):
        name = "append_final" if mode == "append" else "_mark_finalized"
        original = getattr(mod(), name)
        def fail(*args):
            original(*args)
            raise RuntimeError("secret SQL /private")
        monkeypatch.setattr(mod(), name, fail)
    if mode == "rollback":
        def rollback(cb):
            with ledger.connect() as conn:
                tx = conn.begin()
                try: cb(conn)
                finally: tx.rollback()
            raise RuntimeError("rolled back")
        s = sink(ledger, transaction=rollback)
    if mode != "commit":
        with pytest.raises(mod().UsagePersistenceError): finalize(s, identity)
        assert rows(ledger) == before
    else:
        finalize(s, identity)
        trackers, finals = rows(ledger)
        assert trackers[0]["state"] == "FINALIZED" and len(finals) == 1


@pytest.mark.parametrize("mode", [pytest.param(m, marks=pytest.mark.mysql_check("usage_sink", "concurrent", parameter=m))
    for m in ("finish_same", "finish_conflict", "finalize_same", "finalize_conflict", "finish_finalize")])
def test_concurrent_operations_serialize_on_tracker(ledger, mode):
    s = sink(ledger)
    identity = begin(s)
    if mode.startswith("finalize") or mode == "finish_finalize": s.finish(identity, **facts())
    barrier = __import__("threading").Barrier(2)
    def work(index):
        barrier.wait(timeout=10)
        try:
            if mode.startswith("finish_") and mode != "finish_finalize":
                value = facts()
                if index and mode.endswith("conflict"): value["cost"]["amount"] = None
                s.finish(identity, **value)
            elif mode == "finish_finalize" and index: s.finish(identity, **facts())
            else: finalize(s, identity, "other" if index and mode.endswith("conflict") else "run")
            return "ok"
        except mod().UsageConflictError: return "conflict"
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(work, range(2)))
    assert sorted(result) == (["conflict", "ok"] if mode.endswith("conflict") else ["ok", "ok"])
    trackers, finals = rows(ledger)
    assert len(trackers) == 1
    assert len(finals) == (1 if "finalize" in mode else 0)


@pytest.mark.parametrize("stage,drops", [pytest.param(stage, drops, marks=pytest.mark.mysql_check(
    "usage_sink", "commit_unknown", parameter=stage + ("_exhausted" if drops == 3 else "")))
    for stage in ("begin", "finish", "finalize") for drops in (1, 3)])
def test_actual_lost_commit_response_replays_fixed_identity(mysql_schema_url, ledger, stage, drops):
    s = sink(ledger)
    identity = None
    if stage != "begin": identity = begin(s)
    if stage == "finalize": s.finish(identity, **facts())
    with CommitResponseProxy(mysql_schema_url.host, mysql_schema_url.port or 3306, drop_commits=drops) as proxy:
        engine = create_worker_engine(DbSettings(url=mysql_schema_url.set(host="127.0.0.1", port=proxy.port)
            .update_query_dict({"ssl_disabled": "true"})
            .render_as_string(hide_password=False)))
        try:
            def transaction(callback):
                def operation(conn):
                    proxy.arm()
                    return callback(conn)
                return run_worker_transaction(engine, operation, sleep=lambda _: None)
            fault_sink = sink(engine, transaction=transaction)
            def invoke(replay=False):
                nonlocal identity
                if stage == "begin": identity = begin(fault_sink, **({"usage_id": identity} if replay else {}))
                elif stage == "finish": fault_sink.finish(identity, **facts())
                else: finalize(fault_sink, identity)
            if drops == 3:
                with pytest.raises(mod().UsagePersistenceError) as caught:
                    invoke()
                identity = caught.value.usage_id
                before = rows(ledger)
                invoke(replay=True)
                assert rows(ledger) == before
            else: invoke()
            assert proxy.commit_ok_dropped == drops
            trackers, finals = rows(ledger)
            assert len(trackers) == 1 and trackers[0]["usage_id"] == identity
            assert trackers[0]["state"] == {"begin": "STARTED", "finish": "OBSERVED", "finalize": "FINALIZED"}[stage]
            assert len(finals) == (stage == "finalize")
        finally: engine.dispose()


@pytest.mark.mysql_check("usage_sink", "state")
def test_missing_started_and_wrong_execution_cannot_finalize_or_finish(ledger):
    s = sink(ledger)
    identity = begin(s)
    for target in (identity, "missing"):
        with pytest.raises(mod().UsageStateError): finalize(s, target)
    with pytest.raises(mod().UsageStateError): sink(ledger, "other").finish(identity, **facts())
    assert rows(ledger)[1] == []


@pytest.mark.mysql_check("usage_sink", "no_run")
def test_only_explicit_no_run_finalizes_null_and_observation_survives(ledger):
    s = sink(ledger)
    identity = begin(s)
    value = facts()
    value.update(outcome="FAILED", failure_kind="PARSING", cost={"amount": None, "currency": "KRW"})
    s.finish(identity, **value)
    finalize(s, identity, None)
    trackers, finals = rows(ledger)
    assert finals[0]["run_ref"] is None and finals[0]["run_ref_reason"] == "RUN_NOT_PRODUCED"
    assert finals[0]["input_tokens"] == 2 and finals[0]["latency_ms"] == 17 and finals[0]["amount"] is None


@pytest.mark.parametrize("stage,code", [pytest.param(stage, code, marks=pytest.mark.mysql_check(
    "usage_sink", "retry", parameter=f"{stage}_{code}")) for stage in ("begin", "finish", "finalize")
    for code in (1205, 1213)])
def test_real_lock_timeout_and_deadlock_keep_identity_and_facts(ledger, stage, code):
    # Extra locks force a real server error after the usage write, so rollback
    # must undo tracker/Final and replay the same method snapshot.
    with ledger.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE retry_probe (id INT PRIMARY KEY, value INT NOT NULL) ENGINE=InnoDB")
        conn.exec_driver_sql("INSERT INTO retry_probe VALUES (1,0),(2,0)")
    from threading import Barrier
    barrier, errors, snapshots, identities = Barrier(2, timeout=10), [], [], []
    def participant(index):
        first, second = (1, 2) if index == 0 else (2, 1)
        identity = None
        attempts = []
        def transaction(callback):
            def operation(conn):
                attempts.append(1)
                conn.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
                if code == 1213:
                    conn.exec_driver_sql("UPDATE retry_probe SET value=value+1 WHERE id=%s", (first,))
                    if len(attempts) == 1: barrier.wait()
                try:
                    callback(conn)
                    from daesingo.common.usage.schema import usage_inflight
                    snapshots.append([dict(r) for r in conn.execute(sa.select(usage_inflight).where(
                        usage_inflight.c.execution_ref == f"exec{index}")).mappings()])
                    conn.exec_driver_sql("UPDATE retry_probe SET value=value+1 WHERE id=%s", (second,))
                except sa.exc.DBAPIError as error:
                    errors.append(error.orig.args[0])
                    raise
            def retry_wait(seconds):
                assert seconds == 1
                if code == 1205: blocked.rollback()
            return run_worker_transaction(ledger, operation, sleep=retry_wait)
        fault = sink(ledger, f"exec{index}", transaction)
        # Use the same execution for preparatory steps and persistence retries.
        if stage != "begin":
            prepared = sink(ledger, f"exec{index}")
            identity = begin(prepared)
            if stage == "finalize": prepared.finish(identity, **facts())
        if stage == "begin": identity = begin(fault)
        elif stage == "finish": fault.finish(identity, **facts())
        else: finalize(fault, identity)
        identities.append(identity)
    # No preparatory rows should be created with a different execution.
    if code == 1205:
        with ledger.connect() as blocker:
            blocked = blocker.begin()
            blocker.exec_driver_sql("SELECT id FROM retry_probe WHERE id=2 FOR UPDATE")
            try: participant(0)
            finally:
                if blocked.is_active: blocked.rollback()
    else:
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(participant, range(2)))
    assert errors == [code]
    trackers, finals = rows(ledger)
    selected = [r for r in trackers if r["usage_id"] in identities]
    assert len(selected) == len(set(identities)) == (1 if code == 1205 else 2)
    expected = {"begin": "STARTED", "finish": "OBSERVED", "finalize": "FINALIZED"}[stage]
    assert all(r["state"] == expected for r in selected)
    for identity in identities:
        attempt_rows = [r for attempt in snapshots for r in attempt if r["usage_id"] == identity]
        assert attempt_rows and all(r == attempt_rows[0] for r in attempt_rows)
    assert len(finals) == (len(identities) if stage == "finalize" else 0)


@pytest.mark.parametrize("mode", [pytest.param(m, marks=pytest.mark.mysql_check("usage_sink", "validation", parameter=m))
    for m in ("token", "total", "duration", "latency", "pricing", "float", "currency", "outcome", "failure", "extra", "run", "direct_no_run")])
def test_invalid_observation_or_relationship_never_changes_tracker(ledger, mode, caplog):
    s, value, sentinel = sink(ledger), facts(), "secret raw-response SQL /private tracker"
    identity = begin(s)
    if mode == "direct_no_run": s.finish(identity, **value)
    before = rows(ledger)
    if mode == "token": value["token_usage"] = {"input_tokens": sentinel}
    if mode == "total": value["token_usage"]["total_tokens"] = 99
    if mode == "duration": value["processed_duration_sec"] = float("nan")
    if mode == "latency": value["latency_ms"] = sentinel
    if mode == "pricing": value["pricing_context"]["raw"] = sentinel
    if mode == "float": value["cost"]["amount"] = 1.2
    if mode == "currency": value["cost"]["currency"] = sentinel
    if mode == "outcome": value["outcome"] = sentinel
    if mode == "failure": value["failure_kind"] = sentinel
    if mode == "extra": value["token_usage"]["raw"] = sentinel
    with pytest.raises(mod().UsageValidationError) as caught:
        if mode == "direct_no_run": s.finalize(identity, run_ref={"kind": "analysis_run", "ref": "run"}, run_ref_reason="DIRECT_NO_RUN")
        elif mode == "run": s.finalize(identity, run_ref={"kind": sentinel, "ref": sentinel}, run_ref_reason=None)
        else: s.finish(identity, **value)
    assert rows(ledger) == before and ledger.pool.checkedout() == 0
    assert all(item not in str(caught.value) + repr(caught.value) + caplog.text for item in (sentinel, identity))
