"""Caller-owned DB-only callback transactions (Baseline B-D8).

Callbacks must re-read state on every attempt, use stable identities, and handle
already-committed operations idempotently. In particular, a lost COMMIT response
does not mean rollback undid the operation. The helper knows no domain state.
No provider, filesystem publish, handler, or external capability belongs inside
the callback. Python callables are not an I/O sandbox; composition roots enforce
that dependency boundary. Never return a live Connection/cursor/lazy Result.
Callbacks must not end transactions through SQL text, the raw DBAPI connection,
stored procedures, or MySQL implicit-commit DDL. The event guard detects ordinary
Connection.commit()/rollback() misuse only; it cannot enforce arbitrary Python.
"""

from collections.abc import Callable
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import time
from typing import TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

from daesingo.common.logging import log_event
from .errors import (
    BeforeCommitFailure, CommitOutcomeUnknown, TransactionBoundaryError,
    TransactionRetryExhausted, db_reason,
)

T = TypeVar("T")
MAX_ATTEMPTS = 3  # Issue #289: initial attempt + at most two retries.
_active_attempt: ContextVar[tuple[Connection, dict] | None] = ContextVar("db_attempt", default=None)


@dataclass(frozen=True)
class TransactionAttempt:
    """Sanitized begin-to-outcome timing, without connection/result/exception."""
    outcome: str
    duration_ms: float


def _observe(observer, state: dict, outcome: str) -> None:
    if observer is not None and "duration_ms" in state:
        try:
            observer(TransactionAttempt(outcome, state["duration_ms"]))
        except Exception:
            # A sink failure (even a DBAPIError) is never a transaction failure.
            pass


@event.listens_for(Engine, "handle_error")
def _remember_commit_error(context) -> None:
    # This event precedes SQLAlchemy's disconnect invalidation/checkin, which
    # can itself raise. Observe only this attempt's connection during COMMIT,
    # excluding queries (even handled queries in commit listeners). Never infer
    # provenance from ambient __cause__/__context__ chains. One permanent,
    # read-only listener avoids mutating event dispatch during concurrent use.
    attempt = _active_attempt.get()
    if attempt is not None:
        conn, state = attempt
        if (context.connection is conn and state["phase"] == "committing"
                and context.execution_context is None and context.statement is None
                and isinstance(context.sqlalchemy_exception, DBAPIError)):
            state.setdefault("commit_error", context.sqlalchemy_exception)


def _emit(logger: logging.Logger | None, name: str, reason: str) -> None:
    if logger is not None:
        try:
            log_event(logger, "runtime.db." + name, status=reason.upper())
        except Exception:
            pass


@contextmanager
def _callback_boundary(conn: Connection):
    def reject(connection):
        # SQLAlchemy deactivates RootTransaction even if a commit event raises.
        # Discard the DBAPI connection now so no uncommitted state reaches a pool.
        connection.invalidate()
        raise TransactionBoundaryError("callback must not commit or rollback")

    event.listen(conn, "commit", reject)
    event.listen(conn, "rollback", reject)
    try:
        yield
    finally:
        event.remove(conn, "commit", reject)
        event.remove(conn, "rollback", reject)


