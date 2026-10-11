"""RT-03(a) acceptance on disposable real MySQL schemas; no skip fallback."""

from importlib import import_module

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import IntegrityError

from daesingo.common.db.transactions import run_api_transaction
from daesingo.common.db.migrate import upgrade_all

pytestmark = pytest.mark.mysql


@pytest.fixture
def queue(mysql_schema_url, mysql_engine):
    upgrade_all(mysql_schema_url)
    return mysql_engine


def repository():
    return import_module("daesingo.common.jobs.repository")


def table():
    return import_module("daesingo.common.jobs.schema").job_execution


def job(job_id="job_1", **changes):
    return {"job_id": job_id, "case_id": "case_1", "kind": "COARSE_SEARCH", **changes}


def count(engine):
    with engine.connect() as observer:
        return observer.exec_driver_sql("SELECT COUNT(*) FROM job_execution").scalar_one()


@pytest.mark.mysql_check("jobs", "schema")
def test_production_migration_schema_and_tracking(queue):
    with queue.connect() as conn:
        db = inspect(conn)
        assert "job_execution" in db.get_table_names()
        assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "runtime_0002"
        assert db.get_foreign_keys("job_execution") == []
        columns = {c["name"]: c for c in db.get_columns("job_execution")}
        assert set(columns) == {
            "execution_id", "job_id", "status", "attempt", "queued_at", "started_at", "ended_at",
            "produced", "failure_kind", "available_at", "lease_owner", "lease_expires_at",
            "heartbeat_at", "cancel_requested_at", "case_applied_at", "trace_id", "kind", "case_id", "claim_token",
        }
        assert "usage_refs" not in columns
        for name in ("queued_at", "started_at", "ended_at", "available_at", "lease_expires_at",
                     "heartbeat_at", "cancel_requested_at", "case_applied_at"):
            assert columns[name]["type"].fsp == 6
        indexes = {tuple(i["column_names"]) for i in db.get_indexes("job_execution")}
        assert {("status", "available_at", "execution_id"), ("job_id",), ("job_id", "attempt")} <= indexes
        assert any(i["column_names"] == ["job_id", "attempt"] and i["unique"]
                   for i in db.get_indexes("job_execution"))
        ddl = conn.exec_driver_sql("SHOW CREATE TABLE job_execution").one()[1]
        assert "ENGINE=InnoDB" in ddl


@pytest.mark.mysql_check("jobs", "enqueue_rollback")
def test_enqueue_is_visible_in_caller_transaction_and_rollback_leaves_no_row(queue):
    with queue.connect() as conn:
        tx = conn.begin()
        commits, rollbacks = [], []
        event.listen(conn, "commit", lambda c: commits.append(True))
        event.listen(conn, "rollback", lambda c: rollbacks.append(True))
        ids = repository().enqueue(conn, [job()], "trace_1")
        assert len(ids) == 1
        row = conn.execute(select(table())).mappings().one()
        assert row["execution_id"] == ids[0]
        assert (row["job_id"], row["attempt"], row["status"]) == ("job_1", 1, "QUEUED")
        assert (row["case_id"], row["kind"], row["trace_id"]) == ("case_1", "COARSE_SEARCH", "trace_1")
        assert row["queued_at"] == row["available_at"]
        assert row["produced"] == [] and row["failure_kind"] is None
        assert all(row[name] is None for name in ("started_at", "ended_at", "lease_owner", "lease_expires_at",
                                                 "heartbeat_at", "cancel_requested_at", "case_applied_at"))
        assert conn.in_transaction() and not conn.closed
        assert commits == rollbacks == []
        assert count(queue) == 0
        tx.rollback()
    assert count(queue) == 0


def test_enqueue_commits_only_with_caller_and_accepts_unknown_kind(queue):
    with queue.begin() as conn:
        ids = repository().enqueue(conn, [job(kind="FUTURE_HANDLER")], "trace_1")
        assert count(queue) == 0
    assert count(queue) == 1
    with queue.connect() as conn:
        row = conn.execute(select(table())).mappings().one()
        assert row["execution_id"] == ids[0]
        assert row["kind"] == "FUTURE_HANDLER"


