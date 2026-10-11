import pytest
import sqlalchemy as sa
from contextlib import contextmanager
from io import StringIO

from daesingo.common.db import create_api_engine, create_worker_engine
from daesingo.common.db.errors import BeforeCommitFailure, CommitOutcomeUnknown
from daesingo.common.db.transactions import run_api_transaction, run_worker_transaction

pytestmark = pytest.mark.mysql


def proxied_settings(db_settings, proxy):
    from sqlalchemy.engine import make_url
    url = make_url(db_settings.url.get_secret_value()).set(host="127.0.0.1", port=proxy.port)
    # Packet inspection is test-only; disable TLS on this local proxy connection.
    url = url.update_query_dict({"ssl_disabled": "true"})
    return db_settings.model_copy(update={"url": type(db_settings.url)(url.render_as_string(hide_password=False))})


def proxy_for(db_settings, **kwargs):
    from mysql_fault_proxy import CommitResponseProxy
    from sqlalchemy.engine import make_url
    url = make_url(db_settings.url.get_secret_value())
    return CommitResponseProxy(url.host, url.port or 3306, **kwargs)


@pytest.mark.mysql_scenario("commit_response_loss")
@pytest.mark.mysql_check("api", "commit_response_loss")
def test_api_actual_commit_response_loss_is_unknown_but_server_committed(probe, db_settings, engines):
    calls = []
    with proxy_for(db_settings) as proxy:
        engine = engines(create_api_engine(proxied_settings(db_settings, proxy)))

        def operation(conn):
            proxy.arm()
            calls.append(1)
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('commit-lost', 1)")
            return "done"

        with pytest.raises(CommitOutcomeUnknown):
            run_api_transaction(engine, operation)
        assert proxy.commit_forwarded == proxy.commit_ok_dropped == 1
        assert calls == [1]
        with probe.connect() as observer:
            assert observer.exec_driver_sql("SELECT COUNT(*) FROM tx_effect WHERE operation_id='commit-lost'").scalar_one() == 1
        engine.dispose()


@pytest.mark.parametrize("cleanup", ["none", "timeout", "dbapi"])
def test_actual_1205_context_cannot_replace_current_lost_commit(probe, db_settings, engines, cleanup):
    from daesingo.common.logging import configure_logging

    stream = StringIO()
    logger = configure_logging("api", stream=stream)
    with proxy_for(db_settings) as proxy:
        engine = engines(create_api_engine(proxied_settings(db_settings, proxy)))

        def checkin(dbapi_connection, record):
            if cleanup == "dbapi":
                import pymysql
                raise sa.exc.OperationalError(
                    "cleanup-private-sql", {}, pymysql.err.OperationalError(1213, "cleanup-private-detail"),
                )
            if cleanup == "timeout":
                raise sa.exc.TimeoutError("cleanup-private-detail")

        sa.event.listen(engine.pool, "checkin", checkin)

        def operation(conn):
            proxy.arm()
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('ambient-commit', 1)")

        error = None
        try:
            with probe.connect() as blocker, probe.connect() as contender:
                with blocker.begin():
                    blocker.exec_driver_sql("SELECT id FROM tx_counter WHERE id=2 FOR UPDATE")
                    contender.exec_driver_sql("SET SESSION innodb_lock_wait_timeout=1")
                    try:
                        contender.exec_driver_sql("UPDATE tx_counter SET value=value+1 WHERE id=2")
                    except sa.exc.DBAPIError as previous:
                        assert previous.orig.args[0] == 1205
                        try:
                            run_api_transaction(engine, operation, logger=logger)
                        except Exception as observed:
                            error = observed
                    else:
                        pytest.fail("real lock timeout was not injected")
        finally:
            sa.event.remove(engine.pool, "checkin", checkin)
        assert proxy.commit_forwarded == proxy.commit_ok_dropped == 1
        with probe.connect() as observer:
            assert observer.exec_driver_sql("SELECT COUNT(*) FROM tx_effect WHERE operation_id='ambient-commit'").scalar_one() == 1
        assert isinstance(error, CommitOutcomeUnknown), type(error).__name__
        assert "private" not in str(error) + stream.getvalue()
        assert "ambient-commit" not in str(error) + stream.getvalue()
        engine.dispose()


