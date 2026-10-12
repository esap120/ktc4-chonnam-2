"""Startup redelivery is an admission gate, distinct from best-effort hooks."""

from io import StringIO
from threading import Event

import pytest
from sqlalchemy.exc import OperationalError

from daesingo.common.config import WorkerSettings
from daesingo.common.jobs.sweep import SweepService
from daesingo.common.jobs.worker_loop import WorkerLoop
from daesingo.common.logging import configure_logging


@pytest.mark.parametrize("phase", ["startup", "periodic"])
def test_redelivery_scan_precedes_claim_and_runs_each_period(phase):
    stop, calls = Event(), []
    logger = configure_logging("worker", stream=StringIO())

    def redeliver():
        calls.append("redeliver")
        if phase == "startup" and calls.count("redeliver") == 1:
            raise OperationalError("secret", {}, Exception(2003, "secret"))

    def claim():
        calls.append("claim")
        stop.set()

    runner = SweepService(sweep=lambda: calls.append("sweep"), redeliver=redeliver,
        settings=WorkerSettings(), stop=stop, logger=logger,
        retry_wait=lambda seconds: calls.append("retry"), wait=lambda seconds: stop.wait(10))
    if phase == "startup":
        WorkerLoop(claim=claim, dispatch=lambda c: None, record=lambda c, r: True,
            settings=WorkerSettings(), stop=stop, logger=logger, sweeper=runner).run()
        assert calls == ["sweep", "redeliver", "retry", "sweep", "redeliver", "claim"]
    else:
        def wait(seconds):
            if calls.count("redeliver") == 2:
                stop.set()
                return True
            return False
        runner.wait = wait
        runner.run()
        assert calls == ["sweep", "redeliver"] * 2
