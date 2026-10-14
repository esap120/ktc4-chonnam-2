"""RT-07(c) real MySQL terminal relations, immutable Final and P-7."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier

import pytest
import sqlalchemy as sa

from daesingo.common.db.migrate import upgrade_all
from daesingo.common.usage.port import UsageConflictError
from usage_reconciliation_support import (
    RUN, BrokenLogger, begin, broken_observer, facts, job, reconcile, rows, sink,
)

pytestmark = pytest.mark.mysql


def params(scenario, modes):
    return [pytest.param(m, marks=pytest.mark.mysql_check("usage_reconciliation", scenario, parameter=m))
            for m in modes]


@pytest.fixture
def ledger(mysql_schema_url, mysql_engine):
    upgrade_all(mysql_schema_url)
    yield mysql_engine
    assert mysql_engine.pool.checkedout() == 0


@pytest.mark.parametrize("mode", params("relation", (
    "SUCCEEDED", "FAILED", "CANCELLED", "STALE", "absent", "different", "direct_no_run",
    "unknown", "RUNNING", "QUEUED", "missing", "cross_case")))
def test_terminal_produced_matches_declared_intent_only(ledger, mode):
    status = mode if mode in ("SUCCEEDED", "FAILED", "CANCELLED", "STALE", "RUNNING", "QUEUED") else "FAILED"
    produced = (RUN,) if mode in ("SUCCEEDED", "FAILED", "CANCELLED", "STALE") else ()
    if mode == "different": produced = ({"kind": "analysis_run", "ref": "other_run"},)
    if mode != "missing":
        job(ledger, status, produced=produced, case_id="other" if mode == "cross_case" else "case")
    s = sink(ledger)
    identity = begin(s, run=None if mode in ("direct_no_run", "unknown") else RUN,
                     reason="DIRECT_NO_RUN" if mode == "direct_no_run" else None)
    s.finish(identity, **facts())
    before = rows(ledger)
    reconcile(ledger)
    trackers, finals = rows(ledger)
    if mode in ("unknown", "RUNNING", "QUEUED", "missing", "cross_case"):
        assert (trackers, finals) == before
        return
    assert len(finals) == 1 and finals[0]["usage_id"] == identity
    final = finals[0]
    assert final["input_tokens"] == 2 and str(final["amount"]) == "1.200000000000000000000000000000"
    assert final["run_ref"] == (RUN["ref"] if produced == (RUN,) else None)
    assert final["run_ref_reason"] == (None if produced == (RUN,) else
                                      "DIRECT_NO_RUN" if mode == "direct_no_run" else "RUN_NOT_PRODUCED")
    assert trackers[0]["state"] == "FINALIZED" and trackers[0]["recovered_at"] is not None
    fixed = rows(ledger)
    assert reconcile(ledger) == ()
    assert rows(ledger) == fixed


@pytest.mark.mysql_check("usage_reconciliation", "relation", parameter="invalid_produced")
def test_invalid_durable_produced_is_not_interpreted_as_no_run(ledger):
    job(ledger, "FAILED", produced=({"kind": "analysis_run"},))
    s = sink(ledger)
    identity = begin(s)
    s.finish(identity, **facts())
    before = rows(ledger)
    from daesingo.common.usage.port import UsageError
    with pytest.raises(UsageError):
        reconcile(ledger)
    assert rows(ledger) == before


@pytest.mark.parametrize("mode", params("late", ("unobserved", "observed", "direct_no_run", "replay", "conflict", "relationship")))
def test_late_finish_preserves_final_and_durably_records_event(ledger, mode):
    job(ledger, "STALE")
    s = sink(ledger)
    identity = begin(s, run=None if mode == "direct_no_run" else RUN,
                     reason="DIRECT_NO_RUN" if mode == "direct_no_run" else None)
    if mode == "observed": s.finish(identity, **facts())
    reconcile(ledger)
    before = rows(ledger)[1]
    s.finish(identity, **facts())
    tracker, final = rows(ledger)
    assert final == before
    assert tracker[0]["state"] == "FINALIZED" and tracker[0]["late_observed_at"] is not None
    assert tracker[0]["input_tokens"] == 2 and tracker[0]["outcome"] == "SUCCEEDED"
    fixed = rows(ledger)
    s.finish(identity, **facts())
    assert rows(ledger) == fixed
    if mode == "conflict":
        changed = facts(cost={"amount": "9.99", "currency": "KRW"})
        with pytest.raises(UsageConflictError): s.finish(identity, **changed)
    if mode == "relationship":
        with pytest.raises(UsageConflictError): s.finalize(identity, run_ref=RUN, run_ref_reason=None)
    else:
        s.finalize(identity, run_ref=None, run_ref_reason="DIRECT_NO_RUN" if mode == "direct_no_run" else "RUN_NOT_PRODUCED")
    assert rows(ledger) == fixed


@pytest.mark.parametrize("mode", params("concurrent", ("reconcilers", "normal_recovery", "late_same", "late_conflict")))
def test_concurrent_recovery_and_normal_paths_share_one_identity(ledger, mode):
    job(ledger, "SUCCEEDED", produced=(RUN,))
    s = sink(ledger)
    identity = begin(s)
    if not mode.startswith("late"): s.finish(identity, **facts())
    if mode.startswith("late"): reconcile(ledger)
    barrier = Barrier(2)
    def work(index):
        barrier.wait(timeout=10)
        try:
            if mode.startswith("late"):
                value = facts()
                if index and mode == "late_conflict": value["latency_ms"] = 19
                s.finish(identity, **value)
            elif mode == "normal_recovery" and index:
                s.finalize(identity, run_ref=RUN, run_ref_reason=None)
            else:
                reconcile(ledger)
            return "ok"
        except UsageConflictError:
            return "conflict"
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(work, range(2)))
    assert sorted(result) == (["conflict", "ok"] if mode == "late_conflict" else ["ok", "ok"])
    trackers, finals = rows(ledger)
    assert len(trackers) == len(finals) == 1
    assert finals[0]["run_ref"] == RUN["ref"]
    assert trackers[0]["state"] == "FINALIZED"


@pytest.mark.parametrize("mode", params("isolation", ("logger", "observer", "late_logger", "late_observer", "metrics")))
def test_metrics_and_late_sinks_cannot_replay_durable_work(ledger, mode):
    job(ledger, "STALE")
    s = sink(ledger, logger=BrokenLogger() if mode == "late_logger" else None,
             late_observe=broken_observer if mode == "late_observer" else None)
    identity = begin(s)
    calls = [identity]  # fake provider invocation already completed, never inside tx
    recovered = []
    reconcile(ledger, logger=BrokenLogger() if mode == "logger" else None,
              observe=broken_observer if mode == "observer" else recovered.append)
    s.finish(identity, **facts())
    assert calls == [identity]
    assert len(rows(ledger)[1]) == 1
    if recovered:
        assert recovered[-1].recovered_count == 1 and recovered[-1].inflight_count == 0
        assert recovered[-1].inflight_oldest_age_s is None
    fixed = rows(ledger)
    s.finish(identity, **facts())
    assert rows(ledger) == fixed


@pytest.mark.mysql_check("usage_reconciliation", "db_clock", parameter="oldest")
def test_inflight_age_uses_db_time_and_all_pending_executions(ledger):
    from daesingo.common.usage.schema import usage_inflight
    job(ledger, "RUNNING")
    s = sink(ledger)
    identity = begin(s)
    with ledger.begin() as conn:
        conn.execute(usage_inflight.update().values(occurred_at=sa.func.now(6) - sa.text("INTERVAL 123 SECOND")))
    measured = []
    reconcile(ledger, observe=measured.append)
    assert rows(ledger)[1] == [] and rows(ledger)[0][0]["usage_id"] == identity
    assert measured[-1].inflight_count == 1 and measured[-1].recovered_count == 0
    assert 123 <= measured[-1].inflight_oldest_age_s < 130


@pytest.mark.mysql_check("usage_reconciliation", "projection", parameter="final_only")
def test_read_port_projects_sorted_final_ids_per_execution_only(ledger):
    from daesingo.common.jobs.read_port import read_executions
    job(ledger, "SUCCEEDED", produced=(RUN,))
    job(ledger, "SUCCEEDED", execution="other", produced=(RUN,))
    identities = []
    for execution in ("exec", "exec", "other"):
        s = sink(ledger, execution)
        identity = begin(s)
        s.finish(identity, **facts())
        identities.append(identity)
    pending = begin(sink(ledger), run=None)
    reconcile(ledger, execution_ref="exec")
    with ledger.connect() as conn:
        result = read_executions(conn, ["job_exec", "job_other"])
    assert result[0]["usage_refs"] == sorted(identities[:2])
    assert result[1]["usage_refs"] == []
    assert pending not in result[0]["usage_refs"] and identities[2] not in result[0]["usage_refs"]
