"""`scenario_correction_rerun_001`(사용자가 사건 발생 시각을 수동 정정) 전체 파리티 —
§11 제외 범위였던 시나리오를 두 revision(정정 전 / 정정 후) 모두 `build_case_view()`
공개 API 레벨에서 fixture와 바이트 단위로 비교하고, 동시에 `correction.apply_correction()`을
처음으로 단위 검증한다(`phase1-completion-checklist.md` §3-C에서 테스트 부재로 체크 보류돼
있던 항목).

이 시나리오를 재현하면서 정정한 것:
  - `domain.CaseAggregate.select_candidate()`가 `case_rev`를 올리던 것을 멈췄다 — 이
    fixture의 v1(`case_rev:2`, `EVIDENCE_REVIEW`, correction 이전)로 확인됨: candidate
    선택 자체는 새 요청이 아니라서 case_rev가 안 오른다(`test_domain.py` 참고).
  - `correction.apply_correction()`이 `case.bump_revision()`을 호출하도록 추가 —
    v1(case_rev:2)→v2(case_rev:3, correction 적용 후)로 확인.
  - `event_time_display.info_state`가 `INFO_USER_CONFIRMED`로 오를 때
    `source_label_key`도 `time.source.user_correction`으로 함께 바뀐다 — 이건 evidence가
    만드는 `EvidenceRecord.occurred_at.source`를 그대로 옮기는 것뿐이라 case 코드 변경은
    필요 없었고, fixture 그대로 재현된다(evidence의 supersede 책임).
  - `view.py::_build_candidates_view()`가 evidence 확정 시 `candidates[].at/at_provenance`를
    `occurred_at`으로 덮어쓰던 로직을 제거 — 이 fixture가 바로 그 회귀를 잡아낸 지점이다:
    correction 적용 후 `occurred_at.value/source`는 바뀌지만(정정된 시각으로), candidate
    재선택은 없었으므로 `candidates[].at/at_provenance`는 정정 전후 완전히 고정이어야 한다
    (이슈 #39 Required-3에서 이미 승인된 내용 — "후보 재선택이 없었으니 timeline 위치가
    바뀔 이유가 없습니다").
"""
import json
from pathlib import Path

from daesingo.case import correction, jobs
from daesingo.case.adapters import MockFixtureAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.view import build_case_view

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "correction_rerun_001"