@pytest.mark.parametrize("same_batch", [
    pytest.param(False, marks=pytest.mark.mysql_check("jobs", "enqueue_duplicate", parameter="separate_batch")),
    pytest.param(True, marks=pytest.mark.mysql_check("jobs", "enqueue_duplicate", parameter="same_batch")),
])
@pytest.mark.mysql_check("jobs", "enqueue_duplicate")
def test_duplicate_job_attempt_is_rejected_atomically_without_rollback_by_repository(queue, same_batch):
    if not same_batch:
        with queue.begin() as conn:
            repository().enqueue(conn, [job()], "original_trace")
    with queue.begin() as conn:
        commits, rollbacks = [], []
        event.listen(conn, "commit", lambda c: commits.append(True))
        event.listen(conn, "rollback", lambda c: rollbacks.append(True))
        with pytest.raises(IntegrityError):
            repository().enqueue(conn, [job("job_new"), job(), job()] if same_batch else [job("job_new"), job()], "trace_duplicate")
        assert conn.in_transaction() and not conn.closed
        assert commits == rollbacks == []
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM job_execution WHERE job_id='job_new'").scalar_one() == 0
    assert count(queue) == (0 if same_batch else 1)


def test_case_sensitive_job_identity_and_distinct_execution_ids(queue):
    with queue.begin() as conn:
        ids = repository().enqueue(conn, [job("job_A"), job("job_a")], "trace_1")
        assert len(set(ids)) == 2
    assert count(queue) == 2


def test_enqueue_empty_batch_writes_nothing(queue):
    with queue.begin() as conn:
        assert repository().enqueue(conn, [], "trace_1") == []
    assert count(queue) == 0


def test_enqueue_works_under_rt02_transaction_guard(queue):
    ids = run_api_transaction(queue, lambda conn: repository().enqueue(conn, [job()], "trace_guard"))
    assert len(ids) == 1 and count(queue) == 1
    def fail(conn):
        repository().enqueue(conn, [job("job_rollback")], "trace_guard")
        raise ValueError("caller failure")
    with pytest.raises(ValueError, match="caller failure"):
        run_api_transaction(queue, fail)
    assert count(queue) == 1


@pytest.mark.parametrize("changes", [{"job_id": ""}, {"job_id": "가"}, {"job_id": "x" * 192},
                                      {"case_id": None}, {"case_id": "x" * 129}, {"kind": ""}])
def test_invalid_consumed_metadata_is_rejected_before_any_batch_write(queue, changes):
    with queue.begin() as conn:
        with pytest.raises(ValueError):
            repository().enqueue(conn, [job("valid"), job(**changes)], "trace_1")
    assert count(queue) == 0


def test_enqueue_requires_caller_transaction(queue):
    with queue.connect() as conn:
        with pytest.raises(ValueError, match="transaction"):
            repository().enqueue(conn, [job()], "trace_1")
        assert not conn.in_transaction()


@pytest.mark.parametrize("case_id", ["case_1 ", "case_1\t"])
def test_case_valid_ascii_identity_passes_through_existing_case_repository(queue, case_id):
    from daesingo.case.domain import CaseAggregate
    from daesingo.case.jobs import issue_job
    from daesingo.case.store_mysql import MySQLCaseRepository
    from daesingo.common.jobs.read_port import read_executions

    case = CaseAggregate.empty(case_id)
    record = issue_job(case, "COARSE_SEARCH", input_fingerprint="test_fingerprint")
    with queue.begin() as conn:
        MySQLCaseRepository().insert(conn, case)
        execution_ids = repository().enqueue(conn, [record], "trace_case")
        row = conn.execute(select(table())).mappings().one()
        assert row["case_id"] == case_id
        assert read_executions(conn, [record["job_id"]])[0]["execution_id"] == execution_ids[0]
    assert count(queue) == 1
