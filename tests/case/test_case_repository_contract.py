"""`CaseRepository` 계약 — 두 구현이 같아야 하는 동작(`decisions/case-store-mysql.md` §5 · §8)."""

from __future__ import annotations

import pytest

from daesingo.case import jobs
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import AppendOnlyViolation, CaseAlreadyExists, CaseNotFound, InvalidCaseId


def _selected_case(case_id: str = "case_repo001") -> CaseAggregate:
    case = CaseAggregate.empty(case_id)
    case.start_search()
    scope = {"scope_id": "s1", "time_ranges": [], "target_event_types": [], "hint": {}, "budget": {}, "contract_version": "x"}
    jobs.issue_coarse_search(case, scope_ref="s1", input_fingerprint="sha1:c", scope=scope)
    case.receive_candidates([Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="o", thumb_ref="fr_1", rank=1)])
    case.select_candidate("cand_a")
    return case


def test_insert_then_load_round_trips(repo_conn):
    repo, conn = repo_conn
    case = _selected_case()
    repo.insert(conn, case)
    assert repo.load(conn, case.case_id) == case


def test_load_returns_a_new_object_each_time(repo_conn):
    """고치고 save하지 않으면 반영되지 않는다 — in-memory도 MySQL과 같게(Review Focus 2)."""
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    loaded = repo.load(conn, "case_repo001", lock="update")
    loaded.user_reviewed = True
    assert repo.load(conn, "case_repo001").user_reviewed is False


def test_save_persists_changes_and_appended_records(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    case = repo.load(conn, "case_repo001", lock="update")
    jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    case.situation_response = {"value": "CONFIRMED", "responded_at": "2026-10-06T10:00:00+09:00", "candidate_ref": {"kind": "candidate_event", "ref": "cand_a"}}
    repo.save(conn, case)
    back = repo.load(conn, "case_repo001")
    assert [r["kind"] for r in back.job_records] == ["COARSE_SEARCH", "PLATE_READ"]
    assert back.situation_response["value"] == "CONFIRMED"


def test_save_refuses_changed_prefix(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    case = repo.load(conn, "case_repo001", lock="update")
    case.job_records[0] = {**case.job_records[0], "job_id": "job_tampered"}
    with pytest.raises(AppendOnlyViolation):
        repo.save(conn, case)


def test_save_refuses_removed_record(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    case = repo.load(conn, "case_repo001", lock="update")
    case.job_records.clear()
    with pytest.raises(AppendOnlyViolation):
        repo.save(conn, case)


def test_load_missing_case_is_key_error(repo_conn):
    repo, conn = repo_conn
    with pytest.raises(CaseNotFound):
        repo.load(conn, "case_missing")
    with pytest.raises(KeyError):  # 기존 `except KeyError` 호출부 호환
        repo.load(conn, "case_missing")


def test_insert_twice_is_refused(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    with pytest.raises(CaseAlreadyExists):
        repo.insert(conn, _selected_case())


def test_case_ids_differ_by_case_only_are_distinct(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, CaseAggregate.empty("case_A"))
    repo.insert(conn, CaseAggregate.empty("case_a"))
    assert repo.load(conn, "case_A").case_id == "case_A"


@pytest.mark.parametrize("bad", ["", "c" * 129, "case_한글"])
def test_invalid_case_id_is_refused_before_insert(repo_conn, bad):
    repo, conn = repo_conn
    with pytest.raises(InvalidCaseId):
        repo.insert(conn, CaseAggregate.empty(bad))


def test_tuple_in_state_round_trips_as_list(repo_conn):
    """MySQL JSON 칼럼처럼 in-memory도 tuple을 list로 돌려준다."""
    repo, conn = repo_conn
    case = _selected_case()
    case.hints = {"vehicle": ("a", "b")}
    repo.insert(conn, case)
    assert repo.load(conn, case.case_id).hints == {"vehicle": ["a", "b"]}
    back = repo.load(conn, case.case_id, lock="update")
    back.hints = {"vehicle": ("c", "d")}
    repo.save(conn, back)
    assert repo.load(conn, case.case_id).hints == {"vehicle": ["c", "d"]}


def test_non_json_value_in_state_is_refused(repo_conn):
    """datetime은 JSON이 아니다 — memory는 TypeError, MySQL은 StatementError(.orig는 TypeError)."""
    from datetime import datetime

    repo, conn = repo_conn
    case = _selected_case()
    case.hints = {"at": datetime(2026, 10, 6)}
    if conn is None:
        with pytest.raises(TypeError):
            repo.insert(conn, case)
    else:
        from sqlalchemy.exc import StatementError

        with pytest.raises(StatementError) as exc:
            repo.insert(conn, case)
        assert isinstance(exc.value.orig, TypeError)
