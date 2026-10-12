"""이슈 #137 — Fine이 `NOT_OBSERVED`를 냈을 때 case가 downstream을 시작하지 않는다.

유료 호출 없이 synthetic `NOT_OBSERVED` VisualEvidence를 실제 소비 경로
(`real_e2e.build_fixture_evidence_bundle`)에 주입한다. "결과가 비어 있더라"로 끝내지
않고 IncidentClip·readout·TimeResolution·evidence 조립이 **호출되지 않았다는 것**을
call count로 증명한다.

`test_real_e2e.py`가 `OBSERVED` 대표 시나리오의 회귀를 맡고, 이 파일은 같은 경로의
negative 결말을 맡는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from daesingo import search as search_module
from daesingo.case import real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.evidence import NOT_ASSEMBLED
from daesingo.evidence.disposition import NOT_OBSERVED_REASON
from daesingo.recording import RecordingService

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "happy_001"


def _real_scope():
    return search_module.AnalysisScope.model_validate(
        MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID).get_analysis_scopes()[0]
    )


def _not_observed_result(scope):
    """녹화된 `OBSERVED` Fine 결과에서 관찰 상태만 바꾼 synthetic 결과.

    run_id·input_ref·usage 등 실행 provenance는 그대로 둔다 — 이번에 확인하려는 건
    "Fine이 후보를 기각했을 때"이지 "실행이 실패했을 때"가 아니다.
    """
    recorded = search_module.verify_visual(
        search_module.ContractRef(kind="analysis_source", ref="as_h001_fine"), scope.hint
    )
    payload = recorded.model_dump(mode="json")
    payload["visual_evidence"]["verification"] = "NOT_OBSERVED"
    payload["visual_evidence"]["visual_event_type"] = None
    return search_module.VisualVerificationResult.model_validate(payload)


class _Spies:
    def __init__(self, monkeypatch):
        self.calls: dict[str, int] = {}
        self._monkeypatch = monkeypatch

    def watch(self, target, name):
        original = getattr(target, name)
        self.calls[name] = 0

        def counted(*args, **kwargs):
            self.calls[name] += 1
            return original(*args, **kwargs)

        self._monkeypatch.setattr(target, name, counted)


@pytest.fixture
def not_observed_run(monkeypatch):
    scope = _real_scope()
    synthetic = _not_observed_result(scope)
    monkeypatch.setattr(
        real_e2e.search_module, "verify_visual", lambda *args, **kwargs: synthetic
    )

    spies = _Spies(monkeypatch)
    spies.watch(RecordingService, "build_incident_clip")
    spies.watch(real_e2e.readout_api, "read_plate")
    spies.watch(real_e2e.readout_api, "read_overlay_time")
    spies.watch(real_e2e, "resolve_time")
    spies.watch(real_e2e, "assemble_evidence")
    spies.watch(real_e2e, "calculate_evidence_needs")
    spies.watch(real_e2e, "evaluate_requirements")
    spies.watch(real_e2e, "build_report_package")
    return scope, spies


def test_not_observed_ends_without_a_contract_error(not_observed_run):
    """`ContractInputError` 없이 정상 종료한다 — 이게 이번 negative 경로의 성공 기준이다."""
    scope, _ = not_observed_run
    candidate = search_module.search_candidates(scope).candidates[0]

    bundle = real_e2e.build_fixture_evidence_bundle(
        case_id="case_h001_not_observed", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )

    assert bundle.disposition.decision == NOT_ASSEMBLED
    assert bundle.disposition.reason_code == NOT_OBSERVED_REASON
    assert bundle.assembled is False


def test_not_observed_does_not_start_downstream_work(not_observed_run):
    """미호출을 결과 추정이 아니라 call count로 증명한다."""
    scope, spies = not_observed_run
    candidate = search_module.search_candidates(scope).candidates[0]

    real_e2e.build_fixture_evidence_bundle(
        case_id="case_h001_not_observed_spy", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )

    assert spies.calls == {
        "build_incident_clip": 0,
        "read_plate": 0,
        "read_overlay_time": 0,
        "resolve_time": 0,
        "assemble_evidence": 0,
        "calculate_evidence_needs": 0,
        "evaluate_requirements": 0,
        "build_report_package": 0,
    }


def test_not_observed_produces_no_record_report_or_package(not_observed_run):
    scope, _ = not_observed_run
    candidate = search_module.search_candidates(scope).candidates[0]

    bundle = real_e2e.build_fixture_evidence_bundle(
        case_id="case_h001_not_observed_outputs", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )

    assert bundle.evidence_record is None
    assert bundle.evidence_needs is None
    assert bundle.requirement_report_evidence is None
    assert bundle.requirement_report_package is None
    assert bundle.report_package is None
    # `package_error`도 비어 있어야 한다 — 패키지를 만들려다 막힌 게 아니라 애초에
    # 만들 단계까지 가지 않은 것이라서 실패 사유를 지어내면 안 된다.
    assert bundle.package_error is None


def test_not_observed_preserves_visual_evidence_and_fine_execution(not_observed_run):
    """조립을 안 한다고 관찰 결과를 버리지 않는다 — 평가·진단에 그대로 쓰인다."""
    scope, _ = not_observed_run
    candidate = search_module.search_candidates(scope).candidates[0]

    bundle = real_e2e.build_fixture_evidence_bundle(
        case_id="case_h001_not_observed_preserved", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )

    assert bundle.visual_evidence["verification"] == "NOT_OBSERVED"
    assert bundle.visual_evidence["visual_event_type"] is None
    assert bundle.visual_evidence["visual_evidence_id"]
    assert bundle.visual_evidence["input_ref"]
    assert bundle.fine_run["run_id"] == bundle.visual_evidence["run_id"]
    assert bundle.fine_run["operation"] == "VISUAL_VERIFY"
    assert bundle.fine_run["outcome"]
    # UsageRecord/비용 provenance — Fine은 실제로 실행됐고 그 사용량이 남아 있어야 한다.
    assert "usage_refs" in bundle.fine_run
    assert bundle.fine_run["usage_summary"] is not None


def test_real_adapter_reports_a_case_without_evidence(not_observed_run):
    """`RealAdapter` getter들이 예외 없이 "아직 없음"을 돌려주고, `CaseView`는 이미 있는
    `EVIDENCE_REVIEW` + evidence 없음 표현을 그대로 쓴다 — 새 stage나 필드를 만들지 않는다."""
    scope, _ = not_observed_run
    case = CaseAggregate.intake(case_id="case_h001_not_observed_view", hints={}, manifest_summary={})
    case.start_search()
    real = RealAdapter(
        case_id="case_h001_not_observed_view", case=case, search_scope=scope, mock_root=MOCK_ROOT
    )
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    assert real.get_evidence_record() is None
    assert real.get_evidence_records() == []
    assert real.get_evidence_needs() == []
    assert real.get_requirement_report("EVIDENCE") is None
    assert real.get_requirement_reports("FINAL_PACKAGE") == []
    assert real.get_report_package() is None

    view = service.build_view_from_adapter(case, real)
    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["package"] is None
    # evidence가 없는 EVIDENCE_REVIEW는 `case-view/v1.4`가 이미 표현하던 상태다 —
    # 조립 이후 단계는 낙관적으로 PENDING을 보여주지 않고 목록에서 빠진다.
    steps = [step["step"] for step in view["progress"]]
    assert "evidence_assembly" not in steps
    assert "package_assembly" not in steps
    # 음성 결과는 evidence가 없어 조립 전과 값이 같다 — notice로 구분한다(#168 [A]).
    assert real.get_visual_evidence_decision() == "NOT_ASSEMBLED"
    assert [n["code"] for n in view["notices"]] == ["evidence.visual_event_not_observed"]
