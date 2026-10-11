"""`correction_log.export_learning_log()` — `correction-log-reuse.md`의 익명화 최소 규칙
3개(번호판 문자열 제거/정확한 좌표 제거/영상 참조는 로컬 case_id로만)를 지키는지 검증한다.

`vehicle_number`/`location.coord` target의 CorrectionRecord 예시는 현재 mock pack에
하나도 없어(모듈 docstring 참고) 이 테스트는 fixture 정답지가 아니라 계약이 정한 값
공간(§6)을 직접 구성한 합성(synthetic) 데이터로 검증한다. `occurred_at` 대상은 실제
`scenario_correction_rerun_001` fixture의 CorrectionRecord로 "이 3줄이 요구하지 않는
필드는 그대로 내보낸다"를 확인한다.
"""
import json
from pathlib import Path

from daesingo.case import correction
from daesingo.case.correction_log import export_learning_log
from daesingo.case.domain import Candidate, CaseAggregate

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"


def _make_case() -> CaseAggregate:
    """값 정정은 후보를 고른 뒤에만 받으므로(`correction.apply_correction()`) 선택까지 마친 case."""
    case = CaseAggregate.intake(case_id="case_log001", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates([Candidate(candidate_id="c1", at="t", at_provenance="p", observed="o", thumb_ref="f")])
    case.select_candidate("c1")
    return case


def test_vehicle_number_correction_redacts_plate_keeps_length_and_diff_positions():
    case = _make_case()
    correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="12가 3476", new_value="12가 3475",
    )

    [entry] = export_learning_log(case)
    assert entry["target_field"] == "vehicle_number"
    assert "12가 3476" not in json.dumps(entry, ensure_ascii=False)
    assert "12가 3475" not in json.dumps(entry, ensure_ascii=False)
    assert entry["previous_value"] == {"length": len("12가 3476")}
    assert entry["new_value"] == {"length": len("12가 3475")}
    assert entry["diff_positions"] == [len("12가 3476") - 1]  # 마지막 문자 1개만 다르다


def test_location_coord_correction_redacts_coords_keeps_error_radius():
    case = _make_case()
    correction.apply_correction(
        case, kind="OTHER_CANDIDATE", target_field="location.coord",
        previous_value={"lat": 37.5665, "lon": 126.9780},
        new_value={"lat": 37.5651, "lon": 126.9895},
    )

    [entry] = export_learning_log(case)
    assert entry["target_field"] == "location.coord"
    assert entry["previous_value"] is None
    assert entry["new_value"] is None
    assert entry["error_radius_m"] is not None
    assert entry["error_radius_m"] > 0
    assert "37.5665" not in json.dumps(entry)
    assert "126.978" not in json.dumps(entry)


def test_occurred_at_correction_passes_through_unredacted_from_real_fixture():
    path = MOCK_ROOT / "case" / "scenario_correction_rerun_001.json"
    with open(path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    correction_fixture = fixture["correction_records"][0]

    case = _make_case()
    correction.apply_correction(
        case, kind="EVENT_TIME_MANUAL", target_field="occurred_at",
        previous_value=correction_fixture["previous_value"],
        new_value=correction_fixture["new_value"],
    )

    [entry] = export_learning_log(case)
    assert entry["target_field"] == "occurred_at"
    assert entry["previous_value"] == correction_fixture["previous_value"]
    assert entry["new_value"] == correction_fixture["new_value"]
    assert entry["case_id"] == case.case_id  # 원본 영상 참조가 아니라 로컬 case_id만


def test_export_is_empty_when_no_corrections():
    case = _make_case()
    assert export_learning_log(case) == []


def test_export_preserves_selection_rev_and_supersede_chain():
    case = _make_case()
    case.selection_rev = 2
    first = correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="11가 1111", new_value="11가 1112",
    )
    second = correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="11가 1112", new_value="11가 1113",
    )

    entries = export_learning_log(case)
    assert len(entries) == 2
    assert entries[0]["selection_rev"] == entries[1]["selection_rev"] == 2
    assert entries[0]["supersedes_id"] is None
    assert entries[1]["supersedes_id"] == first["correction_id"] == entries[0]["correction_id"]
    assert entries[1]["correction_id"] == second["correction_id"]
