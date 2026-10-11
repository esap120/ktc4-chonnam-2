"""Startup ordering, independent sweep scheduling and hook isolation."""

from importlib import import_module, util
from io import StringIO
from threading import Event, enumerate as threads

import pytest
from sqlalchemy.exc import OperationalError

from daesingo.common.config import WorkerSettings
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.repository import ClaimedExecution
from daesingo.common.jobs.worker_loop import WorkerLoop
from daesingo.common.logging import configure_logging


def service(**kwargs):
    assert util.find_spec("daesingo.common.jobs.sweep"), "RT-06 sweep thread missing"
    return import_module("daesingo.common.jobs.sweep").SweepService(**kwargs)


def test_periodic_wait_uses_config_and_hook_errors_do_not_block_later_hooks():
    stop, calls, stream = Event(), [], StringIO()
    def wait(seconds):
        calls.append(("wait", seconds))
        if calls.count(("wait", 0.25)) == 3:
            stop.set()
            return True
        return False
    def broken():
        calls.append("broken")
        raise RuntimeError("secret /private/path")
    runner = service(sweep=lambda: calls.append("sweep"), hooks=(broken, lambda: calls.append("hook")),
        stop=stop, settings=WorkerSettings(stale_sweep_interval_sec=0.25),
        logger=configure_logging("worker", stream=stream), wait=wait)
    runner.run()
    assert calls == [("wait", 0.25), "sweep", "broken", "hook"] * 2 + [("wait", 0.25)]
    assert "secret" not in stream.getvalue() and "private" not in stream.getvalue()


def test_startup_retries_db_failure_before_first_claim():
    stop, calls = Event(), []
    def sweep():
        calls.append("sweep")
        if calls.count("sweep") == 1:
            raise OperationalError("private SQL", {}, Exception(2003, "private"))
    def claim():
        calls.append("claim")
        stop.set()
    runner = service(sweep=sweep, hooks=(lambda: calls.append("hook"),), stop=stop,
        settings=WorkerSettings(), logger=configure_logging("worker", stream=StringIO()),
        retry_wait=lambda seconds: calls.append(("retry", seconds)))
    WorkerLoop(claim=claim, dispatch=lambda c: None, record=lambda c, r: True,
        settings=WorkerSettings(), stop=stop, logger=configure_logging("worker", stream=StringIO()),
        sweeper=runner).run()
    assert calls == ["sweep", ("retry", 5), "sweep", "hook", "claim"]
    assert not any(t.name.startswith("runtime-sweep") for t in threads())


def test_startup_stop_on_db_backoff_does_not_claim():
    stop = Event()
    def unavailable():
        raise OperationalError("private", {}, Exception(2003, "private"))
    runner = service(sweep=unavailable, stop=stop, settings=WorkerSettings(),
        logger=configure_logging("worker", stream=StringIO()), retry_wait=lambda s: stop.set())
    WorkerLoop(claim=lambda: pytest.fail("claim before successful startup sweep"),
        dispatch=lambda c: None, record=lambda c, r: True, settings=WorkerSettings(), stop=stop,
        logger=configure_logging("worker", stream=StringIO()), sweeper=runner).run()
    assert runner.thread is None


@pytest.mark.parametrize("interrupt", [False, True])
def test_sweep_runs_while_handler_is_blocked_and_joins_on_exit(interrupt):
    from datetime import datetime, timezone
    stop, periodic, calls = Event(), Event(), []
    def sweep():
        calls.append("sweep")
        if len(calls) >= 2:
            periodic.set()
    runner = service(sweep=sweep, stop=stop, settings=WorkerSettings(stale_sweep_interval_sec=0.01),
        logger=configure_logging("worker", stream=StringIO()))
    now = datetime.now(timezone.utc)
    claimed = ClaimedExecution("exec", "job", 1, "TEST", "case", "trace", "owner", now, now)
    def handler(context):
        assert periodic.wait(5)
        stop.set()
        if interrupt:
            raise KeyboardInterrupt()
        return HandlerResult()
    loop = WorkerLoop(claim=lambda: claimed, dispatch=handler, record=lambda c, r: True,
        settings=WorkerSettings(), stop=stop, logger=configure_logging("worker", stream=StringIO()), sweeper=runner)
    if interrupt:
        with pytest.raises(KeyboardInterrupt):
            loop.run()
    else:
        loop.run()
    assert not runner.thread.is_alive()
    assert not any(t.name.startswith("runtime-sweep") for t in threads())


def test_periodic_db_failure_recovers_next_tick_without_traceback(capsys):
    stop, calls, stream = Event(), [], StringIO()
    def sweep():
        calls.append("sweep")
        if len(calls) == 1:
            raise OperationalError("private", {}, Exception(2003, "private"))
        stop.set()
    runner = service(sweep=sweep, stop=stop, settings=WorkerSettings(),
        logger=configure_logging("worker", stream=stream), wait=lambda s: False)
    runner.run()
    assert calls == ["sweep", "sweep"]
    assert capsys.readouterr().err == ""
    assert "private" not in stream.getvalue()
