"""case가 계산하는 `running_jobs[]` — 계약 B§10 불변조건 5, `decisions/running-jobs-derivation.md`."""

import pytest

from daesingo.case import jobs
from daesingo.case.domain import CaseAggregate
from daesingo.case.view import build_case_view, derive_running_jobs


def _case() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_rj", hints={}, manifest_summary={})
    case.start_search()
    return case


def _exec(job_id: str, attempt: int, status: str) -> dict:
    return {"job_id": job_id, "attempt": attempt, "status": status}


def test_job_without_execution_is_pending():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert derive_running_jobs(case) == [
        {"job_id": job["job_id"], "kind": "PLATE_READ", "label_key": "job.plate_read", "status": "PENDING"}
    ]


def test_queued_execution_is_pending():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert derive_running_jobs(case, [_exec(job["job_id"], 1, "QUEUED")])[0]["status"] == "PENDING"


@pytest.mark.parametrize("status", ["RUNNING", "SUCCEEDED", "FAILED", "STALE", "CANCELLED"])
def test_reported_execution_before_settlement_is_running(status):
    # terminal 기록과 case 반영 사이 · retry backoff 동안에도 빠지지 않는다(불변조건 5).
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert derive_running_jobs(case, [_exec(job["job_id"], 1, status)])[0]["status"] == "RUNNING"


def test_representative_execution_is_max_attempt():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    executions = [_exec(job["job_id"], 2, "QUEUED"), _exec(job["job_id"], 1, "STALE")]
    assert derive_running_jobs(case, executions)[0]["status"] == "PENDING"


def test_settled_job_is_dropped_even_if_execution_running():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    case.settle_job(job["job_id"], "CANCELLED")
    assert derive_running_jobs(case, [_exec(job["job_id"], 1, "RUNNING")]) == []


@pytest.mark.parametrize(
    ("issue", "label_key"),
    [
        (lambda c: jobs.issue_coarse_search(c, scope_ref="s", input_fingerprint="f"), "job.generic_processing"),
        (lambda c: jobs.issue_overlay_time_read(c, input_fingerprint="f"), "job.overlay_time_read"),
        (lambda c: jobs.issue_fine_verify(c, input_fingerprint="f"), "job.fine_verify"),
        (lambda c: jobs.issue_report_video_export(c, input_fingerprint="f"), "job.report_video_export"),
        (lambda c: jobs.issue_job(c, "PLATE_IMAGE_EXPORT", input_fingerprint="f"), "job.plate_image_export"),
    ],
)
def test_label_key_by_kind(issue, label_key):
    case = _case()
    issue(case)
    assert derive_running_jobs(case)[0]["label_key"] == label_key


def test_case_view_carries_derived_running_jobs():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f")
    view = build_case_view(case, job_executions=[_exec(job["job_id"], 1, "RUNNING")])
    assert view["running_jobs"] == [
        {"job_id": job["job_id"], "kind": "COARSE_SEARCH", "label_key": "job.generic_processing", "status": "RUNNING"}
    ]


def test_hint_extract_label_key():
    # `HINT_EXTRACT` kind 등재는 PR #286(v1.7)이 한다 — 여기서는 기록된 JobRecord의 label만 본다.
    case = _case()
    case.record_job({"job_id": "job_hint", "kind": "HINT_EXTRACT", "scope_ref": None})
    assert derive_running_jobs(case)[0]["label_key"] == "job.hint_extract"
