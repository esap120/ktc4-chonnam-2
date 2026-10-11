"""Factory policy tests; actual server behavior is in integration/."""

import pytest
from sqlalchemy import event
from sqlalchemy.pool import NullPool

from daesingo.common.config import DbSettings, HeartbeatSettings, ReadySettings, RuntimeConfig


def factories():
    from daesingo.common.db import engines
    return engines


def settings(service="api", **overrides):
    config = RuntimeConfig.from_mapping(service, {
        "DAESINGO_RUNTIME_DB_URL": "mysql+pymysql://test:secret@localhost/test_db",
        "DAESINGO_RUNTIME_MEDIA_ROOT": "/media",
        f"DAESINGO_RUNTIME_{service.upper()}_TEMP_ROOT": "/temp",
    })
    return config.db.model_copy(update=overrides)


def connect_parameters(engine):
    captured = {}

    class StopConnect(Exception):
        pass

    @event.listens_for(engine, "do_connect")
    def capture(dialect, record, args, kwargs):
        captured.update(kwargs)
        raise StopConnect

    try:
        with pytest.raises(StopConnect):
            engine.connect()
        return captured
    finally:
        engine.dispose()


@pytest.mark.parametrize("service,size,overflow", [("api", 5, 5), ("worker", 2, 2)])
def test_application_factories_consume_rt01_defaults(service, size, overflow):
    engine = getattr(factories(), f"create_{service}_engine")(settings(service))
    assert engine.pool.size() == size
    assert engine.pool._max_overflow == overflow
    assert engine.pool.timeout() == 5
    assert engine.pool._recycle == 1800
    assert engine.pool._pre_ping is True
    params = connect_parameters(engine)
    assert [params[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [5, 30, 30]
    assert params.get("autocommit", False) is False


def test_custom_application_timeouts_reach_driver():
    engine = factories().create_worker_engine(settings("worker", pool_size=3, max_overflow=0,
        pool_timeout_sec=0.1, pool_recycle_sec=17, connect_timeout_sec=4,
        read_timeout_sec=9, write_timeout_sec=8))
    assert engine.pool.size() == 3
    assert engine.pool._max_overflow == 0
    assert engine.pool.timeout() == 0.1
    assert engine.pool._recycle == 17
    params = connect_parameters(engine)
    assert [params[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [4, 9, 8]


def test_heartbeat_and_ready_have_no_shared_queue_pool():
    db = settings()
    heartbeat = factories().create_heartbeat_engine(db, HeartbeatSettings())
    ready = factories().create_ready_engine(db, ReadySettings())
    assert isinstance(heartbeat.pool, NullPool)
    assert isinstance(ready.pool, NullPool)
    hp, rp = connect_parameters(heartbeat), connect_parameters(ready)
    assert [hp[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [2, 5, 5]
    assert [rp[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [1, 1, 1]


def test_dedicated_factories_consume_custom_settings():
    heartbeat = factories().create_heartbeat_engine(settings(), HeartbeatSettings(
        connect_timeout_sec=1, read_timeout_sec=3, write_timeout_sec=4))
    ready = factories().create_ready_engine(settings(), ReadySettings(db_timeout_sec=0.8))
    hp, rp = connect_parameters(heartbeat), connect_parameters(ready)
    assert [hp[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [1, 3, 4]
    assert [rp[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [0.4, 0.4, 0.4]


def test_migration_factory_uses_explicit_policy_without_application_io_limits():
    engine = factories().create_migration_engine("mysql+pymysql://test:secret@localhost/test_db")
    assert isinstance(engine.pool, NullPool)
    params = connect_parameters(engine)
    assert "read_timeout" not in params
    assert "write_timeout" not in params
    assert "connect_timeout" not in params
    explicit = factories().create_migration_engine("mysql+pymysql://test:secret@localhost/test_db",
        connect_timeout=7, read_timeout=120, write_timeout=120)
    params = connect_parameters(explicit)
    assert [params[k] for k in ("connect_timeout", "read_timeout", "write_timeout")] == [7, 120, 120]


@pytest.mark.parametrize("query", ["autocommit=true", "init_command=COMMIT", "read_default_file=x"])
def test_url_cannot_bypass_transaction_or_session_policy(query):
    db = DbSettings(url="mysql+pymysql://test:secret@localhost/test_db?" + query)
    with pytest.raises(ValueError, match="DB URL options"):
        factories().create_api_engine(db)


def test_url_timeout_options_do_not_override_role_policy():
    db = DbSettings(url="mysql+pymysql://test:secret@localhost/test_db?read_timeout=999&connect_timeout=99")
    params = connect_parameters(factories().create_ready_engine(db, ReadySettings()))
    assert params["read_timeout"] == params["connect_timeout"] == 1
