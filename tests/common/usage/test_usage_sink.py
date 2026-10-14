"""Caller-side HTTP boundary and immutable DB-only callback input."""

from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import get_type_hints

import pytest


def module():
    return import_module("daesingo.common.usage.sink")


def facts(**changes):
    return dict(token_usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
                processed_duration_sec=4.5, latency_ms=17,
                pricing_context={"pricing_id": "price", "unit": "opaque"},
                cost={"amount": "1.20", "currency": "KRW"}, outcome="SUCCEEDED", **changes)


def begin(sink, **kwargs):
    return sink.begin("SEARCH_COARSE", "fake", {"pricing_id": "price", "unit": "opaque"}, **kwargs)


def make(runner, **kwargs):
    return module().DurableUsageSink(execution_ref="exec", case_id="case", transaction=runner, **kwargs)


def test_begin_failure_blocks_http_and_exposes_only_fixed_replay_identity(monkeypatch):
    calls, ids = [], []
    def insert(conn, row):
        ids.append(deepcopy(row))
    monkeypatch.setattr(module(), "_begin", insert)
    def runner(callback):
        callback(None)
        raise RuntimeError("raw provider secret SQL /private/tracker")
    sink = make(runner)
    for attempt in range(2):
        with pytest.raises(module().UsagePersistenceError) as caught:
            identity = begin(sink, **({"usage_id": identity} if attempt else {}))
            calls.append("HTTP")
        identity = caught.value.usage_id
        assert caught.value.__cause__ is None and caught.value.__suppress_context__
        assert all(s not in str(caught.value) for s in ("secret", "SQL", "private", identity))
    assert calls == [] and ids[0] == ids[1]


def test_finish_failure_never_reinvokes_completed_provider(monkeypatch):
    monkeypatch.setattr(module(), "_begin", lambda conn, row: None)
    monkeypatch.setattr(module(), "_finish", lambda *args: None)
    calls, operations = [], []
    def runner(callback):
        operations.append(callback)
        callback(None)
        if len(operations) > 1:
            raise RuntimeError("private SQL")
    sink = make(runner)
    identity = begin(sink)
    calls.append("HTTP")
    with pytest.raises(module().UsagePersistenceError):
        sink.finish(identity, **facts())
    with pytest.raises(module().UsagePersistenceError):
        sink.finish(identity, **facts())
    assert calls == ["HTTP"]


def test_retry_callback_keeps_id_time_and_snapshot_fixed(monkeypatch):
    rows = []
    monkeypatch.setattr(module(), "_begin", lambda conn, row: rows.append(deepcopy(row)))
    def runner(callback):
        callback(None)
        callback(None)
        callback(None)
    sink = make(runner, clock=lambda: datetime(2026, 10, 13, tzinfo=timezone.utc))
    identity = begin(sink)
    assert len(rows) == 3 and rows[0] == rows[1] == rows[2]
    assert rows[0]["usage_id"] == identity


@pytest.mark.parametrize("mode", ["token", "total", "duration", "latency", "pricing", "float", "currency", "outcome", "failure", "extra"])
def test_validation_hides_input_and_never_opens_transaction(mode, monkeypatch):
    sentinel = "secret raw-response /private tracker SQL"
    value = facts()
    if mode == "token": value["token_usage"] = {"input_tokens": sentinel}
    if mode == "total": value["token_usage"]["total_tokens"] = 99
    if mode == "duration": value["processed_duration_sec"] = float("inf")
    if mode == "latency": value["latency_ms"] = sentinel
    if mode == "pricing": value["pricing_context"]["raw"] = sentinel
    if mode == "float": value["cost"]["amount"] = 1.2
    if mode == "currency": value["cost"]["currency"] = sentinel
    if mode == "outcome": value["outcome"] = sentinel
    if mode == "failure": value["failure_kind"] = sentinel
    if mode == "extra": value["token_usage"]["raw"] = sentinel
    sink = make(lambda callback: pytest.fail("invalid facts must not acquire DB"))
    with pytest.raises(module().UsageValidationError) as caught:
        sink.finish("usage", **value)
    assert sentinel not in str(caught.value) and caught.value.__cause__ is None


def test_execution_context_port_type_has_no_sql_dependency():
    from daesingo.common.jobs.execution import ExecutionContext
    port = import_module("daesingo.common.usage.port")
    assert get_type_hints(ExecutionContext)["usage_sink"] == port.UsageSink | None


def test_begin_replay_rejects_changed_context_and_unissued_identity(monkeypatch):
    monkeypatch.setattr(module(), "_begin", lambda *args: None)
    sink = make(lambda callback: callback(None))
    identity = begin(sink)
    assert begin(sink, usage_id=identity) == identity
    with pytest.raises(module().UsageConflictError):
        sink.begin("OTHER", "fake", {"pricing_id": "price", "unit": "opaque"}, usage_id=identity)
    with pytest.raises(module().UsageStateError):
        begin(sink, usage_id="unissued")


def test_mutable_caller_snapshot_is_copied_before_transaction(monkeypatch):
    value, observed = facts(), []
    monkeypatch.setattr(module(), "_finish", lambda conn, identity, execution, case, snapshot, timestamp:
                        observed.append(deepcopy(snapshot)))
    def runner(callback):
        value["token_usage"]["total_tokens"] = 999
        value["pricing_context"]["pricing_id"] = "changed"
        value["cost"]["amount"] = "9.99"
        callback(None)
        callback(None)
    make(runner).finish("usage", **value)
    assert observed[0] == observed[1]
    assert observed[0]["total_tokens"] == 5 and observed[0]["pricing_id"] == "price"
    assert str(observed[0]["amount"]) == "1.20"


def test_execution_sink_rejects_run_with_direct_no_run_reason_before_transaction():
    sink = make(lambda callback: pytest.fail("invalid relationship must not acquire DB"))
    with pytest.raises(module().UsageValidationError):
        sink.finalize("usage", run_ref={"kind": "analysis_run", "ref": "run"}, run_ref_reason="DIRECT_NO_RUN")
