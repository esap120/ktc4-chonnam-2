"""Role policies consume RT-01 settings; DB URLs are never read from env here."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.pool import NullPool

from daesingo.common.config import DbSettings, HeartbeatSettings, ReadySettings

_TIMEOUTS = ("connect_timeout", "read_timeout", "write_timeout")
_UNSAFE_OPTIONS = frozenset({
    "autocommit", "init_command", "read_default_file", "read_default_group",
    "client_flag", "defer_connect",
})


def _url(value: str | URL) -> URL:
    url = make_url(value)
    if url.drivername != "mysql+pymysql":
        raise ValueError("DB URL must use mysql+pymysql")
    if _UNSAFE_OPTIONS.intersection(url.query):
        raise ValueError("DB URL options cannot override transaction/session policy")
    return url.difference_update_query(_TIMEOUTS)


def _session(engine: Engine, lock_wait: int) -> Engine:
    # connect, rather than first_connect: applies again after recycle/invalidation.
    @event.listens_for(engine, "connect")
    def initialize(dbapi_connection, connection_record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f"SET SESSION innodb_lock_wait_timeout = {int(lock_wait)}")
            cursor.execute("SET SESSION time_zone = '+00:00'")

    @event.listens_for(engine, "checkout")
    def utc_on_checkout(dbapi_connection, connection_record, connection_proxy):
        # SET SESSION survives rollback. Restore UTC even if a prior borrower
        # changed the pooled session; NOW(6) must compare UTC DATETIME(6) values.
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION time_zone = '+00:00'")
    return engine


def _application(db: DbSettings) -> Engine:
    engine = create_engine(
        _url(db.url.get_secret_value()), isolation_level="READ COMMITTED",
        pool_size=db.pool_size, max_overflow=db.max_overflow,
        pool_timeout=db.pool_timeout_sec, pool_recycle=db.pool_recycle_sec,
        pool_pre_ping=db.pool_pre_ping, hide_parameters=True,
        connect_args={"connect_timeout": db.connect_timeout_sec,
                      "read_timeout": db.read_timeout_sec,
                      "write_timeout": db.write_timeout_sec, "autocommit": False},
    )
    return _session(engine, db.lock_wait_timeout_sec)


def create_api_engine(db: DbSettings) -> Engine:
    """Use API RuntimeConfig.db; factory creation does not connect."""
    return _application(db)


def create_worker_engine(db: DbSettings) -> Engine:
    """Use Worker RuntimeConfig.db (its pool defaults are 2 + 2, not 5 + 5)."""
    return _application(db)


def create_heartbeat_engine(db: DbSettings, heartbeat: HeartbeatSettings) -> Engine:
    """One heartbeat thread owns one Connection; reconnect next tick on failure.

    NullPool shares no application checkout queue. RT-05 owns connection retention,
    nonoverlapping ticks, and reconnect scheduling; never use the Worker retry helper.
    """
    engine = create_engine(
        _url(db.url.get_secret_value()), poolclass=NullPool,
        isolation_level="READ COMMITTED", hide_parameters=True,
        connect_args={"connect_timeout": heartbeat.connect_timeout_sec,
                      "read_timeout": heartbeat.read_timeout_sec,
                      "write_timeout": heartbeat.write_timeout_sec, "autocommit": False},
    )
    return _session(engine, heartbeat.lock_wait_timeout_sec)


def create_ready_engine(db: DbSettings, ready: ReadySettings) -> Engine:
    """Fresh connection per probe; no pool wait, automatic retry, or migration.

    B-H1 default is connect/read=1/1s. Bound writes too. These are per-I/O
    timeouts, not proof of an end-to-end deadline; RT-08 owns the probe budget.
    SELECT 1 has no row-lock wait, so it does not inherit B-D1/B-D9.
    """
    stage = ready.db_timeout_sec / 2
    return create_engine(
        _url(db.url.get_secret_value()), poolclass=NullPool,
        isolation_level="AUTOCOMMIT", hide_parameters=True,
        connect_args={"connect_timeout": stage, "read_timeout": stage,
                      "write_timeout": stage},
    )


def create_migration_engine(
    url: str | URL, *, connect_timeout: float | None = None,
    read_timeout: float | None = None, write_timeout: float | None = None,
) -> Engine:
    """Foundation only. Explicit URL/timeouts; no runner/env or application limits.

    Omitted timeouts retain driver defaults, including unbounded read/write for
    potentially long DDL. A future runner must select its own explicit policy.
    """
    timeouts = dict(zip(_TIMEOUTS, (connect_timeout, read_timeout, write_timeout)))
    if any(value is not None and value <= 0 for value in timeouts.values()):
        raise ValueError("migration timeouts must be positive or None")
    return create_engine(_url(url), poolclass=NullPool, hide_parameters=True,
                         connect_args={key: value for key, value in timeouts.items() if value is not None})
