"""Policy/cleanup tests using real SQLite transactions; MySQL faults run separately."""

import json

import pymysql
import pytest
import sqlalchemy as sa


def api():
    from daesingo.common.db import transactions
    return transactions


def errors():
    from daesingo.common.db import errors
    return errors


def failure(code=1205, disconnected=False):
    return sa.exc.OperationalError("sensitive SQL", {}, pymysql.err.OperationalError(code, "secret payload"),
                                  connection_invalidated=disconnected)


@pytest.fixture
def engine(tmp_path):
    engine = sa.create_engine("sqlite:///" + (tmp_path / "tx.sqlite").as_posix())
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE witness (id INTEGER PRIMARY KEY, value INTEGER)")
    yield engine
    engine.dispose()


@pytest.mark.parametrize("code,disconnected", [(1205, False), (1213, False), (2013, True)])
def test_worker_restarts_body_after_rollback_and_never_repeats_outer_capability(engine, code, disconnected):
    external = ["capability result"]  # caller's non-DB work occurs once before helper
    reads, sleeps = [], []

    def operation(conn):
        reads.append(conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one())
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")
        if len(reads) == 1:
            raise failure(code, disconnected)
        return external[0]

    assert api().run_worker_transaction(engine, operation, sleep=sleeps.append) == "capability result"
    assert reads == [0, 0]
    assert sleeps == [1]
    assert external == ["capability result"]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 1


def test_worker_exhausts_at_three_total_attempts_and_two_sleeps(engine):
    attempts, sleeps = [], []

    def operation(conn):
        attempts.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")
        raise failure()

    with pytest.raises(errors().TransactionRetryExhausted) as error:
        api().run_worker_transaction(engine, operation, sleep=sleeps.append)
    assert error.value.attempts == 3
    assert not error.value.outcome_unknown
    assert len(attempts) == 3
    assert sleeps == [1, 1]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 0


def test_worker_does_not_retry_unrelated_database_or_domain_errors(engine):
    for exception in (ValueError("domain"), failure(1064)):
        calls = []

        def operation(conn):
            calls.append(1)
            raise exception

        with pytest.raises(type(exception)):
            api().run_worker_transaction(engine, operation, sleep=lambda _: pytest.fail("must not retry"))
        assert len(calls) == 1


def test_worker_pool_timeout_is_not_a_bd8_retry(engine):
    def operation(conn):
        raise sa.exc.TimeoutError("pool exhausted")

    with pytest.raises(sa.exc.TimeoutError):
        api().run_worker_transaction(engine, operation, sleep=lambda _: pytest.fail("not B-D8"))


@pytest.mark.parametrize("exception", [failure(), failure(1213), failure(2013, True), sa.exc.TimeoutError("pool")])
def test_api_precommit_dependency_failure_runs_body_only_once_and_rolls_back(engine, exception):
    calls = []

    def operation(conn):
        calls.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")
        raise exception

    with pytest.raises(errors().BeforeCommitFailure) as error:
        api().run_api_transaction(engine, operation)
    assert len(calls) == 1
    assert "secret" not in str(error.value)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 0


def test_api_commit_transport_failure_is_unknown_and_not_retried(engine):
    calls = []

    @sa.event.listens_for(engine, "commit")
    def fail_commit(conn):
        raise failure(2013, True)

    def operation(conn):
        calls.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")

    with pytest.raises(errors().CommitOutcomeUnknown):
        api().run_api_transaction(engine, operation)
    assert len(calls) == 1


def test_api_does_not_reclassify_domain_errors_as_dependency_failures(engine):
    def operation(conn):
        raise ValueError("domain error")

    with pytest.raises(ValueError, match="domain error"):
        api().run_api_transaction(engine, operation)


def test_api_connection_establishment_failure_is_precommit_even_without_invalidation(engine, monkeypatch):
    def unavailable():
        raise failure(2003, False)

    monkeypatch.setattr(engine, "connect", unavailable)
    with pytest.raises(errors().BeforeCommitFailure) as error:
        api().run_api_transaction(engine, lambda conn: pytest.fail("no connection acquired"))
    assert error.value.reason == "connect_failure"


