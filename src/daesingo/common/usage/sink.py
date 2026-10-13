"""Execution-local UsageSink with short, replay-safe DB-only transactions."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from .amount import amount_string
from .port import (UsageError, UsageConflictError, UsagePersistenceError,
                   UsageStateError, UsageValidationError)
from .repository import _row, _string, _timestamp, append_final, UsageIdentityConflict
from .schema import usage_inflight

_START = ("usage_id", "execution_ref", "case_id", "occurred_at", "operation", "provider_label")
_OBSERVATION = ("input_tokens", "output_tokens", "total_tokens", "processed_duration_sec", "latency_ms",
                "pricing_id", "unit", "amount", "currency", "outcome", "failure_kind")
_RUN = ("run_kind", "run_ref", "run_ref_reason")


def _same(left, right, fields):
    return all(left[field] == right[field] for field in fields)


def _locked(conn, identity, execution_ref, case_id):
    row = conn.execute(select(usage_inflight).where(usage_inflight.c.usage_id == identity)
                       .with_for_update()).mappings().one_or_none()
    if row is None or row["execution_ref"] != execution_ref or row["case_id"] != case_id:
        raise UsageStateError()
    return dict(row)


def _begin(conn, snapshot):
    try:
        conn.execute(insert(usage_inflight).values(snapshot))
    except IntegrityError as error:
        if not error.orig.args or error.orig.args[0] != 1062:
            raise
        row = _locked(conn, snapshot["usage_id"], snapshot["execution_ref"], snapshot["case_id"])
        # begin's pricing may have been finalized by finish. Identity and the
        # original preparation snapshot remain fixed in this execution's sink.
        if not _same(row, snapshot, _START):
            raise UsageConflictError() from None


def _finish(conn, identity, execution_ref, case_id, snapshot, observed_at):
    row = _locked(conn, identity, execution_ref, case_id)
    if row["state"] in ("OBSERVED", "FINALIZED"):
        if not _same(row, snapshot, _OBSERVATION):
            raise UsageConflictError()
        return
    if row["state"] != "STARTED":
        raise UsageStateError()
    changed = conn.execute(update(usage_inflight).where(
        usage_inflight.c.usage_id == identity, usage_inflight.c.state == "STARTED"
    ).values(**snapshot, observed_at=observed_at, state="OBSERVED")).rowcount
    if changed != 1:
        raise UsageStateError()


def _contract(row):
    return dict(usage_id=row["usage_id"], execution_ref=row["execution_ref"], case_id=row["case_id"],
        occurred_at=row["occurred_at"].replace(tzinfo=timezone.utc), provider_label=row["provider_label"],
        operation=row["operation"], run_ref=None if row["run_ref"] is None else
        {"kind": row["run_kind"], "ref": row["run_ref"]}, run_ref_reason=row["run_ref_reason"],
        token_usage=None if row["input_tokens"] is None else
        {key: row[key] for key in ("input_tokens", "output_tokens", "total_tokens")},
        processed_duration_sec=row["processed_duration_sec"], latency_ms=row["latency_ms"],
        pricing_context={"pricing_id": row["pricing_id"], "unit": row["unit"]},
        cost={"amount": amount_string(row["amount"]), "currency": row["currency"]})


def _mark_finalized(conn, identity, relationship, finalized_at):
    changed = conn.execute(update(usage_inflight).where(
        usage_inflight.c.usage_id == identity, usage_inflight.c.state == "OBSERVED"
    ).values(**relationship, state="FINALIZED", finalized_at=finalized_at)).rowcount
    if changed != 1:
        raise UsageStateError()


def _finalize(conn, identity, execution_ref, case_id, relationship, finalized_at):
    row = _locked(conn, identity, execution_ref, case_id)
    if row["state"] not in ("OBSERVED", "FINALIZED"):
        raise UsageStateError()
    if row["state"] == "FINALIZED" and not _same(row, relationship, _RUN):
        raise UsageConflictError()
    try:
        append_final(conn, _contract({**row, **relationship}))
    except UsageIdentityConflict:
        raise UsageConflictError() from None
    if row["state"] == "OBSERVED":
        _mark_finalized(conn, identity, relationship, finalized_at)


class DurableUsageSink:
    """Fresh per execution; retains prepared begin identities, never DB resources.

    transaction must commit DB-only callbacks using the existing Worker policy.
    Neither this sink nor that callback may dispatch provider/external I/O.
    State, observation and Final idempotency rely on MySQL, not a process lock.
    Recovery and late observations after recovery finalize belong to RT-07(c).
    """

    def __init__(self, *, execution_ref: str, case_id: str,
                 transaction: Callable[[Callable[[Connection], None]], None],
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        try:
            self._execution_ref = _string(execution_ref, "execution_ref", identifier=True, length=128)
            self._case_id = _string(case_id, "case_id", identifier=True, length=128)
        except Exception:
            raise UsageValidationError() from None
        self._transaction, self._clock = transaction, clock
        self._begins: dict[str, dict] = {}
        self._lock = Lock()

    def _template(self, **changes):
        record = dict(usage_id="validation", execution_ref=self._execution_ref, case_id=self._case_id,
            occurred_at=datetime(2000, 1, 1, tzinfo=timezone.utc), operation="validation", provider_label="validation",
            run_ref=None, run_ref_reason="RUN_NOT_PRODUCED", token_usage=None,
            processed_duration_sec=None, latency_ms=None, pricing_context={"pricing_id": "validation", "unit": "validation"},
            cost={"amount": None, "currency": "KRW"})
        return {**record, **changes}

    def _execute(self, callback, identity):
        try:
            self._transaction(callback)
        except UsageError:
            raise
        except Exception:
            raise UsagePersistenceError(usage_id=identity) from None

    def begin(self, operation: str, provider_label: str, pricing_context: Mapping[str, Any], *,
              usage_id: str | None = None) -> str:
        try:
            supplied = _row(self._template(operation=operation, provider_label=provider_label,
                                            pricing_context=pricing_context))
            if usage_id is not None:
                _string(usage_id, "usage_id", identifier=True, length=128)
        except Exception:
            raise UsageValidationError() from None
        with self._lock:
            if usage_id is None:
                usage_id = "usage_" + uuid4().hex
                try:
                    occurred_at = _timestamp(self._clock())
                except Exception:
                    raise UsageValidationError() from None
                snapshot = {**supplied, "usage_id": usage_id, "occurred_at": occurred_at,
                    "run_ref_reason": None, "state": "STARTED", "outcome": None, "failure_kind": None,
                    "observed_at": None, "finalized_at": None}
                self._begins[usage_id] = snapshot
            else:
                snapshot = self._begins.get(usage_id)
                if snapshot is None:
                    raise UsageStateError()
                if not _same(snapshot, supplied, ("operation", "provider_label", "pricing_id", "unit")):
                    raise UsageConflictError()
        self._execute(lambda conn: _begin(conn, snapshot), usage_id)
        return usage_id

    def finish(self, usage_id: str, *, token_usage, processed_duration_sec, latency_ms,
               pricing_context, cost, outcome: str, failure_kind: str | None = None) -> None:
        try:
            identity = _string(usage_id, "usage_id", identifier=True, length=128)
            validated = _row(self._template(token_usage=token_usage, processed_duration_sec=processed_duration_sec,
                latency_ms=latency_ms, pricing_context=pricing_context, cost=cost))
            if outcome not in ("SUCCEEDED", "FAILED") or (outcome == "FAILED") != (failure_kind is not None):
                raise ValueError
            failure = _string(failure_kind, "failure_kind", nullable=True)
            snapshot = {key: validated[key] for key in _OBSERVATION if key in validated}
            snapshot.update(outcome=outcome, failure_kind=failure)
            observed_at = _timestamp(self._clock())
        except Exception:
            raise UsageValidationError() from None
        self._execute(lambda conn: _finish(conn, identity, self._execution_ref, self._case_id,
                                           snapshot, observed_at), identity)

    def finalize(self, usage_id: str, *, run_ref, run_ref_reason: str | None) -> None:
        try:
            identity = _string(usage_id, "usage_id", identifier=True, length=128)
            if run_ref is None and run_ref_reason != "RUN_NOT_PRODUCED":
                raise ValueError
            validated = _row(self._template(run_ref=run_ref, run_ref_reason=run_ref_reason))
            relationship = {key: validated[key] for key in _RUN}
            finalized_at = _timestamp(self._clock())
        except Exception:
            raise UsageValidationError() from None
        self._execute(lambda conn: _finalize(conn, identity, self._execution_ref, self._case_id,
                                             relationship, finalized_at), identity)
