"""이슈 #73 WARN ① — 정정 후 부분 재실행이 정책 표대로 일어나는지.

`부분 재실행 정책 표 초안 v1`: `EVENT_TIME_MANUAL`·`REPORT_TYPE_CHANGE`는 "제자리, 요건 검사만
다시, 절대 안 건드리는 것: 전부"다. PR #94는 정정 후 evidence가 다시 계산되고 새 `JobRecord`가
생기지 않는 것까지만 확인했다. 그런데 adapter 캐시가 `case_rev`만 보고 evidence 묶음 전체를
다시 만들어서, Job 발주 없이 함수 호출로 Search·Fine·readout이 다시 돌았다(실영상 경로에서는
유료 Fine까지). 여기서는 그 호출 횟수를 직접 센다.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from daesingo.case import adapters, correction, jobs, real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter, RealVideoAdapter
from daesingo.case.domain import Candidate, CaseAggregate

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "happy_001"


def _count_calls(monkeypatch, owner: Any, name: str) -> dict[str, int]:
    """원래 함수를 그대로 부르면서 호출 횟수만 센다(동작은 바꾸지 않는다)."""
    original = getattr(owner, name)
    counter = {"calls": 0}

    def spy(*args, **kwargs):
        counter["calls"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, spy)
    return counter


def _happy_case_with_selection() -> tuple[CaseAggregate, RealAdapter]:
    scope = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID).get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_h001_partial_rerun", hints={}, manifest_summary={})
    real = RealAdapter(
        case_id="case_h001_partial_rerun", case=case, search_scope=scope, mock_root=MOCK_ROOT
    )
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)
    return case, real


def test_evidence_after_selection_does_not_rerun_coarse_search(monkeypatch):
    """정책 표 2행(`OTHER_CANDIDATE`): 선택이 바뀌어도 1차 탐색은 「절대 안 건드리는 것」이다.
    evidence 조립은 선택된 CandidateEvent를 이미 받은 탐색 결과에서 찾아야 한다 — search를 다시
    부르면 실제 search 서비스에서는 영상 전체 Coarse가 다시 돈다(W7 7순위 러너가 찾음).
    `RealVideoAdapter`는 이미 `candidate_id`별로 캐시한다."""
    scope = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID).get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_h001_no_coarse_rerun", hints={}, manifest_summary={})
    real = RealAdapter(case_id=case.case_id, case=case, search_scope=scope, mock_root=MOCK_ROOT)
    search_calls = _count_calls(monkeypatch, adapters.search_module, "search_candidates")
    case.start_search()
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    real.get_evidence_record()

    assert search_calls["calls"] == 1  # receive_search_candidates()의 한 번뿐


def test_event_time_manual_does_not_rerun_search_fine_or_readout(monkeypatch):
    case, real = _happy_case_with_selection()
    search_calls = _count_calls(monkeypatch, adapters.search_module, "search_candidates")
    fine_calls = _count_calls(monkeypatch, real_e2e, "_resolve_via_search_stream_context")
    plate_calls = _count_calls(monkeypatch, real_e2e.readout_api, "read_plate")
    overlay_calls = _count_calls(monkeypatch, real_e2e.readout_api, "read_overlay_time")

    before = real.get_evidence_record()
    counts_before = (
        search_calls["calls"], fine_calls["calls"], plate_calls["calls"], overlay_calls["calls"]
    )
    assert counts_before == (0, 1, 1, 1)  # search는 후보를 받을 때 한 번 — 조립은 다시 부르지 않는다

    corrected_value = "2026-08-24T18:10:00+09:00"
    correction.apply_correction(
        case,
        kind="EVENT_TIME_MANUAL",
        target_field="occurred_at",
        previous_value=before["occurred_at"]["value"],
        new_value=corrected_value,
    )
    after = real.get_evidence_record()
    package_report = real.get_requirement_report("FINAL_PACKAGE")

    assert after["occurred_at"]["value"] == corrected_value
    assert package_report is not None
    assert (
        search_calls["calls"], fine_calls["calls"], plate_calls["calls"], overlay_calls["calls"]
    ) == counts_before


def test_report_type_change_does_not_rerun_fine(monkeypatch):
    case, real = _happy_case_with_selection()
    fine_calls = _count_calls(monkeypatch, real_e2e, "_resolve_via_search_stream_context")

    real.get_evidence_record()
    correction.apply_correction(
        case,
        kind="REPORT_TYPE_CHANGE",
        target_field="event.safety_report_type",
        previous_value="TRAFFIC_VIOLATION",
        new_value="MOTORCYCLE_VIOLATION",
    )
    after = real.get_evidence_record()

    assert after["event"]["safety_report_type"]["value"] == "MOTORCYCLE_VIOLATION"
    assert fine_calls["calls"] == 1


# ── RealVideoAdapter ────────────────────────────────────────────────────
# 실영상 경로는 ffmpeg·유료 Fine·PaddleOCR이 필요해 여기서 실제로 돌릴 수 없다. 관찰 단계
# (Fine·IncidentClip·OCR)와 조립 단계(시각·evidence·요건·Package)를 가짜로 바꿔, adapter가
# 정정 뒤에 관찰 단계를 다시 부르지 않는지만 확인한다.


def _fake_real_video_adapter(monkeypatch) -> tuple[CaseAggregate, RealVideoAdapter, dict[str, list]]:
    case = CaseAggregate.intake(case_id="case_rv_partial_rerun", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates(
        [
            Candidate(candidate_id=cid, at=None, at_provenance=None, observed="", thumb_ref=None)
            for cid in ("cand_a", "cand_b")
        ]
    )
    case.select_candidate("cand_a")

    adapter = RealVideoAdapter(
        case_id="case_rv_partial_rerun", case=case, local_video_path="unused.mp4", scope_id="scope_rv"
    )
    adapter._candidates_by_id = {
        "cand_a": SimpleNamespace(candidate_id="cand_a"),
        "cand_b": SimpleNamespace(candidate_id="cand_b"),
    }
    context = object()
    monkeypatch.setattr(adapter, "_ensure_context", lambda: context)

    calls: dict[str, list] = {"observe": [], "assemble": []}

    def fake_observe(ctx, candidate, **kwargs):
        assert ctx is context
        calls["observe"].append(candidate.candidate_id)
        return SimpleNamespace(candidate_id=candidate.candidate_id)

    def fake_assemble(observations, **kwargs):
        calls["assemble"].append(
            (observations.candidate_id, len(kwargs["correction_records"]), kwargs["selection_rev"])
        )
        record = {"candidate_id": observations.candidate_id}
        return SimpleNamespace(evidence_record=record)

    monkeypatch.setattr(real_e2e, "observe_real_video_candidate", fake_observe)
    monkeypatch.setattr(real_e2e, "assemble_evidence_bundle", fake_assemble)
    return case, adapter, calls


def test_real_video_correction_reassembles_without_new_fine(monkeypatch):
    case, adapter, calls = _fake_real_video_adapter(monkeypatch)

    adapter.get_evidence_record()
    correction.apply_correction(
        case,
        kind="EVENT_TIME_MANUAL",
        target_field="occurred_at",
        previous_value=None,
        new_value="2026-08-24T18:10:00+09:00",
    )
    adapter.get_evidence_record()
    adapter.get_evidence_record()

    assert calls["observe"] == ["cand_a"]
    assert [c[:2] for c in calls["assemble"]] == [("cand_a", 0), ("cand_a", 1)]


def test_real_video_new_selection_of_same_candidate_observes_again(monkeypatch):
    """`TIME_HINT_EDIT` 뒤 재검색에서 같은 candidate_id가 다시 선택돼도 새 선택 context다
    (정책 표: 후보·2차 확인·선택·증거 폐기). `select_candidate()`는 `case_rev`를 올리지 않고
    `selection_rev`만 올리므로 candidate_id만 보면 이전 Fine 결과를 잘못 재사용한다."""
    case, adapter, calls = _fake_real_video_adapter(monkeypatch)

    adapter.get_evidence_record()
    correction.edit_time_hint(case, {"time": "18시 10분쯤"})
    case.receive_candidates(
        [Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="", thumb_ref=None)]
    )
    case.select_candidate("cand_a")
    adapter.get_evidence_record()

    assert calls["observe"] == ["cand_a", "cand_a"]


def test_real_video_other_candidate_observes_again(monkeypatch):
    """다른 후보 선택(`OTHER_CANDIDATE`)은 정책 표상 2차 확인이 다시 도는 경우다."""
    case, adapter, calls = _fake_real_video_adapter(monkeypatch)

    adapter.get_evidence_record()
    correction.reselect_candidate(case, "cand_b")
    record = adapter.get_evidence_record()

    assert calls["observe"] == ["cand_a", "cand_b"]
    assert record["candidate_id"] == "cand_b"


# ── A→B→A 재선택 (decisions/reselect-observation-reuse.md) ─────────────
# 같은 탐색 결과 안에서 이미 관찰한 후보로 돌아오면 관찰(Fine·클립·판독)을 재사용하고, 조립만 현재
# 선택 context(`selection_rev`·그 선택의 정정)로 다시 한다. 후보 목록이 바뀌면(재탐색) 버린다 —
# 그 경우는 위 `test_real_video_new_selection_of_same_candidate_observes_again`.


def test_real_video_return_to_observed_candidate_reuses_observation(monkeypatch):
    case, adapter, calls = _fake_real_video_adapter(monkeypatch)

    adapter.get_evidence_record()
    correction.reselect_candidate(case, "cand_b")
    adapter.get_evidence_record()
    correction.reselect_candidate(case, "cand_a")
    adapter.get_evidence_record()

    assert calls["observe"] == ["cand_a", "cand_b"]
    # 조립은 매번 현재 선택 context로 — A로 돌아온 조립은 새 selection_rev다.
    assert [(c[0], c[2]) for c in calls["assemble"]] == [("cand_a", 1), ("cand_b", 2), ("cand_a", 3)]


def _fake_real_adapter(monkeypatch) -> tuple[CaseAggregate, RealAdapter, dict[str, list]]:
    """`RealAdapter`의 관찰·조립을 가짜로 바꾼다 — 후보 2개짜리 fixture가 없어서."""
    scope = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID).get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_ra_reselect", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates(
        [
            Candidate(candidate_id=cid, at=None, at_provenance=None, observed="", thumb_ref=None)
            for cid in ("cand_a", "cand_b")
        ]
    )
    case.select_candidate("cand_a")
    adapter = RealAdapter(case_id=case.case_id, case=case, search_scope=scope, mock_root=MOCK_ROOT)
    adapter._candidates_by_id = {
        "cand_a": SimpleNamespace(candidate_id="cand_a"),
        "cand_b": SimpleNamespace(candidate_id="cand_b"),
    }
    calls: dict[str, list] = {"observe": [], "assemble": []}

    def fake_observe(*, candidate, **kwargs):
        calls["observe"].append(candidate.candidate_id)
        return SimpleNamespace(candidate_id=candidate.candidate_id)

    def fake_assemble(observations, **kwargs):
        calls["assemble"].append((observations.candidate_id, kwargs["selection_rev"]))
        return SimpleNamespace(evidence_record={"candidate_id": observations.candidate_id})

    monkeypatch.setattr(real_e2e, "observe_fixture_candidate", fake_observe)
    monkeypatch.setattr(real_e2e, "assemble_evidence_bundle", fake_assemble)
    return case, adapter, calls


def test_real_adapter_return_to_observed_candidate_reuses_observation(monkeypatch):
    case, adapter, calls = _fake_real_adapter(monkeypatch)

    adapter.get_evidence_record()
    correction.reselect_candidate(case, "cand_b")
    adapter.get_evidence_record()
    correction.reselect_candidate(case, "cand_a")
    adapter.get_evidence_record()

    assert calls["observe"] == ["cand_a", "cand_b"]
    assert calls["assemble"] == [("cand_a", 1), ("cand_b", 2), ("cand_a", 3)]


def test_real_adapter_drops_observations_when_candidates_are_replaced(monkeypatch):
    """재탐색으로 후보 목록이 바뀌면 같은 candidate_id라도 다시 관찰한다(정책 표 1행)."""
    case, adapter, calls = _fake_real_adapter(monkeypatch)

    adapter.get_evidence_record()
    correction.edit_time_hint(case, {"time": "18시 10분쯤"})
    case.receive_candidates(
        [Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="", thumb_ref=None)]
    )
    case.select_candidate("cand_a")
    adapter.get_evidence_record()

    assert calls["observe"] == ["cand_a", "cand_a"]