def _load_case_fixture() -> dict:
    path = MOCK_ROOT / "case" / f"scenario_{SCENARIO_ID}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_correction_rerun_before_and_after_match_fixture():
    fixture = _load_case_fixture()
    before_view, after_view = fixture["case_views"]
    assert before_view["stage"] == after_view["stage"] == "EVIDENCE_REVIEW"
    correction_fixture = fixture["correction_records"][0]
    assert correction_fixture["kind"] == "EVENT_TIME_MANUAL"

    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)

    case = CaseAggregate.intake(
        case_id="case_r001",
        hints=before_view["hints"],
        manifest_summary=before_view["manifest_summary"],
    )
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_r001", input_fingerprint="sha1:r001-coarse-search")

    # candidates[].at/at_provenance는 evidence 확정·correction 적용 후에도 view.py가
    # 덮어쓰지 않으므로(2026-09-14 정정) fixture의 최종 값을 직접 공급한다 — 이 값은
    # correction 전후 동일한 Candidate 객체에서 그대로 유지된다.
    raw_candidates = adapter.get_candidate_events()
    candidates = [
        Candidate(
            candidate_id=c["candidate_id"],
            at="2026-08-27T13:15:30+09:00",
            at_provenance="recording.filename_time",
            observed=c["summary"],
            thumb_ref=c["thumbnail_ref"],
            rank=c["rank"],
            representative_ms=c["span"]["representative_ms"],
        )
        for c in raw_candidates
    ]
    case.receive_candidates(candidates)
    case.select_candidate("candidate_r001")

    issued = [
        jobs.issue_plate_read(case, input_fingerprint="sha1:r001-plate-read-clip_r001"),
        jobs.issue_overlay_time_read(case, input_fingerprint="sha1:r001-overlay-read-clip_r001"),
        jobs.issue_fine_verify(case, input_fingerprint="sha1:r001-fine-verify-as_r001_fine"),
    ]
    # 이 시나리오의 v1은 세 job의 결과가 이미 evidence에 반영된 시점이다(8-8이 할 정산을 테스트가 대신한다).
    for job in issued:
        case.settle_job(job["job_id"], "REFLECTED")

    evidence_records = adapter.get_evidence_records()
    evidence_reports = adapter.get_requirement_reports("EVIDENCE")
    assert len(evidence_records) == len(evidence_reports) == 2  # 전제 확인 — v1(정정 전)/v2(정정 후)
    evidence_v1, evidence_v2 = evidence_records
    report_v1, report_v2 = evidence_reports

    # ── v1: 시각 정정 전 (overlay 판독이 없어 filename time이 needs_review로 남음) ──
    view_before = build_case_view(
        case,
        evidence_record=evidence_v1,
        plate_readouts=adapter.get_plate_readouts(),
        requirement_report_evidence=report_v1,
        notices=before_view["notices"],
    )

    assert view_before["stage"] == before_view["stage"]
    assert view_before["case_rev"] == before_view["case_rev"]
    assert view_before["progress"] == before_view["progress"]
    assert view_before["candidates"] == before_view["candidates"]
    assert view_before["evidence"] == before_view["evidence"]
    assert view_before["requirements_evidence"] == before_view["requirements_evidence"]
    assert view_before["requirements_package"] is None
    assert view_before["package"] is None
    assert view_before["running_jobs"] == []
    assert view_before["notices"] == before_view["notices"]

    # ── 사용자 정정 제출 — CorrectionRecord 생성 + case_rev 상승 ──────────────
    record = correction.apply_correction(
        case,
        kind="EVENT_TIME_MANUAL",
        target_field="occurred_at",
        previous_value=correction_fixture["previous_value"],
        new_value=correction_fixture["new_value"],
    )
    assert record["contract"] == "CorrectionRecord"
    assert record["contract_version"] == "correction-record/v1.1"
    assert record["kind"] == "EVENT_TIME_MANUAL"
    assert record["target_field"] == "occurred_at"
    assert record["previous_value"] == correction_fixture["previous_value"]
    assert record["new_value"] == correction_fixture["new_value"]
    assert record["supersedes_ref"] is None  # 이 target_field의 첫 correction
    assert record["selection_rev"] == 1  # select_candidate() 1회 = selection_rev 1
    assert case.correction_records == [record]

    # ── v2: 정정 후 (evidence가 user_correction으로 supersede) ────────────────
    view_after = build_case_view(
        case,
        evidence_record=evidence_v2,
        plate_readouts=adapter.get_plate_readouts(),
        requirement_report_evidence=report_v2,
        notices=after_view["notices"],
    )

    assert view_after["stage"] == after_view["stage"]
    assert view_after["case_rev"] == after_view["case_rev"]
    assert view_after["progress"] == after_view["progress"]
    assert view_after["candidates"] == after_view["candidates"]
    assert view_after["evidence"] == after_view["evidence"]
    assert view_after["requirements_evidence"] == after_view["requirements_evidence"]
    assert view_after["requirements_package"] is None
    assert view_after["package"] is None
    assert view_after["running_jobs"] == []
    assert view_after["notices"] == after_view["notices"]

    # 정정이 무관한 값(번호판, candidate 위치)을 리셋하지 않는다 — 이슈 #39 교훈.
    assert view_after["evidence"]["plate_display"] == view_before["evidence"]["plate_display"]
    assert view_after["candidates"] == view_before["candidates"]
