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


def _searching_case(case_id: str) -> CaseAggregate:
    case = CaseAggregate.empty(case_id)
    case.start_search()
    return case


def _append_job(repo, conn, case_id: str, tag: str) -> CaseAggregate:
    """command 하나 — 잠그고 읽고 JobRecord 하나 · `hints`를 바꿔 저장한다. commit은 호출자."""
    from daesingo.case import jobs

    case = repo.load(conn, case_id, lock="update")
    jobs.issue_coarse_search(case, scope_ref=f"scope_{tag}", input_fingerprint=f"sha1:{tag}")
    case.hints = {"time": tag}
    repo.save(conn, case)
    return case


def _job_count(engine, case_id: str) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(
            "SELECT COUNT(*) FROM job_records WHERE case_id = %s", (case_id,)
        ).scalar_one()


def test_waiting_writer_sees_first_writers_commit_under_read_committed(mysql_engine):
    """줄을 선 두 번째 command는 앞 command가 commit한 레코드까지 읽고 그 뒤에 붙인다(store_mysql docstring
    「격리 요건」). 대기만 보는 `test_update_lock_makes_second_writer_wait`의 다음 단계다."""
    import threading
    import time

    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.begin() as conn:
        repo.insert(conn, _searching_case("case_rc_queue001"))

    b_thread_id: list[int] = []
    b_seen: list[int] = []
    b_error: list[BaseException] = []

    def second_writer() -> None:
        try:
            with mysql_engine.connect() as b:
                b = b.execution_options(isolation_level="READ COMMITTED")
                with b.begin():
                    b_thread_id.append(b.exec_driver_sql("SELECT CONNECTION_ID()").scalar_one())
                    case = _append_job(repo, b, "case_rc_queue001", "b")
                    b_seen.append(len(case.job_records))
        except BaseException as exc:  # 스레드 예외는 본 스레드에서 다시 던진다
            b_error.append(exc)

    with mysql_engine.connect() as a:
        a = a.execution_options(isolation_level="READ COMMITTED")
        ta = a.begin()
        _append_job(repo, a, "case_rc_queue001", "a")
        worker = threading.Thread(target=second_writer)
        worker.start()
        deadline = time.monotonic() + 5
        while True:  # B가 `cases` 행 잠금을 기다리기 시작할 때까지
            assert not b_error, b_error
            waiting = b_thread_id and a.exec_driver_sql(
                "SELECT COUNT(*) FROM information_schema.INNODB_TRX "
                "WHERE trx_mysql_thread_id = %s AND trx_state = 'LOCK WAIT'", (b_thread_id[0],)
            ).scalar_one()
            if waiting:
                break
            assert time.monotonic() < deadline, "두 번째 writer가 잠금 대기에 들어가지 않았다"
            time.sleep(0.05)
        ta.commit()
    worker.join(timeout=10)
    assert not worker.is_alive()
    if b_error:
        raise b_error[0]

    assert b_seen == [2]  # A의 레코드 1개 + B가 붙인 1개
    with mysql_engine.connect() as conn:
        final = repo.load(conn, "case_rc_queue001")
        seqs = [r[0] for r in conn.exec_driver_sql(
            "SELECT seq FROM job_records WHERE case_id = 'case_rc_queue001' ORDER BY seq")]
    assert final.hints == {"time": "b"}
    assert seqs == [0, 1]


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "READ COMMITTED"])
def test_plain_read_before_lock_pins_stale_records_only_under_repeatable_read(mysql_engine, isolation):
    """`load(lock="update")` 전에 일반 SELECT가 있으면 RR은 그때의 snapshot으로 레코드를 읽는다 — `cases` 행은
    최신, 레코드는 낡은 상태가 섞이고 `save()`가 `UNIQUE(case_id, seq)`에 걸린다. RC는 최신을 읽는다
    (store_mysql docstring 「격리 요건」)."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    case_id = "case_rr001" if isolation == "REPEATABLE READ" else "case_rc001"
    with mysql_engine.begin() as conn:
        repo.insert(conn, _searching_case(case_id))

    with mysql_engine.connect() as b:
        b = b.execution_options(isolation_level=isolation)
        tb = b.begin()
        b.exec_driver_sql("SELECT COUNT(*) FROM job_records").scalar_one()  # 첫 일관 읽기 — RR은 여기서 snapshot 고정

        with mysql_engine.begin() as a:  # 그사이 다른 command가 commit한다
            _append_job(repo, a, case_id, "a")
        assert _job_count(mysql_engine, case_id) == 1

        case = repo.load(b, case_id, lock="update")
        assert case.hints == {"time": "a"}  # `cases` 행은 잠금 읽기라 둘 다 최신이다
        if isolation == "REPEATABLE READ":
            assert case.job_records == []  # 레코드는 고정된 옛 snapshot
            from daesingo.case import jobs

            jobs.issue_coarse_search(case, scope_ref="scope_b", input_fingerprint="sha1:b")
            with pytest.raises(sa.exc.IntegrityError, match="uq_job_records_case_seq"):
                repo.save(b, case)  # 옛 길이로 seq=0을 매겨 A의 행과 충돌
            tb.rollback()
            assert _job_count(mysql_engine, case_id) == 1
        else:
            assert len(case.job_records) == 1
            from daesingo.case import jobs

            jobs.issue_coarse_search(case, scope_ref="scope_b", input_fingerprint="sha1:b")
            repo.save(b, case)
            tb.commit()
            assert _job_count(mysql_engine, case_id) == 2
