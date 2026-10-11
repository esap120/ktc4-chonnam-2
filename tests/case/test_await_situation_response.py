"""#165 — Fine `UNCERTAIN` + 상황 응답 전(`AWAIT_SITUATION_RESPONSE`)을 조립 전에 소비한다.

real E2E가 disposition을 `NOT_ASSEMBLED`만 분기하고 AWAIT는 `assemble_evidence()`로 흘려
`ContractInputError: an uncertain event requires USER_UNSURE context`로 끝났다. 또 분류할
때 사용자 응답을 넘기지 않아, 응답이 와도 계속 AWAIT로 분류됐다.

- 무응답이면 조립하지 않고 관찰 결과만 보존한다. `USER_UNSURE`를 만들어 넣지 않는다.
- 실제 응답이 오면 같은 selection context의 관찰 결과로 조립만 다시 한다(Fine·OCR 재실행 없음).
- 응답 전에 어디까지 실행할지는 #171 B 결정 몫 — 지금 관찰 단계(IncidentClip·OCR·시간
  source)는 그대로 진행한다(추천 A안과 같은 동작).
- 응답 전에도 이미 확보한 상황 독립 값(번호판 · 시각 · 위치 · 근거 프레임)은 `evidence`에
  `record_id=null`로 부분 투영한다(#239). 값은 evidence `resolve_independent_facts()`가 만든다 —
  case가 판독에서 다시 만들지 않는다. 상황 종속 셋은 `INFO_UNKNOWN`, requirements · package는 null이다.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from daesingo import search as search_module
from daesingo.case import correction, jobs, real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.evidence import ASSEMBLE, AWAIT_SITUATION_RESPONSE

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"


def _uncertain(visual_evidence: dict) -> dict:
    return dict(visual_evidence, verification="UNCERTAIN", visual_event_type=None)


@pytest.fixture(scope="module")
def uncertain_observations() -> real_e2e.ObservationBundle:
    """happy_001 관찰 결과에서 Fine만 `UNCERTAIN`으로 바꾼다."""
    scope = search_module.AnalysisScope.model_validate(
        MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    )
    candidate = search_module.search_candidates(scope).candidates[0]
    obs = real_e2e.observe_happy_001_candidate(
        case_id="case_await_001", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )
    return replace(obs, visual_evidence=_uncertain(obs.visual_evidence))


def test_await_without_response_does_not_assemble_or_raise(uncertain_observations) -> None:
    bundle = real_e2e.assemble_evidence_bundle(uncertain_observations, case_id="case_await_001")

    assert bundle.disposition.decision == AWAIT_SITUATION_RESPONSE
    assert bundle.evidence_record is None
    assert bundle.report_package is None
    # 관찰 결과(Fine 판정·비용 기록)는 지우지 않는다.
    assert bundle.visual_evidence["verification"] == "UNCERTAIN"
    assert bundle.fine_run == uncertain_observations.fine_run


def test_user_unsure_response_resumes_assembly_from_same_observations(uncertain_observations) -> None:
    response = {
        "value": "USER_UNSURE",
        "responded_at": "2026-08-24T18:22:30+09:00",
        "candidate_ref": {"kind": "candidate_event", "ref": uncertain_observations.candidate.candidate_id},
    }

    bundle = real_e2e.assemble_evidence_bundle(
        uncertain_observations, case_id="case_await_001", situation_response=response
    )

    assert bundle.disposition.decision == ASSEMBLE
    assert bundle.evidence_record is not None
    assert bundle.evidence_record["situation_response"]["value"] == "USER_UNSURE"


def test_real_adapter_caseview_for_await_is_partial_and_not_ready(monkeypatch) -> None:
    """adapter 경로 — 무응답 AWAIT는 CaseView 조립까지 예외 없이 가고, evidence는 부분 투영(#239)이며
    EvidenceRecord · Package가 없다."""
    original = real_e2e.observe_happy_001_candidate

    def observe_uncertain(**kwargs):
        obs = original(**kwargs)
        return replace(obs, visual_evidence=_uncertain(obs.visual_evidence))

    monkeypatch.setattr(real_e2e, "observe_happy_001_candidate", observe_uncertain)

    scope = MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_await_002", hints={}, manifest_summary={})
    real = RealAdapter(case_id="case_await_002", case=case, search_scope=scope, mock_root=MOCK_ROOT)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:await-coarse")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    view = service.build_view_from_adapter(case, real)

    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["evidence"]["record_id"] is None
    assert real.get_evidence_record() is None
    assert view["package"] is None


def test_real_adapter_resumes_after_user_unsure_without_reobserving(monkeypatch) -> None:
    """응답 뒤 같은 selection context로 재개 — 관찰(Fine·OCR)은 다시 돌지 않는다."""
    original = real_e2e.observe_happy_001_candidate
    calls = []

    def observe_uncertain(**kwargs):
        calls.append(kwargs["candidate"].candidate_id)
        obs = original(**kwargs)
        return replace(obs, visual_evidence=_uncertain(obs.visual_evidence))

    monkeypatch.setattr(real_e2e, "observe_happy_001_candidate", observe_uncertain)

    scope = MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_await_003", hints={}, manifest_summary={})
    real = RealAdapter(case_id="case_await_003", case=case, search_scope=scope, mock_root=MOCK_ROOT)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:await-coarse")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)
    assert service.build_view_from_adapter(case, real)["evidence"]["record_id"] is None

    case.record_situation_response("USER_UNSURE", responded_at="2026-08-24T18:22:30+09:00")
    view = service.build_view_from_adapter(case, real)

    assert view["evidence"]["record_id"] is not None
    assert len(calls) == 1


PENDING_CODE = "case.situation_response_pending"


def _await_case(
    monkeypatch, case_id: str, *, plate_outcome: str | None = None, hints: dict | None = None
) -> tuple[CaseAggregate, RealAdapter]:
    original = real_e2e.observe_happy_001_candidate

    def observe_uncertain(**kwargs):
        obs = original(**kwargs)
        obs = replace(obs, visual_evidence=_uncertain(obs.visual_evidence))
        return replace(obs, plate_read_outcome=plate_outcome) if plate_outcome else obs

    monkeypatch.setattr(real_e2e, "observe_happy_001_candidate", observe_uncertain)
    scope = MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id=case_id, hints=hints or {}, manifest_summary={})
    real = RealAdapter(case_id=case_id, case=case, search_scope=scope, mock_root=MOCK_ROOT)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint=f"sha1:{case_id}")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)
    return case, real


def _await_view(monkeypatch, case_id: str, *, plate_outcome: str | None = None) -> dict:
    case, real = _await_case(monkeypatch, case_id, plate_outcome=plate_outcome)
    return service.build_view_from_adapter(case, real)


def test_await_view_says_response_pending(monkeypatch) -> None:
    """응답 대기는 「상황 응답 전」으로 알린다 — 조립 중과 구분된다(PR #224 리뷰). 부분 투영(#239)이라
    `evidence`가 있어도 원래 발동 조건(`evidence` non-null + `NOT_ASKED` + `package == null`)에 들어맞는다."""
    view = _await_view(monkeypatch, "case_await_004")

    assert view["evidence"]["record_id"] is None
    assert PENDING_CODE in [n["code"] for n in view["notices"]]


_INDEPENDENT_DISPLAYS = ("plate_display", "event_time_display", "location_display", "preview_ref", "plate_preview_ref")
_SITUATION_DISPLAYS = ("case_type_display", "report_type_display", "violation_display")
_LOCATION_HINT = {"location": "광주 북구 용봉동 교차로"}


def test_await_projects_independent_values_without_assembling(monkeypatch) -> None:
    """#239 Acceptance — 응답 전에도 확보한 번호판 · 시각 · 위치 · 근거 프레임이 손실 없이 투영되고, 상황 종속
    값은 확정하지 않으며, 무응답을 `USER_UNSURE`로 바꾸지 않고, EvidenceRecord · Requirement · Package를 만들지 않는다."""
    case, real = _await_case(monkeypatch, "case_await_007", hints=_LOCATION_HINT)

    view = service.build_view_from_adapter(case, real)
    evidence = view["evidence"]

    assert evidence["record_id"] is None
    assert evidence["plate_display"]["value"] == "12가3456"
    assert evidence["event_time_display"]["value"] is not None
    assert evidence["location_display"]["value"] == _LOCATION_HINT["location"]
    assert evidence["preview_ref"] is not None
    assert evidence["plate_preview_ref"] is not None
    for name in _SITUATION_DISPLAYS:
        assert evidence[name] == {
            "code": None, "label": None, "needs_review": False, "info_state": "INFO_UNKNOWN", "source_label_key": None,
        }
    assert (view["requirements_evidence"], view["requirements_package"], view["package"]) == (None, None, None)
    assert case.situation_response is None
    assert next(c for c in view["candidates"] if c["selected"])["situation_confirmation"] == "NOT_ASKED"
    assert real.get_evidence_record() is None
    assert real.get_requirement_report("EVIDENCE") is None
    assert real.get_report_package() is None


def test_await_partial_values_match_the_view_after_response(monkeypatch) -> None:
    """같은 selection context에서 응답 뒤 조립한 CaseView와 상황 독립 값이 같다 — 두 경로가 evidence의 같은
    규칙을 쓴다(#239). 응답 뒤에는 상황 종속 셋이 채워진다."""
    case, real = _await_case(monkeypatch, "case_await_008", hints=_LOCATION_HINT)
    partial = service.build_view_from_adapter(case, real)["evidence"]

    case.record_situation_response("USER_UNSURE", responded_at="2026-08-24T18:22:30+09:00")
    assembled = service.build_view_from_adapter(case, real)["evidence"]

    assert assembled["record_id"] is not None
    assert {k: partial[k] for k in _INDEPENDENT_DISPLAYS} == {k: assembled[k] for k in _INDEPENDENT_DISPLAYS}
    assert assembled["report_type_display"]["code"] is not None


def test_await_partial_projection_applies_corrections(monkeypatch) -> None:
    """응답 전 정정도 evidence 규칙 그대로 부분 투영에 반영되고, 응답 뒤 Record와 같다."""
    case, real = _await_case(monkeypatch, "case_await_009")
    before = service.build_view_from_adapter(case, real)["evidence"]["plate_display"]["value"]

    correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number", previous_value=before, new_value="34나5678"
    )
    partial = service.build_view_from_adapter(case, real)["evidence"]

    assert partial["record_id"] is None
    assert partial["plate_display"]["value"] == "34나5678"
    assert partial["plate_display"]["info_state"] == "INFO_USER_CONFIRMED"
    assert partial["user_edited"] is True

    case.record_situation_response("USER_UNSURE", responded_at="2026-08-24T18:22:30+09:00")
    assert real.get_evidence_record()["vehicle_number"]["value"] == "34나5678"
    assert service.build_view_from_adapter(case, real)["evidence"]["plate_display"] == partial["plate_display"]


def test_await_progress_shows_finished_observations_not_running(monkeypatch) -> None:
    """응답 전에도 관찰(OCR·시간 source)은 끝났다. 조립 이후는 응답 뒤에 하므로 PENDING이다."""
    view = _await_view(monkeypatch, "case_await_005")

    assert {p["step"]: p["state"] for p in view["progress"]} == {
        "file_intake": "DONE",
        "coarse_search": "DONE",
        "candidate_review": "DONE",
        "plate_read": "DONE",
        "overlay_time_read": "DONE",
        "evidence_assembly": "PENDING",
        "requirement_check": "PENDING",
        "package_assembly": "PENDING",
    }


def test_await_progress_keeps_plate_read_failure(monkeypatch) -> None:
    view = _await_view(monkeypatch, "case_await_006", plate_outcome="FAILED")

    assert next(p["state"] for p in view["progress"] if p["step"] == "plate_read") == "FAILED"
    assert "readout.plate_read_failed" in [n["code"] for n in view["notices"]]
