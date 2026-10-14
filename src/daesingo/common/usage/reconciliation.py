"""Terminal-only Usage finalization using Runtime's first durable Run relation.

Issue #294: Search has no Run store; a planned ID alone is not a produced Run.
All callbacks are DB-only. One usage transaction at a time, after scan release.
"""

from dataclasses import dataclass
import time

from sqlalchemy import case, func, select, text, update

from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.jobs.schema import job_execution as jobs
from daesingo.common.job_execution import RuntimeContractRef
from daesingo.common.logging import log_event_best_effort
from .port import UsageError, UsageStateError, UsageConflictError, UsagePersistenceError
from .repository import append_final, UsageIdentityConflict
from .schema import usage_inflight as tracker, usage_record
from .sink import _contract, _OBSERVATION, _RUN, _START, _same

_TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED", "STALE")


@dataclass(frozen=True)
class UsageMetrics:
    recovered_count: int
    inflight_count: int
    inflight_oldest_age_s: float | None


@dataclass(frozen=True)
class ReconciliationOutcome:
    usage_id: str
    execution_ref: str


def _relationship(row, execution):
    try:
        if type(execution["produced"]) is not list:
            raise ValueError
        produced = [RuntimeContractRef.model_validate(ref).model_dump() for ref in execution["produced"]]
        if len({(ref["kind"], ref["ref"]) for ref in produced}) != len(produced):
            raise ValueError
    except Exception:
        raise UsageStateError() from None
    if row["direct_no_run"]:
        return dict(run_kind=None, run_ref=None, run_ref_reason="DIRECT_NO_RUN")
    if row["planned_run_ref"] is None:
        return None  # legacy/unknown intent is not a non-production declaration
    expected = {"kind": row["planned_run_kind"], "ref": row["planned_run_ref"]}
    if expected in produced:
        return dict(run_kind=expected["kind"], run_ref=expected["ref"], run_ref_reason=None)
    return dict(run_kind=None, run_ref=None, run_ref_reason="RUN_NOT_PRODUCED")


def _metrics(conn):
    pending = tracker.c.state != "FINALIZED"
    oldest = func.min(case((pending, tracker.c.occurred_at)))
    # One DB snapshot for both counts and DB UTC oldest age.
    recovered, count, age = conn.execute(select(
        func.coalesce(func.sum(case((tracker.c.recovered_at.is_not(None), 1), else_=0)), 0),
        func.coalesce(func.sum(case((pending, 1), else_=0)), 0),
        func.greatest(0, func.timestampdiff(text("MICROSECOND"), oldest, func.now(6))) / 1_000_000,
    )).one()
    return UsageMetrics(int(recovered), int(count), None if age is None else float(age))


def _observe(metrics, logger, observer):
    if logger is not None:
        log_event_best_effort(logger, "runtime.usage.recovered_count", count=metrics.recovered_count)
        log_event_best_effort(logger, "runtime.usage.inflight_count", count=metrics.inflight_count)
        if metrics.inflight_oldest_age_s is not None:
            log_event_best_effort(logger, "runtime.usage.inflight_oldest_age_s",
                                 duration_ms=metrics.inflight_oldest_age_s * 1000)
    if observer is not None:
        try:
            observer(metrics)
        except Exception:
            pass


def reconcile_once(engine, *, execution_ref=None, recovery=True, sleep=time.sleep, logger=None, observe=None):
    """Scan terminal candidates; resolve each under fresh locks, preserve replay.

    A returned receipt can recover an ambiguous COMMIT. Ordinary candidate
    faults propagate sanitized errors to the existing sweep hook isolation.
    Completed candidates survive a later candidate failure.
    """
    query = select(tracker.c.usage_id, tracker.c.execution_ref).join(
        jobs, jobs.c.execution_id == tracker.c.execution_ref
    ).where(jobs.c.status.in_(_TERMINAL), tracker.c.state != "FINALIZED").order_by(
        tracker.c.execution_ref, tracker.c.usage_id)
    if execution_ref is not None:
        query = query.where(tracker.c.execution_ref == execution_ref)
    outcomes = []
    try:
        with engine.connect() as conn:
            candidates = conn.execute(query).all()
        for identity, execution in candidates:
            prepared = None
            def operation(conn):
                nonlocal prepared
                job = conn.execute(select(jobs).where(jobs.c.execution_id == execution)
                    .with_for_update()).mappings().one_or_none()
                if job is None or job["status"] not in _TERMINAL:
                    return None
                row = conn.execute(select(tracker).where(tracker.c.usage_id == identity)
                    .with_for_update()).mappings().one_or_none()
                if row is None or row["case_id"] != job["case_id"] or row["execution_ref"] != execution:
                    return None
                if row["state"] == "FINALIZED":
                    if prepared is None:
                        return None
                    final = conn.execute(select(usage_record).where(usage_record.c.usage_id == identity)
                        .with_for_update()).mappings().one_or_none()
                    if final is None or not _same(final, prepared, _START + _OBSERVATION[:-2] + _RUN):
                        raise UsageConflictError()
                    return ReconciliationOutcome(identity, execution)
                relation = _relationship(row, job)
                if relation is None:
                    return None
                if prepared is None:
                    prepared = {**dict(row), **relation, "finalized_at": conn.scalar(select(func.now(6)))}
                elif not _same(row, prepared, _START + _OBSERVATION) or not _same(relation, prepared, _RUN):
                    raise UsageConflictError()
                try:
                    append_final(conn, _contract(prepared))
                except UsageIdentityConflict:
                    raise UsageConflictError() from None
                conn.execute(update(tracker).where(tracker.c.usage_id == identity).values(
                    **relation, state="FINALIZED", finalized_at=prepared["finalized_at"],
                    # A normal T1 can follow failed finish persistence. Its
                    # unobserved fallback Final is recovery too, so later finish
                    # replay must enrich the tracker without changing the Final.
                    recovered_at=prepared["finalized_at"] if recovery or prepared["observed_at"] is None else None))
                return ReconciliationOutcome(identity, execution)
            result = run_worker_transaction(engine, operation, sleep=sleep, logger=logger)
            if result is not None:
                outcomes.append(result)
        with engine.connect() as conn:
            metrics = _metrics(conn)
    except UsageError:
        raise
    except Exception:
        raise UsagePersistenceError() from None
    _observe(metrics, logger, observe)
    return tuple(outcomes)
