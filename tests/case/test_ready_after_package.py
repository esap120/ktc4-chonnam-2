"""#167 — `READY`는 FINAL `PASS`/`WARN` + ReportPackage가 실제로 있을 때만.

real E2E 경로(`scripts/dump_real_video_caseview.py`)가 evidence·Package를 만들기 **전에**
`case.mark_ready()`를 불러서, Package가 막힌 결과와 `NOT_ASSEMBLED`(evidence 없음)까지
`stage=READY`로 나왔다. CaseView 계약: `READY` = `PACKAGE_READY` 파생 gate 성립 시점
(#171 C 결정). Package 전 결과의 화면은 #168·#171이 정하고, case는 앞 단계에 머문다.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from daesingo.case import jobs, real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import Candidate, CaseAggregate, InvalidTransition

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"


class _SnapshotAdapter:
    """`fetch_case_view_inputs()`가 읽는 getter만 가진 스냅샷."""

    def __init__(
        self,
        *,
        evidence_record: dict[str, Any] | None,
        final_readiness: str | None,
        report_package: dict[str, Any] | None,
    ) -> None:
        self._evidence_record = evidence_record
        self._final = None if final_readiness is None else {"overall": final_readiness, "checks": []}
        self._package = report_package

    def get_evidence_record(self) -> dict[str, Any] | None:
        return self._evidence_record

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None:
        return self._final if scope == "FINAL_PACKAGE" else None

    def get_report_package(self) -> dict[str, Any] | None:
        return self._package

    def get_plate_read_status(self) -> str | None:
        return None

    def get_evidence_needs(self) -> list[dict[str, Any]]:
        return []

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        return []

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        return []

    def get_visual_evidence_decision(self) -> str | None:
        return None

    def get_independent_facts(self) -> dict | None:
        return None


_EVIDENCE = {
    "record_ref": {"kind": "evidence_record", "ref": "er_test_001"},
    # 아래 `_case_in_evidence_review()`의 선택 context — 첫 선택이라 selection_rev=1.
    "basis": {"candidate_ref": {"kind": "candidate_event", "ref": "cand_ready_gate"}},
    "selection_rev": 1,
}
_PACKAGE = {"package_ref": {"kind": "report_package", "ref": "pkg_test_001"}}


def _case_in_evidence_review(candidate_id: str = "cand_ready_gate") -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_ready_gate", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates(
        [
            Candidate(
                candidate_id=candidate_id,
                at=None,
                at_provenance="recording.timeline_relative_only",
                observed="테스트 후보",
                thumb_ref=None,
            )
        ]
    )
    case.select_candidate(candidate_id)
    return case


@pytest.mark.parametrize("readiness", ["PASS", "WARN"])
def test_ready_when_final_passes_and_package_exists(readiness: str) -> None:
    case = _case_in_evidence_review()
    adapter = _SnapshotAdapter(evidence_record=_EVIDENCE, final_readiness=readiness, report_package=_PACKAGE)

    assert service.mark_ready_if_package_ready(case, adapter) is True
    assert case.stage == "READY"


def test_package_blocked_observed_result_stays_in_evidence_review() -> None:
    """Positive + Package blocked(예: 상황 응답 전 D2-c) — evidence는 있고 Package는 없다."""
    case = _case_in_evidence_review()
    rev = case.case_rev
    adapter = _SnapshotAdapter(evidence_record=_EVIDENCE, final_readiness="UNKNOWN", report_package=None)

    assert service.mark_ready_if_package_ready(case, adapter) is False
    assert case.stage == "EVIDENCE_REVIEW"
    assert case.case_rev == rev


def test_not_assembled_result_stays_in_evidence_review() -> None:
    """NOT_OBSERVED → NOT_ASSEMBLED — evidence·요건·Package 전부 없다."""
    case = _case_in_evidence_review()
    adapter = _SnapshotAdapter(evidence_record=None, final_readiness=None, report_package=None)

    assert service.mark_ready_if_package_ready(case, adapter) is False
    assert case.stage == "EVIDENCE_REVIEW"


def test_package_without_passing_final_report_is_not_ready() -> None:
    """ReportPackage는 ready-only라 FINAL이 PASS/WARN이 아니면 원래 생기지 않는다 — 어긋난
    스냅샷이 오더라도 READY로 올리지 않는다."""
    case = _case_in_evidence_review()
    adapter = _SnapshotAdapter(evidence_record=_EVIDENCE, final_readiness="FAIL", report_package=_PACKAGE)

    assert service.mark_ready_if_package_ready(case, adapter) is False
    assert case.stage == "EVIDENCE_REVIEW"


@pytest.mark.parametrize(
    "basis_candidate, selection_rev",
    [("cand_other", 1), ("cand_ready_gate", 0)],
    ids=["other-candidate", "previous-selection-context"],
)
def test_package_from_another_selection_is_not_ready(basis_candidate: str, selection_rev: int) -> None:
    """READY는 **현재 선택**의 Package로만 — CaseView가 evidence를 거르는 기준(#191)과 같다.
    다르면 stage는 READY인데 CaseView의 evidence·package는 null이 된다(I1). 결과가 늦게 도착하는
    worker 경로(W7 6.6순위)에서 이전 선택의 Package가 오는 경우다."""
    case = _case_in_evidence_review()
    rev = case.case_rev
    evidence = dict(_EVIDENCE, basis={"candidate_ref": {"kind": "candidate_event", "ref": basis_candidate}},
                    selection_rev=selection_rev)
    adapter = _SnapshotAdapter(evidence_record=evidence, final_readiness="PASS", report_package=_PACKAGE)

    assert service.mark_ready_if_package_ready(case, adapter) is False
    assert case.stage == "EVIDENCE_REVIEW"
    assert case.case_rev == rev


# ── domain 가드 — READY는 준비된 Package 없이 들어갈 수 없다 ──────────────


def test_domain_rejects_ready_without_package() -> None:
    """real 스크립트만 고치면 누가 `mark_ready()`를 직접 불러 같은 버그가 다시 난다 —
    domain이 Package 없이 READY로 가는 전이를 거부한다."""
    case = _case_in_evidence_review()
    rev = case.case_rev

    with pytest.raises(InvalidTransition):
        case.mark_ready(report_package=None)

    assert case.stage == "EVIDENCE_REVIEW"
    assert case.case_rev == rev


def test_domain_ready_with_package() -> None:
    case = _case_in_evidence_review()
    case.mark_ready(report_package=_PACKAGE)
    assert case.stage == "READY"


# ── 실제 adapter 경로 ──────────────────────────────────────────────────


class _DictModel(dict):
    def model_dump(self, mode: str = "json") -> dict:
        return dict(self)


def _selected_real_adapter(case_id: str) -> tuple[CaseAggregate, RealAdapter]:
    scope = MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id=case_id, hints={}, manifest_summary={})
    real = RealAdapter(case_id=case_id, case=case, search_scope=scope, mock_root=MOCK_ROOT)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint=f"sha1:{case_id}-coarse")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)
    return case, real


def test_real_adapter_not_observed_does_not_reach_ready(monkeypatch) -> None:
    """Fine `NOT_OBSERVED` → `NOT_ASSEMBLED`(evidence·Package 없음)이 실제 adapter 경로에서도
    READY가 되지 않는다."""
    original = real_e2e._resolve_via_search_stream_context

    def resolve_not_observed(**kwargs):
        result, media_stream_ref = original(**kwargs)
        visual = dict(result.visual_evidence.model_dump(mode="json"), verification="NOT_OBSERVED", visual_event_type=None)
        fake = SimpleNamespace(visual_evidence=_DictModel(visual), analysis_run=result.analysis_run)
        return fake, media_stream_ref

    monkeypatch.setattr(real_e2e, "_resolve_via_search_stream_context", resolve_not_observed)
    case, real = _selected_real_adapter("case_ready_not_observed")

    assert service.mark_ready_if_package_ready(case, real) is False
    view = service.build_view_from_adapter(case, real)
    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["evidence"] is None
    assert view["package"] is None


def test_mock_happy_path_with_package_still_reaches_ready() -> None:
    """Package가 있는 정상 경로(공용 Mock happy_001, `pkg_h001`)는 이 함수로 READY가 된다.
    fixture evidence의 `basis.candidate_ref`(`candidate_h001`)를 골라야 현재 선택 context로 투영된다(#173 E-4)."""
    case = _case_in_evidence_review("candidate_h001")
    adapter = MockFixtureAdapter(MOCK_ROOT, "happy_001")

    assert service.mark_ready_if_package_ready(case, adapter) is True
    assert case.stage == "READY"
    view = service.build_view_from_adapter(case, adapter)
    assert view["stage"] == "READY"
    assert view["package"] is not None
