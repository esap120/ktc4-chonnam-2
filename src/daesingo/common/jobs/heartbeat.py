"""One execution, one synchronous heartbeat thread, one dedicated connection."""

from contextlib import contextmanager
from dataclasses import dataclass
import math
import sys
from threading import Event, Lock, Thread
import time

from sqlalchemy import text

from daesingo.common.logging import copy_context_call, log_event_best_effort


class OwnershipLost(RuntimeError):
    """Internal fencing outcome, never a handler failure or a DB retry."""


class OwnershipFence:
    def __init__(self):
        self._lost = Event()
        self._commit = Lock()

    @property
    def lost(self):
        return self._lost.is_set()

    def wait_lost(self, timeout):
        return self._lost.wait(timeout)

    def mark_lost(self):
        # Serialize observed loss with the final check + COMMIT. SQL's owner
        # predicate arbitrates ownership transfers that have not been observed.
        with self._commit:
            self._lost.set()

    def check(self):
        if self.lost:
            raise OwnershipLost("execution ownership lost")

    @contextmanager
    def commit_guard(self):
        with self._commit:
            self.check()
            yield


@dataclass(frozen=True)
class HeartbeatObservation:
    outcome: str
    attempt_ms: float
    lag_ms: float | None
    skipped_tick_count: int
    consecutive_failures: int


@dataclass(frozen=True)
class CancelObservation:
    duration_ms: float