def _attempt(engine: Engine, operation: Callable[[Connection], T], state: dict,
             commit_guard=None) -> T:
    state["phase"] = "acquire"
    try:
        with engine.connect() as conn:
            primary = None
            token = _active_attempt.set((conn, state))
            try:
                state["started_ns"] = time.monotonic_ns()
                with ExitStack() as guard_scope, conn.begin():
                    state["phase"] = "body"
                    try:
                        with _callback_boundary(conn):
                            result = operation(conn)
                        if commit_guard is not None:
                            guard_scope.enter_context(commit_guard())
                        # Before DBAPI commit: socket send failures can be ambiguous.
                        state["phase"] = "committing"
                    except BaseException as error:
                        primary = error
                        raise
                # Context exit acknowledged COMMIT, before pool checkin/close.
                state["duration_ms"] = (time.monotonic_ns() - state["started_ns"]) / 1_000_000
            except BaseException as error:
                if "started_ns" in state:
                    state["duration_ms"] = (time.monotonic_ns() - state["started_ns"]) / 1_000_000
                if primary is None:
                    primary = state.get("commit_error")
                state["failure"] = primary if primary is not None else error
                if primary is not None and error is not primary:
                    # Discard a possibly dirty connection, preserving the
                    # transaction failure even if invalidation also fails.
                    try:
                        conn.invalidate()
                    except BaseException:
                        pass
                raise state["failure"] from None
            finally:
                # Restore enclosing attempts, including nested callbacks, and
                # stop observing before connection-context cleanup begins.
                _active_attempt.reset(token)
            state["phase"] = "committed"
            state["result"] = result
    except BaseException as error:
        # Priority: acknowledged COMMIT > transaction failure > close/checkin.
        # The runners handle acknowledged commits; retain every earlier failure
        # across __exit__, including domain errors and unknown COMMIT outcomes.
        primary = state.get("failure")
        if primary is not None and error is not primary:
            raise primary from None
        raise
    return result


def run_api_transaction(
    engine: Engine, operation: Callable[[Connection], T], *, logger: logging.Logger | None = None,
) -> T:
    """One attempt only. Domain/unrelated SQL errors retain their original meaning."""
    state: dict = {}
    try:
        return _attempt(engine, operation, state)
    except Exception as error:
        reason = db_reason(error)
        if reason is None and state.get("phase") == "acquire" and isinstance(error, DBAPIError):
            # Connection refused/auth/server capacity errors need not invalidate
            # a connection: no connection/transaction existed in the first place.
            reason = "connect_failure"
        if state.get("phase") == "committed":
            # A close/reset error cannot turn an acknowledged commit into a safe retry.
            _emit(logger, "error_count", reason or "cleanup")
            return state["result"]
        if reason:
            _emit(logger, "error_count" if reason in ("disconnect", "connect_failure") else reason + "_count", reason)
            if state.get("phase") == "committing" and reason == "disconnect":
                raise CommitOutcomeUnknown() from None
            raise BeforeCommitFailure(reason) from None
        raise


def run_worker_transaction(
    engine: Engine, operation: Callable[[Connection], T], *,
    sleep: Callable[[float], None] = time.sleep, logger: logging.Logger | None = None,
    observe: Callable[[TransactionAttempt], None] | None = None,
    before_attempt: Callable[[], None] | None = None,
    commit_guard: Callable | None = None,
) -> T:
    """At most three complete DB attempts; resources release before each 1s wait.

    Pool exhaustion is not a B-D8 retry (the Worker loop owns B-Q3). Heartbeat
    must not use this helper. Unknown-commit replays require a DB-state/idempotency
    check in the operation; exhaustion preserves whether any commit was unknown.
    Optional admission/commit guards stay domain-independent. A commit guard is
    entered after the callback and held through transaction context exit; its
    failure rolls back and retains the same primary-exception precedence.
    """
    unknown = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if before_attempt is not None:
            before_attempt()
        state: dict = {}
        try:
            result = _attempt(engine, operation, state, commit_guard)
            _observe(observe, state, "COMMITTED")
            return result
        except Exception as error:
            reason = db_reason(error)
            if state.get("phase") == "committed":
                _emit(logger, "error_count", reason or "cleanup")
                _observe(observe, state, "COMMITTED")
                return state["result"]
            outcome = ("COMMIT_UNKNOWN" if state.get("phase") == "committing" and reason == "disconnect"
                       else (reason or "failed").upper())
            _observe(observe, state, outcome)
            if reason not in ("lock_wait_timeout", "deadlock", "disconnect"):
                raise
            unknown |= state.get("phase") == "committing" and reason == "disconnect"
            _emit(logger, reason + "_count" if reason != "disconnect" else "error_count", reason)
            if attempt == MAX_ATTEMPTS:
                _emit(logger, "tx_retry_exhausted_count", reason)
                raise TransactionRetryExhausted(attempt, outcome_unknown=unknown) from None
            _emit(logger, "tx_retry_count", reason)
        sleep(1)
    raise AssertionError("unreachable")
