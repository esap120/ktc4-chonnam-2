"""RT-05(b) signal/checkpoint and caller-owned port validation."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module, util
from io import StringIO
import json
from threading import Event

import pytest

from daesingo.common.jobs.execution import ExecutionContext, HandlerResult
from daesingo.common.logging import configure_logging
from daesingo.worker.registry import KindRegistry


def cancellation():
    assert util.find_spec("daesingo.common.jobs.cancel"), "RT-05(b) cancellation is missing"
    return import_module("daesingo.common.jobs.cancel")


def test_signal_thread_safe_first_request_and_checkpoint_time():
    module = cancellation()
    signal = module.CancelSignal(clock=lambda: 12.5)
    context = ExecutionContext("exec", "job", "case", "TEST", 1, "trace", cancel_signal=signal)
    context.checkpoint()
    assert not signal.requested and signal.checkpoint_at is None
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: signal.request(), range(64))) == 1
    assert signal.requested and signal.checkpoint_at is None
    for _ in range(2):
        with pytest.raises(module.CancellationRequested, match="cancellation requested"):
            context.checkpoint()
    assert signal.checkpoint_at == 12.5


def test_registry_propagates_cancel_and_preserves_other_error_policy():
    module = cancellation()
    context = ExecutionContext("exec", "job", "case", "TEST", 1, "trace")
    context.cancel_signal.request()
    with pytest.raises(module.CancellationRequested):
        KindRegistry({"TEST": lambda ctx: ctx.checkpoint()}).dispatch(context)
    def fails(ctx):
        raise RuntimeError("private payload")
    assert KindRegistry({"TEST": fails}).dispatch(context).failure_kind == "RUNTIME_HANDLER_ERROR"
    for error in (KeyboardInterrupt, SystemExit):
        def fatal(ctx):
            raise error()
        with pytest.raises(error):
            KindRegistry({"TEST": fatal}).dispatch(context)


@pytest.mark.parametrize("jobs", ["job", b"job", ["job", None], ["job", ""],
                                      ["job", "x" * 192], ["job", "비공개"], ["job", 1]])
def test_port_validates_every_input_before_any_sql_and_sanitizes(jobs):
    module = cancellation()
    class Connection:
        def in_transaction(self):
            return True
        def execute(self, *args, **kwargs):
            pytest.fail("validation reached SQL")
    with pytest.raises(ValueError, match="invalid cancel job_ids") as error:
        module.request_cancel(Connection(), jobs)
    assert "비공개" not in str(error.value)


def test_generator_error_is_sanitized_before_writes_and_empty_is_noop():
    module = cancellation()
    class Connection:
        def in_transaction(self):
            return True
        def execute(self, *args, **kwargs):
            pytest.fail("empty/invalid input reached SQL")
    def broken():
        yield "job"
        raise RuntimeError("private raw input")
    with pytest.raises(ValueError, match="invalid cancel job_ids") as error:
        module.request_cancel(Connection(), broken())
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert module.request_cancel(Connection(), iter(())) is None


def test_port_requires_existing_transaction():
    module = cancellation()
    class Connection:
        def in_transaction(self):
            return False
    with pytest.raises(ValueError, match="caller-owned transaction"):
        module.request_cancel(Connection(), [])


@pytest.mark.parametrize("mode", ["checkpoint", "late_success", "ownership"])
def test_worker_cancel_outcome_and_heartbeat_cleanup(mode):
    module = cancellation()
    from daesingo.common.jobs.worker_loop import WorkerLoop
    from daesingo.common.config import WorkerSettings
    from daesingo.common.jobs.repository import ClaimedExecution
    stop, events, results, reflected = Event(), [], [], []
    class Heartbeat:
        def start(self, execution):
            events.append("start")
        def stop_and_join(self):
            events.append("join")
    def handler(ctx):
        ctx.checkpoint()
        ctx.cancel_signal.request()
        stop.set()
        if mode == "ownership":
            ctx.ownership.mark_lost()
        if mode != "late_success":
            ctx.checkpoint()
        return HandlerResult(produced=[{"kind": "Candidates", "ref": "ref"}])
    def record(ctx, result):
        results.append(result)
        return True
    WorkerLoop(claim=lambda: ClaimedExecution("exec", "job", 1, "TEST", "case", "trace", "owner", None, None),
        dispatch=KindRegistry({"TEST": handler}).dispatch, record=record,
        settings=WorkerSettings(), stop=stop, logger=configure_logging("worker", stream=StringIO()),
        heartbeat=lambda ctx: Heartbeat(), reflect=lambda *args: reflected.append(args)).run()
    assert events == ["start", "join"]
    if mode == "ownership":
        assert results == []
    else:
        assert results[0].status == ("CANCELLED" if mode == "checkpoint" else "SUCCEEDED")
        assert bool(results[0].produced) == (mode == "late_success")
    assert bool(reflected) == (mode == "late_success")


def test_terminal_metric_spans_checkpoint_to_commit_excluding_join():
    cancellation()
    from daesingo.common.jobs.worker_loop import WorkerLoop
    from daesingo.common.config import WorkerSettings
    from daesingo.common.jobs.repository import ClaimedExecution
    stop, timeline, stream = Event(), [10.0], StringIO()
    class Heartbeat:
        def start(self, execution):
            pass
        def stop_and_join(self):
            timeline[0] += 100
    def heartbeat(ctx):
        ctx.cancel_signal.clock = lambda: timeline[0]
        return Heartbeat()
    def dispatch(ctx):
        ctx.cancel_signal.request()
        ctx.checkpoint()
    def record(ctx, result):
        timeline[0] += 2.5
        stop.set()
        return True
    WorkerLoop(claim=lambda: ClaimedExecution("exec", "job", 1, "TEST", "case", "trace", "owner", None, None),
        dispatch=dispatch, record=record, settings=WorkerSettings(), stop=stop,
        logger=configure_logging("worker", stream=stream), heartbeat=heartbeat).run()
    metric, = [json.loads(line) for line in stream.getvalue().splitlines()
               if json.loads(line)["event"] == "runtime.cancel.checkpoint_to_terminal_ms"]
    assert metric["duration_ms"] == 2500
