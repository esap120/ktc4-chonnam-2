from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
import time
from uuid import uuid4

import pytest
import sqlalchemy as sa

from daesingo.common.db.errors import BeforeCommitFailure, TransactionRetryExhausted
from daesingo.common.db.transactions import run_api_transaction, run_worker_transaction

pytestmark = pytest.mark.mysql


def counts(engine):
    with engine.connect() as conn:
        return (conn.exec_driver_sql("SELECT COUNT(*) FROM tx_effect").scalar_one(),
                conn.exec_driver_sql("SELECT value FROM tx_counter ORDER BY id").scalars().all())


@pytest.mark.mysql_scenario("worker_1205", "capability_boundary")
@pytest.mark.mysql_check("worker", "worker_1205")
@pytest.mark.mysql_check("worker", "capability_boundary")
def test_real_1205_rolls_back_preceding_writes_and_restarts_from_read(probe):
    reads, codes, external_calls = [], [], []

    def capability():
        assert probe.pool.checkedout() == 0
        external_calls.append(1)
        return "observed-result"

    payload = capability()  # outside the retryable transaction; no provider re-call
    with probe.connect() as blocker:
        lock = blocker.begin()
        blocker.exec_driver_sql("SELECT id FROM tx_counter WHERE id=2 FOR UPDATE")

        def operation(conn):
            conn.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
            reads.append(conn.exec_driver_sql("SELECT value FROM tx_counter WHERE id=1").scalar_one())
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('stable-op', %s)", (len(reads),))
            conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=1")
            try:
                conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=2")
            except sa.exc.DBAPIError as error:
                codes.append(error.orig.args[0])
                raise
            return payload

        def release_after_rollback(seconds):
            assert seconds == 1
            assert counts(probe) == (0, [0, 0])
            lock.rollback()
            time.sleep(seconds)

        try:
            assert run_worker_transaction(probe, operation, sleep=release_after_rollback) == payload
        finally:
            if lock.is_active:
                lock.rollback()
    assert reads == [0, 0]
    assert codes == [1205]
    assert external_calls == [1]
    assert counts(probe) == (1, [1, 1])
    with probe.connect() as conn:
        assert conn.exec_driver_sql("SELECT attempt_no FROM tx_effect").scalar_one() == 2


@pytest.mark.mysql_scenario("worker_exhaustion")
@pytest.mark.mysql_check("worker", "worker_exhaustion")
def test_real_1205_exhausts_after_initial_plus_two_retries(probe):
    attempts, sleeps = [], []
    with probe.connect() as blocker:
        lock = blocker.begin()
        blocker.exec_driver_sql("SELECT id FROM tx_counter WHERE id=2 FOR UPDATE")

        def operation(conn):
            conn.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
            attempts.append(conn.exec_driver_sql("SELECT value FROM tx_counter WHERE id=1").scalar_one())
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('exhausted-op', %s)", (len(attempts),))
            conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=1")
            conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=2")

        def wait(seconds):
            assert counts(probe) == (0, [0, 0])
            sleeps.append(seconds)
            time.sleep(seconds)

        try:
            with pytest.raises(TransactionRetryExhausted) as error:
                run_worker_transaction(probe, operation, sleep=wait)
            assert error.value.attempts == 3
            assert not error.value.outcome_unknown
        finally:
            lock.rollback()
    assert attempts == [0, 0, 0]
    assert sleeps == [1, 1]
    assert counts(probe) == (0, [0, 0])


@pytest.mark.mysql_scenario("worker_1213")
@pytest.mark.mysql_check("worker", "worker_1213")
def test_real_deadlock_victim_restarts_whole_transaction_without_fixed_victim(probe):
    first_locks = Barrier(2, timeout=10)
    reads, codes = {"a": [], "b": []}, []

    def participant(name, first, second):
        def operation(conn):
            reads[name].append(conn.exec_driver_sql("SELECT value FROM tx_counter WHERE id=%s", (first,)).scalar_one())
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES (%s, %s)", (name, len(reads[name])))
            conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=%s", (first,))
            if len(reads[name]) == 1:
                first_locks.wait()
            try:
                conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=%s", (second,))
            except sa.exc.DBAPIError as error:
                codes.append(error.orig.args[0])
                raise
            return name
        return run_worker_transaction(probe, operation)

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(participant, "a", 1, 2)
        b = executor.submit(participant, "b", 2, 1)
        assert {a.result(timeout=20), b.result(timeout=20)} == {"a", "b"}
    assert codes == [1213]
    assert sorted(reads.values(), key=len) == [[0], [0, 1]]
    assert counts(probe) == (2, [2, 2])


