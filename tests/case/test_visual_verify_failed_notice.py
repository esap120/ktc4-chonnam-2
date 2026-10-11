"""Fine(`FINE_VERIFY`) **실행 실패**를 notice로 알린다 — 고도화 문서 8-14, #244 R-1 후속.

Runtime 자동 재시도가 `STALE`에만 붙으면(#244 R-1) Fine `FAILED`는 terminal이다. 지금은 진행 상태에
Fine step이 없고 notice도 없어, `EVIDENCE_REVIEW` + `evidence=null`이 「조립 전」과 같아 보여 web이
진행 화면에서 끝나지 않는다. 음성 결과(`evidence.visual_event_not_observed`)와 같은 방식으로 받는다.

Fine 실행 상태는 JobExecution 값이라 adapter가 아니라 호출자가 넘긴다(`running_jobs`와 같다) —
worker 경로에서는 `representative_execution_status(..., "FINE_VERIFY")`가 만든다.
"""
from __future__ import annotations

from typing import Any

import pytest

from daesingo.case import service
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import CaseStore

CODE = "search.visual_verify_failed"


class _Adapter:
    """`fetch_case_view_inputs()`가 읽는 getter만 가진 스냅샷 — Fine이 실패해 downstream 값이 없다."""

    def get_evidence_record(self) -> dict[str, Any] | None:
        return None

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None:
        return None

    def get_report_package(self) -> dict[str, Any] | None:
        return None

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        return []

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        return []

    def get_plate_read_status(self) -> str | None:
        return None

    def get_evidence_needs(self) -> list[dict[str, Any]]:
        return []

    def get_visual_evidence_decision(self) -> str | None:
        return None

    def get_independent_facts(self) -> dict | None:
        return None


def _case_with_selection() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_fine_failed", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates(
        [Candidate(candidate_id="cand_1", at=None, at_provenance=None, observed="후보", thumb_ref="fr_thumb", rank=1)]
    )
    case.select_candidate("cand_1")
    return case


def _codes(view: dict[str, Any]) -> list[str]:
    return [n["code"] for n in view["notices"]]


def test_notice_shape_matches_contract():
    assert service.VISUAL_VERIFY_FAILED_NOTICE == {
        "code": CODE,
        "severity": "ERROR",
        "blocking": True,
        "message_key": "notice.visual_verify_failed",
        "actions": [],
    }


@pytest.mark.parametrize("status", ["FAILED", "STALE"])
def test_failed_fine_gets_notice(status):
    """대표 execution이 `STALE`인 것도 재시도가 끝난 실패다(B§13 `STALE→FAILED`)."""
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter(), visual_verify_status=status)

    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["evidence"] is None
    assert _codes(view) == [CODE]


@pytest.mark.parametrize("status", [None, "QUEUED", "RUNNING", "SUCCEEDED", "CANCELLED"])
def test_no_notice_unless_failed(status):
    """진행 중 · 성공은 실패가 아니고, 중단(`CANCELLED`)은 중단 쪽 투영(#245 C-3)이 맡는다."""
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter(), visual_verify_status=status)
    assert CODE not in _codes(view)


def test_failed_fine_progress_ends_at_candidate_review():
    """Fine이 실패하면 IncidentClip~package가 시작되지 않는다 — 뒤 단계를 RUNNING으로 보이지 않고
    뺀다. 음성 결과와 같은 step 집합 규칙 3이다."""
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter(), visual_verify_status="FAILED")
    assert view["progress"] == [
        {"step": "file_intake", "state": "DONE"},
        {"step": "coarse_search", "state": "DONE"},
        {"step": "candidate_review", "state": "DONE"},
    ]


def test_notice_not_duplicated():
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter(), visual_verify_status="FAILED")
    again = service.derive_notices(view, visual_verify_status="FAILED")
    assert _codes(again).count(CODE) == 1


def test_get_view_passes_status_through():
    store = CaseStore()
    case = _case_with_selection()
    store.register(case, _Adapter())

    view = service.get_view(case.case_id, store=store, visual_verify_status="FAILED")

    assert _codes(view) == [CODE]
