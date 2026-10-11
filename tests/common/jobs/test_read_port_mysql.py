"""Contract projections are checked against persisted MySQL rows, not stubs."""

from datetime import datetime, timezone
from importlib import import_module
import json

import pytest
from sqlalchemy import event

from daesingo.common.fixtures import CommonFixture
from daesingo.common.job_execution import JobExecution
from daesingo.common.db.migrate import upgrade_all

pytestmark = pytest.mark.mysql


@pytest.fixture
def queue(mysql_schema_url, mysql_engine):
    upgrade_all(mysql_schema_url)
    return mysql_engine


def read(conn, ids):
    return import_module("daesingo.common.jobs.read_port").read_executions(conn, ids)


def enqueue(conn, *ids):
    jobs = [{"job_id": job_id, "case_id": "case_1", "kind": "COARSE_SEARCH"} for job_id in ids]
    return import_module("daesingo.common.jobs.repository").enqueue(conn, jobs, "trace_1")


@pytest.mark.mysql_check("jobs", "read_contract")
def test_read_uncommitted_enqueue_contract_and_does_not_end_caller_transaction(queue):
    with queue.connect() as conn:
        tx = conn.begin()
        ids = enqueue(conn, "job_1")
        boundaries = []
        event.listen(conn, "commit", lambda c: boundaries.append("commit"))
        event.listen(conn, "rollback", lambda c: boundaries.append("rollback"))
        payloads = read(conn, ["job_1"])
        assert len(payloads) == 1
        payload = payloads[0]
        assert set(payload) == set(JobExecution.model_fields)
        assert payload["execution_id"] == ids[0]
        assert payload["status"] == "QUEUED" and payload["attempt"] == 1
        assert payload["produced"] == payload["usage_refs"] == []
        assert all(payload[k] is None for k in ("started_at", "ended_at", "failure_kind"))
        assert datetime.fromisoformat(payload["queued_at"]).utcoffset().total_seconds() == 0
        fixture = CommonFixture.model_validate_json(json.dumps({
            "scenario_id": "scenario_rt03a", "module": "common", "job_executions": payloads,
        }))
        assert fixture.job_executions[0].execution_id == ids[0]
        with queue.connect() as observer:
            assert read(observer, ["job_1"]) == []
        assert conn.in_transaction() and boundaries == []
        tx.rollback()
    with queue.connect() as observer:
        assert read(observer, ["job_1"]) == []


def test_empty_input_issues_no_sql_and_missing_ids_return_empty(queue):
    with queue.connect() as conn:
        statements = []
        event.listen(conn, "before_cursor_execute", lambda *args: statements.append(args[2]))
        assert read(conn, []) == []
        assert statements == [] and not conn.in_transaction()
        assert read(conn, ["missing"]) == []


def test_filter_preserves_case_and_returns_all_attempts_without_selecting_representative(queue):
    from daesingo.common.jobs.schema import job_execution
    with queue.begin() as conn:
        enqueue(conn, "job_A", "job_a", "unrequested")
        conn.execute(job_execution.insert().values(
            execution_id="exec_second", job_id="job_A", status="QUEUED", attempt=2,
            queued_at=datetime(2026, 10, 8), available_at=datetime(2026, 10, 8), produced=[],
            trace_id="trace_1", kind="COARSE_SEARCH", case_id="case_1",
        ))
    with queue.connect() as conn:
        payloads = read(conn, ["job_a", "job_A", "job_A", "missing"])
        assert [(p["job_id"], p["attempt"]) for p in payloads] == [("job_A", 1), ("job_A", 2), ("job_a", 1)]
        assert len(read(conn, ["job_A"])) == 2
        assert len(read(conn, ["job_a"])) == 1
        CommonFixture.model_validate_json(json.dumps({
            "scenario_id": "scenario_rt03a", "module": "common", "job_executions": payloads,
        }))


@pytest.mark.parametrize("status", [
    pytest.param("QUEUED", marks=pytest.mark.mysql_check("jobs", "read_states", parameter="QUEUED")),
    pytest.param("RUNNING", marks=pytest.mark.mysql_check("jobs", "read_states", parameter="RUNNING")),
    pytest.param("SUCCEEDED", marks=pytest.mark.mysql_check("jobs", "read_states", parameter="SUCCEEDED")),
    pytest.param("FAILED", marks=pytest.mark.mysql_check("jobs", "read_states", parameter="FAILED")),
    pytest.param("STALE", marks=pytest.mark.mysql_check("jobs", "read_states", parameter="STALE")),
    pytest.param("CANCELLED", marks=pytest.mark.mysql_check("jobs", "read_states", parameter="CANCELLED")),
])
@pytest.mark.mysql_check("jobs", "read_states")
def test_each_contract_state_roundtrips_json_nulls_timestamps_and_hides_private_columns(queue, status):
    from daesingo.common.jobs.schema import job_execution
    queued = datetime(2026, 10, 8, 1, 2, 3, 123456)
    started = queued if status in {"RUNNING", "SUCCEEDED", "STALE", "CANCELLED"} else None
    ended = queued if status in {"SUCCEEDED", "FAILED", "CANCELLED"} else None
    produced = [{"kind": "analysis_run", "ref": "run_1"}] if status in {"SUCCEEDED", "CANCELLED"} else []
    with queue.begin() as conn:
        conn.execute(job_execution.insert().values(
            execution_id="exec_1", job_id="job_1", status=status, attempt=1, queued_at=queued,
            started_at=started, ended_at=ended, produced=produced,
            failure_kind="RUNTIME_TEST" if status == "FAILED" else None,
            available_at=queued, lease_owner="private_owner", lease_expires_at=queued,
            heartbeat_at=queued, cancel_requested_at=queued, case_applied_at=queued,
            trace_id="private_trace", kind="PRIVATE_KIND", case_id="private_case",
        ))
    with queue.connect() as conn:
        payload = read(conn, ["job_1"])[0]
        assert set(payload) == set(JobExecution.model_fields)
        parsed = JobExecution.model_validate_json(json.dumps(payload))
        assert parsed.status == status and parsed.produced == [
            import_module("daesingo.common.job_execution").RuntimeContractRef(**p) for p in produced]
        assert parsed.queued_at == queued.replace(tzinfo=timezone.utc)
        assert parsed.ended_at == (ended.replace(tzinfo=timezone.utc) if ended else None)
        assert parsed.started_at == (started.replace(tzinfo=timezone.utc) if started else None)
        assert parsed.usage_refs == []
        assert "private" not in json.dumps(payload)


def test_enqueue_uses_db_utc_clock_even_in_non_utc_session(queue):
    with queue.begin() as conn:
        conn.exec_driver_sql("SET SESSION time_zone = '+09:00'")
        try:
            before = conn.exec_driver_sql("SELECT UTC_TIMESTAMP(6)").scalar_one()
            enqueue(conn, "job_1")
            after = conn.exec_driver_sql("SELECT UTC_TIMESTAMP(6)").scalar_one()
            payload = read(conn, ["job_1"])[0]
            stored = datetime.fromisoformat(payload["queued_at"]).replace(tzinfo=None)
            assert before <= stored <= after
        finally:
            conn.exec_driver_sql("SET SESSION time_zone = '+00:00'")
