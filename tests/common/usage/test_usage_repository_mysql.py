"""RT-07(a) acceptance: real InnoDB constraints, replay and transaction ownership."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from importlib import import_module
import threading

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError

from daesingo.common.config import DbSettings
from daesingo.common.db import create_api_engine, create_migration_engine
from daesingo.common.db.errors import CommitOutcomeUnknown
from daesingo.common.db.migrate import upgrade_all
from daesingo.common.db.transactions import run_api_transaction, run_worker_transaction
from migration_support import ROOT
from mysql_fault_proxy import CommitResponseProxy

pytestmark = pytest.mark.mysql


@pytest.fixture
def ledger(mysql_schema_url, mysql_engine):
    upgrade_all(mysql_schema_url)
    return mysql_engine


def repo():
    return import_module("daesingo.common.usage.repository")


def schema():
    return import_module("daesingo.common.usage.schema")


def record(**changes):
    return {
        "usage_id": "usage_1", "execution_ref": "exec_1", "case_id": "case_1",
        "occurred_at": "2026-09-01T18:00:12Z", "provider_label": "gemini",
        "operation": "SEARCH_COARSE", "run_ref": {"kind": "analysis_run", "ref": "run_1"},
        "run_ref_reason": None, "token_usage": {"input_tokens": 128400, "output_tokens": 2100, "total_tokens": 130500},
        "processed_duration_sec": 4.5, "latency_ms": 41200,
        "pricing_context": {"pricing_id": "gemini-2026-08", "unit": "per_1k_tokens"},
        "cost": {"amount": "184.20", "currency": "KRW"}, **changes,
    }


def physical(table="usage_record", **changes):
    row = dict(usage_id="usage_1", execution_ref="exec_1", case_id="case_1",
               occurred_at=datetime(2026, 9, 1, 18, 0, 12), provider_label="gemini", operation="SEARCH_COARSE",
               run_kind="analysis_run", run_ref="run_1", run_ref_reason=None,
               input_tokens=128400, output_tokens=2100, total_tokens=130500,
               processed_duration_sec=4.5, latency_ms=41200, pricing_id="gemini-2026-08",
               unit="per_1k_tokens", amount="184.20", currency="KRW")
    if table == "usage_inflight":
        row.update(state="STARTED", run_kind=None, run_ref=None, run_ref_reason=None,
                   observed_at=None, finalized_at=None, outcome=None, failure_kind=None)
    return {**row, **changes}


def reflected(conn, name):
    return sa.Table(name, sa.MetaData(), autoload_with=conn)


@pytest.mark.mysql_check("usage", "schema")
def test_frozen_migration_matches_live_metadata_and_contract_shape(ledger):
    with ledger.begin() as conn:
        db = sa.inspect(conn)
        assert {"usage_inflight", "usage_record"} <= set(db.get_table_names())
        columns = {c["name"]: c for c in db.get_columns("usage_record")}
        assert set(columns) == set(physical())
        assert columns["amount"]["type"].precision == 65
        assert columns["amount"]["type"].scale == 30
        for name in ("usage_record", "usage_inflight"):
            assert db.get_pk_constraint(name)["constrained_columns"] == ["usage_id"]
            assert db.get_foreign_keys(name) == []
            assert any(i["column_names"] == ["execution_ref"] for i in db.get_indexes(name))
            ddl = conn.exec_driver_sql(f"SHOW CREATE TABLE {name}").one()[1]
            assert "ENGINE=InnoDB" in ddl and "ascii_bin" in ddl
        before = {name: conn.exec_driver_sql(f"SHOW CREATE TABLE {name}").one()[1]
                  for name in ("usage_record", "usage_inflight")}
        # Recreate ONLY these per-test tables with live metadata; compare actual
        # server DDL, including columns, CHECKs, defaults, indexes and collations.
        conn.exec_driver_sql("DROP TABLE usage_record, usage_inflight")
        schema().metadata.create_all(conn)
        assert {name: conn.exec_driver_sql(f"SHOW CREATE TABLE {name}").one()[1]
                for name in before} == before


@pytest.mark.mysql_check("usage", "migration")
def test_forward_upgrade_preserves_previous_head_rows_and_is_repeatable(mysql_schema_url):
    engine = create_migration_engine(mysql_schema_url)
    try:
        cfg = Config(str(ROOT / "migrations/runtime/alembic.ini"))
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "runtime_0002")
            from daesingo.common.jobs.repository import enqueue
            enqueue(conn, [{"job_id": "before", "case_id": "case_1", "kind": "SEARCH_COARSE"}], "trace_1")
        with engine.connect() as conn:
            before = conn.exec_driver_sql("SELECT * FROM job_execution").all()
        upgrade_all(mysql_schema_url)
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "runtime_0004"
            assert conn.exec_driver_sql("SELECT * FROM job_execution").all() == before
            ddl = conn.exec_driver_sql("SHOW CREATE TABLE usage_record").one()[1]
        upgrade_all(mysql_schema_url)
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SHOW CREATE TABLE usage_record").one()[1] == ddl
            assert conn.exec_driver_sql("SELECT * FROM job_execution").all() == before
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            with pytest.raises(NotImplementedError, match="forward-only"):
                command.downgrade(cfg, "runtime_0002")
    finally:
        engine.dispose()


BAD_ROWS = {
    "partial_input": dict(input_tokens=None), "partial_output": dict(output_tokens=None),
    "partial_total": dict(total_tokens=None), "only_input": dict(output_tokens=None, total_tokens=None),
    "only_output": dict(input_tokens=None, total_tokens=None), "only_total": dict(input_tokens=None, output_tokens=None),
    "sum": dict(total_tokens=1), "currency": dict(currency="USD"), "lower_currency": dict(currency="krw"),
    "run_kind": dict(run_kind="unknown", run_ref="run_1", run_ref_reason=None),
    "run_partial": dict(run_kind="analysis_run", run_ref=None, run_ref_reason=None),
    "run_reason": dict(run_kind="analysis_run", run_ref="run_1", run_ref_reason="DIRECT_NO_RUN"),
    "reason_invalid": dict(run_kind=None, run_ref=None, run_ref_reason="UNKNOWN"),
    "run_kind_space": dict(run_kind="analysis_run ", run_ref="run_1", run_ref_reason=None),
    "reason_space": dict(run_kind=None, run_ref=None, run_ref_reason="DIRECT_NO_RUN "),
}


@pytest.mark.parametrize("table,mode", [
    pytest.param(table, mode, marks=pytest.mark.mysql_check("usage", "checks", parameter=f"{table}_{mode}"))
    for table in ("usage_record", "usage_inflight") for mode in BAD_ROWS
])
def test_typed_db_checks_reject_partial_or_inconsistent_values(ledger, table, mode):
    with ledger.begin() as conn:
        target = reflected(conn, table)
        with pytest.raises(DBAPIError) as caught:
            conn.execute(target.insert().values(physical(table, **BAD_ROWS[mode])))
        assert caught.value.orig.args[0] == 3819
        assert conn.scalar(sa.select(sa.func.count()).select_from(target)) == 0


@pytest.mark.mysql_check("usage", "checks", parameter="usage_record_reason_missing")
def test_final_cannot_leave_run_relationship_pending(ledger):
    with ledger.begin() as conn:
        with pytest.raises(DBAPIError) as caught:
            conn.execute(reflected(conn, "usage_record").insert().values(
                physical(run_kind=None, run_ref=None, run_ref_reason=None)))
        assert caught.value.orig.args[0] == 3819


@pytest.mark.parametrize("field,value", [
    pytest.param(field, value, marks=pytest.mark.mysql_check("usage", "checks", parameter=f"usage_inflight_{field}_space"))
    for field, value in (("state", "STARTED "), ("outcome", "SUCCEEDED "))
])
def test_inflight_enums_reject_pad_space_aliases(ledger, field, value):
    with ledger.begin() as conn:
        with pytest.raises(DBAPIError) as caught:
            conn.execute(schema().usage_inflight.insert().values(physical("usage_inflight", **{field: value})))
        assert caught.value.orig.args[0] == 3819
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_inflight").scalar_one() == 0


@pytest.mark.mysql_check("usage", "references")
def test_inflight_can_hold_pending_run_and_final_has_independent_snapshot(ledger):
    with ledger.begin() as conn:
        inflight = schema().usage_inflight
        final = schema().usage_record
        conn.execute(inflight.insert().values(physical("usage_inflight", input_tokens=None, output_tokens=None,
                                                      total_tokens=None, amount=None)))
        conn.execute(final.insert().values(physical()))
        # No FK to execution/case/Run/in-flight. A direct fixture Final does not
        # depend on a tracker row. Cleanup here is test-only, not a retention API.
        conn.execute(inflight.delete())
        conn.execute(final.insert().values(physical(usage_id="fixture", execution_ref=None, case_id=None,
                                                   run_kind=None, run_ref=None, run_ref_reason="DIRECT_NO_RUN")))
        assert conn.scalar(sa.select(sa.func.count()).select_from(final)) == 2


@pytest.mark.parametrize("mode,value", [
    pytest.param(mode, value, marks=pytest.mark.mysql_check("usage", "amount", parameter=mode))
    for mode, value in (("null", None), ("zero", "0"), ("example", "184.20"), ("tiny", "1e-30"),
                        ("max", "9" * 35 + "." + "9" * 30), ("negative", "-184.20"))
], ids=lambda value: str(value)[:70])
def test_amount_roundtrip_without_float_or_precision_loss(ledger, mode, value):
    with ledger.begin() as conn:
        assert repo().append_final(conn, record(cost={"amount": value, "currency": "KRW"})) is True
        raw = conn.execute(sa.select(schema().usage_record.c.amount)).scalar_one()
        assert raw is None if value is None else isinstance(raw, Decimal) and raw == Decimal(value)
        got = repo().read_final(conn, "usage_1")
        assert got["cost"]["amount"] is None if value is None else Decimal(got["cost"]["amount"]) == Decimal(value)


# Stable parameter marks are applied independently of node-id display choices.
test_amount_roundtrip_without_float_or_precision_loss = pytest.mark.mysql_check("usage", "amount")(
    test_amount_roundtrip_without_float_or_precision_loss)


@pytest.mark.parametrize("table,mode,value", [
    pytest.param(table, mode, value, marks=pytest.mark.mysql_check("usage", "binding", parameter=f"{table}_{mode}"))
    for table in ("usage_record", "usage_inflight")
    for mode, value in (("float", 184.2), ("integer", 0), ("precision", "1e35"),
                        ("scale", "1e-31"), ("zero_scale", "1." + "0" * 31), ("nonfinite", Decimal("NaN")))
])
def test_live_metadata_binding_rejects_amount_before_server_rounds(ledger, table, mode, value):
    with ledger.begin() as conn:
        with pytest.raises(StatementError) as caught:
            conn.execute(getattr(schema(), table).insert().values(physical(table, amount=value)))
        assert isinstance(caught.value.orig, (TypeError, ValueError))
        assert conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one() == 0


@pytest.mark.parametrize("mode", [
    pytest.param(mode, marks=pytest.mark.mysql_check("usage", "append", parameter=mode))
    for mode in ("commit", "rollback")
])
def test_final_append_participates_in_caller_transaction(ledger, mode):
    with ledger.connect() as conn:
        tx = conn.begin()
        events = []
        sa.event.listen(conn, "commit", lambda c: events.append("commit"))
        sa.event.listen(conn, "rollback", lambda c: events.append("rollback"))
        assert repo().append_final(conn, record()) is True
        assert conn.in_transaction() and not conn.closed and events == []
        assert repo().read_final(conn, "usage_1")["token_usage"]["total_tokens"] == 130500
        with ledger.connect() as observer:
            assert repo().read_final(observer, "usage_1") is None
        getattr(tx, mode)()
        assert events == [mode]
    with ledger.connect() as observer:
        assert (repo().read_final(observer, "usage_1") is not None) == (mode == "commit")


@pytest.mark.mysql_check("usage", "duplicate", parameter="direct_pk")
def test_database_itself_forbids_second_final_for_identity(ledger):
    with ledger.begin() as conn:
        target = reflected(conn, "usage_record")
        conn.execute(target.insert().values(physical()))
        with pytest.raises(IntegrityError):
            conn.execute(target.insert().values(physical(execution_ref="different_exec")))
        assert conn.scalar(sa.select(sa.func.count()).select_from(target)) == 1


@pytest.mark.mysql_check("usage", "duplicate", parameter="identical")
def test_identical_replay_is_noop_even_with_decimal_and_timezone_equivalence(ledger):
    with ledger.begin() as conn:
        assert repo().append_final(conn, record()) is True
    with ledger.begin() as conn:
        data = record(occurred_at="2026-09-02T03:00:12+09:00", cost={"amount": Decimal("184.2"), "currency": "KRW"})
        assert repo().append_final(conn, data) is False
        assert repo().read_final(conn, "usage_1")["cost"] == {"amount": "184.2", "currency": "KRW"}


CONFLICTS = {
    "amount": {"cost": {"amount": "185", "currency": "KRW"}},
    "null_zero": {"cost": {"amount": None, "currency": "KRW"}},
    "run": {"run_ref": None, "run_ref_reason": "RUN_NOT_PRODUCED"},
    "pricing": {"pricing_context": {"pricing_id": "new", "unit": "per_second"}},
    "context": {"execution_ref": "exec_other"}, "token": {"token_usage": None},
    "latency": {"latency_ms": 1}, "provider": {"provider_label": "other"},
}


@pytest.mark.parametrize("mode", [
    pytest.param(mode, marks=pytest.mark.mysql_check("usage", "duplicate", parameter=mode)) for mode in CONFLICTS
])
def test_identity_conflict_never_changes_final_or_rolls_back_caller(ledger, mode):
    with ledger.begin() as conn:
        original = record(cost={"amount": "0", "currency": "KRW"}) if mode == "null_zero" else record()
        repo().append_final(conn, original)
    with ledger.begin() as conn:
        before = repo().read_final(conn, "usage_1")
        with pytest.raises(repo().UsageIdentityConflict):
            repo().append_final(conn, record(**CONFLICTS[mode]))
        assert repo().read_final(conn, "usage_1") == before
        # Caller can decide to continue; primitive did not close or rollback.
        repo().append_final(conn, record(usage_id="usage_2"))
    with ledger.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_record").scalar_one() == 2


@pytest.mark.parametrize("mode", [
    pytest.param(mode, marks=pytest.mark.mysql_check("usage", "concurrent", parameter=mode))
    for mode in ("commit", "rollback", "conflict")
])
def test_competing_final_insert_resolves_after_first_transaction(ledger, mode):
    with ledger.connect() as conn:
        tx = conn.begin()
        repo().append_final(conn, record())
        entered = threading.Event()
        def competitor():
            with ledger.begin() as other:
                entered.set()
                data = record(**CONFLICTS["amount"]) if mode == "conflict" else record()
                return repo().append_final(other, data)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(competitor)
            assert entered.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.15)
            tx.rollback() if mode == "rollback" else tx.commit()
            if mode == "conflict":
                with pytest.raises(repo().UsageIdentityConflict):
                    future.result(timeout=10)
            else:
                assert future.result(timeout=10) is (mode == "rollback")
    with ledger.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_record").scalar_one() == 1


@pytest.mark.parametrize("mode", [
    pytest.param(mode, marks=pytest.mark.mysql_check("usage", "commit_unknown", parameter=mode))
    for mode in ("manual", "worker")
])
def test_real_commit_response_loss_replays_only_fixed_final_snapshot(ledger, mysql_schema_url, mode):
    data = record()
    calls = []
    with CommitResponseProxy(mysql_schema_url.host, mysql_schema_url.port or 3306) as proxy:
        url = mysql_schema_url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        engine = create_api_engine(DbSettings(url=url.render_as_string(hide_password=False)))
        try:
            def operation(conn):
                result = repo().append_final(conn, data)
                calls.append(result)
                if len(calls) == 1:
                    proxy.arm()
                return result
            if mode == "manual":
                with pytest.raises(CommitOutcomeUnknown):
                    run_api_transaction(engine, operation)
                with ledger.begin() as conn:
                    assert repo().read_final(conn, "usage_1") is not None
                    assert repo().append_final(conn, data) is False
                assert calls == [True]
            else:
                assert run_worker_transaction(engine, operation, sleep=lambda _: None) is False
                assert calls == [True, False]
        finally:
            engine.dispose()
    with ledger.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_record").scalar_one() == 1


INVALID = {
    "float": {"cost": {"amount": 1.0, "currency": "KRW"}},
    "scale": {"cost": {"amount": "1e-31", "currency": "KRW"}},
    "precision": {"cost": {"amount": "1e35", "currency": "KRW"}},
    "currency": {"cost": {"amount": None, "currency": "USD"}},
    "token": {"token_usage": {"input_tokens": 1, "output_tokens": None, "total_tokens": 1}},
    "sum": {"token_usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 4}},
    "run": {"run_ref": None, "run_ref_reason": None},
    "extra": {"raw_response": "private-payload"},
    "nested_extra": {"cost": {"amount": "1", "currency": "KRW", "raw": "private-payload"}},
    "identity": {"usage_id": "bad ",},
    "naive_time": {"occurred_at": datetime(2026, 1, 1)},
}


@pytest.mark.parametrize("mode", [
    pytest.param(mode, marks=pytest.mark.mysql_check("usage", "validation", parameter=mode)) for mode in INVALID
])
def test_invalid_input_writes_nothing_and_error_does_not_echo_payload(ledger, mode):
    with ledger.begin() as conn:
        with pytest.raises((TypeError, ValueError)) as caught:
            repo().append_final(conn, record(**INVALID[mode]))
        assert "private-payload" not in str(caught.value)
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_record").scalar_one() == 0


@pytest.mark.mysql_check("usage", "validation", parameter="transaction")
def test_append_requires_explicit_caller_transaction(ledger):
    with ledger.connect() as conn:
        with pytest.raises(ValueError, match="transaction"):
            repo().append_final(conn, record())
        assert not conn.in_transaction()


@pytest.mark.parametrize("run,reason,case,execution", [
    ({"kind": "analysis_run", "ref": "run_1"}, None, None, "exec_1"),
    ({"kind": "readout_run", "ref": "rr_1"}, None, "case_1", "exec_1"),
    (None, "DIRECT_NO_RUN", None, None),
    (None, "RUN_NOT_PRODUCED", "case_1", "exec_1"),
])
def test_final_contract_projection_preserves_independent_nullable_axes(ledger, run, reason, case, execution):
    data = record(run_ref=run, run_ref_reason=reason, case_id=case, execution_ref=execution,
                  token_usage=None, processed_duration_sec=None, latency_ms=None,
                  cost={"amount": None, "currency": "KRW"})
    with ledger.begin() as conn:
        repo().append_final(conn, data)
    with ledger.connect() as conn:
        assert repo().read_final(conn, "usage_1") == data
        assert repo().read_final(conn, "missing") is None


@pytest.mark.parametrize("missing", tuple(record()))
def test_required_contract_keys_cannot_be_omitted(ledger, missing):
    data = record()
    del data[missing]
    with ledger.begin() as conn:
        with pytest.raises(ValueError, match="fields"):
            repo().append_final(conn, data)
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_record").scalar_one() == 0


def test_usage_identity_is_case_sensitive_and_inflight_pk_also_forbids_reuse(ledger):
    with ledger.begin() as conn:
        repo().append_final(conn, record())
        repo().append_final(conn, record(usage_id="Usage_1"))
        inflight = schema().usage_inflight
        conn.execute(inflight.insert().values(physical("usage_inflight")))
        with pytest.raises(IntegrityError) as caught:
            conn.execute(inflight.insert().values(physical("usage_inflight", execution_ref="exec_other")))
        assert caught.value.orig.args[0] == 1062
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM usage_record").scalar_one() == 2
