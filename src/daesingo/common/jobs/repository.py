"""Runtime queue persistence; only claim owns its short DB transaction."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import insert, select, func, text, update
from sqlalchemy.engine import Connection, Engine

from daesingo.common.config import WorkerSettings
from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.job_execution import (
    JobExecution, JobExecutionError, RuntimeContractRef, validate_transition,
)
from daesingo.common.logging import log_event

from .schema import job_execution


def _identifier(value: Any, name: str, length: int) -> str:
    # Match existing Case ascii_bin identity storage. Never silently truncate IDs.
    if not isinstance(value, str) or not value or len(value) > length or not value.isascii():
        raise ValueError(f"invalid {name}")
    return value


def enqueue(conn: Connection, job_records: Iterable[Mapping[str, Any]], trace_id: str) -> list[str]:
    """Append attempt 1 QUEUED rows and return their IDs in input order.

    Consume only job_id/case_id/kind; Case retains ownership of intent and kind
    semantics. Unknown kinds are accepted for later Worker dispatch. Validate
    the entire input before writing; one multi-row INSERT is statement-atomic
    on InnoDB. Duplicate (job_id, attempt) propagates IntegrityError; the caller
    decides rollback. This is not an idempotent unknown-COMMIT retry callback.
    """
    if not conn.in_transaction():
        raise ValueError("enqueue requires a caller-owned transaction")
    trace = _identifier(trace_id, "trace_id", 128)
    rows = [
        {"execution_id": f"exec_{uuid4().hex}",
         "job_id": _identifier(job["job_id"], "job_id", 191),
         "case_id": _identifier(job["case_id"], "case_id", 128),
         "kind": _identifier(job["kind"], "kind", 64), "trace_id": trace,
         "status": "QUEUED", "attempt": 1, "produced": []}
        for job in job_records
    ]
    if not rows:
        return []
    # MySQL DATETIME has no timezone. Use the DB's UTC clock, independent of
    # session timezone or API/container clocks; preserve microsecond precision.
    now = conn.scalar(select(func.utc_timestamp(6)))
    for row in rows:
        row.update(queued_at=now, available_at=now)
    conn.execute(insert(job_execution).values(rows))
    return [row["execution_id"] for row in rows]


class ClaimLostError(RuntimeError):
    """A pinned receipt cannot safely be dispatched; never an empty queue."""


@dataclass(frozen=True)
class ClaimedExecution:
    execution_id: str
    job_id: str
    attempt: int
    kind: str
    case_id: str
    trace_id: str
    lease_owner: str
    started_at: datetime
    lease_expires_at: datetime


_CLAIM_SELECT = text("""SELECT execution_id FROM job_execution
WHERE status = 'QUEUED' AND available_at <= NOW(6)
ORDER BY available_at, execution_id LIMIT 1 FOR UPDATE SKIP LOCKED""")
_CLAIM_UPDATE = text("""UPDATE job_execution
SET status = 'RUNNING', started_at = NOW(6), heartbeat_at = NOW(6),
    lease_owner = :owner, lease_expires_at = TIMESTAMPADD(MICROSECOND, :lease_us, NOW(6)),
    claim_token = :token
