"""Registration contracts for fake public capabilities (RT-10 adds real kinds)."""

from importlib import import_module

import pytest


def api():
    return import_module("daesingo.worker.registry")


def context():
    cls = import_module("daesingo.common.jobs.execution").ExecutionContext
    return cls("exec", "job", "case", "TEST", 1, "trace")


def test_registered_kind_dispatches_once_with_execution_context():
    calls = []
    module = api()
    expected = module.HandlerResult(produced=[{"kind": "Candidates", "ref": "cand_1"}])
    registry = module.KindRegistry({"TEST": lambda ctx: calls.append(ctx) or expected})
    ctx = context()
    assert registry.dispatch(ctx) == expected
    assert calls == [ctx]
    assert ctx.cancel_signal is None and ctx.usage_sink is None
    assert "claim_token" not in repr(ctx)


def test_registry_snapshot_cannot_be_changed_by_registration_mapping():
    module = api()
    handlers = {"TEST": lambda ctx: module.HandlerResult()}
    registry = module.KindRegistry(handlers)
    handlers.clear()
    assert registry.dispatch(context()).status == "SUCCEEDED"


def test_unregistered_kind_fails_without_invoking_any_handler():
    result = api().KindRegistry({}).dispatch(context())
    assert result.status == "FAILED" and result.failure_kind == "RUNTIME_UNREGISTERED_KIND"
    assert result.produced == ()


@pytest.mark.parametrize("failure_kind", ["SEARCH_ACCOUNT_BLOCKED", "RECORDING_SOURCE_MISSING"])
def test_module_failure_taxonomy_and_partial_produced_are_preserved(failure_kind):
    module = api()
    expected = module.HandlerResult(status="FAILED", failure_kind=failure_kind,
                                    produced=[{"kind": "Partial", "ref": "partial_1"}])
    assert module.KindRegistry({"TEST": lambda ctx: expected}).dispatch(context()) == expected


@pytest.mark.parametrize("behavior", ["raise", "malformed", "invalid_refs"])
def test_handler_exception_or_invalid_result_is_runtime_failure(behavior):
    module = api()
    def handler(ctx):
        if behavior == "raise":
            raise RuntimeError("/private/path secret provider/user payload")
        if behavior == "invalid_refs":
            return module.HandlerResult(produced=[{"kind": "x", "ref": ""}])
        return {"provider_payload": "secret"}
    result = module.KindRegistry({"TEST": handler}).dispatch(context())
    assert result.status == "FAILED" and result.failure_kind.startswith("RUNTIME_")
    assert "secret" not in repr(result)


@pytest.mark.parametrize("kwargs", [
    {"status": "FAILED"}, {"failure_kind": "SEARCH_FAILURE"},
    {"status": "CANCELLED"}, {"status": "FAILED", "failure_kind": "x" * 192},
    {"produced": [{"kind": "x", "ref": "r"}, {"kind": "x", "ref": "r"}]},
])
def test_invalid_terminal_shape_is_rejected(kwargs):
    with pytest.raises(ValueError):
        api().HandlerResult(**kwargs)