@pytest.mark.mysql_scenario("worker_unknown_commit")
@pytest.mark.mysql_check("worker", "worker_unknown_commit")
def test_worker_unknown_commit_restarts_read_and_returns_existing_result_without_duplicate(probe, db_settings, engines):
    reads = []
    with proxy_for(db_settings) as proxy:
        engine = engines(create_worker_engine(proxied_settings(db_settings, proxy)))

        def operation(conn):
            proxy.arm()
            existing = conn.exec_driver_sql("SELECT attempt_no FROM tx_effect WHERE operation_id='stable-identity'").scalar_one_or_none()
            reads.append(existing)
            if existing is not None:
                return existing
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('stable-identity', 1)")
            return 1

        assert run_worker_transaction(engine, operation) == 1
        assert reads == [None, 1]
        assert proxy.commit_ok_dropped == 1
        with probe.connect() as observer:
            assert observer.exec_driver_sql("SELECT COUNT(*) FROM tx_effect").scalar_one() == 1
        engine.dispose()


@pytest.mark.mysql_scenario("api_precommit")
@pytest.mark.mysql_check("api", "precommit_proxy_disconnect")
def test_api_before_commit_kill_does_not_send_commit_and_leaves_no_rows(probe, db_settings, engines):
    with proxy_for(db_settings) as proxy:
        engine = engines(create_api_engine(proxied_settings(db_settings, proxy)))

        def operation(conn):
            proxy.arm()
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('before-commit', 1)")
            connection_id = conn.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one()
            with probe.connect() as control:
                control.exec_driver_sql(f"KILL CONNECTION {connection_id}")
            conn.exec_driver_sql("SELECT 1")

        with pytest.raises(BeforeCommitFailure):
            run_api_transaction(engine, operation)
        assert proxy.commit_forwarded == proxy.commit_ok_dropped == 0
        with probe.connect() as observer:
            assert observer.exec_driver_sql("SELECT COUNT(*) FROM tx_effect").scalar_one() == 0
        engine.dispose()


@pytest.mark.mysql_scenario("commit_response_loss_cleanup")
@pytest.mark.parametrize("cleanup", [
    pytest.param("context_exit", marks=pytest.mark.mysql_check("api", "commit_response_loss_context_exit")),
    pytest.param("pool_checkin", marks=pytest.mark.mysql_check("api", "commit_response_loss_pool_checkin")),
])
def test_actual_committed_row_and_unknown_outcome_survive_secondary_cleanup_timeout(probe, db_settings, engines, monkeypatch, cleanup):
    from daesingo.common.logging import configure_logging

    stream = StringIO()
    logger = configure_logging("api", stream=stream)
    with proxy_for(db_settings) as proxy:
        engine = engines(create_api_engine(proxied_settings(db_settings, proxy)))

        def checkin(dbapi_connection, record):
            raise sa.exc.TimeoutError("cleanup-private-token")

        if cleanup == "pool_checkin":
            sa.event.listen(engine.pool, "checkin", checkin)
        else:
            original_connect = engine.connect

            @contextmanager
            def connection_context():
                try:
                    with original_connect() as conn:
                        yield conn
                finally:
                    raise sa.exc.TimeoutError("cleanup-private-token")

            monkeypatch.setattr(engine, "connect", connection_context)

        def operation(conn):
            proxy.arm()
            conn.exec_driver_sql("INSERT INTO tx_effect VALUES ('commit-cleanup', 1)")

        error = None
        try:
            run_api_transaction(engine, operation, logger=logger)
        except Exception as observed:
            error = observed
        finally:
            if cleanup == "pool_checkin":
                sa.event.remove(engine.pool, "checkin", checkin)
        assert proxy.commit_ok_dropped == 1
        with probe.connect() as observer:
            assert observer.exec_driver_sql("SELECT COUNT(*) FROM tx_effect WHERE operation_id='commit-cleanup'").scalar_one() == 1
        chain, current = [], error
        while current is not None and len(chain) < 8:
            code = getattr(current, "args", (None,))[0]
            chain.append((type(current).__module__, type(current).__name__, code if isinstance(code, int) else None))
            current = current.__context__
        assert isinstance(error, CommitOutcomeUnknown), chain
        assert "cleanup-private-token" not in str(error) + stream.getvalue()
        assert "commit-cleanup" not in str(error) + stream.getvalue()
        engine.dispose()
