"""Expired lease recovery and handler-independent startup/periodic sweeps.

Each candidate uses a short transaction. Never call hooks while holding a DB
connection; RT-07 can register reconciliation without an import from Runtime.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from threading import Event, Thread
import time
from uuid import uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout

from daesingo.common.config import WorkerSettings
from daesingo.common.db.errors import TransactionRetryExhausted, db_reason
from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.job_execution import validate_transition
from daesingo.common.logging import bind_context, log_event_best_effort, safe_correlation

from .retry_policy import is_stale, retry_backoff, should_retry
from .schema import job_execution as jobs

_DB_ERRORS = (DBAPIError, PoolTimeout, TransactionRetryExhausted)


@dataclass(frozen=True, slots=True)
class SweepOutcome:
    execution_id: str
    job_id: str
    case_id: str
    trace_id: str
    ended_at: datetime
    heartbeat_at: datetime | None
    retry_execution_id: str | None
    reason: str

    @property
    def detect_latency_sec(self) -> float | None:
        return _detect_latency(self)


def _detect_latency(outcome: SweepOutcome) -> float | None:
    # Schema permits NULL. Never substitute the lease, start time or zero for
    # an absent/invalid last heartbeat. This observation runs after COMMIT.
    if outcome.heartbeat_at is None:
        return None
    seconds = (outcome.ended_at - outcome.heartbeat_at).total_seconds()
    return seconds if seconds >= 0 else None


def sweep_expired(conn: Connection, execution_id: str, settings: WorkerSettings, *,
                  retry_execution_id: str | None = None) -> SweepOutcome | None:
    """Caller owns commit/rollback. Recheck lease and marker under the row lock.

    SKIP LOCKED lets another sweeper, heartbeat, terminal writer or cancellation
    finish first. UNIQUE(job_id, attempt) is the final duplicate guard. INSERT
    errors propagate: callers must roll back the entire transaction.
    """
    if not conn.in_transaction():
        raise ValueError("sweep requires a caller-owned transaction")
    row = conn.execute(select(jobs).where(jobs.c.execution_id == execution_id)
        .with_for_update(skip_locked=True)).mappings().one_or_none()
    if row is None:
        return None
    now = conn.scalar(select(func.now(6)))
    if not is_stale(row["status"], row["lease_expires_at"], now):
        return None
    validate_transition("RUNNING", "STALE")
    changed = conn.execute(update(jobs).where(
        jobs.c.execution_id == execution_id, jobs.c.status == "RUNNING",
        jobs.c.lease_expires_at < func.now(6),
    ).values(status="STALE", ended_at=func.now(6), produced=[])).rowcount
    if changed != 1:
        return None
    # Use the actual UPDATE's DB timestamp for both the receipt and new attempt.
    now = conn.scalar(select(jobs.c.ended_at).where(jobs.c.execution_id == execution_id))
    cancelled = row["cancel_requested_at"] is not None
    retry_id = None
    reason = "CANCELLED" if cancelled else "EXHAUSTED"
    if should_retry("STALE", row["attempt"], cancelled, retry_max=settings.stale_retry_max):
        retry_id = retry_execution_id if retry_execution_id is not None else "exec_" + uuid4().hex
        attempt = row["attempt"] + 1
        conn.execute(insert(jobs).values(
            execution_id=retry_id, job_id=row["job_id"], case_id=row["case_id"],
            kind=row["kind"], trace_id=row["trace_id"], attempt=attempt,
            status="QUEUED", produced=[], queued_at=now,
            available_at=now + timedelta(seconds=retry_backoff(attempt, settings)),
        ))
        reason = "RETRIED"
    return SweepOutcome(execution_id, row["job_id"], row["case_id"], row["trace_id"], now,
        row["heartbeat_at"], retry_id, reason)


def _recover(conn: Connection, outcome: SweepOutcome) -> SweepOutcome | None:
    # A blocking PK read resolves a possibly still-finishing unknown COMMIT.
    row = conn.execute(select(jobs.c.status, jobs.c.ended_at).where(
        jobs.c.execution_id == outcome.execution_id).with_for_update()).mappings().one_or_none()
    if row is None or row["status"] != "STALE" or row["ended_at"] != outcome.ended_at:
        return None
    if outcome.retry_execution_id is not None:
        child = conn.execute(select(jobs.c.execution_id).where(
            jobs.c.execution_id == outcome.retry_execution_id).with_for_update()).scalar_one_or_none()
        if child is None:
            return None
    return outcome


def sweep_once(engine: Engine, settings: WorkerSettings, *, sleep: Callable = time.sleep,
               logger: logging.Logger | None = None) -> tuple[SweepOutcome, ...]:
    """One candidate scan, then one B-D8 transaction per original execution.

    Pin retry IDs across replay; already-STALE rows never create another child.
    Independent committed candidates survive a later candidate's failure.
    """
    with engine.connect() as conn:
        candidates = conn.execute(select(jobs.c.execution_id).where(
            jobs.c.status == "RUNNING", jobs.c.lease_expires_at < func.now(6),
        ).order_by(jobs.c.job_id, jobs.c.attempt)).scalars().all()
    outcomes = []
    for execution_id in candidates:
        retry_id = "exec_" + uuid4().hex
        pending = None

        def operation(conn):
            nonlocal pending
            if pending is not None:
                recovered = _recover(conn, pending)
                if recovered is not None:
                    return recovered
            pending = sweep_expired(conn, execution_id, settings, retry_execution_id=retry_id)
            return pending

        result = run_worker_transaction(engine, operation, sleep=sleep, logger=logger)
        if result is not None:
            outcomes.append(result)
            if logger is not None:
                with bind_context(**safe_correlation(trace_id=result.trace_id, case_id=result.case_id,
                    job_id=result.job_id, execution_id=result.execution_id)):
                    log_event_best_effort(logger, "runtime.stale.count", status="STALE")
                    # Existing logging schema carries durations in milliseconds.
                    try:
                        latency = result.detect_latency_sec
                        if latency is not None:
                            log_event_best_effort(logger, "runtime.stale.detect_latency_s", status="STALE",
                                duration_ms=latency * 1000)
                    except Exception:
                        # Measurement/sink failures cannot replay durable recovery.
                        pass
                    if result.reason == "RETRIED":
                        log_event_best_effort(logger, "runtime.retry.auto_count", status="QUEUED")
                    elif result.reason == "EXHAUSTED":
                        log_event_best_effort(logger, "runtime.retry.exhausted_count", status="STALE")
    return tuple(outcomes)


class SweepService:
    """Synchronous startup gate followed by one periodic thread per Worker.

    Hooks are immutable registration at composition time, run after recovery
    transactions, and own their own persistence boundaries. Ordinary hook faults
    are isolated so reconciliation cannot prevent other registered work.
    """
    def __init__(self, *, sweep: Callable, settings: WorkerSettings, stop: Event,
                 logger: logging.Logger, hooks: Sequence[Callable[[], object]] = (),
                 wait: Callable | None = None, retry_wait: Callable | None = None):
        self.sweep, self.settings, self.worker_stop, self.logger = sweep, settings, stop, logger
        self.hooks = tuple(hooks)
        self.stop = Event()
        self.wait = wait if wait is not None else self.stop.wait
        self.retry_wait = retry_wait if retry_wait is not None else stop.wait
        self.thread = None
        self._fatal = None

    def _pass(self):
        self.sweep()
        for hook in self.hooks:
            try:
                hook()
            except Exception:
                log_event_best_effort(self.logger, "runtime.sweep.hook_failed", level=logging.ERROR,
                    status="FAILED")

    def _db_error(self, error):
        log_event_best_effort(self.logger, "runtime.sweep.failed", level=logging.ERROR,
            status=(db_reason(error) or "db_failure").upper())

    def start(self):
        # B-L5: no claim admission until the startup pass has succeeded.
        while not self.worker_stop.is_set():
            try:
                self._pass()
                break
            except _DB_ERRORS as error:
                self._db_error(error)
                self.retry_wait(self.settings.error_backoff_sec)
        if not self.worker_stop.is_set():
            # Start outside execution context: sweep handles multiple executions.
            self.thread = Thread(target=self._thread_main, name="runtime-sweep")
            self.thread.start()

    def run(self):
        while not self.stop.is_set() and not self.worker_stop.is_set():
            if self.wait(self.settings.stale_sweep_interval_sec) or self.stop.is_set() or self.worker_stop.is_set():
                break
            try:
                self._pass()
            except Exception as error:
                self._db_error(error)

    def _thread_main(self):
        try:
            self.run()
        except BaseException as error:
            self._fatal = error
            self.worker_stop.set()

    def stop_and_join(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        if self._fatal is not None:
            raise self._fatal
