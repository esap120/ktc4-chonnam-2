"""등록된 원본 기록 — 분석 시작이 타임라인을 만들 입력(`decisions/start-analysis.md` §3-1)."""

from daesingo.case import service
from daesingo.case.domain import CaseAggregate
from daesingo.case.store import CaseStore


def _asset(ref: str, *, availability: str = "AVAILABLE", duration: float | None = 10.0) -> dict:
    return {"source_asset_ref": ref, "availability": availability, "duration_sec": duration}


def _streams(*types: str) -> list[dict]:
    return [{"media_stream_ref": f"ms_{i}", "media_type": t} for i, t in enumerate(types)]


def test_available_source_is_recorded_with_unique_video_stream():
    case = CaseAggregate.empty("case_src1")
    case.record_source_registered(_asset("sa_1"), _streams("VIDEO", "AUDIO"))
    assert case.sources == [{"source_asset_ref": "sa_1", "video_stream_ref": "ms_0", "duration_sec": 10.0}]


def test_two_video_streams_record_no_stream_ref():
    case = CaseAggregate.empty("case_src2")
    case.record_source_registered(_asset("sa_1"), _streams("VIDEO", "VIDEO"))
    assert case.sources[0]["video_stream_ref"] is None


def test_without_streams_argument_records_no_stream_ref():
    case = CaseAggregate.empty("case_src3")
    case.record_source_registered(_asset("sa_1"))
    assert case.sources == [{"source_asset_ref": "sa_1", "video_stream_ref": None, "duration_sec": 10.0}]


def test_unavailable_source_is_counted_but_not_recorded():
    case = CaseAggregate.empty("case_src4")
    case.record_source_registered(_asset("sa_1", availability="UNAVAILABLE"), _streams("VIDEO"))
    assert case.manifest_summary["file_count"] == 1
    assert case.sources == []


def test_sources_keep_registration_order():
    case = CaseAggregate.empty("case_src5")
    case.record_source_registered(_asset("sa_b"), _streams("VIDEO"))
    case.record_source_registered(_asset("sa_a"), _streams("VIDEO"))
    assert [s["source_asset_ref"] for s in case.sources] == ["sa_b", "sa_a"]


def test_sources_and_description_survive_store_round_trip():
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(case_id, _asset("sa_1"), media_streams=_streams("VIDEO"), store=store)
    case = store.load_for_update(case_id)
    case.description = "흰 SUV"
    store.save(case)
    loaded = store.get_case(case_id)
    assert loaded.sources[0]["video_stream_ref"] == "ms_0"
    assert loaded.description == "흰 SUV"
