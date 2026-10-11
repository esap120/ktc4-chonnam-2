"""`service.derive_notices()` — 조립된 CaseView 값만으로 발동하는 notice(이슈 #48).

`evidence.location_search_keyword_missing`의 계약 발동 조건은
`evidence.location_display.search_keyword == null`이다(`contract-job-record-case-view.md`
B절 `notices[].code`, 2026-09-14 등재). 정답지는 이 notice가 들어간 case fixture 4개다.
`happy_001`도 #48 I2 재생성으로 근거 없던 `search_keyword`가 빠져 대상이 됐다 — 검색어가 있는
경우는 fixture 값에 검색어를 채운 사본으로 확인한다.

`case.situation_response_pending` — #171 C-2(Case 결정): Package 전 결과 화면의 「준비 전」
이유를 notice로 내린다. 발동 조건은 evidence가 있고, 선택된 후보의 `situation_confirmation`이
`NOT_ASKED`이며, `package`가 없을 때다(ADR-EVIDENCE-005 D2-c로 Package가 막힌 상태).
"""
import copy
import json
from pathlib import Path

import pytest

from daesingo.case import service
from daesingo.case.adapters import MockFixtureAdapter
from daesingo.case.domain import CaseAggregate

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
CODE = "evidence.location_search_keyword_missing"
PENDING_CODE = "case.situation_response_pending"
DERIVED_CODES = {CODE, PENDING_CODE}


def _case_views(scenario_id: str) -> list[dict]:
    path = MOCK_ROOT / "case" / f"scenario_{scenario_id}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["case_views"]


def _without_notice(view: dict) -> dict:
    stripped = copy.deepcopy(view)
    stripped["notices"] = [n for n in stripped["notices"] if n["code"] not in DERIVED_CODES]
    return stripped


@pytest.mark.parametrize(
    "scenario_id", ["correction_rerun_001", "happy_001", "plate_reread_001", "unknown_abstain_partial_001"]
)
def test_derives_notice_when_search_keyword_is_null(scenario_id):
    for expected in _case_views(scenario_id):
        if expected["evidence"] is None:
            continue
        assert expected["evidence"]["location_display"]["search_keyword"] is None
        derived = service.derive_notices(_without_notice(expected))
        assert derived["notices"] == expected["notices"]


def test_notice_shape_matches_contract():
    assert service.LOCATION_SEARCH_KEYWORD_MISSING_NOTICE == {
        "code": CODE,
        "severity": "INFO",
        "blocking": False,
        "message_key": "notice.location_search_keyword_missing",
        "actions": [],
    }


def test_no_notice_when_search_keyword_present():
    for expected in _case_views("happy_001"):
        if expected["evidence"] is None:
            continue
        view = _without_notice(expected)
        view["evidence"]["location_display"]["search_keyword"] = "광주 상무지구 상무중앙로 사거리"
        codes = [n["code"] for n in service.derive_notices(view)["notices"]]
        assert CODE not in codes


def test_no_notice_before_evidence():
    view = {"evidence": None, "notices": []}
    assert service.derive_notices(view)["notices"] == []


def test_does_not_duplicate_or_mutate_caller_notices():
    view = _without_notice(_case_views("unknown_abstain_partial_001")[-1])
    caller_notices = view["notices"]
    before = list(caller_notices)

    once = service.derive_notices(view)
    twice = service.derive_notices(once)

    assert [n["code"] for n in twice["notices"]].count(CODE) == 1
    assert caller_notices == before


