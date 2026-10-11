"""MySQL 전용 — `DAESINGO_MYSQL_URL`이 있을 때만 돈다(`decisions/case-store-mysql.md` §8)."""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")


def test_migration_creates_case_tables_with_ascii_bin_ids(mysql_engine):
    with mysql_engine.connect() as conn:
        tables = {r[0] for r in conn.exec_driver_sql("SHOW TABLES")}
        assert {"cases", "job_records", "correction_records", "analysis_scopes", "case_alembic_version"} <= tables
        coll = conn.exec_driver_sql(
            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cases' AND COLUMN_NAME = 'case_id'"
        ).scalar_one()
        assert coll == "ascii_bin"


from daesingo.case.domain import CaseAggregate  # noqa: E402


def test_rollback_leaves_nothing(mysql_engine):
    """command 하나 = case 저장이 한 commit — 실패하면 남지 않는다(runtime-tech-spec §16 item 9의 case 쪽)."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.connect() as conn:
        trans = conn.begin()
        repo.insert(conn, CaseAggregate.empty("case_rb001"))
        trans.rollback()
    with mysql_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM cases WHERE case_id = 'case_rb001'").scalar_one() == 0


def test_update_lock_makes_second_writer_wait(mysql_engine):
    """같은 case 동시 쓰기는 줄을 선다(Review Focus 3)."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.begin() as conn:
        repo.insert(conn, CaseAggregate.empty("case_lock001"))
    with mysql_engine.connect() as a, mysql_engine.connect() as b:
        ta = a.begin()
        repo.load(a, "case_lock001", lock="update")
        tb = b.begin()
        b.exec_driver_sql("SET SESSION innodb_lock_wait_timeout = 1")
        with pytest.raises(sa.exc.OperationalError) as err:
            repo.load(b, "case_lock001", lock="update")
        assert "1205" in str(err.value)  # Lock wait timeout exceeded
        tb.rollback()
        ta.rollback()
    with mysql_engine.begin() as conn:
        for table in ("analysis_scopes", "correction_records", "job_records"):
            conn.exec_driver_sql(f"DELETE FROM {table} WHERE case_id = 'case_lock001'")
        conn.exec_driver_sql("DELETE FROM cases WHERE case_id = 'case_lock001'")


def test_repository_never_commits(mysql_engine):
    """저장소는 commit하지 않는다 — 호출자가 rollback하면 save도 사라진다."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.begin() as conn:
        repo.insert(conn, CaseAggregate.empty("case_nc001"))
    with mysql_engine.connect() as conn:
        trans = conn.begin()
        case = repo.load(conn, "case_nc001", lock="update")
        case.start_search()
        repo.save(conn, case)
        trans.rollback()
    with mysql_engine.connect() as conn:
        assert repo.load(conn, "case_nc001").stage == "INTAKE"


def test_append_only_violation_writes_nothing_even_if_caller_commits(mysql_engine):
    """append-only 검사는 어떤 쓰기보다 먼저 한다 — 호출자가 예외를 삼키고 commit해도 `cases` 행이
    반쪽만 바뀌지 않는다(#282 Runtime 리뷰)."""
    from daesingo.case import jobs
    from daesingo.case.store import AppendOnlyViolation
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    case = CaseAggregate.empty("case_ao001")
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_ao", input_fingerprint="sha1:ao")
    with mysql_engine.begin() as conn:
        repo.insert(conn, case)
    with mysql_engine.connect() as conn:
        trans = conn.begin()
        loaded = repo.load(conn, "case_ao001", lock="update")
        loaded.job_records[0]["job_id"] = "job_tampered"  # 저장된 앞부분을 바꾼다
        loaded.hints = {"time": "바뀐 값"}
        with pytest.raises(AppendOnlyViolation):
            repo.save(conn, loaded)
        trans.commit()  # 잘못된 호출자 — 예외를 삼키고 commit
    with mysql_engine.connect() as conn:
        assert repo.load(conn, "case_ao001").hints == case.hints
