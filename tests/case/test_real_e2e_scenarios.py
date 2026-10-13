"""real 경로 5개 시나리오 — case fixture(`data/mock/case/`) 마지막 CaseView와 핵심 사실을 대조한다
(`decisions/real-e2e-scenarios.md` §4-4). 값은 fixture에서 읽고 여기 다시 적지 않는다. real이 아직 못 맞추는
사실은 `KNOWN_GAPS` · `UNDERIVED_NOTICES`에 이름만 두고 이유는 결정 문서 §6에 둔다 — 원인이 풀리면 이 테스트가
「차이가 사라졌다」로 실패해 알려 준다."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daesingo.case import correction, jobs, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import CaseAggregate

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"

# Mock fixture에만 있고 case 코드 어디에서도 만들지 않는 notice(§6 발견 사항 1).
UNDERIVED_NOTICES = {
    "evidence.time_post_stamp_required",
    "evidence.time_conflict_needs_notice",
    "evidence.visual_event_unconfirmed",
}

# real이 fixture와 다른 사실(§6 발견 사항 2).
KNOWN_GAPS: dict[str, set[str]] = {
    "unknown_abstain_partial_001": {"stage", "package"},
}

SCENARIOS = [
    "happy_001",
    "unknown_abstain_partial_001",
    "correction_rerun_001",
    "plate_reread_001",
    "empty_001",
]


def _fixture(name: str) -> dict:
    return json.loads((MOCK_ROOT / "case" / f"scenario_{name}.json").read_text(encoding="utf-8"))


def _facts(view: dict) -> dict:
    evidence = view["evidence"] or {}
    return {
        "stage": view["stage"],
        "package": view["package"] is not None,
        "plate": (evidence.get("plate_display") or {}).get("value"),
        "event_time": (evidence.get("event_time_display") or {}).get("value"),
        "candidates": len(view["candidates"]),
        "situation": [c.get("situation_confirmation") for c in view["candidates"]],
    }


def _run(name: str) -> dict:
    """fixture가 기록한 사용자 행동(정정 · 상황 응답)과 재판독 Need를 real 경로로 그대로 재생한다."""
    fixture = _fixture(name)
    final = fixture["case_views"][-1]
    mock = MockFixtureAdapter(MOCK_ROOT, name)
    scope = mock.get_analysis_scopes()[0]
    case_id = f"case_real_{name}"
    case = CaseAggregate.intake(case_id=case_id, hints=mock.get_hints(), manifest_summary={})
    real = RealAdapter(case_id=case_id, case=case, search_scope=scope, mock_root=MOCK_ROOT, scenario_id=f"scenario_{name}")
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref=scope["scope_id"], input_fingerprint=f"sha1:{name}-coarse")
    candidates = service.receive_search_candidates(case, real)
    if candidates:
        case.select_candidate(candidates[0].candidate_id)
        jobs.issue_plate_read(case, input_fingerprint=f"sha1:{name}-plate")
        needs = real.get_evidence_needs()
        if needs and any(i["kind"] == "PLATE_REREAD" for i in needs[0]["items"]):
            jobs.issue_needed_jobs(case, needs[0])
        for record in fixture.get("correction_records", []):
            correction.apply_correction(
                case,
                kind=record["kind"],
                target_field=record["target_field"],
                previous_value=record["previous_value"],
                new_value=record["new_value"],
            )
        response = final["candidates"][0].get("situation_confirmation")
        if response in ("CONFIRMED", "USER_UNSURE"):
            case.record_situation_response(response, responded_at="2026-01-01T00:00:00+09:00")
        service.mark_ready_if_package_ready(case, real)
    return service.build_view_from_adapter(case, real)


@pytest.mark.parametrize("name", SCENARIOS)
def test_real_path_matches_case_fixture(name):
    expected = _facts(_fixture(name)["case_views"][-1])
    actual = _facts(_run(name))
    gaps = KNOWN_GAPS.get(name, set())

    assert {k: v for k, v in actual.items() if k not in gaps} == {k: v for k, v in expected.items() if k not in gaps}
    for key in gaps:
        assert actual[key] != expected[key], f"{name}.{key}: 차이가 사라졌다 — KNOWN_GAPS와 §6을 고친다"


@pytest.mark.parametrize("name", SCENARIOS)
def test_real_notices_are_fixture_notices_minus_underived(name):
    expected = {n["code"] for n in _fixture(name)["case_views"][-1]["notices"]}
    actual = {n["code"] for n in _run(name)["notices"]}

    assert actual == expected - UNDERIVED_NOTICES
    assert UNDERIVED_NOTICES.isdisjoint(actual), "만들지 않던 notice가 생겼다 — UNDERIVED_NOTICES와 §6을 고친다"
