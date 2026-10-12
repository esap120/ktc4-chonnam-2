"""Nonlocking T2 candidates, one caller-owned transaction per delivery.

No domain dependencies, delivery lease or Runtime-first lock. The Case port
serializes execution deduplication; reflect_terminal rechecks the Runtime
receipt after that lock and commits Case, followups and receipt atomically.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.engine import Engine

from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.logging import bind_context, log_event_best_effort, safe_correlation

from .execution import HandlerResult
from .reflection import ReflectionInput, ReflectionResult, ResultReflector, reflect_terminal
from .schema import job_execution as jobs


def observe_reflection(incoming: ReflectionInput, result: ReflectionResult,
                       logger: logging.Logger | None) -> None:
    """Post-commit observation shared by direct delivery and redelivery."""
    if (logger is not None and incoming.attempt >= 2 and result.status == "NOT_APPLIED"
            and result.reason == "STOPPED_WAITING"):
        log_event_best_effort(logger, "runtime.retry.after_case_stopped_count", status="STOPPED_WAITING")


def redeliver_once(engine: Engine, reflector: ResultReflector, *,
                   sleep: Callable = time.sleep, logger: logging.Logger | None = None
                   ) -> tuple[ReflectionResult, ...]:
    """Startup/periodic pass. Scan failures propagate; candidate faults isolate.

    A fresh, nonlocking read on every callback replay prevents calling Case for
    a durable receipt, including unknown COMMIT. A concurrent receipt may race
    that read: Case-first reflect_terminal resolves it under its later locks.
    CANCELLED and STALE are not Case ExecutionOutcome inputs.
    """
    with engine.connect() as conn:
        candidates = conn.execute(select(jobs.c.execution_id).where(
            jobs.c.status.in_(("SUCCEEDED", "FAILED")), jobs.c.case_applied_at.is_(None),
        ).order_by(jobs.c.job_id, jobs.c.attempt)).scalars().all()
    results = []
    for execution_id in candidates:
        incoming = trace_id = None

        def operation(conn):
            nonlocal incoming, trace_id
            row = conn.execute(select(jobs).where(jobs.c.execution_id == execution_id)).mappings().one_or_none()
            if row is None or row["status"] not in ("SUCCEEDED", "FAILED"):
                return None
            if row["case_applied_at"] is not None:
                return ReflectionResult("ALREADY_APPLIED")
            incoming = ReflectionInput(row["execution_id"], row["job_id"], row["case_id"],
                row["kind"], row["attempt"], HandlerResult(status=row["status"],
                    produced=row["produced"], failure_kind=row["failure_kind"]))
            trace_id = row["trace_id"]
            return reflect_terminal(conn, incoming, reflector, trace_id)

        try:
            result = run_worker_transaction(engine, operation, sleep=sleep, logger=logger)
        except Exception:
            # No exception strings, SQL, unsupported kind or reader payload logs.
            if logger is not None:
                with bind_context(**safe_correlation(execution_id=execution_id)):
                    log_event_best_effort(logger, "runtime.reflect.failed", level=logging.ERROR, status="FAILED")
            continue
        if result is not None:
            results.append(result)
            if logger is not None and incoming is not None:
                with bind_context(**safe_correlation(trace_id=trace_id, case_id=incoming.case_id,
                    job_id=incoming.job_id, execution_id=execution_id)):
                    log_event_best_effort(logger, "runtime.reflect.redelivery_count", status=result.status)
                    observe_reflection(incoming, result, logger)
    return tuple(results)
