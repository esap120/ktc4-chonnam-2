"""overlay 판독 결과 notice 3종 — readout `failure-taxonomy.md` 「`CaseView.notices[].code` 매핑」(#31 A-1).

overlay 판독이 정상 종료했지만 시각을 얻지 못한 갈래는 실행 실패가 아니라 notice로만 알린다.
`observation.reason.code`와 notice code는 1:1이고(점 → 밑줄), 셋을 합치지 않는다 — 「화면에 시각이
없다」(사실)와 「확인하지 못했다」(모름)는 다른 말이다(`core-user-flow.md` §5).

근거는 현재 선택 후보의 **가장 나중** overlay 판독이다(CaseView 계약 A§10-7 — 재판독 뒤에는 이전
판독의 notice를 남기지 않는다). evidence가 없어도 붙는다(`scenario_infra_failure_001` rev1~3).
예전엔 case가 overlay 판독을 받지 않아 real 경로에서 한 번도 뜨지 않았고, mock 테스트는 fixture의
notice를 그대로 넘겨 가려져 있었다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from daesingo.case import jobs, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.view import build_case_view

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
OVERLAY_CODES = {
    "readout.overlay_not_present",
    "readout.overlay_presence_undetermined",
    "readout.overlay_ocr_failed",
}


def _readout(candidate_id: str, status: str, reason_code: str | None) -> dict[str, Any]:
    return {
        "readout_id": f"ro_{candidate_id}_{reason_code}",
        "candidate_id": candidate_id,
        "observation": {"status": status, "value": None, "reason": None if reason_code is None else {"code": reason_code}},
    }


class _Adapter:
    """`fetch_case_view_inputs()`가 읽는 getter만 가진 스냅샷 — evidence 조립 전."""

    def __init__(self, overlay_time_readouts: list[dict[str, Any]]) -> None:
        self._overlay = overlay_time_readouts

    def get_evidence_record(self) -> dict[str, Any] | None:
        return None

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None:
        return None

    def get_report_package(self) -> dict[str, Any] | None:
        return None

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        return []

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        return self._overlay

    def get_plate_read_status(self) -> str | None:
        return None

    def get_evidence_needs(self) -> list[dict[str, Any]]:
        return []

    def get_visual_evidence_decision(self) -> str | None:
        return None

    def get_independent_facts(self) -> dict | None:
        return None


def _case_with_selection(candidate_id: str = "cand_1") -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_overlay", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates(
        [Candidate(candidate_id=candidate_id, at=None, at_provenance=None, observed="후보", thumb_ref="fr_t", rank=1)]
    )
    case.select_candidate(candidate_id)
    return case


def _overlay_codes(view: dict[str, Any]) -> list[str]:
    return [n["code"] for n in view["notices"] if n["code"] in OVERLAY_CODES]


@pytest.mark.parametrize(
    ("status", "reason_code", "notice_code"),
    [
        ("NOT_APPLICABLE", "readout.overlay.not_present", "readout.overlay_not_present"),
        ("UNKNOWN", "readout.overlay.presence_undetermined", "readout.overlay_presence_undetermined"),
        ("UNKNOWN", "readout.overlay.ocr_failed", "readout.overlay_ocr_failed"),
    ],
)
def test_reason_code_maps_one_to_one(status, reason_code, notice_code):
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter([_readout("cand_1", status, reason_code)]))

    assert view["evidence"] is None  # evidence 조립 전에도 붙는다
    notice = next(n for n in view["notices"] if n["code"] == notice_code)
    assert notice == {
        "code": notice_code,
        "severity": "INFO",
        "blocking": False,
        "message_key": "notice." + notice_code.removeprefix("readout."),
        "actions": [],
    }
    assert _overlay_codes(view) == [notice_code]


def test_read_overlay_has_no_notice():
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter([_readout("cand_1", "OK", None)]))
    assert _overlay_codes(view) == []


def test_latest_readout_of_selected_candidate_wins():
    """재판독 뒤에는 이전 판독의 notice를 남기지 않는다(A§10-7 — infra_failure rev3→rev4)."""
    readouts = [
        _readout("cand_1", "UNKNOWN", "readout.overlay.presence_undetermined"),
        _readout("cand_1", "UNKNOWN", "readout.overlay.ocr_failed"),
    ]
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter(readouts))
    assert _overlay_codes(view) == ["readout.overlay_ocr_failed"]


def test_other_candidate_readout_is_ignored():
    """다른 후보를 보던 때의 판독은 지금 화면의 notice가 아니다."""
    readouts = [_readout("cand_other", "NOT_APPLICABLE", "readout.overlay.not_present")]
    view = service.build_view_from_adapter(_case_with_selection("cand_1"), _Adapter(readouts))
    assert _overlay_codes(view) == []


def test_unregistered_reason_code_gets_no_notice():
    """readout이 notice로 매핑하지 않은 reason은 case가 지어내지 않는다."""
    view = service.build_view_from_adapter(
        _case_with_selection(), _Adapter([_readout("cand_1", "UNKNOWN", "readout.overlay.something_new")])
    )
    assert _overlay_codes(view) == []


@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [
        ("correction_rerun_001", ["readout.overlay_not_present"]),
        ("unknown_abstain_partial_001", ["readout.overlay_not_present"]),
        ("infra_failure_001", ["readout.overlay_ocr_failed"]),  # 최종 상태(재판독 뒤)
        ("happy_001", []),
    ],
)
def test_mock_adapter_matches_fixture_final_notice(scenario_id, expected):
    """mock fixture의 판독 목록만으로 마지막 CaseView revision의 overlay notice가 나온다. infra_failure는
    evidence 모듈이 의도적으로 없어 adapter 전체 조립 대신 판독 목록만 넘긴다."""
    adapter = MockFixtureAdapter(MOCK_ROOT, scenario_id)
    case = _case_with_selection(adapter.get_overlay_time_readouts()[0]["candidate_id"])

    view = service.derive_notices(build_case_view(case), overlay_time_readouts=adapter.get_overlay_time_readouts())

    assert _overlay_codes(view) == expected


def test_real_adapter_exposes_overlay_readout():
    """실제 readout 경로 — 조립에 쓴 `OverlayTimeReadout`을 case가 받는다."""
    scope = MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_overlay_real", hints={}, manifest_summary={})
    real = RealAdapter(case_id="case_overlay_real", case=case, search_scope=scope, mock_root=MOCK_ROOT)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:overlay-real-coarse")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    readouts = real.get_overlay_time_readouts()

    assert len(readouts) == 1
    assert readouts[0]["candidate_id"] == candidates[0].candidate_id
    assert "observation" in readouts[0]