class Heartbeat:
    """Slow attempts account for elapsed ticks after returning; never catch up.

    Neither a second timer thread nor a second DB attempt is needed. Observation
    can be delayed by the synchronous DB call, which has no whole-attempt bound.
    """
    def __init__(self, *, renew, fence, interval, logger, close=lambda: None,
                 clock=time.monotonic, wait=None, observe=None):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("invalid heartbeat interval")
        self.renew, self.fence, self.interval, self.logger = renew, fence, interval, logger
        self.close_connection, self.clock, self.observe = close, clock, observe
        self.stop = Event()
        self.wait = wait if wait is not None else self.stop.wait
        self.thread = None
        self._fatal = None

    def start(self, execution_id):
        self.thread = Thread(target=copy_context_call(self._thread_main),
                             name="runtime-heartbeat-" + execution_id)
        self.thread.start()

    def _thread_main(self):
        try:
            self.run()
        except BaseException as error:
            # Preserve BaseException for the owning thread, without threading's
            # default raw traceback disclosure. It is never a retryable failure.
            self._fatal = error
            self.fence.mark_lost()

    def stop_and_join(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        if self._fatal is not None:
            raise self._fatal

    def _observe(self, observation):
        if self.observe is not None:
            try:
                self.observe(observation)
            except Exception:
                pass
        # Keep the existing logging field contract: counts use a sanitized
        # numeric status token; durations use the existing duration_ms field.
        for metric, value in (("attempt_ms", observation.attempt_ms),
                              ("lag_ms", observation.lag_ms)):
            if value is not None:
                log_event_best_effort(self.logger, "runtime.heartbeat." + metric,
                                      status=observation.outcome, duration_ms=value)
        for metric, value in (("skipped_tick_count", observation.skipped_tick_count),
                              ("consecutive_failures", observation.consecutive_failures)):
            log_event_best_effort(self.logger, "runtime.heartbeat." + metric, status=str(value))

    def run(self):
        last_success = self.clock()
        tick = last_success + self.interval
        failures = 0
        pending_skipped = 0
        try:
            while not self.stop.is_set() and not self.fence.lost:
                # Observer/logger latency also must not cause off-cadence
                # catch-up work. Report these missed ticks with the next attempt.
                missed = max(0, math.ceil((self.clock() - tick) / self.interval))
                tick += missed * self.interval
                pending_skipped += missed
                if self.wait(max(0, tick - self.clock())) or self.stop.is_set() or self.fence.lost:
                    break
                started = self.clock()
                lag = None
                try:
                    changed = self.renew()
                except Exception:
                    failures += 1
                    outcome = "OWNERSHIP_LOST" if self.fence.lost else "FAILED"
                else:
                    if changed == 0:
                        self.fence.mark_lost()
                        outcome = "OWNERSHIP_LOST"
                    else:
                        outcome = "RENEWED"
                        failures = 0
                        now = self.clock()
                        lag = max(0, (now - last_success - self.interval) * 1000)
                        last_success = now
                finished = self.clock()
                tick += self.interval
                skipped = max(0, math.ceil((finished - tick) / self.interval))
                tick += skipped * self.interval
                self._observe(HeartbeatObservation(outcome, max(0, (finished - started) * 1000),
                                                   lag, skipped + pending_skipped, failures))
                pending_skipped = 0
        finally:
            primary = sys.exc_info()[1]
            try:
                self.close_connection()
            except Exception:
                if primary is None:
                    log_event_best_effort(self.logger, "runtime.heartbeat.cleanup_failed", status="FAILED")
            except BaseException:
                if primary is None:
                    raise


_RENEW = text("""UPDATE job_execution SET heartbeat_at = NOW(6),
lease_expires_at = TIMESTAMPADD(MICROSECOND, :lease_us, NOW(6))
WHERE execution_id = :execution_id AND status = 'RUNNING' AND lease_owner = :owner""")

_CANCEL_OBSERVATION = text("""SELECT cancel_requested_at,
TIMESTAMPDIFF(MICROSECOND, cancel_requested_at, NOW(6)) / 1000.0 AS latency_ms
FROM job_execution WHERE execution_id = :execution_id
AND status = 'RUNNING' AND lease_owner = :owner""")


class LeaseConnection:
    """Only the heartbeat thread may use/close this retained Connection.

    Roll back and close after any ordinary attempt failure; reconnect at the
    next tick. There is no transaction helper or automatic replay here.
    """
    def __init__(self, engine, execution_id, owner, lease_duration, *, fence, owns_engine=False,
                 cancel_signal=None, logger=None, cancel_observe=None, clock=time.monotonic):
        self.engine, self.execution_id, self.owner = engine, execution_id, owner
        self.lease_us = int(lease_duration * 1_000_000)
        self.conn = None
        self.owns_engine = owns_engine
        self.fence = fence
        self.cancel_signal, self.logger, self.cancel_observe = cancel_signal, logger, cancel_observe
        self.clock = clock

    def renew(self):
        primary = None
        cancellation = None
        observation_started = None
        try:
            if self.conn is None:
                self.conn = self.engine.connect()
            with self.conn.begin():
                try:
                    changed = self.conn.execute(_RENEW, {"execution_id": self.execution_id,
                        "owner": self.owner, "lease_us": self.lease_us}).rowcount
                    if changed == 0:
                        # The zero-row fact needs no commit acknowledgement.
                        self.fence.mark_lost()
                    elif self.cancel_signal is not None and not self.cancel_signal.requested:
                        observation_started = self.clock()
                        cancellation = self.conn.execute(_CANCEL_OBSERVATION,
                            {"execution_id": self.execution_id, "owner": self.owner}).mappings().one_or_none()
                except BaseException as error:
                    primary = error
                    raise
        except BaseException as error:
            try:
                self._close_connection()
            except BaseException:
                pass
            if primary is not None and error is not primary:
                raise primary from None
            raise
        # Deliver only a successfully committed heartbeat observation. Sinks run
        # after the signal and outside the DB-failure/connection cleanup boundary.
        if (cancellation is not None and cancellation["cancel_requested_at"] is not None
                and self.cancel_signal.request()):
            # DB marker age at SELECT plus elapsed read/commit acknowledgement.
            # No host wall-clock comparison; include signal delivery latency.
            observation = CancelObservation(max(0, float(cancellation["latency_ms"]))
                + max(0, self.clock() - observation_started) * 1000)
            if self.cancel_observe is not None:
                try:
                    self.cancel_observe(observation)
                except Exception:
                    pass
            if self.logger is not None:
                log_event_best_effort(self.logger, "runtime.cancel.observe_latency_ms",
                                      status="REQUESTED", duration_ms=observation.duration_ms)
        return changed

    def _close_connection(self):
        conn, self.conn = self.conn, None
        if conn is not None:
            conn.close()

    def close(self):
        primary = None
        try:
            self._close_connection()
        except BaseException as error:
            primary = error
            raise
        finally:
            if self.owns_engine:
                try:
                    self.engine.dispose()
                except BaseException:
                    if primary is None:
                        raise