@pytest.mark.parametrize("method", ["commit", "rollback"])
def test_callback_cannot_end_the_caller_owned_transaction(engine, method):
    def operation(conn):
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")
        getattr(conn, method)()

    with pytest.raises(errors().TransactionBoundaryError):
        api().run_worker_transaction(engine, operation)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 0


def test_retry_observability_uses_only_safe_events(engine):
    from daesingo.common.logging import configure_logging
    from io import StringIO

    stream = StringIO()
    logger = configure_logging("worker", stream=stream)
    calls = []

    def operation(conn):
        calls.append(1)
        if len(calls) < 3:
            raise failure()
        return 42

    assert api().run_worker_transaction(engine, operation, sleep=lambda _: None, logger=logger) == 42
    output = stream.getvalue()
    events = [json.loads(line)["event"] for line in output.splitlines()]
    assert events.count("runtime.db.tx_retry_count") == 2
    assert events.count("runtime.db.lock_wait_timeout_count") == 2
    assert "secret" not in output
    assert "sensitive SQL" not in output


def test_rollback_disconnect_cannot_turn_domain_failure_into_worker_retry(engine):
    calls = []

    def fail_once(conn):
        if len(calls) == 1:
            raise failure(2013, True)

    sa.event.listen(engine, "rollback", fail_once)

    def operation(conn):
        calls.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")
        raise ValueError("domain failure")

    try:
        with pytest.raises(ValueError, match="domain failure"):
            api().run_worker_transaction(engine, operation, sleep=lambda _: pytest.fail("domain error must not retry"))
    finally:
        sa.event.remove(engine, "rollback", fail_once)
    assert calls == [1]
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 0


def test_worker_exhaustion_preserves_an_earlier_unknown_commit(engine):
    calls, sleeps = [], []

    def fail_commit(conn):
        conn.invalidate()
        raise failure(2013, True)

    sa.event.listen(engine, "commit", fail_commit)

    def operation(conn):
        calls.append(1)
        if len(calls) > 1:
            raise failure(1205)
        return 1

    with pytest.raises(errors().TransactionRetryExhausted) as error:
        api().run_worker_transaction(engine, operation, sleep=sleeps.append)
    assert error.value.outcome_unknown
    assert error.value.attempts == len(calls) == 3
    assert sleeps == [1, 1]


@pytest.mark.parametrize("role", ["api", "worker"])
@pytest.mark.parametrize("outcome", ["domain", "precommit", "acknowledged"])
@pytest.mark.parametrize("cleanup", ["timeout", "dbapi"])
def test_transaction_outcome_takes_priority_over_pool_checkin_error(engine, role, outcome, cleanup):
    calls, sleeps = [], []

    def fail_checkin(dbapi_connection, record):
        if cleanup == "dbapi":
            raise failure(1213)
        if outcome == "acknowledged":
            raise RuntimeError("private cleanup detail")
        raise sa.exc.TimeoutError("private cleanup detail")

    sa.event.listen(engine.pool, "checkin", fail_checkin)

    def operation(conn):
        calls.append(1)
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")
        if outcome == "domain":
            raise ValueError("domain failure")
        if outcome == "precommit" and len(calls) == 1:
            raise failure(1205)
        return "acknowledged result"

    runner = api().run_api_transaction if role == "api" else api().run_worker_transaction
    kwargs = {} if role == "api" else {"sleep": sleeps.append}
    try:
        if outcome == "domain":
            with pytest.raises(ValueError, match="domain failure"):
                runner(engine, operation, **kwargs)
        elif outcome == "precommit" and role == "api":
            with pytest.raises(errors().BeforeCommitFailure) as error:
                runner(engine, operation, **kwargs)
            assert error.value.reason == "lock_wait_timeout"
        else:
            assert runner(engine, operation, **kwargs) == "acknowledged result"
    finally:
        sa.event.remove(engine.pool, "checkin", fail_checkin)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == (
            1 if outcome == "acknowledged" or (outcome == "precommit" and role == "worker") else 0)
    assert len(calls) == (2 if outcome == "precommit" and role == "worker" else 1)


