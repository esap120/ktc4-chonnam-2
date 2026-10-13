"""Worker preserves usage persistence/provider failure boundaries."""

from importlib import import_module
from threading import Event

import pytest

from daesingo.common.jobs.execution import HandlerResult
from test_worker_loop import claim, loop


def test_factory_creates_separate_execution_sinks():
    contexts, sinks = [], []
    stop = Event()
    def factory(context):
        obj = object()
        sinks.append(obj)
        return obj
    def dispatch(context):
        contexts.append(context)
        if len(contexts) == 2: stop.set()
        return HandlerResult()
    loop(claim=lambda: claim(str(len(contexts))), dispatch=dispatch, stop=stop,
         usage_sink_factory=factory).run()
    assert len(sinks) == 2 and sinks[0] is not sinks[1]
    assert [ctx.usage_sink for ctx in contexts] == sinks


@pytest.mark.parametrize("kind", ["persistence", "validation", "conflict", "state"])
def test_usage_error_is_terminal_without_redispatch_or_private_logging(kind):
    module = import_module("daesingo.common.usage.port")
    error = {"persistence": module.UsagePersistenceError, "validation": module.UsageValidationError,
             "conflict": module.UsageConflictError, "state": module.UsageStateError}[kind]()
    calls, results = [], []
    stop = Event()
    def dispatch(context):
        calls.append(context)
        raise error
    def record(context, result):
        results.append(result)
        stop.set()
        return True
    loop(claim=claim, dispatch=dispatch, record=record, stop=stop).run()
    assert len(calls) == len(results) == 1
    assert results[0].status == "FAILED"
    assert results[0].failure_kind == "RUNTIME_USAGE_" + kind.upper()


def test_cancel_observed_before_dispatch_creates_no_usage():
    stop, calls, results = Event(), [], []
    class Heartbeat:
        def __init__(self, ctx): self.ctx = ctx
        def start(self, execution): self.ctx.cancel_signal.request()
        def stop_and_join(self): pass
    def record(ctx, result):
        results.append(result)
        stop.set()
        return True
    loop(claim=claim, heartbeat=Heartbeat, stop=stop, record=record,
         dispatch=lambda ctx: calls.append(ctx)).run()
    assert calls == [] and results[0].status == "CANCELLED"
