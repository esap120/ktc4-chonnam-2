"""JobRecord 정산 기록 — `decisions/running-jobs-derivation.md`."""

import pytest

from daesingo.case import jobs
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import CaseStore


def _case() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_settle", hints={}, manifest_summary={})
    case.start_search()
    return case


def _candidate(cid: str) -> Candidate:
    return Candidate(candidate_id=cid, at=None, at_provenance=None, observed="", thumb_ref=None, rank=1)


def test_new_job_is_waiting():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    assert case.waiting_job_records() == [job]


def test_settled_job_is_not_waiting():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    assert case.settle_job(job["job_id"], "CANCELLED") is True
    assert case.waiting_job_records() == []
    assert case.settled_jobs == {job["job_id"]: "CANCELLED"}


def test_first_reason_wins():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.settle_job(job["job_id"], "STOPPED_WAITING")
    assert case.settle_job(job["job_id"], "REFLECTED") is False
    assert case.settled_jobs[job["job_id"]] == "STOPPED_WAITING"


def test_settle_does_not_bump_case_rev():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    rev = case.case_rev
    case.settle_job(job["job_id"], "REFLECTED")
    assert case.case_rev == rev


def test_unknown_reason_is_rejected():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    with pytest.raises(ValueError):
        case.settle_job(job["job_id"], "DONE")


def test_unknown_job_id_is_rejected():
    with pytest.raises(ValueError):
        _case().settle_job("job_missing", "REFLECTED")


def test_reissue_same_kind_and_scope_supersedes_previous():
    case = _case()
    old = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    new = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    assert case.settled_jobs == {old["job_id"]: "SUPERSEDED"}
    assert case.waiting_job_records() == [new]


def test_different_scope_or_kind_does_not_supersede():
    case = _case()
    a = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    b = jobs.issue_coarse_search(case, scope_ref="scope_b", input_fingerprint="sha1:b")
    c = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert case.waiting_job_records() == [a, b, c]


def test_receiving_candidates_reflects_coarse_search():
    case = _case()
    search = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.receive_candidates([_candidate("cand_a")])
    assert case.settled_jobs == {search["job_id"]: "REFLECTED"}


def test_search_failure_reflects_coarse_search():
    case = _case()
    search = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.record_candidate_search_failure()
    assert case.settled_jobs == {search["job_id"]: "REFLECTED"}


def test_settled_jobs_survive_store_round_trip():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.settle_job(job["job_id"], "CANCELLED")
    store = CaseStore()
    store.register(case)
    assert store.get_case(case.case_id).settled_jobs == {job["job_id"]: "CANCELLED"}
