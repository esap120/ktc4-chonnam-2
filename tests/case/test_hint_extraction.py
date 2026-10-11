"""단서 구조화(`HINT_EXTRACT`) 결과를 `case.hints`에 반영한다 — case 판단 부분(#210 (a)).

호출 · 프롬프트 · 실패 분류는 search public 함수가 맡고, case는 결과를 `hints` 4개 키로 옮기는
매핑과 실패 처리만 한다. 결과 모양은 #210 Search 의견(`OK` / `ABSTAINED` / `FAILED` + `*_hint`
4개)을 가정했다 — Search PR에서 모양이 정해지면 입력만 맞춘다.
"""
from __future__ import annotations

import pytest

from daesingo.case import service
from daesingo.case.domain import CaseAggregate, InvalidTransition

_ALL_NULL = {"time": None, "vehicle": None, "situation": None, "location": None}


def _searching_case() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_hint", hints=dict(_ALL_NULL), manifest_summary={})
    case.start_search()
    return case


def _result(status: str, **hints: str | None) -> dict:
    return {
        "status": status,
        "time_hint": hints.get("time"),
        "vehicle_hint": hints.get("vehicle"),
        "situation_hint": hints.get("situation"),
        "location_hint": hints.get("location"),
    }


def test_ok_result_maps_four_hint_fields():
    case = _searching_case()

    service.receive_hint_extraction(
        case, _result("OK", time="18:30 전후", vehicle="흰색 SUV", situation="실선 넘어 끼어듦", location="미금역 근처")
    )

    assert case.hints == {
        "time": "18:30 전후",
        "vehicle": "흰색 SUV",
        "situation": "실선 넘어 끼어듦",
        "location": "미금역 근처",
    }


def test_ok_result_may_leave_some_fields_empty():
    """일부만 구조화돼도 `OK`다. 빈 문자열도 단서가 아니므로 `null`로 둔다 — 값을 지어내지 않는다."""
    case = _searching_case()

    service.receive_hint_extraction(case, _result("OK", vehicle="흰색 SUV", situation="  "))

    assert case.hints == {"time": None, "vehicle": "흰색 SUV", "situation": None, "location": None}


@pytest.mark.parametrize("status", ["ABSTAINED", "FAILED"])
def test_abstained_or_failed_leaves_all_hints_null(status):
    """보류 · 실패는 같은 처리다 — 모델이 무언가를 냈더라도 쓰지 않고 빈 단서로 진행한다."""
    case = _searching_case()

    service.receive_hint_extraction(case, _result(status, vehicle="흰색 SUV"))

    assert case.hints == _ALL_NULL


def test_reflection_does_not_bump_case_rev():
    """결과 반영은 사용자 요청이 아니라 실행 결과다(`record_candidate_search_failure()`와 같다)."""
    case = _searching_case()
    before = case.case_rev

    service.receive_hint_extraction(case, _result("OK", vehicle="흰색 SUV"))

    assert case.case_rev == before
    assert case.stage == "SEARCHING"


def test_unknown_status_is_rejected():
    """모르는 상태를 「실패」로 뭉개면 결과 모양이 바뀐 것을 알아채지 못한다."""
    case = _searching_case()

    with pytest.raises(ValueError):
        service.receive_hint_extraction(case, _result("PARTIAL", vehicle="흰색 SUV"))
    assert case.hints == _ALL_NULL


def test_only_accepted_while_searching():
    """구조화 결과는 분석 시작 직후(`SEARCHING`, 탐색 발주 전)에만 들어온다."""
    case = CaseAggregate.intake(case_id="case_hint", hints=dict(_ALL_NULL), manifest_summary={})

    with pytest.raises(InvalidTransition):
        service.receive_hint_extraction(case, _result("OK", vehicle="흰색 SUV"))
    assert case.hints == _ALL_NULL
