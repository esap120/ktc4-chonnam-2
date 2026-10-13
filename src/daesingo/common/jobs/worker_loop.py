"""Single-execution scheduling; only short claim/T1 callbacks touch the DB."""

from collections.abc import Callable
from dataclasses import dataclass, replace
import logging
import sys
from threading import Event
import time

from sqlalchemy.exc import DBAPIError, TimeoutError

from daesingo.common.config import WorkerSettings
from daesingo.common.db.errors import TransactionRetryExhausted, db_reason
from daesingo.common.jobs.execution import ExecutionContext, HandlerResult, runtime_failure, validated_terminal
from daesingo.common.jobs.repository import ClaimedExecution, ClaimLostError
from daesingo.common.jobs.heartbeat import OwnershipLost
from daesingo.common.jobs.cancel import CancellationRequested, CancelledExecution
from daesingo.common.logging import bind_context, log_event_best_effort, safe_correlation
from daesingo.common.usage.port import UsageError, UsageSink

_DB_ERRORS = (DBAPIError, TimeoutError, TransactionRetryExhausted)


@dataclass(frozen=True, slots=True)
class TerminalCommit:
    """Internal successful T1 receipt, frozen before sinks/pool cleanup."""
    acknowledged_at: float | None


class WorkerLoop:
    def __init__(
        self, *, claim: Callable[[], ClaimedExecution | None],
        dispatch: Callable[[ExecutionContext], HandlerResult],
        record: Callable[[ExecutionContext, HandlerResult | CancelledExecution], bool | TerminalCommit],
        settings: WorkerSettings, stop: Event, logger: logging.Logger,
        reflect: Callable[[ExecutionContext, HandlerResult], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        idle_wait: Callable[[float], object] | None = None,
        clock: Callable[[], float] = time.monotonic,
        heartbeat: Callable | None = None,
        sweeper=None,
        usage_sink_factory: Callable[[ExecutionContext], UsageSink] | None = None,
    ):
        self.claim, self.dispatch, self.record = claim, dispatch, record
        self.settings, self.stop, self.logger = settings, stop, logger
        self.reflect = reflect
        self.heartbeat = heartbeat
        self.sweeper = sweeper
        self.usage_sink_factory = usage_sink_factory
        self.sleep, self.idle_wait, self.clock = sleep, idle_wait or sleep, clock

    def _db_error(self, error: Exception):
        # Never serialize the exception, SQL, parameters or raw driver message.
        reason = db_reason(error) or "db_failure"
        log_event_best_effort(self.logger, "runtime.db.error_count", level=logging.ERROR,
                  status=reason.upper())

    def run(self) -> None:
        try:
            if self.sweeper is not None:
                self.sweeper.start()
            self._run_claims()
        finally:
            if self.sweeper is not None:
                primary = sys.exc_info()[1]
                try:
                    self.sweeper.stop_and_join()
                except BaseException:
                    if primary is None:
                        raise

    def _run_claims(self) -> None:
        while not self.stop.is_set():
            try:
                claimed = self.claim()
            except _DB_ERRORS as error:
                self._db_error(error)
                self.idle_wait(self.settings.error_backoff_sec)
                continue
            except ClaimLostError:
                log_event_best_effort(self.logger, "runtime.execution.claim_lost", level=logging.WARNING)
                self.idle_wait(self.settings.error_backoff_sec)
                continue
            if claimed is None:
                if not self.stop.is_set():
                    self.idle_wait(self.settings.idle_poll_sec)
                continue
            context = ExecutionContext(claimed.execution_id, claimed.job_id,
                                       claimed.case_id, claimed.kind, claimed.attempt, claimed.trace_id)
            with bind_context(**safe_correlation(
                trace_id=context.trace_id, case_id=context.case_id,
                job_id=context.job_id, execution_id=context.execution_id,
            )):
                started = self.clock()
                heartbeat = self.heartbeat(context) if self.heartbeat is not None else None
                try:
                    if heartbeat is not None:
                        heartbeat.start(context.execution_id)
                    if claimed.queued_at is not None:
                        log_event_best_effort(self.logger, "runtime.queue.wait_ms",
                            status="RETRY" if claimed.attempt >= 2 else "INITIAL",
                            duration_ms=max(0, (claimed.started_at - claimed.queued_at).total_seconds() * 1000))
                    log_event_best_effort(self.logger, "runtime.execution.started", status="RUNNING")
                    try:
                        context.checkpoint()
                        if self.usage_sink_factory is not None:
                            context = replace(context, usage_sink=self.usage_sink_factory(context))
                        result = self.dispatch(context)
                        if not isinstance(result, HandlerResult):
                            result = runtime_failure("RUNTIME_INVALID_RESULT")
                        else:
                            result = validated_terminal(result)
                    except CancellationRequested:
                        result = CancelledExecution()
                    except UsageError as error:
                        result = runtime_failure("RUNTIME_USAGE_" + error.code)
                    except Exception:
                        result = runtime_failure("RUNTIME_HANDLER_ERROR")
                    # Preserve terminal facts across DB retries; every attempt,
                    # including B-D8 retries, must still own this execution.
                    committed = False
                    while not context.ownership.lost:
                        try:
                            committed = self.record(context, result)
                            break
                        except OwnershipLost:
                            break
                        except _DB_ERRORS as error:
                            self._db_error(error)
                            if context.ownership.lost:
                                break
                            self.sleep(self.settings.error_backoff_sec)
                    if committed and result.status == "CANCELLED":
                        # A production receipt retains the COMMIT endpoint even
                        # if record's terminal metric sink was slow or failed.
                        # Metrics run outside the terminal transaction retry path.
                        try:
                            ended = (committed.acknowledged_at if isinstance(committed, TerminalCommit)
                                     else context.cancel_signal.clock())
                            checkpoint_at = context.cancel_signal.checkpoint_at
                            if ended is not None and checkpoint_at is not None:
                                log_event_best_effort(self.logger, "runtime.cancel.checkpoint_to_terminal_ms",
                                    status="CANCELLED", duration_ms=max(0, (ended - checkpoint_at) * 1000))
                        except Exception:
                            pass
                finally:
                    if heartbeat is not None:
                        primary = sys.exc_info()[1]
                        try:
                            heartbeat.stop_and_join()
                        except BaseException:
                            if primary is None:
                                raise
                if committed:
                    log_event_best_effort(self.logger, "runtime.execution.completed", status=result.status,
                              duration_ms=max(0, (self.clock() - started) * 1000))
                    if self.reflect is not None and result.status != "CANCELLED":
                        try:
                            self.reflect(context, result)
                        except _DB_ERRORS as error:
                            # RT-06 owns T2 redelivery. Back off before the next
                            # claim, using the same interruptible idle boundary.
                            self._db_error(error)
                            log_event_best_effort(self.logger, "runtime.reflect.failed", level=logging.ERROR,
                                                  status="FAILED")
                            self.idle_wait(self.settings.error_backoff_sec)
                        except Exception:
                            # T1 is durable. RT-06 owns redelivery, not this loop.
                            log_event_best_effort(self.logger, "runtime.reflect.failed", level=logging.ERROR,
                                                  status="FAILED")
                else:
                    log_event_best_effort(self.logger, "runtime.execution.finish_rejected", level=logging.WARNING)
