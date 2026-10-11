"""`web → case.get_view() → CaseView`(module-architecture.md §5-1 ⑪)의 실제 진입점 검증.

지금까지 `build_case_view()`/`build_view_from_adapter()`는 이미 만들어진 `case`
객체와 `adapter`를 손에 쥐고 있어야만 쓸 수 있었다 — web이 실제로 가진 건 `case_id`
문자열 하나뿐이다. 이 파일은 그 간극(`CaseStore` + `case.get_view(case_id)`)이
메워졌는지 확인한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from daesingo import case as case_package
from daesingo.case import jobs, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.case.store import CaseStore

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "happy_001"


def test_get_view_is_exported_from_case_package():
    """`case.get_view(case_id)`로 부를 수 있어야 한다 — module-architecture.md가 적은
    형태 그대로."""
    assert case_package.get_view is service.get_view
    assert case_package.CaseStore is CaseStore


def test_get_view_unknown_case_id_fails_clearly():
    store = CaseStore()
    with pytest.raises(KeyError, match="unknown_case"):
        service.get_view("unknown_case", store=store)


def test_get_view_rejects_duplicate_registration():
    store = CaseStore()
    case = CaseAggregate.intake(case_id="dup_case", hints={}, manifest_summary={})
    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    store.register(case, adapter)
    with pytest.raises(ValueError, match="dup_case"):
        store.register(case, adapter)


def test_get_view_with_mock_adapter_matches_smoke_fixture():
    """Mock 경로로도 get_view(case_id)가 CaseView를 조립하는지 확인한다 — real만
    되고 mock이 깨지면 회귀다."""
    store = CaseStore()
    case = CaseAggregate.intake(case_id="case_h001_getview_mock", hints={}, manifest_summary={})
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")

    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    store.register(case, adapter)

    case = store.load_for_update("case_h001_getview_mock")  # 등록 뒤 변경은 복사본을 받아 고친 뒤 save
    candidates = service.receive_search_candidates(case, adapter)
    case.select_candidate(candidates[0].candidate_id)
    jobs.issue_plate_read(case, input_fingerprint="sha1:h001-plate-read-clip_h001")
    jobs.issue_overlay_time_read(case, input_fingerprint="sha1:h001-overlay-read-clip_h001")
    jobs.issue_fine_verify(case, input_fingerprint="sha1:h001-fine-verify-as_h001_fine")
    jobs.issue_report_video_export(case, input_fingerprint="sha1:h001-report-video-export")
    assert service.mark_ready_if_package_ready(case, adapter) is True
    store.save(case)

    view = service.get_view("case_h001_getview_mock", store=store)
    assert view["stage"] == "READY"
    assert view["case_id"] == "case_h001_getview_mock"


def test_get_view_with_real_adapter_reaches_ready_caseview():
    """W6 데모의 실제 형태 — web이 가진 건 case_id 하나뿐이라고 가정하고
    `case.get_view(case_id)` 한 줄로 CaseView를 받는다."""
    mock = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    scope = mock.get_analysis_scopes()[0]

    store = CaseStore()
    case = CaseAggregate.intake(case_id="case_h001_getview_real", hints={}, manifest_summary={})
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")

    real = RealAdapter(case_id="case_h001_getview_real", case=case, search_scope=scope, mock_root=MOCK_ROOT)
    store.register(case, real)

    case = store.load_for_update("case_h001_getview_real")  # 등록 뒤 변경은 복사본을 받아 고친 뒤 save
    store.get_adapter(case.case_id, case)  # real adapter에 방금 로드한 aggregate를 붙인다
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)
    jobs.issue_plate_read(case, input_fingerprint="sha1:h001-plate-read-clip_h001")
    jobs.issue_overlay_time_read(case, input_fingerprint="sha1:h001-overlay-read-clip_h001")
    jobs.issue_fine_verify(case, input_fingerprint="sha1:h001-fine-verify-as_h001_fine")
    jobs.issue_report_video_export(case, input_fingerprint="sha1:h001-report-video-export")
    service.mark_ready_if_package_ready(case, real)
    store.save(case)

    view = case_package.get_view("case_h001_getview_real", store=store)

    # READY는 Package가 실제로 준비됐을 때만(#167). 상황 응답 전이라 ADR-EVIDENCE-005 D2-c로
    # Package가 막혀 EVIDENCE_REVIEW에 머문다.
    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["package"] is None
    assert view["evidence"]["plate_display"]["value"] == "12가3456"
