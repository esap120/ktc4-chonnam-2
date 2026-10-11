"""Injected monotonic scheduling; real lease SQL is tested separately on MySQL."""

from importlib import import_module, util
from io import StringIO
from threading import Event
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from daesingo.common.logging import configure_logging


def heartbeat_module():
    assert util.find_spec("daesingo.common.jobs.heartbeat"), "RT-05 heartbeat lifecycle is missing"
    return import_module("daesingo.common.jobs.heartbeat")


class Clock:
    def __init__(self):
        self.now = 0
        self.waits = []

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return False


def test_slow_attempt_skips_ticks_and_resumes_fixed_rate_without_overlap():
    hb = heartbeat_module()
    clock, stop, attempts, observations = Clock(), Event(), [], []
    def renew():
        attempts.append(clock())
        if len(attempts) == 1:
            clock.now += 25
        else:
            stop.set()
        return 1
    runner = hb.Heartbeat(renew=renew, fence=hb.OwnershipFence(), interval=10,
                          logger=configure_logging("worker", stream=StringIO()),
                          clock=clock, wait=clock.wait, observe=observations.append)
    runner.stop = stop
    runner.run()
    assert attempts == [10, 40]
    assert sum(o.skipped_tick_count for o in observations) == 2
    assert clock.waits == [10, 5]


@pytest.mark.parametrize("fault", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_attempt_error_policy_and_cleanup(fault):
    hb = heartbeat_module()
    clock, stop, closed, observations = Clock(), Event(), [], []
    def renew():
        stop.set()
        raise fault("private payload")
    runner = hb.Heartbeat(renew=renew, close=lambda: closed.append(True),
                          fence=hb.OwnershipFence(), interval=10,
                          logger=configure_logging("worker", stream=StringIO()),
                          clock=clock, wait=clock.wait, observe=observations.append)
    runner.stop = stop
    if issubclass(fault, Exception):
        runner.run()
        assert observations[0].consecutive_failures == 1
    else:
        with pytest.raises(fault):
            runner.run()
    assert closed == [True]


def test_zero_rows_sets_fence_before_broken_observer_and_logger():
    hb = heartbeat_module()
    fence, clock, stop = hb.OwnershipFence(), Clock(), Event()
    class Logger:
        def log(self, *args, **kwargs):
            raise RuntimeError("private logger")
    def observer(value):
        assert fence.lost
        raise RuntimeError("private observer")
    runner = hb.Heartbeat(renew=lambda: 0, fence=fence, interval=10, logger=Logger(),
                          clock=clock, wait=clock.wait, observe=observer)
    runner.run()
    assert fence.lost
    with pytest.raises(hb.OwnershipLost):
        with fence.commit_guard():
            pytest.fail("stale owner reached commit")


def test_transaction_commit_guard_rolls_back_and_blocks_retry():
    hb = heartbeat_module()
    from sqlalchemy import create_engine, text
    from daesingo.common.db.transactions import run_worker_transaction
    engine = create_engine("sqlite://")
    fence = hb.OwnershipFence()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE results (value INTEGER)"))
    def operation(conn):
        conn.execute(text("INSERT INTO results VALUES (1)"))
        fence.mark_lost()
    try:
        with pytest.raises(hb.OwnershipLost):
            run_worker_transaction(engine, operation, before_attempt=fence.check,
                                   commit_guard=fence.commit_guard)
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT COUNT(*) FROM results")) == 0
    finally:
        engine.dispose()


def test_primary_baseexception_survives_cleanup_baseexception():
    hb = heartbeat_module()
    clock = Clock()
    def renew():
        raise SystemExit(7)
    def close():
        raise KeyboardInterrupt()
    runner = hb.Heartbeat(renew=renew, close=close, fence=hb.OwnershipFence(),
                          interval=10, logger=configure_logging("worker", stream=StringIO()),
                          clock=clock, wait=clock.wait)
    with pytest.raises(BaseException) as error:
        runner.run()
    assert isinstance(error.value, SystemExit)
    assert error.value.code == 7


def test_slow_observer_cannot_trigger_off_cadence_catchup_attempt():
    hb = heartbeat_module()
    clock, attempts, observations = Clock(), [], []
    runner = None
    def renew():
        attempts.append(clock())
        if len(attempts) == 2:
            runner.stop.set()
        return 1
    def observe(value):
        observations.append(value)
        if len(observations) == 1:
            clock.now += 25
    runner = hb.Heartbeat(renew=renew, fence=hb.OwnershipFence(), interval=10,
                          logger=configure_logging("worker", stream=StringIO()),
                          clock=clock, wait=clock.wait, observe=observe)
    runner.run()
    assert attempts == [10, 40]
    assert sum(o.skipped_tick_count for o in observations) == 2


@pytest.mark.parametrize("primary", ["loss", "interrupt"])
def test_commit_guard_primary_survives_rollback_failure(primary):
    hb = heartbeat_module()
    from sqlalchemy import create_engine, text, event
    from daesingo.common.db.transactions import run_worker_transaction
    engine = create_engine("sqlite://")
    fence = hb.OwnershipFence()
    def bad_rollback(conn):
        raise RuntimeError("private cleanup")
    event.listen(engine, "rollback", bad_rollback)
    @contextmanager
    def guard():
        raise KeyboardInterrupt()
        yield
    def operation(conn):
        conn.execute(text("SELECT 1"))
        if primary == "loss":
            fence.mark_lost()
    try:
        with pytest.raises(BaseException) as error:
            run_worker_transaction(engine, operation,
                                   commit_guard=fence.commit_guard if primary == "loss" else guard)
        assert isinstance(error.value, hb.OwnershipLost if primary == "loss" else KeyboardInterrupt)
    finally:
        event.remove(engine, "rollback", bad_rollback)
        engine.dispose()


def test_lease_close_baseexception_survives_engine_dispose_error():
    hb = heartbeat_module()
    disposed = []
    def dispose():
        disposed.append(True)
        raise RuntimeError("private engine cleanup")
    def close():
        raise SystemExit(7)
    lease = hb.LeaseConnection(SimpleNamespace(dispose=dispose), "exec", "owner", 60,
                               fence=hb.OwnershipFence(), owns_engine=True)
    lease.conn = SimpleNamespace(close=close)
    with pytest.raises(BaseException) as error:
        lease.close()
    assert isinstance(error.value, SystemExit)
    assert error.value.code == 7 and disposed == [True]


def test_lease_execute_baseexception_survives_transaction_rollback_error():
    hb = heartbeat_module()
    from sqlalchemy import create_engine, event
    engine = create_engine("sqlite://")
    def execute_failure(*args):
        raise SystemExit(7)
    def rollback_failure(conn):
        raise RuntimeError("private rollback")
    event.listen(engine, "before_cursor_execute", execute_failure)
    event.listen(engine, "rollback", rollback_failure)
    lease = hb.LeaseConnection(engine, "exec", "owner", 60, fence=hb.OwnershipFence())
    try:
        with pytest.raises(BaseException) as error:
            lease.renew()
        assert isinstance(error.value, SystemExit)
        assert error.value.code == 7
    finally:
        event.remove(engine, "before_cursor_execute", execute_failure)
        event.remove(engine, "rollback", rollback_failure)
        lease.close()
        engine.dispose()
