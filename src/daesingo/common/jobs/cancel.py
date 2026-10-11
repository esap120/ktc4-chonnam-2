"""Caller-owned cancellation port and execution-local cooperative signal."""

from collections.abc import Iterable
from dataclasses import dataclass
from threading import Event, Lock
import time

from sqlalchemy import text
from sqlalchemy.engine import Connection


class CancellationRequested(Exception):
    """Checkpoint control flow, never a handler failure or ownership loss."""

    def __init__(self):
        super().__init__("cancellation requested")


class CancelSignal:
    def __init__(self, *, clock=time.monotonic):
        self._requested = Event()
        self._lock = Lock()
        self._checkpoint_at = None
        self.clock = clock

    @property
    def requested(self) -> bool:
        return self._requested.is_set()

    @property
    def checkpoint_at(self) -> float | None:
        with self._lock:
            return self._checkpoint_at

    def request(self) -> bool:
        """Return true only for the first observation, independent of sinks."""
        with self._lock:
            if self._requested.is_set():
                return False
            self._requested.set()
            return True

    def checkpoint(self) -> None:
        with self._lock:
            if not self._requested.is_set():
                return
            if self._checkpoint_at is None:
                self._checkpoint_at = self.clock()
        raise CancellationRequested()


@dataclass(frozen=True, slots=True)
class CancelledExecution:
    """Internal T1 outcome; handlers/Case reflection retain HandlerResult."""
    status: str = "CANCELLED"
    produced: tuple = ()
    failure_kind: None = None


_LOCK_JOB = text("""SELECT execution_id, status FROM job_execution
FORCE INDEX (uq_job_execution_job_attempt)
WHERE job_id = :job_id
ORDER BY job_id, attempt, execution_id FOR UPDATE""")
_CANCEL_QUEUED = text("""UPDATE job_execution
SET status = 'CANCELLED', cancel_requested_at = COALESCE(cancel_requested_at, NOW(6)),
ended_at = NOW(6), produced = JSON_ARRAY()
WHERE execution_id = :execution_id AND status = 'QUEUED'""")
_MARK_CANCEL = text("""UPDATE job_execution
SET cancel_requested_at = COALESCE(cancel_requested_at, NOW(6))
WHERE execution_id = :execution_id AND status IN ('RUNNING', 'STALE')""")


def request_cancel(conn: Connection, job_ids: Iterable[str]) -> None:
    """Lock every attempt before writes. Never commit, roll back or retry.

    Unique (job_id, attempt) index scans acquire locks in index order rather
    than relying on a filesort to order locks. A sweeper must lock its STALE
    row and recheck its marker before inserting the next attempt (RT-06).
    Caller must use the shared READ COMMITTED/UTC application Connection.
    """
    if not conn.in_transaction():
        raise ValueError("request_cancel requires a caller-owned transaction")
    try:
        if isinstance(job_ids, (str, bytes)):
            raise ValueError()
        snapshot = list(job_ids)
        if any(type(job) is not str or not job or len(job) > 191 or not job.isascii()
               for job in snapshot):
            raise ValueError()
        ordered = sorted(set(snapshot))
    except Exception:
        raise ValueError("invalid cancel job_ids") from None
    locked = []
    for job in ordered:
        locked.extend(conn.execute(_LOCK_JOB, {"job_id": job}).mappings().all())
    for row in locked:
        if row["status"] == "QUEUED":
            conn.execute(_CANCEL_QUEUED, {"execution_id": row["execution_id"]})
        elif row["status"] in ("RUNNING", "STALE"):
            conn.execute(_MARK_CANCEL, {"execution_id": row["execution_id"]})
