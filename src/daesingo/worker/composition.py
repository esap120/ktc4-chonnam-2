"""Worker wiring: reuse RT-01 config and RT-02/03 DB transaction boundaries."""

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from functools import partial
from threading import Event
import time
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.engine import Engine

from daesingo.common.bootstrap import Startup
from daesingo.common.db import create_heartbeat_engine
from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.jobs.execution import ExecutionContext, HandlerResult
from daesingo.common.jobs.cancel import CancelledExecution
from daesingo.common.jobs.heartbeat import Heartbeat, LeaseConnection
from daesingo.common.jobs.repository import claim_one, finish
from daesingo.common.jobs.schema import job_execution
from daesingo.common.jobs.sweep import SweepService, sweep_once
from daesingo.common.jobs.worker_loop import WorkerLoop, TerminalCommit
from daesingo.common.jobs.reflection import ReflectionInput, ResultReflector, reflect_terminal
from daesingo.common.jobs.redelivery import observe_reflection, redeliver_once
from daesingo.common.logging import bind_context, log_event_best_effort, safe_correlation
from daesingo.worker.registry import KindRegistry
from daesingo.common.usage.sink import DurableUsageSink
from daesingo.common.usage.reconciliation import reconcile_once

_CANCEL_TERMINAL_LATENCY = text("""SELECT
TIMESTAMPDIFF(MICROSECOND, cancel_requested_at, NOW(6)) / 1000.0
FROM job_execution WHERE execution_id = :execution_id""")


def compose_worker(
    *, engine: Engine, startup: Startup, registry: KindRegistry, stop: Event,
    reflector: ResultReflector | None = None,
    heartbeat_engine: Engine | None = None, heartbeat_observe: Callable | None = None,
    cancel_observe: Callable | None = None,
    worker_id: str | None = None, sleep: Callable[[float], None] = time.sleep,
    idle_wait: Callable[[float], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sweep_hooks: Sequence[Callable[[], object]] = (),
    usage_observe: Callable | None = None, usage_late_observe: Callable | None = None,
) -> WorkerLoop:
    """One main-thread execution at a time; no domain service is instantiated.

    RD-09a mutable Recording state belongs to a future per-execution invocation,
    with close in finally. Durable repositories need not be execution-local.
    """
    if startup.config.service != "worker" or startup.config.worker is None:
        raise ValueError("Worker composition requires Worker configuration")
    owner = worker_id if worker_id is not None else "worker_" + uuid4().hex
    settings = startup.config.worker

    def record(context: ExecutionContext, result: HandlerResult | CancelledExecution) -> bool | TerminalCommit:
        produced = [ref.model_dump() for ref in result.produced]
        terminal_latency = None
        sampled_at = acknowledged_at = None

        @contextmanager
        def commit_guard():
            nonlocal acknowledged_at
            with context.ownership.commit_guard():
                yield
                # run_worker_transaction exits conn.begin() before this guard:
                # COMMIT has acknowledged, pool cleanup/observers have not run.
                # An ambiguous COMMIT never reaches this successful exit.
                if result.status == "CANCELLED":
                    try:
                        acknowledged_at = context.cancel_signal.clock()
                    except Exception:
                        pass

        def cancellation_latency(conn):
            nonlocal terminal_latency, sampled_at
            if result.status == "CANCELLED":
                sampled_at = context.cancel_signal.clock()
                terminal_latency = conn.scalar(_CANCEL_TERMINAL_LATENCY,
                    {"execution_id": context.execution_id})

        def operation(conn):
            nonlocal terminal_latency, sampled_at, acknowledged_at
            terminal_latency = sampled_at = acknowledged_at = None
            context.ownership.check()
            changed = finish(conn, context.execution_id, owner, status=result.status,
                             produced=result.produced, failure_kind=result.failure_kind)
            if changed == 1:
                cancellation_latency(conn)
                return True
            # A lost COMMIT acknowledgement can replay T1 against its own already
            # terminal row. Re-read durable facts; 0 rows alone proves no success.
            # A locking read also waits for a possibly still-finishing COMMIT.
            stored = conn.execute(select(
                job_execution.c.status, job_execution.c.lease_owner,
                job_execution.c.produced, job_execution.c.failure_kind,
            ).where(job_execution.c.execution_id == context.execution_id)
              .with_for_update()).mappings().one_or_none()
            recovered = bool(stored is not None and stored["lease_owner"] == owner
                        and stored["status"] == result.status
                        and stored["produced"] == produced
                        and stored["failure_kind"] == result.failure_kind)
            if recovered:
                cancellation_latency(conn)
            return recovered

        committed = run_worker_transaction(engine, operation, sleep=sleep, logger=startup.logger,
                                      before_attempt=context.ownership.check,
                                      commit_guard=commit_guard)
        if committed:
            # Separate from T1 and after its connection has returned. Failure
            # leaves terminal usage for the next sweep; never replay the handler/T1.
            try:
                reconcile_once(engine, execution_ref=context.execution_id, recovery=False,
                    sleep=sleep, logger=startup.logger, observe=usage_observe)
            except Exception:
                log_event_best_effort(startup.logger, "runtime.usage.reconciliation_failed", status="FAILED")
        if committed and result.status == "CANCELLED":
            receipt = TerminalCommit(acknowledged_at)
            # Durable T1 is already final. Calculation/sink faults must never
            # become transaction failures or cause another terminal attempt.
            try:
                if terminal_latency is not None and sampled_at is not None and acknowledged_at is not None:
                    duration = float(terminal_latency) + (acknowledged_at - sampled_at) * 1000
                    log_event_best_effort(startup.logger, "runtime.cancel.terminal_latency_ms",
                                          status="CANCELLED", duration_ms=max(0, duration))
            except Exception:
                pass
            return receipt
        return committed

    def heartbeat(context):
        dedicated = heartbeat_engine if heartbeat_engine is not None else create_heartbeat_engine(
            startup.config.db, startup.config.heartbeat)
        lease = LeaseConnection(dedicated, context.execution_id, owner, settings.lease_duration_sec,
                                fence=context.ownership,
                                owns_engine=heartbeat_engine is None,
                                cancel_signal=context.cancel_signal, logger=startup.logger,
                                cancel_observe=cancel_observe)
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
            observe_reflection(incoming, result, startup.logger)
            return result

    return WorkerLoop(
        claim=partial(claim_one, engine, owner,
                      lease_duration_sec=settings.lease_duration_sec, logger=startup.logger),
        dispatch=registry.dispatch, record=record, settings=settings, stop=stop,
        logger=startup.logger, sleep=sleep, idle_wait=idle_wait or stop.wait, clock=clock,
        reflect=reflect if reflector is not None else None,
        heartbeat=heartbeat,
        usage_sink_factory=lambda context: DurableUsageSink(
            execution_ref=context.execution_id, case_id=context.case_id,
            logger=startup.logger, late_observe=usage_late_observe,
            transaction=lambda callback: run_worker_transaction(
                engine, callback, sleep=sleep, logger=startup.logger)),
        sweeper=SweepService(
            sweep=partial(sweep_once, engine, settings, sleep=sleep, logger=startup.logger),
            settings=settings, stop=stop, logger=startup.logger,
            hooks=(partial(reconcile_once, engine, sleep=sleep, logger=startup.logger, observe=usage_observe),
                   *sweep_hooks),
            redeliver=partial(redeliver_once, engine, reflector, sleep=sleep, logger=startup.logger)
                if reflector is not None else None,
        ),
    )
