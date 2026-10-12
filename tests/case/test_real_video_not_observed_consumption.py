"""이슈 #137 — `build_evidence_for_real_video_candidate()`도 `build_fixture_evidence_bundle()`과
동일하게 Fine이 `NOT_OBSERVED`를 냈을 때 downstream을 시작하지 않는다(PR #131→#142 후속
정합화, 2026-09-22).

real 영상 경로 전체(`prepare_real_video_context()`)는 ffmpeg/ffprobe/paddleocr와 실제
영상 파일이 필요하다(`test_real_video_pipeline.py`). 이 파일은 그 경로를 타지 않는다 —
happy_001 recording fixture가 이미 갖고 있는 실제 `media_streams`/`AnalysisSource` 값을
재사용해 `RealVideoContext`를 synthetic으로 구성하므로, 유료 호출도 ffmpeg도 필요 없다.
`NOT_OBSERVED` 분기는 그 뒤(두 번째 `resolve_span`/`build_incident_clip`/readout)를
아예 타지 않으므로 `rec_service`가 실제로 동작할 필요조차 없다.

`test_not_observed_consumption.py`가 fixture 경로(`build_fixture_evidence_bundle`)의
negative 결말을 맡고, 이 파일은 같은 결말을 real 영상 경로에서 맡는다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from daesingo import search as search_module
from daesingo.case import real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealVideoAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.case.real_e2e import RealVideoContext
from daesingo.evidence import NOT_ASSEMBLED
from daesingo.evidence.disposition import NOT_OBSERVED_REASON
from daesingo.recording import RecordingService

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "happy_001"


def _real_scope():
    return search_module.AnalysisScope.model_validate(
        MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID).get_analysis_scopes()[0]
    )


def _not_observed_visual_evidence() -> dict[str, Any]:
    """녹화된 `OBSERVED` Fine 결과에서 관찰 상태만 바꾼 synthetic 결과 —
    `test_not_observed_consumption.py::_not_observed_result`와 동일한 변형이다."""
    data = json.loads((MOCK_ROOT / "search" / "scenario_happy_001.json").read_text(encoding="utf-8"))
    visual_evidence = dict(data["visual_evidences"][0])
    visual_evidence["verification"] = "NOT_OBSERVED"
    visual_evidence["visual_event_type"] = None
    return visual_evidence


class _DictModel(dict):
    def model_dump(self, mode: str = "json") -> dict:
        return dict(self)


@dataclass
class _FakeVisualResult:
    visual_evidence: _DictModel
    analysis_run: _DictModel


@dataclass
class _FakeSelectedStream:
    media_stream_ref: str


@dataclass
class _FakeExecution:
    result: Any
    selected_video_stream: Any


def _synthetic_video_context() -> RealVideoContext:
    """happy_001 recording fixture의 실제 `media_streams`/`AnalysisSource` 값을 재사용한다
    — `analysis_source_ref`/`media_stream_refs`가 임의 문자열이 아니라 이미 계약을 통과한
    값이라 신뢰할 수 있다(`_match_analysis_source_streams()`가 그대로 검증에 쓴다)."""
    fixture = real_e2e.load_recording_fixture(real_e2e.DEFAULT_SCENARIO_ID)
    analysis_source = fixture.analysis_sources[0]
    bootstrap_ref = analysis_source.media_stream_refs[0]
    return RealVideoContext(
        rec_service=None,
        registered=SimpleNamespace(media_streams=fixture.media_streams),
        timeline=None,
        scope=_real_scope(),
        gemini_service=None,
        analysis_source=analysis_source,
        bootstrap_ref=bootstrap_ref,
        local_video_path="unused-in-not-observed-path",
    )


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
def not_observed_video_run(monkeypatch):
    context = _synthetic_video_context()
    synthetic_visual_evidence = _not_observed_visual_evidence()

    def fake_verify_visual_with_stream_context(
        *, input_ref, candidate, analysis_source_streams, target_hint, service=None
    ):
        del input_ref, candidate, analysis_source_streams, target_hint, service
        visual_evidence = dict(synthetic_visual_evidence)
        analysis_run = {
            "run_id": "run_monday_not_observed_fine",
            "operation": "VISUAL_VERIFY",
            "outcome": "SUCCEEDED",
            "usage_refs": [],
            "usage_summary": None,
        }
        return _FakeExecution(
            result=_FakeVisualResult(_DictModel(visual_evidence), _DictModel(analysis_run)),
            selected_video_stream=_FakeSelectedStream(media_stream_ref=context.bootstrap_ref),
        )

    monkeypatch.setattr(
        real_e2e.search_module,
        "verify_visual_with_stream_context",
        fake_verify_visual_with_stream_context,
    )

    spies = _Spies(monkeypatch)
    spies.watch(RecordingService, "resolve_span")
    spies.watch(RecordingService, "build_incident_clip")
    spies.watch(real_e2e.readout_api, "read_plate")
    spies.watch(real_e2e.readout_api, "read_overlay_time")
    spies.watch(real_e2e, "resolve_time")
    spies.watch(real_e2e, "assemble_evidence")
    spies.watch(real_e2e, "calculate_evidence_needs")
    spies.watch(real_e2e, "evaluate_requirements")
    spies.watch(real_e2e, "build_report_package")
    return context, spies


def _candidate_for(context: RealVideoContext) -> search_module.CandidateEvent:
    return search_module.search_candidates(context.scope, service=context.gemini_service).candidates[0]


def test_not_observed_ends_without_a_contract_error(not_observed_video_run):
    context, _ = not_observed_video_run
    candidate = _candidate_for(context)

    bundle = real_e2e.build_evidence_for_real_video_candidate(
        context, candidate, case_id="case_video_not_observed"
    )

    assert bundle.disposition.decision == NOT_ASSEMBLED
    assert bundle.disposition.reason_code == NOT_OBSERVED_REASON
    assert bundle.assembled is False


def test_not_observed_does_not_start_downstream_work(not_observed_video_run):
    """미호출을 결과 추정이 아니라 call count로 증명한다 — 두 번째 `resolve_span()`
    (video 경로 고유)까지 포함해서 전부 0이어야 한다."""
    context, spies = not_observed_video_run
    candidate = _candidate_for(context)

    real_e2e.build_evidence_for_real_video_candidate(
        context, candidate, case_id="case_video_not_observed_spy"
    )

    assert spies.calls == {
        "resolve_span": 0,
        "build_incident_clip": 0,
        "read_plate": 0,
        "read_overlay_time": 0,
        "resolve_time": 0,
        "assemble_evidence": 0,
        "calculate_evidence_needs": 0,
        "evaluate_requirements": 0,
        "build_report_package": 0,
    }


def test_not_observed_produces_no_record_report_or_package(not_observed_video_run):
    context, _ = not_observed_video_run
    candidate = _candidate_for(context)

    bundle = real_e2e.build_evidence_for_real_video_candidate(
        context, candidate, case_id="case_video_not_observed_outputs"
    )

    assert bundle.evidence_record is None
    assert bundle.evidence_needs is None
    assert bundle.requirement_report_evidence is None
    assert bundle.requirement_report_package is None
    assert bundle.report_package is None
    assert bundle.package_error is None


def test_not_observed_preserves_visual_evidence_and_fine_execution(not_observed_video_run):
    context, _ = not_observed_video_run
    candidate = _candidate_for(context)

    bundle = real_e2e.build_evidence_for_real_video_candidate(
        context, candidate, case_id="case_video_not_observed_preserved"
    )

    assert bundle.visual_evidence["verification"] == "NOT_OBSERVED"
    assert bundle.visual_evidence["visual_event_type"] is None
    assert bundle.fine_run["run_id"] == "run_monday_not_observed_fine"
    assert bundle.fine_run["operation"] == "VISUAL_VERIFY"


def test_not_observed_still_invokes_capture_hook(not_observed_video_run):
    """`on_visual_result`는 조립 여부와 무관하게 Fine 응답을 받은 직후 항상 불린다
    (모듈 docstring "Fine 응답을 실제로 받은 직후" — capture-and-replay 용도)."""
    context, _ = not_observed_video_run
    candidate = _candidate_for(context)
    captured = []

    real_e2e.build_evidence_for_real_video_candidate(
        context,
        candidate,
        case_id="case_video_not_observed_hook",
        on_visual_result=lambda visual_result, media_stream_ref: captured.append(
            (visual_result, media_stream_ref)
        ),
    )

    assert len(captured) == 1
    visual_result, media_stream_ref = captured[0]
    assert visual_result.visual_evidence["verification"] == "NOT_OBSERVED"
    assert media_stream_ref == context.bootstrap_ref


def test_real_video_adapter_reports_a_case_without_evidence(monkeypatch, not_observed_video_run):
    """`RealVideoAdapter` getter들이 예외 없이 "아직 없음"을 돌려준다 —
    `RealAdapter`(fixture 경로)와 동일 원칙(`test_not_observed_consumption.py` 참고)."""
    context, _ = not_observed_video_run
    monkeypatch.setattr(real_e2e, "prepare_real_video_context", lambda **kwargs: context)

    case = CaseAggregate.intake(case_id="case_video_not_observed_view", hints={}, manifest_summary={})
    adapter = RealVideoAdapter(
        case_id=case.case_id, case=case, local_video_path="unused", scope_id="scope_unused"
    )

    case.start_search()
    candidates = service.receive_search_candidates(case, adapter)
    assert len(candidates) == 1
    case.select_candidate(candidates[0].candidate_id)

    assert adapter.get_evidence_record() is None
    assert adapter.get_evidence_records() == []
    assert adapter.get_visual_evidence_decision() == "NOT_ASSEMBLED"

    view = service.build_view_from_adapter(case, adapter)
    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["evidence"] is None
    assert [n["code"] for n in view["notices"]] == ["evidence.visual_event_not_observed"]
