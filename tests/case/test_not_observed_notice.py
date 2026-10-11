"""#168 [A] 후속 — 음성 결과(Fine `NOT_OBSERVED` → `NOT_ASSEMBLED`)를 notice로 알린다.

#202 이후 음성 결과는 `EVIDENCE_REVIEW` + `evidence=null`에 머문다. web은 이 조합을 「증거 조립
전」으로 읽어 진행 화면을 그리므로, 끝난 탐색을 사용자가 계속 기다리게 된다(@uminshin 요청).
`evidence=null`만으로는 음성·조립 전·응답 대기가 구분되지 않아 web이 가려내면 판정 재계산이라,
case가 adapter의 Fine 판정(`VisualEvidenceDisposition.decision`)을 받아 notice로 내린다.
real 경로(`RealAdapter`·`RealVideoAdapter`)는 `test_*not_observed_consumption.py`가 확인한다.
"""
from __future__ import annotations

from typing import Any

import pytest

from daesingo.case import service
from daesingo.case.domain import Candidate, CaseAggregate

CODE = "evidence.visual_event_not_observed"


class _Adapter:
    """`fetch_case_view_inputs()`가 읽는 getter만 가진 스냅샷."""

    def __init__(self, *, visual_evidence_decision: str | None, evidence_record: dict[str, Any] | None = None) -> None:
        self._decision = visual_evidence_decision
        self._evidence_record = evidence_record

    def get_evidence_record(self) -> dict[str, Any] | None:
        return self._evidence_record

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
        return self._decision

    def get_independent_facts(self) -> dict | None:
        return None


def _case_with_selection() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_not_observed", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates(
        [Candidate(candidate_id="cand_1", at=None, at_provenance=None, observed="후보", thumb_ref="fr_thumb", rank=1)]
    )
    case.select_candidate("cand_1")
    return case


def _codes(view: dict[str, Any]) -> list[str]:
    return [n["code"] for n in view["notices"]]


def test_notice_shape_matches_contract():
    assert service.VISUAL_EVENT_NOT_OBSERVED_NOTICE == {
        "code": CODE,
        "severity": "INFO",
        "blocking": False,
        "message_key": "notice.visual_event_not_observed",
        "actions": [],
    }


def test_not_assembled_result_gets_notice_and_stays_in_evidence_review():
    case = _case_with_selection()
    view = service.build_view_from_adapter(case, _Adapter(visual_evidence_decision="NOT_ASSEMBLED"))

    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["evidence"] is None
    assert _codes(view) == [CODE]


@pytest.mark.parametrize("decision", [None, "AWAIT_SITUATION_RESPONSE"])
def test_no_notice_while_not_negative(decision):
    """조립 전(판정 없음)·응답 대기(`UNCERTAIN`)는 음성 결과가 아니다 — 응답 대기는 `case.situation_response_pending`."""
    view = service.build_view_from_adapter(_case_with_selection(), _Adapter(visual_evidence_decision=decision))
    assert CODE not in _codes(view)


def test_notice_not_duplicated():
    case = _case_with_selection()
    adapter = _Adapter(visual_evidence_decision="NOT_ASSEMBLED")
    view = service.build_view_from_adapter(case, adapter)
    again = service.derive_notices(view, visual_evidence_decision="NOT_ASSEMBLED")
    assert _codes(again).count(CODE) == 1



def test_not_assembled_progress_ends_at_candidate_review():
    """음성 결과는 IncidentClip~package를 시작하지 않는다 — 뒤 단계를 RUNNING으로 보이지 않고 뺀다.
    `candidates=[]`로 멈춘 경우와 같은 step 집합 규칙 3이다(PR #224 리뷰)."""
    view = service.build_view_from_adapter(
        _case_with_selection(), _Adapter(visual_evidence_decision="NOT_ASSEMBLED")
    )
    assert view["progress"] == [
        {"step": "file_intake", "state": "DONE"},
        {"step": "coarse_search", "state": "DONE"},
        {"step": "candidate_review", "state": "DONE"},
    ]
