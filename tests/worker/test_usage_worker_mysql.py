"""Production Worker injection, zero HTTP on begin failure, no repeat on finish failure."""

from io import StringIO

import pytest

from daesingo.common.jobs.execution import HandlerResult
from test_worker_mysql import queue, seed, row, composed  # noqa: F401
from usage_sink_support import begin, facts, rows, finalize, mod

pytestmark = pytest.mark.mysql


@pytest.mark.parametrize("mode", [pytest.param(m, marks=pytest.mark.mysql_check("usage_sink", "worker", parameter=m))
    for m in ("isolation", "begin_failure", "finish_failure", "cancel", "ownership")])
def test_worker_usage_boundary_on_real_mysql(queue, monkeypatch, mode):
    ids = seed(queue, ("TEST", "TEST") if mode == "isolation" else ("TEST",))
    contexts, calls, stream = [], [], StringIO()
    if mode.endswith("failure"):
        name = "_begin" if mode == "begin_failure" else "_finish"
        original = getattr(mod(), name)
        def fail(*args):
            original(*args)
            raise RuntimeError("secret raw-provider-response SQL /private tracker")
        monkeypatch.setattr(mod(), name, fail)
    def handler(ctx):
        contexts.append(ctx)
        assert ctx.usage_sink is not None
        identity = begin(ctx.usage_sink)
        assert queue.pool.checkedout() == 0
        calls.append(identity)  # fake provider HTTP, outside DB callback
        if mode == "ownership": ctx.ownership.mark_lost()
        ctx.usage_sink.finish(identity, **facts())
        finalize(ctx.usage_sink, identity, "failed_run")
        assert queue.pool.checkedout() == 0
        return HandlerResult(status="FAILED", failure_kind="PROVIDER_FAILURE")
    worker = composed(queue, {"TEST": handler}, stream=stream)
    if mode == "cancel":
        class CancelHeartbeat:
            def __init__(self, context): self.context = context
            def start(self, execution): self.context.cancel_signal.request()
            def stop_and_join(self): pass
        worker.heartbeat = CancelHeartbeat
    worker.run()
    trackers, finals = rows(queue)
    if mode == "cancel":
        assert calls == contexts == trackers == finals == []
        assert row(queue, ids[0])["status"] == "CANCELLED"
    elif mode == "begin_failure":
        assert calls == trackers == finals == []
        assert row(queue, ids[0])["failure_kind"] == "RUNTIME_USAGE_PERSISTENCE"
    elif mode == "finish_failure":
        assert len(calls) == len(trackers) == 1 and finals == []
        assert trackers[0]["state"] == "STARTED"
        assert row(queue, ids[0])["failure_kind"] == "RUNTIME_USAGE_PERSISTENCE"
    else:
        assert len(trackers) == len(finals) == len(calls) == len(ids)
        assert all(r["run_ref"] == "failed_run" for r in finals)
        assert {r["execution_ref"] for r in trackers} == set(ids)
        if mode == "isolation": assert contexts[0].usage_sink is not contexts[1].usage_sink
        else: assert row(queue, ids[0])["status"] == "RUNNING"  # T1 is fenced, observations aren't
    for word in ("secret", "raw-provider", "SQL", "private", "tracker", "usage_id", "claim_token"):
        assert word not in stream.getvalue()
    assert queue.pool.checkedout() == 0
