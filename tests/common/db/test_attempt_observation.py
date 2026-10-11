"""Observation occurs after commit acknowledgement and cannot change DB outcomes."""

import pytest
import sqlalchemy as sa
import pymysql

from daesingo.common.db import transactions


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine("sqlite:///" + (tmp_path / "observer.sqlite").as_posix())
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE witness(id INTEGER PRIMARY KEY)")
    yield engine
    engine.dispose()


def failure():
    return sa.exc.OperationalError(None, {}, pymysql.err.OperationalError(1213, "test deadlock"))


def test_success_duration_ends_at_commit_ack_excludes_checkout_and_checkin(engine, monkeypatch):
    clock = [1_000_000_000]
    observations = []
    monkeypatch.setattr(transactions.time, "monotonic_ns", lambda: clock[0])
    @sa.event.listens_for(engine, "checkout")
    def checkout(*args):
        clock[0] = 10_000_000_000
    original = engine.dialect.do_commit
    def commit(connection):
        assert observations == []
        original(connection)
        clock[0] = 10_150_000_000
    monkeypatch.setattr(engine.dialect, "do_commit", commit)
    @sa.event.listens_for(engine, "checkin")
    def checkin(*args):
        clock[0] = 90_000_000_000
    assert transactions.run_worker_transaction(engine, lambda conn: 42, observe=observations.append) == 42
    assert len(observations) == 1
    assert observations[0].outcome == "COMMITTED" and observations[0].duration_ms == 150


@pytest.mark.parametrize("fault", ["sink", "dbapi_sink"])
def test_broken_observer_does_not_replay_acknowledged_write(engine, fault):
    calls = []
    def operation(conn):
        calls.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES(1)")
        return 1
    def observe(attempt):
        raise failure() if fault == "dbapi_sink" else RuntimeError("sink failed")
    assert transactions.run_worker_transaction(engine, operation, observe=observe) == 1
    assert calls == [1]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 1


def test_retry_decision_and_rollback_survive_broken_logger_and_observer(engine):
    calls = []
    class BrokenLogger:
        def log(self, *args, **kwargs):
            raise failure()
    def operation(conn):
        calls.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES(1)")
        if len(calls) == 1:
            raise failure()
        return 2
    def observe(attempt):
        raise failure()
    assert transactions.run_worker_transaction(engine, operation, sleep=lambda _: None,
                                                logger=BrokenLogger(), observe=observe) == 2
    assert calls == [1, 1]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 1


def test_observe_reports_each_attempt_without_leaking_sql(engine):
    calls, observations = [], []
    def operation(conn):
        calls.append(1)
        if len(calls) == 1:
            raise failure()
        return 42
    assert transactions.run_worker_transaction(engine, operation, sleep=lambda _: None,
                                                observe=observations.append) == 42
    assert [o.outcome for o in observations] == ["DEADLOCK", "COMMITTED"]
    assert all(o.duration_ms >= 0 for o in observations)
    assert all(set(vars(o)) == {"outcome", "duration_ms"} for o in observations)