def test_build_view_from_adapter_attaches_notice():
    """실제 진입점(`build_view_from_adapter()`)에서도 붙는지 — 호출자는 notice를 넘기지 않는다."""
    adapter = MockFixtureAdapter(MOCK_ROOT, "unknown_abstain_partial_001")
    case = CaseAggregate.intake(case_id="case_u001", hints={}, manifest_summary={})
    case.start_search()
    service.receive_search_candidates(case, adapter)
    case.select_candidate("candidate_u001")  # 현재 선택의 evidence만 투영된다(W7 6.6순위)
    view = service.build_view_from_adapter(case, adapter)

    assert view["evidence"]["location_display"]["search_keyword"] is None
    # overlay가 안 찍힌 영상이라 `readout.overlay_not_present`도 붙는다 — fixture 마지막 revision과 같은 순서다.
    assert [n["code"] for n in view["notices"]] == ["readout.overlay_not_present", CODE]


# ── case.situation_response_pending ─────────────────────────────────────


def test_pending_notice_shape_matches_contract():
    assert service.SITUATION_RESPONSE_PENDING_NOTICE == {
        "code": PENDING_CODE,
        "severity": "INFO",
        "blocking": False,
        "message_key": "notice.situation_response_pending",
        "actions": [],
    }


@pytest.mark.parametrize("scenario_id", ["correction_rerun_001", "plate_reread_001"])
def test_pending_notice_on_evidence_without_response(scenario_id):
    """P·R은 evidence가 있지만 상황 응답 전이라 Package가 없다 — 모든 스냅샷이 대상이다."""
    for expected in _case_views(scenario_id):
        assert expected["evidence"] is not None and expected["package"] is None
        codes = [n["code"] for n in service.derive_notices(_without_notice(expected))["notices"]]
        assert PENDING_CODE in codes


def test_no_pending_notice_after_response():
    """U는 `USER_UNSURE`로 이미 응답했다 — 무응답이 아니다."""
    for view in _case_views("unknown_abstain_partial_001"):
        codes = [n["code"] for n in service.derive_notices(_without_notice(view))["notices"]]
        assert PENDING_CODE not in codes


def test_no_pending_notice_without_evidence():
    """evidence가 아직 없으면(조립 전·실패) 값 화면 자체가 없어 붙이지 않는다(#165 미결)."""
    for view in _case_views("infra_failure_001"):
        assert view["evidence"] is None
        codes = [n["code"] for n in service.derive_notices(_without_notice(view))["notices"]]
        assert PENDING_CODE not in codes


def test_no_pending_notice_when_package_exists():
    view = copy.deepcopy(_case_views("plate_reread_001")[-1])
    view["package"] = {"package_ref": "pkg_x"}
    codes = [n["code"] for n in service.derive_notices(_without_notice(view))["notices"]]
    assert PENDING_CODE not in codes


# ── evidence.plate_abstained ────────────────────────────────────────────
# #172 D-3(09-29 확정): 일부 판독 / `NEEDS_REVIEW`(1·2)는 「검토·재판독 필요」를 표시한다. 읽지 못함
# (1·3)·실행 실패(4a)와 CaseView 값(`plate_display.value=null`, `INFO_UNKNOWN`)이 같아서, 발동 근거는
# evidence가 현재 EvidenceRecord에 대해 낸 `EvidenceNeeds`의 `PLATE_REREAD` 항목이다.

ABSTAINED_CODE = "evidence.plate_abstained"


def _evidence_needs(scenario_id: str) -> list[dict]:
    path = MOCK_ROOT / "evidence" / f"scenario_{scenario_id}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["evidence_needs"]


def _without(view: dict, code: str) -> dict:
    stripped = _without_notice(view)
    stripped["notices"] = [n for n in stripped["notices"] if n["code"] != code]
    return stripped


def test_abstained_notice_shape_matches_contract():
    """`actions[]`는 비운다 — `MANUAL_PLATE_INPUT`은 입력형 command 판본(#106) 전에는 보낼 경로가 없다."""
    assert service.PLATE_ABSTAINED_NOTICE == {
        "code": ABSTAINED_CODE,
        "severity": "WARN",
        "blocking": False,
        "message_key": "notice.plate_abstained",
        "actions": [],
    }


