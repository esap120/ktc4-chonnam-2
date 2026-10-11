"""Consume Case's existing migration/repository without changing its fixtures."""

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest

from daesingo.case.domain import CaseAggregate
from daesingo.case.store_mysql import MySQLCaseRepository
from daesingo.common.db.transactions import run_api_transaction, run_worker_transaction

pytestmark = [pytest.mark.mysql, pytest.mark.mysql_scenario("case_compatibility")]


@pytest.mark.mysql_check("case", "case_compatibility")
def test_common_factory_connection_participates_in_existing_case_repository(mysql_engine, mysql_schema_url, monkeypatch):
    # This invokes only the existing Case migration on our isolated test schema.
    monkeypatch.setenv("DAESINGO_MYSQL_URL", mysql_schema_url.render_as_string(hide_password=False))
    cfg = Config(str(Path(__file__).resolve().parents[4] / "migrations/case/alembic.ini"))
    with mysql_engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    repo = MySQLCaseRepository()
    run_api_transaction(mysql_engine, lambda conn: repo.insert(conn, CaseAggregate.empty("case_common001")))

    def update(conn):
        assert conn.exec_driver_sql("SELECT @@transaction_isolation").scalar_one() == "READ-COMMITTED"
        case = repo.load(conn, "case_common001", lock="update")
        case.start_search()
        repo.save(conn, case)
        return case.stage

    assert run_worker_transaction(mysql_engine, update) == "SEARCHING"
    with mysql_engine.connect() as observer:
        assert repo.load(observer, "case_common001").stage == "SEARCHING"

    def fail(conn):
        repo.insert(conn, CaseAggregate.empty("case_common_rollback"))
        raise ValueError("domain failure")

    with pytest.raises(ValueError):
        run_api_transaction(mysql_engine, fail)
    with mysql_engine.connect() as observer:
        assert observer.exec_driver_sql("SELECT COUNT(*) FROM cases WHERE case_id='case_common_rollback'").scalar_one() == 0