@pytest.mark.parametrize("ambient", [failure(), failure(1213), failure(2013, True), ValueError("prior domain")],
                         ids=["lock_wait", "deadlock", "disconnect", "domain"])
@pytest.mark.parametrize("link", ["context", "cause"])
@pytest.mark.parametrize("cleanup", ["none", "timeout", "dbapi"])
def test_current_commit_error_ignores_ambient_chain_even_when_checkin_masks_it(
    engine, monkeypatch, ambient, link, cleanup,
):
    import sqlite3

    original_commit = engine.dialect.do_commit

    def commit_then_lose_response(dbapi_connection):
        original_commit(dbapi_connection)
        # Exercise SQLAlchemy's real error handling/invalidation before checkin.
        raise sqlite3.ProgrammingError("Cannot operate on a closed database.")

    monkeypatch.setattr(engine.dialect, "do_commit", commit_then_lose_response)

    def checkin(dbapi_connection, record):
        if cleanup == "dbapi":
            raise failure(1205)
        if cleanup == "timeout":
            raise sa.exc.TimeoutError("private cleanup detail")

    sa.event.listen(engine.pool, "checkin", checkin)

    def operation(conn):
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")

    try:
        try:
            raise ambient
        except Exception as previous:
            try:
                if link == "cause":
                    raise RuntimeError("prior wrapper") from previous
                raise RuntimeError("prior wrapper")
            except RuntimeError:
                with pytest.raises(errors().CommitOutcomeUnknown) as observed:
                    api().run_api_transaction(engine, operation)
                assert "private" not in str(observed.value)
                assert "sensitive" not in str(observed.value)
    finally:
        sa.event.remove(engine.pool, "checkin", checkin)
        monkeypatch.setattr(engine.dialect, "do_commit", original_commit)
    with engine.connect() as observer:
        assert observer.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 1


@pytest.mark.parametrize("link", ["context", "cause"])
def test_current_non_dbapi_commit_error_keeps_its_meaning_inside_ambient_db_error(engine, link):
    current = ValueError("current domain failure")

    def commit(conn):
        raise current

    sa.event.listen(engine, "commit", commit)
    try:
        try:
            raise failure(1213)
        except Exception as previous:
            try:
                if link == "cause":
                    raise RuntimeError("prior wrapper") from previous
                raise RuntimeError("prior wrapper")
            except RuntimeError:
                with pytest.raises(ValueError) as observed:
                    api().run_api_transaction(engine, lambda conn: "result")
                assert observed.value is current
    finally:
        sa.event.remove(engine, "commit", commit)


@pytest.mark.parametrize("query_connection", ["same", "other"])
def test_handled_query_error_in_commit_listener_is_not_the_commit_failure(engine, monkeypatch, query_connection):
    import sqlite3

    original_commit = engine.dialect.do_commit

    def commit_then_lose_response(dbapi_connection):
        original_commit(dbapi_connection)
        raise sqlite3.ProgrammingError("Cannot operate on a closed database.")

    monkeypatch.setattr(engine.dialect, "do_commit", commit_then_lose_response)

    def commit(conn):
        def handled_query(connection):
            try:
                connection.exec_driver_sql("SELECT FROM")
            except sa.exc.DBAPIError:
                pass

        if query_connection == "same":
            handled_query(conn)
        else:
            with engine.connect() as other:
                handled_query(other)

    sa.event.listen(engine, "commit", commit)
    def operation(conn):
        conn.exec_driver_sql("INSERT INTO witness VALUES (1, 7)")

    try:
        with pytest.raises(errors().CommitOutcomeUnknown):
            api().run_api_transaction(engine, operation)
    finally:
        sa.event.remove(engine, "commit", commit)
        monkeypatch.setattr(engine.dialect, "do_commit", original_commit)
    with engine.connect() as observer:
        assert observer.exec_driver_sql("SELECT COUNT(*) FROM witness").scalar_one() == 1