def test_abstained_notice_when_current_record_needs_plate_reread():
    """`plate_reread_001` rev3 — v1 basis(`ev_p001`)에 `PLATE_REREAD` Need가 있다."""
    expected = _case_views("plate_reread_001")[0]
    assert ABSTAINED_CODE in [n["code"] for n in expected["notices"]]

    derived = service.derive_notices(
        _without(expected, ABSTAINED_CODE), evidence_needs=_evidence_needs("plate_reread_001")
    )

    codes = [n["code"] for n in derived["notices"]]
    assert codes.count(ABSTAINED_CODE) == 1
    assert next(n for n in derived["notices"] if n["code"] == ABSTAINED_CODE)["actions"] == []


def test_no_abstained_notice_after_reread_fills_plate():
    """rev4 — 재판독 v2 basis(`ev_p001_v2`)의 Need는 비었다. v1의 Need로 발동하지 않는다."""
    view = _without(_case_views("plate_reread_001")[1], ABSTAINED_CODE)
    derived = service.derive_notices(view, evidence_needs=_evidence_needs("plate_reread_001"))
    assert ABSTAINED_CODE not in [n["code"] for n in derived["notices"]]


def test_no_abstained_notice_for_unread_plate_without_need():
    """1·3(읽지 못함) — 값은 똑같이 없지만 Need가 없다. 「보류」로 보이지 않는다."""
    view = _without(_case_views("plate_reread_001")[0], ABSTAINED_CODE)
    record_id = view["evidence"]["record_id"]
    needs = [{"basis_record_ref": {"kind": "evidence_record", "ref": record_id}, "items": []}]
    derived = service.derive_notices(view, evidence_needs=needs)
    assert ABSTAINED_CODE not in [n["code"] for n in derived["notices"]]


class _RereadPendingAdapter(MockFixtureAdapter):
    """재판독 전(v1 `ev_p001`) 시점의 스냅샷 — `MockFixtureAdapter`는 체인의 마지막(v2)을 현재로 준다(#177)."""

    def get_evidence_record(self):
        records = self.get_evidence_records()
        return records[0] if records else None

    def get_requirement_report(self, scope):
        return next(iter(self.get_requirement_reports(scope)), None)

    def get_report_package(self):
        packages = self._load("evidence").get("report_packages", [])
        return packages[0] if packages else None


def _selected_plate_reread_case(adapter: MockFixtureAdapter) -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_p001", hints={}, manifest_summary={})
    case.start_search()
    service.receive_search_candidates(case, adapter)
    case.select_candidate("candidate_p001")
    return case


def test_build_view_from_adapter_attaches_abstained_notice():
    """실제 진입점에서 adapter의 EvidenceNeeds로 붙는지 — 호출자는 notice를 넘기지 않는다."""
    adapter = _RereadPendingAdapter(MOCK_ROOT, "plate_reread_001")
    view = service.build_view_from_adapter(_selected_plate_reread_case(adapter), adapter)
    record_id = view["evidence"]["record_id"]
    reread_pending = any(
        n["basis_record_ref"]["ref"] == record_id and any(i["kind"] == "PLATE_REREAD" for i in n["items"])
        for n in adapter.get_evidence_needs()
    )

    assert reread_pending  # v1(`ev_p001`)이 현재 기록이다
    assert ABSTAINED_CODE in [n["code"] for n in view["notices"]]


def test_build_view_from_adapter_drops_abstained_notice_after_reread():
    """재판독 뒤(v2 `ev_p001_v2`)에는 현재 기록에 `PLATE_REREAD` Need가 없어 붙지 않는다."""
    adapter = MockFixtureAdapter(MOCK_ROOT, "plate_reread_001")
    view = service.build_view_from_adapter(_selected_plate_reread_case(adapter), adapter)

    assert view["evidence"]["record_id"] == "ev_p001_v2"
    assert ABSTAINED_CODE not in [n["code"] for n in view["notices"]]
