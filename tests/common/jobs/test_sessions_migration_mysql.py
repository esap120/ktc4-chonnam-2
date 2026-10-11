"""Catch UTC session drift and missing forward receipt migration on real MySQL."""

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect

from daesingo.common.config import DbSettings
from daesingo.common.db import create_api_engine, create_worker_engine, create_migration_engine
from daesingo.common.db.migrate import upgrade_all
from migration_support import ROOT

pytestmark = pytest.mark.mysql


@pytest.mark.parametrize("factory,role,mode", [
    pytest.param(factory, role, mode, marks=pytest.mark.mysql_check(role, "utc_session", parameter=mode))
    for factory, role in [(create_api_engine, "api"), (create_worker_engine, "worker")]
    for mode in ("fresh", "reused", "replacement")
])
def test_utc_now_survives_non_utc_server_and_session_reuse(mysql_schema_url, factory, role, mode):
    engine = factory(DbSettings(url=mysql_schema_url.render_as_string(hide_password=False),
                                pool_size=1, max_overflow=0))
    try:
        with engine.connect() as conn:
            if mode != "fresh":
                conn.exec_driver_sql("SET SESSION time_zone = '+09:00'")
                if mode == "replacement":
                    conn.invalidate()
        with engine.connect() as conn:
            tz, now, utc = conn.exec_driver_sql("SELECT @@session.time_zone, NOW(6), UTC_TIMESTAMP(6)").one()
            assert tz == "+00:00"
            assert now == utc
            assert conn.get_isolation_level() == "READ COMMITTED"
    finally:
        engine.dispose()


@pytest.mark.mysql_check("jobs", "token_migration")
def test_forward_upgrade_preserves_runtime_0001_rows_and_hides_token(mysql_schema_url):
    engine = create_migration_engine(mysql_schema_url)
    try:
        with engine.begin() as conn:
            cfg = Config(str(ROOT / "migrations/runtime/alembic.ini"))
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "runtime_0001")
            assert "claim_token" not in {c["name"] for c in inspect(conn).get_columns("job_execution")}
            conn.exec_driver_sql("""INSERT INTO job_execution
                (execution_id,job_id,status,attempt,queued_at,available_at,produced,trace_id,kind,case_id)
                VALUES ('old_execution','old_job','QUEUED',1,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),
                        '[]','trace','TEST','case')""")
        upgrade_all(mysql_schema_url)
        with engine.connect() as conn:
            col = {c["name"]: c for c in inspect(conn).get_columns("job_execution")}
            assert "claim_token" in col
            assert col["claim_token"]["nullable"]
            assert conn.exec_driver_sql("SELECT claim_token FROM job_execution").scalar_one() is None
            assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "runtime_0002"
            from daesingo.common.jobs.read_port import read_executions
            assert "claim_token" not in read_executions(conn, ["old_job"])[0]
    finally:
        engine.dispose()
