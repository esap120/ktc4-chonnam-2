"""CaseView `package.report` — 최종 신고문(제목 · 본문)을 `ReportPackage.report`에서 그대로 옮긴다
(`case-view/v1.7`, 이슈 #274). case는 문장을 만들거나 고치지 않고, `template_ref`는 내리지 않는다."""

from pathlib import Path

import pytest

from daesingo.case.adapters import MockFixtureAdapter
from daesingo.case.view import _build_package_view

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"


@pytest.mark.parametrize("scenario_id", ["happy_001", "unknown_abstain_partial_001"])
def test_package_carries_report_title_and_description_verbatim(scenario_id):
    adapter = MockFixtureAdapter(MOCK_ROOT, scenario_id)
    report_package = adapter.get_report_package()

    package = _build_package_view(report_package, adapter.get_evidence_record())

    assert package["report"] == {
        "title": report_package["report"]["title"],
        "description": report_package["report"]["description"],
    }


def test_package_report_does_not_expose_template_ref():
    adapter = MockFixtureAdapter(MOCK_ROOT, "happy_001")
    assert "template_ref" in adapter.get_report_package()["report"]  # 전제 확인

    package = _build_package_view(adapter.get_report_package(), adapter.get_evidence_record())

    assert "template_ref" not in package["report"]


def test_no_package_before_report_package():
    adapter = MockFixtureAdapter(MOCK_ROOT, "happy_001")
    assert _build_package_view(None, adapter.get_evidence_record()) is None
