"""case 저장소 계약 테스트용 fixture — 같은 테스트를 in-memory와 MySQL 두 구현에 돌린다.

MySQL은 `DAESINGO_MYSQL_URL`(예: `mysql+pymysql://root:pw@127.0.0.1:3306/daesingo_test`)이 있을 때만 돈다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from daesingo.case.store import InMemoryCaseRepository


@pytest.fixture(params=["memory", "mysql"])
def repo_conn(request):
    if request.param == "memory":
        yield InMemoryCaseRepository(), None
        return
    url = os.environ.get("DAESINGO_MYSQL_URL")
    if not url:
        pytest.skip("DAESINGO_MYSQL_URL 미지정 — MySQL 통합 테스트는 opt-in")
    engine = request.getfixturevalue("mysql_engine")
    from daesingo.case.store_mysql import MySQLCaseRepository

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            yield MySQLCaseRepository(), conn
        finally:
            trans.rollback()


@pytest.fixture(scope="session")
def mysql_engine():
    url = os.environ.get("DAESINGO_MYSQL_URL")
    if not url:
        pytest.skip("DAESINGO_MYSQL_URL 미지정 — MySQL 통합 테스트는 opt-in")
    sa = pytest.importorskip("sqlalchemy")
    from alembic import command
    from alembic.config import Config

    engine = sa.create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:  # 깨끗한 schema에서 시작한다 — 테스트 전용 DB만 가리켜야 한다
        for table in ("analysis_scopes", "correction_records", "job_records", "cases", "case_alembic_version"):
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
    cfg = Config(str(Path(__file__).resolve().parents[2] / "migrations" / "case" / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()