@pytest.mark.mysql_scenario("worker_disconnect")
@pytest.mark.mysql_check("worker", "worker_disconnect")
def test_real_connection_kill_discards_transaction_and_restarts_read(probe):
    reads, ids, codes = [], [], []

    def operation(conn):
        reads.append(conn.exec_driver_sql("SELECT COUNT(*) FROM tx_effect").scalar_one())
        ids.append(conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one())
        conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('killed-op', %s)", (len(reads),))
        if len(reads) == 1:
            with probe.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {ids[-1]}")
        try:
            conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=1")
        except sa.exc.DBAPIError as error:
            assert error.connection_invalidated
            codes.append(error.orig.args[0])
            raise

    run_worker_transaction(probe, operation)
    assert reads == [0, 0]
    assert ids[0] != ids[1]
    assert len(codes) == 1
    assert counts(probe) == (1, [1, 0])


@pytest.mark.mysql_scenario("api_precommit")
@pytest.mark.parametrize("fault", [
    pytest.param("1205", marks=pytest.mark.mysql_check("api", "precommit_1205")),
    pytest.param("kill", marks=pytest.mark.mysql_check("api", "precommit_disconnect")),
])
def test_api_real_precommit_failure_never_reexecutes_callback(probe, fault):
    calls = []
    with probe.connect() as blocker:
        lock = blocker.begin()
        blocker.exec_driver_sql("SELECT id FROM tx_counter WHERE id=2 FOR UPDATE")

        def operation(conn):
            calls.append(1)
            conn.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('api-op', 1)")
            if fault == "kill":
                connection_id = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
                with probe.connect() as control:
                    control.exec_driver_sql(f"KILL CONNECTION {connection_id}")
            conn.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=2")

        try:
            with pytest.raises(BeforeCommitFailure) as error:
                run_api_transaction(probe, operation)
            assert error.value.reason == ("lock_wait_timeout" if fault == "1205" else "disconnect")
        finally:
            lock.rollback()
    assert calls == [1]
    assert counts(probe) == (0, [0, 0])


@pytest.mark.mysql_scenario("require_privileges")
@pytest.mark.mysql_check("harness", "require_privileges")
def test_require_mode_rejects_real_schema_permission_failure(mysql_server_url):
    from mysql_harness import _control_engine

    engine = _control_engine(mysql_server_url)
    name, password = "rt02a_low_" + uuid4().hex[:16], uuid4().hex
    try:
        with engine.connect() as control:
            control.exec_driver_sql(f"CREATE USER '{name}'@'%%' IDENTIFIED BY '{password}'")
            control.exec_driver_sql(f"GRANT SELECT ON `{mysql_server_url.database}`.* TO '{name}'@'%%'")
        url = mysql_server_url.set(username=name, password=password)
        env = dict(os.environ, DAESINGO_REQUIRE_MYSQL="1", PYTHONDONTWRITEBYTECODE="1",
                   DAESINGO_MYSQL_URL=url.render_as_string(hide_password=False))
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "pytest", "tests/common/db/test_engines.py",
                                 "--collect-only", "-q", "-p", "no:cacheprovider"],
                                cwd=Path(__file__).resolve().parents[4], env=env, text=True,
                                encoding="utf-8", capture_output=True, timeout=30)
        assert result.returncode != 0
        assert "MySQL preflight failed" in result.stdout + result.stderr
        assert "skipped" not in result.stdout
        assert password not in result.stdout + result.stderr
    finally:
        with engine.connect() as control:
            control.exec_driver_sql(f"DROP USER IF EXISTS '{name}'@'%%'")
        engine.dispose()
