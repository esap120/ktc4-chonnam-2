"""W5/W6 데드라인 증빙: `scenario_happy_001` 대표 시나리오가 recording→search→readout→
evidence→`CaseView`까지 **전부 real 함수 호출로** 통과하는지 확인한다.

`test_scenario_happy_smoke.py`/`test_service.py`가 `MockFixtureAdapter`로 같은 시나리오를
검증하는 것과 짝을 이룬다 — 이 파일은 "같은 계약 모양이 나오는가"가 아니라 "실제 모듈
호출 체인이 안 끊기고 끝까지 도는가"를 확인한다. 그래서 mock 정답지와 완전히 같은 값을
요구하지 않는다 — id는 이 실행에서 새로 생성되고, `situation_response`/`observation_facts`가
없어(real_e2e.py 「알려진 단순화 2」) `package`는 `None`일 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from daesingo import search as search_module
from daesingo.case import correction, jobs, real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.recording import AssetSpan, MediaStream, SpanResolution, TimeRange, TimelineRef

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "happy_001"


def _real_scope():
    mock = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    return mock.get_analysis_scopes()[0]


def _real_hints():
    return MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID).get_hints()


def _span(*, sequence: int, media_stream_ref: str) -> AssetSpan:
    return AssetSpan(
        sequence=sequence,
        timeline_range=TimeRange(start_sec=0.0, end_sec=10.0),
        source_asset_ref="sa_multi",
        media_stream_ref=media_stream_ref,
        source_range=TimeRange(start_sec=0.0, end_sec=10.0),
    )


def _resolution(*spans: AssetSpan) -> SpanResolution:
    return SpanResolution(
        contract="SpanResolution",
        contract_version="span-resolution/v1.2",
        timeline_ref=TimelineRef(timeline_id="tl_multi", revision=1),
        requested_range=TimeRange(start_sec=0.0, end_sec=10.0),
        status="COMPLETE",
        spans=list(spans),
        missing_ranges=[],
        failure=None,
    )


def test_select_asset_span_returns_only_span_without_ref():
    """단일 stream만 있을 때는 지금까지처럼 media_stream_ref 없이도 그 span을 쓴다."""
    resolution = _resolution(_span(sequence=0, media_stream_ref="ms_front"))

    selected = real_e2e._select_asset_span(resolution, None)

    assert selected.media_stream_ref == "ms_front"


def test_select_asset_span_matches_requested_ref():
    """여러 stream이 같은 시간대를 가리켜도, 지정한 media_stream_ref와 일치하는
    span만 명시적으로 골라 쓴다 — `spans[0]`을 조용히 쓰지 않는다."""
    resolution = _resolution(
        _span(sequence=0, media_stream_ref="ms_rear"),
        _span(sequence=1, media_stream_ref="ms_front"),
    )

    selected = real_e2e._select_asset_span(resolution, "ms_front")

    assert selected.media_stream_ref == "ms_front"


def test_select_asset_span_raises_when_ambiguous_without_ref():
    """여러 span이 있는데 media_stream_ref를 안 주면 `spans[0]`으로 조용히 넘어가지
    않고 명확히 실패한다."""
    resolution = _resolution(
        _span(sequence=0, media_stream_ref="ms_rear"),
        _span(sequence=1, media_stream_ref="ms_front"),
    )

    with pytest.raises(real_e2e.StreamSelectionError):
        real_e2e._select_asset_span(resolution, None)


def test_select_asset_span_raises_when_ref_has_no_match():
    """요청한 media_stream_ref가 어떤 span에도 없으면 실패한다."""
    resolution = _resolution(_span(sequence=0, media_stream_ref="ms_front"))

    with pytest.raises(real_e2e.StreamSelectionError):
        real_e2e._select_asset_span(resolution, "ms_unknown")


def _media_stream(*, ref: str, media_type: str, source_asset_ref: str = "sa_multi") -> MediaStream:
    return MediaStream(
        contract="MediaStream",
        contract_version="source-asset-media-stream/v1",
        media_stream_ref=ref,
        source_asset_ref=source_asset_ref,
        media_type=media_type,
        role="UNKNOWN" if media_type == "VIDEO" else None,
        availability="AVAILABLE",
        duration_sec=1200.0,
    )


def test_unique_video_media_stream_ref_returns_the_only_video():
    """정철원 확인(2026-09-21) — VIDEO 1개/AUDIO 1개뿐인 월요일 대표 파일 케이스."""
    streams = [
        _media_stream(ref="ms_video", media_type="VIDEO"),
        _media_stream(ref="ms_audio", media_type="AUDIO"),
    ]

    assert real_e2e._unique_video_media_stream_ref(streams) == "ms_video"


def test_unique_video_media_stream_ref_raises_when_no_video():
    streams = [_media_stream(ref="ms_audio", media_type="AUDIO")]

    with pytest.raises(real_e2e.StreamSelectionError):
        real_e2e._unique_video_media_stream_ref(streams)


def test_unique_video_media_stream_ref_raises_when_multiple_video():
    """복수 카메라(front/rear)는 W7 후속 — case가 임의로 고르지 않고 실패한다."""
    streams = [
        _media_stream(ref="ms_front", media_type="VIDEO"),
        _media_stream(ref="ms_rear", media_type="VIDEO"),
    ]

    with pytest.raises(real_e2e.StreamSelectionError):
        real_e2e._unique_video_media_stream_ref(streams)


def test_match_analysis_source_streams_builds_analysis_source_stream_tuple():
    import daesingo.search as search_module

    streams = [
        _media_stream(ref="ms_video", media_type="VIDEO"),
        _media_stream(ref="ms_audio", media_type="AUDIO"),
    ]

    result = real_e2e._match_analysis_source_streams(["ms_video"], streams)

    assert len(result) == 1
    assert isinstance(result[0], search_module.AnalysisSourceStream)
    assert result[0].media_stream_ref == "ms_video"
    assert result[0].media_type == "VIDEO"


def test_match_analysis_source_streams_raises_when_ref_missing():
    """AnalysisSource가 참조하는 ref가 등록된 media_streams에 없으면 fixture로
    보정하지 않고 실패한다(정철원 확인, 2026-09-21)."""
    streams = [_media_stream(ref="ms_video", media_type="VIDEO")]

    with pytest.raises(real_e2e.StreamSelectionError):
        real_e2e._match_analysis_source_streams(["ms_missing"], streams)


def test_match_analysis_source_streams_raises_when_ref_duplicated():
    streams = [
        _media_stream(ref="ms_video", media_type="VIDEO"),
        _media_stream(ref="ms_video", media_type="VIDEO"),
    ]

    with pytest.raises(real_e2e.StreamSelectionError):
        real_e2e._match_analysis_source_streams(["ms_video"], streams)


def test_evidence_bundle_uses_real_plate_and_time_values():
    """readout/search/recording을 실제로 호출해서 나온 값이지, mock JSON을 베낀 게
    아니라는 걸 값으로 확인한다 — 세 값 다 `data/mock/readout/scenario_happy_001.json`과
    같지만, 이번엔 `readout.read_plate()`/`read_overlay_time()`을 실제로 실행해서 나온
    결과다(`real_e2e.build_fixture_evidence_bundle` 내부에서 fixture JSON을 읽지 않음
    — 예외는 모듈 docstring에 적은 time_source_candidates 한 곳뿐)."""
    import daesingo.search as search_module

    scope_dict = _real_scope()
    scope = search_module.AnalysisScope.model_validate(scope_dict)
    candidate = search_module.search_candidates(scope).candidates[0]

    bundle = real_e2e.build_fixture_evidence_bundle(
        case_id="case_h001_bundle_test", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )

    assert bundle.evidence_record["vehicle_number"]["value"] == "12가3456"
    assert bundle.evidence_record["occurred_at"]["value"] == "2026-08-24T18:05:12+09:00"
    assert bundle.requirement_report_evidence["scope"] == "EVIDENCE"
    assert bundle.requirement_report_package["scope"] == "FINAL_PACKAGE"
    # 알려진 단순화 2(situation_response/observation_facts 없음) 때문에 package는 못
    # 만들 수 있다 — 이게 조용한 실패가 아니라 사유가 남는다는 것까지 확인한다.
    if bundle.report_package is None:
        assert bundle.package_error is not None


def test_evidence_bundle_wires_search_stream_context(monkeypatch):
    """`search.verify_visual_with_stream_context`(서어진, 2026-09-21 합의)가 아직
    어느 브랜치에도 push되지 않아서, 여기서는 합의된 계약대로 동작하는 스텁으로
    case 쪽 배선만 검증한다 — search가 실제로 push되면 이 스텁을 지우고 real
    호출로 교체한다. 확인하는 것: ① `AnalysisSourceStream`을
    `analysis_source.media_stream_refs`·`fixture.media_streams`로부터 만드는지
    ② `target_hint`를 그대로 전달하는지 ③ 돌려받은 `selected_video_stream`으로
    두 번째 span 선택을 좁혀도 회귀 없이 끝까지 도는지."""
    import daesingo.search as search_module

    @dataclass
    class _FakeAnalysisSourceStream:
        media_stream_ref: str
        media_type: str

    @dataclass
    class _FakeSelectedStream:
        media_stream_ref: str

    @dataclass
    class _FakeExecution:
        result: Any
        selected_video_stream: _FakeSelectedStream

    captured: dict[str, Any] = {}

    def _fake_verify_visual_with_stream_context(
        *, input_ref, candidate, analysis_source_streams, target_hint, service=None
    ):
        captured["input_ref"] = input_ref
        captured["candidate"] = candidate
        captured["analysis_source_streams"] = analysis_source_streams
        captured["target_hint"] = target_hint
        captured["service"] = service
        video_streams = [s for s in analysis_source_streams if s.media_type == "VIDEO"]
        assert len(video_streams) == 1  # 서어진의 합의대로 — VIDEO가 정확히 하나일 때만 선택
        real_result = search_module.verify_visual(input_ref, target_hint)
        return _FakeExecution(
            result=real_result,
            selected_video_stream=_FakeSelectedStream(
                media_stream_ref=video_streams[0].media_stream_ref
            ),
        )

    monkeypatch.setattr(
        search_module, "AnalysisSourceStream", _FakeAnalysisSourceStream, raising=False
    )
    monkeypatch.setattr(
        search_module,
        "verify_visual_with_stream_context",
        _fake_verify_visual_with_stream_context,
        raising=False,
    )

    scope_dict = _real_scope()
    scope = search_module.AnalysisScope.model_validate(scope_dict)
    candidate = search_module.search_candidates(scope).candidates[0]

    bundle = real_e2e.build_fixture_evidence_bundle(
        case_id="case_h001_stream_context_test", candidate=candidate, scope=scope, mock_root=MOCK_ROOT
    )

    assert captured["target_hint"] == scope.hint
    assert captured["analysis_source_streams"]
    assert all(
        isinstance(s, _FakeAnalysisSourceStream) for s in captured["analysis_source_streams"]
    )
    assert bundle.evidence_record["vehicle_number"]["value"] == "12가3456"


def test_real_adapter_caches_evidence_bundle():
    """evidence 체인(recording/readout/evidence 여러 호출)은 비용이 있으니, 같은
    `RealAdapter` 인스턴스에서 여러 getter를 불러도 한 번만 계산해야 한다."""
    scope = _real_scope()
    case = CaseAggregate.intake(case_id="case_h001_cache_test", hints={}, manifest_summary={})
    case.start_search()
    real = RealAdapter(case_id="case_h001_cache_test", case=case, search_scope=scope, mock_root=MOCK_ROOT)
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    record_first = real.get_evidence_record()
    record_second = real.get_evidence_record()
    assert record_first is record_second  # 같은 객체 — 재계산 안 했다는 뜻


def test_real_adapter_requires_selected_candidate_before_evidence():
    """2026-09-19 수정 — evidence가 case의 실제 선택값을 쓰게 바꾸면서 생긴 안전장치.
    candidate를 아직 선택하지 않은 case로 evidence를 조회하면 조용히 아무 값이나
    돌려주지 않고 명확히 실패해야 한다(Mock의 정직한 실패 원칙과 동일 — 이전엔
    `search.search_candidates()`를 자체적으로 다시 불러 항상 값을 돌려줬었다)."""
    scope = _real_scope()
    case = CaseAggregate.intake(case_id="case_h001_no_selection", hints={}, manifest_summary={})
    case.start_search()
    real = RealAdapter(case_id="case_h001_no_selection", case=case, search_scope=scope, mock_root=MOCK_ROOT)
    service.receive_search_candidates(case, real)  # CANDIDATE_REVIEW까지만, 선택은 안 함

    with pytest.raises(NotImplementedError, match="선택된"):
        real.get_evidence_record()


def test_real_adapter_recomputes_evidence_after_event_time_manual_correction():
    """EVENT_TIME_MANUAL 정정 뒤 evidence가 최신 correction을 반영해 다시 계산되는지 확인한다."""
    scope = _real_scope()
    case = CaseAggregate.intake(
        case_id="case_h001_correction_rerun", hints={}, manifest_summary={}
    )
    real = RealAdapter(
        case_id="case_h001_correction_rerun",
        case=case,
        search_scope=scope,
        mock_root=MOCK_ROOT,
    )
    case.start_search()
    jobs.issue_coarse_search(
        case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search"
    )
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    record_before = real.get_evidence_record()
    jobs_before = list(case.job_records)
    corrected_value = "2026-08-24T18:10:00+09:00"
    correction.apply_correction(
        case,
        kind="EVENT_TIME_MANUAL",
        target_field="occurred_at",
        previous_value=record_before["occurred_at"]["value"],
        new_value=corrected_value,
    )
    assert case.job_records == jobs_before

    record_after = real.get_evidence_record()
    assert record_after is not record_before
    assert record_after["occurred_at"]["value"] == corrected_value
    assert record_after["occurred_at"]["user_corrected"] is True
    assert record_after["occurred_at"]["source"]["kind"] == "case.user_correction"
    assert record_after["vehicle_number"]["value"] == record_before["vehicle_number"]["value"]
    assert real.get_evidence_record() is record_after


def test_real_adapter_recomputes_evidence_after_report_type_change_correction():
    """REPORT_TYPE_CHANGE도 같은 correction 배선으로 반영되는지 확인한다."""
    scope = _real_scope()
    case = CaseAggregate.intake(
        case_id="case_h001_report_type_change", hints={}, manifest_summary={}
    )
    real = RealAdapter(
        case_id="case_h001_report_type_change",
        case=case,
        search_scope=scope,
        mock_root=MOCK_ROOT,
    )
    case.start_search()
    jobs.issue_coarse_search(
        case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search"
    )
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    record_before = real.get_evidence_record()
    jobs_before = list(case.job_records)
    correction.apply_correction(
        case,
        kind="REPORT_TYPE_CHANGE",
        target_field="event.safety_report_type",
        previous_value="TRAFFIC_VIOLATION",
        new_value="MOTORCYCLE_VIOLATION",
    )
    assert case.job_records == jobs_before

    record_after = real.get_evidence_record()
    assert record_after["event"]["safety_report_type"]["value"] == "MOTORCYCLE_VIOLATION"
    assert record_after["event"]["safety_report_type"]["user_corrected"] is True
    assert (
        record_after["event"]["safety_report_type"]["source"]["kind"]
        == "case.user_correction"
    )


def test_real_e2e_happy_path_reaches_ready_caseview():
    """recording→search→후보 선택→readout→evidence 전부 real로 돌려서 `CaseView`까지
    도달하는지 확인한다 — 이번 W5/W6 마감의 증빙 테스트다.

    `READY`는 Package가 실제로 준비됐을 때만이다(#167). 상황 응답 전에는 ADR-EVIDENCE-005
    D2-c로 Package가 막혀 `EVIDENCE_REVIEW`에 머문다."""
    scope = _real_scope()
    case = CaseAggregate.intake(case_id="case_h001_full_e2e", hints=_real_hints(), manifest_summary={})
    real = RealAdapter(case_id="case_h001_full_e2e", case=case, search_scope=scope, mock_root=MOCK_ROOT)

    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")

    candidates = service.receive_search_candidates(case, real)
    assert len(candidates) == 1
    case.select_candidate(candidates[0].candidate_id)
    assert case.selection_rev == 1  # RealAdapter가 이 값을 그대로 evidence에 넘긴다(2026-09-19)

    jobs.issue_plate_read(case, input_fingerprint="sha1:h001-plate-read-clip_h001")
    jobs.issue_overlay_time_read(case, input_fingerprint="sha1:h001-overlay-read-clip_h001")
    jobs.issue_fine_verify(case, input_fingerprint="sha1:h001-fine-verify-as_h001_fine")
    jobs.issue_report_video_export(case, input_fingerprint="sha1:h001-report-video-export")
    service.mark_ready_if_package_ready(case, real)

    view = service.build_view_from_adapter(case, real)

    # READY ⇔ Package 존재(#167). 상황 응답 전이라 지금은 둘 다 아니다.
    assert (view["stage"] == "READY") == (view["package"] is not None)
    assert view["stage"] == "EVIDENCE_REVIEW"
    assert view["evidence"]["plate_display"]["value"] == "12가3456"
    assert view["evidence"]["event_time_display"]["value"] == "2026-08-24T18:05:12+09:00"
    assert view["evidence"]["location_display"]["value"] == "상무중앙로 사거리 부근"
    assert view["evidence"]["location_display"]["coord"] is None
    assert view["requirements_evidence"]["readiness"] == "PASS"
    # 이슈 #103 — hints가 더 이상 {}로 고정되지 않는다.
    assert view["hints"] != {}
    # package는 알려진 단순화 2 때문에 None일 수 있다 — 존재 자체를 요구하지 않는다.
    assert view["package"] is None or "package_ref" in view["package"]


def test_real_adapter_runs_other_scenario():
    """시나리오 이름은 recording fixture 로드에만 쓴다 — search · readout은 값으로 찾는다."""
    mock = MockFixtureAdapter(MOCK_ROOT, "correction_rerun_001")
    scope = mock.get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_r001_real", hints=mock.get_hints(), manifest_summary={})
    real = RealAdapter(
        case_id="case_r001_real",
        case=case,
        search_scope=scope,
        mock_root=MOCK_ROOT,
        scenario_id="scenario_correction_rerun_001",
    )
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref=scope["scope_id"], input_fingerprint="f")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)

    view = service.build_view_from_adapter(case, real)

    assert view["evidence"]["plate_display"]["value"] == "34나7890"


def test_single_analysis_source_is_required(monkeypatch):
    """AnalysisSource가 하나가 아니면 `[0]`을 조용히 쓰지 않는다."""
    fixture = real_e2e.load_recording_fixture(real_e2e.DEFAULT_SCENARIO_ID)
    doubled = fixture.model_copy(update={"analysis_sources": fixture.analysis_sources * 2})
    monkeypatch.setattr(real_e2e, "load_recording_fixture", lambda _sid: doubled)
    scope = search_module.AnalysisScope.model_validate(_real_scope())
    candidate = search_module.search_candidates(scope).candidates[0]

    with pytest.raises(ValueError, match="AnalysisSource"):
        real_e2e.observe_fixture_candidate(case_id="c", candidate=candidate, scope=scope, mock_root=MOCK_ROOT)
