import time

import pytest
import sqlalchemy as sa

from daesingo.common.config import HeartbeatSettings, ReadySettings
from daesingo.common.db import (
    create_api_engine, create_worker_engine, create_heartbeat_engine,
    create_ready_engine, create_migration_engine,
)
from daesingo.common.db.errors import BeforeCommitFailure
from daesingo.common.db.transactions import run_api_transaction

pytestmark = pytest.mark.mysql


def factory_params(scenario):
    return [pytest.param(create_api_engine, id="api", marks=pytest.mark.mysql_check("api", scenario)),
            pytest.param(create_worker_engine, id="worker", marks=pytest.mark.mysql_check("worker", scenario))]


def session(conn, lock_wait=5):
    assert conn.exec_driver_sql("SELECT @@session.transaction_isolation").scalar_one() == "READ-COMMITTED"
    assert conn.exec_driver_sql("SELECT @@session.innodb_lock_wait_timeout").scalar_one() == lock_wait
    return conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()


@pytest.mark.mysql_scenario("sessions")
@pytest.mark.parametrize("factory", factory_params("sessions"))
def test_actual_application_sessions_are_read_committed(db_settings, engines, factory):
    engine = engines(factory(db_settings))
    with engine.connect() as conn:
        session(conn)
        assert conn.exec_driver_sql("SELECT @@session.autocommit").scalar_one() == 0


@pytest.mark.mysql_scenario("idle_recycle", "session_replacements")
@pytest.mark.parametrize("factory", factory_params("idle_recycle"))
def test_recycle_replaces_connection_and_reapplies_session(db_settings, engines, factory):
    engine = engines(factory(db_settings.model_copy(update={"pool_size": 1, "max_overflow": 0, "pool_recycle_sec": 1})))
    with engine.connect() as conn:
        first = session(conn)
    time.sleep(1.2)
    with engine.connect() as conn:
        assert session(conn) != first


@pytest.mark.mysql_scenario("wait_timeout", "session_replacements")
@pytest.mark.parametrize("factory", factory_params("wait_timeout"))
def test_pre_ping_recovers_after_server_wait_timeout_without_recycle(db_settings, engines, factory):
    engine = engines(factory(db_settings.model_copy(update={"pool_size": 1, "max_overflow": 0, "pool_recycle_sec": 1800})))
    with engine.connect() as conn:
        first = session(conn)
        conn.exec_driver_sql("SET SESSION wait_timeout = 1")
    time.sleep(2)
    with engine.connect() as conn:
        assert session(conn) != first


@pytest.mark.mysql_scenario("session_replacements")
@pytest.mark.parametrize("factory", factory_params("disconnect_replacement"))
def test_disconnect_replacement_reapplies_session(db_settings, engines, factory):
    engine = engines(factory(db_settings.model_copy(update={"pool_size": 1, "max_overflow": 0})))
    controller = engines(create_migration_engine(db_settings.url.get_secret_value()))
    with engine.connect() as conn:
        first = session(conn)
        with controller.connect() as control:
            control.exec_driver_sql(f"KILL CONNECTION {first}")
        with pytest.raises(sa.exc.DBAPIError) as error:
            conn.exec_driver_sql("SELECT 1")
        assert error.value.connection_invalidated
    with engine.connect() as conn:
        assert session(conn) != first


@pytest.mark.mysql_scenario("pool_exhaustion", "api_precommit", "dedicated_connections")
@pytest.mark.mysql_check("api", "pool_exhaustion")
@pytest.mark.mysql_check("heartbeat", "sessions")
@pytest.mark.mysql_check("heartbeat", "dedicated_connections")
@pytest.mark.mysql_check("ready", "dedicated_connections")
def test_pool_exhaustion_is_precommit_and_dedicated_connections_still_work(db_settings, engines):
    pool = engines(create_api_engine(db_settings.model_copy(update={"pool_size": 1, "max_overflow": 1, "pool_timeout_sec": 0.15})))
    heartbeat = engines(create_heartbeat_engine(db_settings, HeartbeatSettings()))
    ready = engines(create_ready_engine(db_settings, ReadySettings()))
    calls = []
    with pool.connect() as one, pool.connect() as two:
        ids = {session(one), session(two)}
        with pytest.raises(BeforeCommitFailure) as error:
            run_api_transaction(pool, lambda conn: calls.append(1))
        assert error.value.reason == "pool_timeout"
        assert calls == []
        with heartbeat.connect() as conn:
            first_heartbeat = session(conn, 2)
            assert first_heartbeat not in ids
        with heartbeat.connect() as conn:
            assert session(conn, 2) not in ids | {first_heartbeat}
        with ready.connect() as conn:
            assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one() not in ids
    with pool.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


@pytest.mark.mysql_scenario("migration_policy")
@pytest.mark.mysql_check("migration", "migration_policy")
def test_migration_engine_is_separate_and_can_execute_without_creating_runtime_tables(db_settings, engines):
    engine = engines(create_migration_engine(db_settings.url.get_secret_value(), connect_timeout=2, read_timeout=10))
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert conn.exec_driver_sql("SHOW TABLES").all() == []


@pytest.mark.mysql_scenario("api_precommit")
@pytest.mark.mysql_check("api", "connect_failure")
def test_actual_driver_connection_refused_is_precommit_without_running_callback(db_settings, engines):
    from sqlalchemy.engine import make_url
    url = make_url(db_settings.url.get_secret_value()).set(host="127.0.0.1", port=1)
    db = db_settings.model_copy(update={"url": type(db_settings.url)(url.render_as_string(hide_password=False))})
    engine = engines(create_api_engine(db))
    with pytest.raises(BeforeCommitFailure) as error:
        run_api_transaction(engine, lambda conn: pytest.fail("must not run without connection"))
    assert error.value.reason == "connect_failure"