WHERE execution_id = :execution_id AND status = 'QUEUED' AND available_at <= NOW(6)""")


_EXECUTION_CONTRACT_FIELDS = (
    "execution_id", "job_id", "status", "attempt", "queued_at", "started_at",
    "ended_at", "produced", "failure_kind",
)


def _execution_model(row: Mapping[str, Any], **changes: Any) -> JobExecution:
    # Pydantic errors retain their input even when extra fields are ignored.
    # Project before validation so neither rows nor overrides disclose internals.
    payload = {name: row[name] for name in _EXECUTION_CONTRACT_FIELDS}
    payload.update({name: value for name, value in changes.items()
                    if name in _EXECUTION_CONTRACT_FIELDS})
    for name in ("queued_at", "started_at", "ended_at"):
        if payload[name] is not None:
            payload[name] = payload[name].replace(tzinfo=timezone.utc)
    return JobExecution(contract="JobExecution", contract_version="job-execution/v1.1",
                        usage_refs=[], **payload)


def _claimed(row: Mapping[str, Any]) -> ClaimedExecution:
    model = _execution_model(row)
    return ClaimedExecution(
        execution_id=model.execution_id, job_id=model.job_id, attempt=model.attempt,
        kind=row["kind"], case_id=row["case_id"], trace_id=row["trace_id"],
        lease_owner=row["lease_owner"], started_at=model.started_at,
        lease_expires_at=row["lease_expires_at"].replace(tzinfo=timezone.utc),
    )


def claim_one(
    engine: Engine, worker_id: str, *,
    lease_duration_sec: float = WorkerSettings.model_fields["lease_duration_sec"].default,
    logger: logging.Logger | None = None,
) -> ClaimedExecution | None:
    """Claim at most one execution, returning only after acknowledged commit.

    Requires the RT-02 READ COMMITTED/UTC application engine. ID and receipt are
    scoped to this public invocation, not the worker ID, and survive all retries.
    A retry locks the same PK to resolve a possibly still-finishing transaction;
    it never skips that receipt and never selects a second queue row.
    """
    owner = _identifier(worker_id, "worker_id", 128)
    if (type(lease_duration_sec) not in (int, float) or not math.isfinite(lease_duration_sec)
            or lease_duration_sec <= 0 or lease_duration_sec * 1_000_000 < 1):
        raise ValueError("invalid lease_duration_sec")
    lease_us = int(lease_duration_sec * 1_000_000)
    token = "claim_" + uuid4().hex
    execution_id = None
    attempt_status = "CLAIMED"

    def operation(conn: Connection):
        nonlocal execution_id, attempt_status
        attempt_status = "CLAIMED"
        if execution_id is None:
            execution_id = conn.execute(_CLAIM_SELECT).scalar_one_or_none()
            if execution_id is None:
                attempt_status = "EMPTY"
                return None
        else:
            existing = conn.execute(select(job_execution).where(
                job_execution.c.execution_id == execution_id).with_for_update()).mappings().one_or_none()
            if existing is None:
                raise ClaimLostError("claim receipt missing")
            if existing["status"] == "RUNNING":
                now = conn.scalar(select(func.now(6)))
                if (existing["claim_token"] != token or existing["lease_owner"] != owner
                        or existing["lease_expires_at"] is None or existing["lease_expires_at"] <= now):
                    raise ClaimLostError("claim receipt no longer owned")
                attempt_status = "RECOVERED"
                return _claimed(existing)
            if existing["status"] != "QUEUED" or existing["claim_token"] is not None:
                raise ClaimLostError("claim receipt no longer queued")
        validate_transition("QUEUED", "RUNNING")
        changed = conn.execute(_CLAIM_UPDATE, {
            "execution_id": execution_id, "owner": owner, "token": token, "lease_us": lease_us,
        }).rowcount
        if changed != 1:
            raise ClaimLostError("claim eligibility changed")
        snapshot = conn.execute(select(job_execution).where(
            job_execution.c.execution_id == execution_id)).mappings().one()
        return _claimed(snapshot)

    def observe(attempt):
        if logger is not None:
            status = attempt_status if attempt.outcome == "COMMITTED" else attempt.outcome
            name = "claim_recovery_latency_ms" if attempt_status == "RECOVERED" else "claim_latency_ms"
            log_event(logger, "runtime.db." + name, status=status, duration_ms=attempt.duration_ms)

    return run_worker_transaction(engine, operation, logger=logger, observe=observe)


FinishStatus = Literal["SUCCEEDED", "FAILED", "CANCELLED"]


def finish(
    conn: Connection, execution_id: str, owner: str, *, status: FinishStatus,
    produced: Iterable[RuntimeContractRef | dict[str, Any]] = (), failure_kind: str | None = None,
) -> int:
    """Worker terminal write; caller owns rollback, commit and any full retry.

    Validate a snapshot, but arbitrate through the final conditional UPDATE.
    Lease expiry alone is not loss of ownership; RT-06 owns STALE transitions.
    Keep lease/receipt metadata for audit and do not create another attempt.
    """
    if not conn.in_transaction():
        raise ValueError("finish requires a caller-owned transaction")
    execution = _identifier(execution_id, "execution_id", 128)
    lease_owner = _identifier(owner, "owner", 128)
    validate_transition("RUNNING", status)
    if status == "STALE":
        raise JobExecutionError("INVALID_FINISH_STATUS", "STALE belongs to recovery")
    refs = [RuntimeContractRef.model_validate(ref) for ref in produced]
    if status == "CANCELLED" and refs:
        raise ValueError("CANCELLED produced must be empty")
    if failure_kind is not None and (not isinstance(failure_kind, str) or len(failure_kind) > 191):
        raise ValueError("invalid failure_kind")
    predicate = (job_execution.c.execution_id == execution,
                 job_execution.c.status == "RUNNING", job_execution.c.lease_owner == lease_owner)
    snapshot = conn.execute(select(job_execution).where(*predicate)).mappings().one_or_none()
    if snapshot is None:
        return 0
    ended = conn.scalar(select(func.now(6)))
    model = _execution_model(snapshot, status=status, ended_at=ended, produced=refs,
                             failure_kind=failure_kind)
    return conn.execute(update(job_execution).where(*predicate).values(
        status=status, ended_at=ended, produced=[r.model_dump() for r in model.produced],
        failure_kind=model.failure_kind,
    )).rowcount
