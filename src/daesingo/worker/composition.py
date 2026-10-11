"""Worker wiring: reuse RT-01 config and RT-02/03 DB transaction boundaries."""

from collections.abc import Callable
from functools import partial
from threading import Event
import time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine

from daesingo.common.bootstrap import Startup
from daesingo.common.db import create_heartbeat_engine
from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.jobs.execution import ExecutionContext, HandlerResult
from daesingo.common.jobs.heartbeat import Heartbeat, LeaseConnection
from daesingo.common.jobs.repository import claim_one, finish
from daesingo.common.jobs.schema import job_execution
from daesingo.common.jobs.worker_loop import WorkerLoop
from daesingo.common.jobs.reflection import ReflectionInput, ResultReflector, reflect_terminal
from daesingo.common.logging import bind_context, log_event_best_effort, safe_correlation
from daesingo.worker.registry import KindRegistry


def compose_worker(
    *, engine: Engine, startup: Startup, registry: KindRegistry, stop: Event,
    reflector: ResultReflector | None = None,
    heartbeat_engine: Engine | None = None, heartbeat_observe: Callable | None = None,
    worker_id: str | None = None, sleep: Callable[[float], None] = time.sleep,
    idle_wait: Callable[[float], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> WorkerLoop:
    """One main-thread execution at a time; no domain service is instantiated.

    RD-09a mutable Recording state belongs to a future per-execution invocation,
    with close in finally. Durable repositories need not be execution-local.
    """
    if startup.config.service != "worker" or startup.config.worker is None:
        raise ValueError("Worker composition requires Worker configuration")
    owner = worker_id if worker_id is not None else "worker_" + uuid4().hex
    settings = startup.config.worker

    def record(context: ExecutionContext, result: HandlerResult) -> bool:
        produced = [ref.model_dump() for ref in result.produced]

        def operation(conn):
            context.ownership.check()
            changed = finish(conn, context.execution_id, owner, status=result.status,
                             produced=result.produced, failure_kind=result.failure_kind)
            if changed == 1:
                return True
            # A lost COMMIT acknowledgement can replay T1 against its own already
            # terminal row. Re-read durable facts; 0 rows alone proves no success.
            # A locking read also waits for a possibly still-finishing COMMIT.
            stored = conn.execute(select(
                job_execution.c.status, job_execution.c.lease_owner,
                job_execution.c.produced, job_execution.c.failure_kind,
            ).where(job_execution.c.execution_id == context.execution_id)
              .with_for_update()).mappings().one_or_none()
            return bool(stored is not None and stored["lease_owner"] == owner
                        and stored["status"] == result.status
                        and stored["produced"] == produced
                        and stored["failure_kind"] == result.failure_kind)

        return run_worker_transaction(engine, operation, sleep=sleep, logger=startup.logger,
                                      before_attempt=context.ownership.check,
                                      commit_guard=context.ownership.commit_guard)

    def heartbeat(context):
        dedicated = heartbeat_engine if heartbeat_engine is not None else create_heartbeat_engine(
            startup.config.db, startup.config.heartbeat)
        lease = LeaseConnection(dedicated, context.execution_id, owner, settings.lease_duration_sec,
                                fence=context.ownership,
                                owns_engine=heartbeat_engine is None)
        return Heartbeat(renew=lease.renew, close=lease.close, fence=context.ownership,
                         interval=settings.heartbeat_interval_sec, logger=startup.logger,
                         observe=heartbeat_observe)

    def reflect(context: ExecutionContext, terminal: HandlerResult):
        incoming = ReflectionInput(context.execution_id, context.job_id, context.case_id,
                                   context.kind, context.attempt, terminal)
        with bind_context(**safe_correlation(trace_id=context.trace_id, case_id=context.case_id,
                                            job_id=context.job_id, execution_id=context.execution_id)):
            result = run_worker_transaction(
                engine, lambda conn: reflect_terminal(conn, incoming, reflector, context.trace_id),
                sleep=sleep, logger=startup.logger,
            )
            # A recovered/completed receipt is ALREADY_APPLIED, so no double count.
            if incoming.attempt >= 2 and result.status == "NOT_APPLIED" and result.reason == "STOPPED_WAITING":
                log_event_best_effort(startup.logger, "runtime.retry.after_case_stopped_count",
                                      status="STOPPED_WAITING")
            return result

    return WorkerLoop(
        claim=partial(claim_one, engine, owner,
                      lease_duration_sec=settings.lease_duration_sec, logger=startup.logger),
        dispatch=registry.dispatch, record=record, settings=settings, stop=stop,
        logger=startup.logger, sleep=sleep, idle_wait=idle_wait or stop.wait, clock=clock,
        reflect=reflect if reflector is not None else None,
        heartbeat=heartbeat,
    )
