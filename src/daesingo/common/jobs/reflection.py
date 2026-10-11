"""Caller-owned Case reflection port; no Case dependency or intent taxonomy."""

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.engine import Connection
from sqlalchemy import func, select, update

from .execution import HandlerResult, validated_terminal
from .repository import _identifier, enqueue
from .schema import job_execution


def _initialize(value, extra, **fields):
    if extra:
        # Generated dataclass TypeErrors echo untrusted keyword names.
        raise TypeError("invalid reflection fields")
    for key, field in fields.items():
        object.__setattr__(value, key, field)
    value.__post_init__()


@dataclass(frozen=True, slots=True, init=False)
class RuntimeJobRecord:
    """Immutable enqueue projection; Case retains its full JobRecord/intent."""
    job_id: str
    case_id: str
    kind: str

    def __init__(self, job_id: str, case_id: str, kind: str, **extra):
        _initialize(self, extra, job_id=job_id, case_id=case_id, kind=kind)

    def __post_init__(self):
        try:
            _identifier(self.job_id, "job_id", 191)
            _identifier(self.case_id, "case_id", 128)
            _identifier(self.kind, "kind", 64)
        except Exception:
            raise ValueError("invalid reflection job") from None


@dataclass(frozen=True, slots=True, init=False)
class ReflectionInput:
    execution_id: str
    job_id: str
    case_id: str
    kind: str
    attempt: int
    terminal: HandlerResult

    def __init__(self, execution_id: str, job_id: str, case_id: str, kind: str,
                 attempt: int, terminal: HandlerResult, **extra):
        _initialize(self, extra, execution_id=execution_id, job_id=job_id, case_id=case_id,
                    kind=kind, attempt=attempt, terminal=terminal)

    def __post_init__(self):
        try:
            _identifier(self.execution_id, "execution_id", 128)
            RuntimeJobRecord(self.job_id, self.case_id, self.kind)
            if type(self.attempt) is not int or self.attempt < 1 or type(self.terminal) is not HandlerResult:
                raise ValueError()
            terminal = validated_terminal(self.terminal)
            object.__setattr__(self, "terminal", terminal)
        except Exception:
            raise ValueError("invalid reflection input") from None


@dataclass(frozen=True, slots=True, init=False)
class ReflectionResult:
    status: Literal["APPLIED", "ALREADY_APPLIED", "NOT_APPLIED"]
    reason: Literal["STOPPED_WAITING", "CANCELLED", "SUPERSEDED"] | None = None
    jobs: tuple[RuntimeJobRecord, ...] = ()

    def __init__(self, status: Literal["APPLIED", "ALREADY_APPLIED", "NOT_APPLIED"],
                 reason: Literal["STOPPED_WAITING", "CANCELLED", "SUPERSEDED"] | None = None,
                 jobs=(), **extra):
        _initialize(self, extra, status=status, reason=reason, jobs=jobs)

    def __post_init__(self):
        try:
            if type(self.status) is not str or self.status not in ("APPLIED", "ALREADY_APPLIED", "NOT_APPLIED"):
                raise ValueError()
            if self.reason is not None and type(self.reason) is not str:
                raise ValueError()
            if (self.reason not in ("STOPPED_WAITING", "CANCELLED", "SUPERSEDED")
                    if self.status == "NOT_APPLIED" else self.reason is not None):
                raise ValueError()
            jobs = tuple(self.jobs)
            if self.status != "APPLIED" and jobs:
                raise ValueError()
            if any(type(job) is not RuntimeJobRecord for job in jobs):
                raise ValueError()
            jobs = tuple(RuntimeJobRecord(job.job_id, job.case_id, job.kind) for job in jobs)
            if len({job.job_id for job in jobs}) != len(jobs):
                raise ValueError()
            object.__setattr__(self, "jobs", jobs)
        except Exception:
            raise ValueError("invalid reflection result") from None


def validated_result(value: ReflectionResult) -> ReflectionResult:
    """Rebuild at the port boundary, including model_copy/object tampering."""
    if type(value) is not ReflectionResult:
        raise ValueError("invalid reflection result")
    return ReflectionResult(value.status, value.reason, value.jobs)


class ResultReflector(Protocol):
    def reflect(self, conn: Connection, incoming: ReflectionInput) -> ReflectionResult:
        """Lock Case first, deduplicate execution_id, never commit/rollback/retry.

        The caller handles enqueue and the Runtime marker in this transaction.
        Actual Case execution-id persistence belongs to Case 8-8.
        """
        ...


def reflect_terminal(conn: Connection, incoming: ReflectionInput, reflector: ResultReflector,
                     trace_id: str) -> ReflectionResult:
    """One T2 attempt. Caller owns commit/rollback and whole-transaction retry.

    No Runtime row is locked before the reflector's Case lock. The Case port
    owns execution-id idempotency; Runtime also confirms its durable T2 receipt
    before replaying enqueue (which deliberately is not itself idempotent).
    """
    if not conn.in_transaction() or type(incoming) is not ReflectionInput:
        raise ValueError("invalid reflection transaction")
    incoming = ReflectionInput(incoming.execution_id, incoming.job_id, incoming.case_id,
                               incoming.kind, incoming.attempt, incoming.terminal)
    trace = _identifier(trace_id, "trace_id", 128)
    result = validated_result(reflector.reflect(conn, incoming))
    if any(job.case_id != incoming.case_id for job in result.jobs):
        raise ValueError("invalid reflection job case")
    expected = {
        "execution_id": incoming.execution_id, "job_id": incoming.job_id,
        "case_id": incoming.case_id, "kind": incoming.kind, "attempt": incoming.attempt,
        "status": incoming.terminal.status, "failure_kind": incoming.terminal.failure_kind,
        "produced": [ref.model_dump() for ref in incoming.terminal.produced], "trace_id": trace,
    }
    statement = select(*(job_execution.c[key] for key in expected), job_execution.c.case_applied_at).where(
        job_execution.c.execution_id == incoming.execution_id).with_for_update()

    def matching(row):
        return row is not None and all(row[key] == value for key, value in expected.items())

    stored = conn.execute(statement).mappings().one_or_none()
    if not matching(stored):
        raise ValueError("reflection terminal facts mismatch")
    if stored["case_applied_at"] is not None:
        if result.status == "APPLIED":
            raise ValueError("reflection receipt conflict")
        return ReflectionResult("ALREADY_APPLIED")
    enqueue(conn, [{"job_id": job.job_id, "case_id": job.case_id, "kind": job.kind}
                   for job in result.jobs], trace)
    changed = conn.execute(update(job_execution).where(
        job_execution.c.execution_id == incoming.execution_id,
        job_execution.c.status == incoming.terminal.status,
        job_execution.c.case_applied_at.is_(None),
    ).values(case_applied_at=func.utc_timestamp(6))).rowcount
    if changed != 1:
        stored = conn.execute(statement).mappings().one_or_none()
        if not matching(stored) or stored["case_applied_at"] is None:
            raise ValueError("reflection marker not recorded")
        return ReflectionResult("ALREADY_APPLIED")
    return result
