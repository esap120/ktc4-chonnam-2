"""Caller-owned transactions, INSERT-only Final append and fixed-identity replay."""

from collections.abc import Mapping
from datetime import datetime, timezone
import math
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from .amount import amount_string, parse_amount
from .schema import usage_record

_FIELDS = frozenset({
    "usage_id", "execution_ref", "case_id", "occurred_at", "provider_label", "operation",
    "run_ref", "run_ref_reason", "token_usage", "processed_duration_sec", "latency_ms", "pricing_context", "cost",
})


class UsageIdentityConflict(ValueError):
    """A durable Final already owns this identity with a different snapshot."""


def _object(value, keys, name):
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"invalid {name} fields")
    return value


def _string(value, name, *, identifier=False, length=191, nullable=False):
    if value is None and nullable:
        return None
    if (not isinstance(value, str) or not value or len(value) > length
            or (identifier and (not value.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)))):
        raise ValueError(f"invalid {name}")
    return value


def _integer(value, name, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or not -(2**63) <= value < 2**63:
        raise ValueError(f"invalid {name}")
    return value


def _timestamp(value):
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid occurred_at") from None


def _row(record: Mapping[str, Any]) -> dict:
    data = _object(record, _FIELDS, "UsageRecord")
    row = {
        "usage_id": _string(data["usage_id"], "usage_id", identifier=True, length=128),
        "execution_ref": _string(data["execution_ref"], "execution_ref", identifier=True, length=128, nullable=True),
        "case_id": _string(data["case_id"], "case_id", identifier=True, length=128, nullable=True),
        "occurred_at": _timestamp(data["occurred_at"]),
        "provider_label": _string(data["provider_label"], "provider_label"),
        "operation": _string(data["operation"], "operation"),
        "latency_ms": _integer(data["latency_ms"], "latency_ms", nullable=True),
    }
    run = data["run_ref"]
    reason = data["run_ref_reason"]
    if run is None:
        if reason not in ("DIRECT_NO_RUN", "RUN_NOT_PRODUCED"):
            raise ValueError("invalid run_ref_reason")
        row.update(run_kind=None, run_ref=None, run_ref_reason=reason)
    else:
        run = _object(run, {"kind", "ref"}, "run_ref")
        if run["kind"] not in ("analysis_run", "readout_run") or reason is not None:
            raise ValueError("invalid run_ref relationship")
        row.update(run_kind=run["kind"], run_ref=_string(run["ref"], "run_ref", identifier=True, length=128), run_ref_reason=None)
    token = data["token_usage"]
    if token is None:
        row.update(input_tokens=None, output_tokens=None, total_tokens=None)
    else:
        token = _object(token, {"input_tokens", "output_tokens", "total_tokens"}, "token_usage")
        row.update({name: _integer(token[name], name) for name in token})
        if row["total_tokens"] != row["input_tokens"] + row["output_tokens"]:
            raise ValueError("invalid token_usage total")
    duration = data["processed_duration_sec"]
    try:
        if duration is not None and (type(duration) not in (int, float) or not math.isfinite(duration)):
            raise ValueError
        row["processed_duration_sec"] = float(duration) if duration is not None else None
    except (ValueError, OverflowError):
        raise ValueError("invalid processed_duration_sec") from None
    pricing = _object(data["pricing_context"], {"pricing_id", "unit"}, "pricing_context")
    row.update(pricing_id=_string(pricing["pricing_id"], "pricing_id"), unit=_string(pricing["unit"], "unit"))
    cost = _object(data["cost"], {"amount", "currency"}, "cost")
    if cost["currency"] != "KRW":
        raise ValueError("invalid cost currency")
    row.update(amount=parse_amount(cost["amount"]), currency="KRW")
    return row


def append_final(conn: Connection, record: Mapping[str, Any]) -> bool:
    """Insert Final; return True for insertion, False for identical replay.

    The result is tentative until the caller commits. Never commit/rollback,
    update/delete Final, finalize in-flight, allocate identity or call a provider.
    Only MySQL duplicate-key (1062) triggers a locked read and full comparison.
    A different snapshot fails explicitly, including null vs zero. All other
    SQL failures propagate for the caller's transaction policy to handle.

    For unknown COMMIT, keep the identity AND complete snapshot fixed. This
    makes this append replay-safe; other callback effects need their own guards.
    INSERT waits for an earlier competing transaction before the locked read.
    """
    if not conn.in_transaction():
        raise ValueError("append_final requires a caller-owned transaction")
    row = _row(record)
    try:
        conn.execute(insert(usage_record).values(row))
    except IntegrityError as error:
        if not error.orig.args or error.orig.args[0] != 1062:
            raise
        existing = conn.execute(select(usage_record).where(
            usage_record.c.usage_id == row["usage_id"]).with_for_update()).mappings().one_or_none()
        if existing is None or dict(existing) != row:
            raise UsageIdentityConflict("usage identity already has a different Final snapshot") from None
        return False
    return True


def read_final(conn: Connection, usage_id: str) -> dict | None:
    """Project only Final Contract fields; amount is a string or null."""
    identity = _string(usage_id, "usage_id", identifier=True, length=128)
    row = conn.execute(select(usage_record).where(usage_record.c.usage_id == identity)).mappings().one_or_none()
    if row is None:
        return None
    return {
        "usage_id": row["usage_id"], "execution_ref": row["execution_ref"], "case_id": row["case_id"],
        "occurred_at": row["occurred_at"].replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider_label": row["provider_label"], "operation": row["operation"],
        "run_ref": None if row["run_ref"] is None else {"kind": row["run_kind"], "ref": row["run_ref"]},
        "run_ref_reason": row["run_ref_reason"],
        "token_usage": None if row["input_tokens"] is None else {name: row[name] for name in
                                                               ("input_tokens", "output_tokens", "total_tokens")},
        "processed_duration_sec": row["processed_duration_sec"], "latency_ms": row["latency_ms"],
        "pricing_context": {"pricing_id": row["pricing_id"], "unit": row["unit"]},
        "cost": {"amount": amount_string(row["amount"]), "currency": row["currency"]},
    }
