"""CaseView 최상위 `description`(`case-view/v1.7`, 이슈 #259) · `HINT_EXTRACT` kind 등재."""

from daesingo.case import jobs
from daesingo.case.domain import CaseAggregate
from daesingo.case.view import build_case_view


def test_description_is_null_before_analysis_start():
    # 분석 시작(`START_ANALYSIS`) 전에는 원문이 없다 — 키는 늘 있고 값은 null.
    view = build_case_view(CaseAggregate.intake(case_id="case_desc", hints={}, manifest_summary={}))
    assert "description" in view
    assert view["description"] is None


def test_description_is_projected_from_case():
    case = CaseAggregate.intake(case_id="case_desc2", hints={}, manifest_summary={})
    case.description = "  "
    assert build_case_view(case)["description"] == "  "


def test_hint_extract_is_a_registered_job_kind():
    case = CaseAggregate.intake(case_id="case_hint", hints={}, manifest_summary={})
    case.start_search()
    record = jobs.issue_job(case, "HINT_EXTRACT", input_fingerprint="sha1:hint")
    assert record["kind"] == "HINT_EXTRACT"
