"""빈 case 생성 · adapter 없는 등록 · 업로드마다 `manifest_summary` 갱신 (W7 8순위 8-12).

`docs/modules/case/decisions/empty-case-and-manifest.md`.
"""

from __future__ import annotations

import re

import pytest

from daesingo import case as case_package
from daesingo.case import service
from daesingo.case.domain import Candidate, SourceNotAccepted
from daesingo.case.store import CaseStore

EMPTY_MANIFEST = {"file_count": 0, "ok_file_count": 0, "failed_file_count": 0, "duration_sec": 0, "range": None}
EMPTY_HINTS = {"time": None, "vehicle": None, "situation": None, "location": None}


def _source_asset(ref: str, *, availability: str = "AVAILABLE", duration_sec: float | None = 60.0) -> dict:
    return {
        "source_asset_ref": ref,
        "asset_kind": "SOURCE_ASSET",
        "availability": availability,
        "duration_sec": duration_sec,
        "byte_size": 1024 if availability == "AVAILABLE" else None,
    }


def test_create_case_issues_new_ascii_case_id_each_time():
    store = CaseStore()

    first = service.create_case(store=store)
    second = service.create_case(store=store)

    assert re.fullmatch(r"case_[0-9a-f]{32}", first)
    assert first != second


def test_create_case_registers_empty_intake_case_viewable_without_adapter():
    store = CaseStore()

    case_id = service.create_case(store=store)
    view = service.get_view(case_id, store=store)

    assert view["case_id"] == case_id
    assert view["case_rev"] == 1
    assert view["stage"] == "INTAKE"
    assert view["user_reviewed"] is False
    assert view["manifest_summary"] == EMPTY_MANIFEST
    assert view["hints"] == EMPTY_HINTS
    assert view["candidates"] == []
    assert view["evidence"] is None
    assert view["package"] is None


def test_record_source_registered_counts_available_file_and_keeps_case_rev():
    store = CaseStore()
    case_id = service.create_case(store=store)

    service.record_source_registered(case_id, _source_asset("sa_1"), store=store)
    service.record_source_registered(case_id, _source_asset("sa_2"), store=store)
    view = service.get_view(case_id, store=store)

    assert view["manifest_summary"]["file_count"] == 2
    assert view["manifest_summary"]["ok_file_count"] == 2
    assert view["case_rev"] == 1


def test_record_source_registered_counts_unavailable_file_only_in_file_count():
    """`failed_file_count`의 의미는 recording · web과 정하기 전이라(미결) 올리지 않는다."""
    store = CaseStore()
    case_id = service.create_case(store=store)

    service.record_source_registered(case_id, _source_asset("sa_1", availability="UNAVAILABLE", duration_sec=None), store=store)
    manifest = service.get_view(case_id, store=store)["manifest_summary"]

    assert manifest["file_count"] == 1
    assert manifest["ok_file_count"] == 0
    assert manifest["failed_file_count"] == 0


def test_record_source_registered_does_not_compute_duration_or_range():
    """전방 · 후방이 같은 시간대를 찍으면 합산은 틀린 값이다 — 「전체 구간 길이」는 recording timeline 몫."""
    store = CaseStore()
    case_id = service.create_case(store=store)

    service.record_source_registered(case_id, _source_asset("sa_front", duration_sec=600.0), store=store)
    service.record_source_registered(case_id, _source_asset("sa_rear", duration_sec=600.0), store=store)
    manifest = service.get_view(case_id, store=store)["manifest_summary"]

    assert manifest["duration_sec"] == 0
    assert manifest["range"] is None


def test_record_source_registered_rejects_after_intake():
    store = CaseStore()
    case_id = service.create_case(store=store)
    case = store.load_for_update(case_id)
    case.start_search()
    store.save(case)

    with pytest.raises(SourceNotAccepted):
        service.record_source_registered(case_id, _source_asset("sa_late"), store=store)

    assert service.get_view(case_id, store=store)["manifest_summary"]["file_count"] == 0


def test_record_source_registered_unknown_case_is_key_error():
    with pytest.raises(KeyError):
        service.record_source_registered("case_missing", _source_asset("sa_1"), store=CaseStore())


def test_get_view_after_selection_without_adapter_fails_clearly():
    store = CaseStore()
    case_id = service.create_case(store=store)
    case = store.load_for_update(case_id)
    case.start_search()
    case.receive_candidates([Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="", thumb_ref=None, rank=1)])
    case.select_candidate("cand_a")
    store.save(case)

    with pytest.raises(service.AdapterNotAttached):
        service.get_view(case_id, store=store)


def test_create_case_and_record_source_are_exported_from_case_package():
    assert case_package.create_case is service.create_case
    assert case_package.record_source_registered is service.record_source_registered


def test_empty_case_progress_lists_all_steps_pending():
    """CaseView 계약 B절 `progress[]` step 집합 규칙 1 — 도달 전 step은 `PENDING`. 원본은 파일마다 따로
    들어오므로 「다 올렸다」는 분석 시작(INTAKE 이탈)으로만 안다 — 그 전에는 `file_intake`도 `PENDING`."""
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(case_id, _source_asset("sa_1"), store=store)

    progress = service.get_view(case_id, store=store)["progress"]

    assert [p["step"] for p in progress] == [
        "file_intake", "coarse_search", "candidate_review", "plate_read",
        "overlay_time_read", "evidence_assembly", "requirement_check", "package_assembly",
    ]
    assert {p["state"] for p in progress} == {"PENDING"}


def test_file_intake_is_done_once_analysis_starts():
    store = CaseStore()
    case_id = service.create_case(store=store)
    case = store.load_for_update(case_id)
    case.start_search()
    store.save(case)

    progress = service.get_view(case_id, store=store)["progress"]

    assert progress[0] == {"step": "file_intake", "state": "DONE"}
