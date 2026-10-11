"""`scenario_plate_reread_001`(번호판 판독 abstain → 자동 재판독 → 성공) 전체 파리티 —
§11 제외 범위였던 시나리오를 두 revision(재판독 발주 직후 / 재판독 성공 후) 모두
`build_case_view()` 공개 API 레벨에서 fixture와 바이트 단위로 비교한다.

이 시나리오를 재현하면서 고친 결함/추가한 것:
  - `vehicle_number`도 `location`처럼 `EvidenceRecord`에 **키 자체가 없을 수** 있다
    (번호판 abstain, `ev_p001`) — `evidence_record["vehicle_number"]`가 `KeyError`를
    던지던 결함을 `.get()` 방어로 고쳤다(`view.py::_field_states`/`_build_evidence_view`).
  - `domain.CaseAggregate.bump_revision()` 신설 — `case_rev`가 stage 전이 없이도
    오르는 경우(증거가 v1→v2로 supersede될 때)를 위한 범용 카운터. 이 fixture의
    rev1(case_rev:3, 재판독 PENDING)→rev2(case_rev:4, 재판독 완료)가 stage 변화
    없이 case_rev만 오르는 것으로 확인됨.
  - `MockFixtureAdapter.get_evidence_records()`/`get_requirement_reports()` 신설 —
    supersede 체인(v1/v2)을 순서대로 읽으려면 기존 "첫 건만" 메서드로는 부족했다.
  - `stage`는 끝까지 `EVIDENCE_REVIEW`에 머문다(`READY` 아님) — `EVIDENCE_SUFFICIENT=true`
    이지만 `PACKAGE_READY`는 별도 gate라는 `phase1-completion-checklist.md` §6 설명 그대로.
    `report_video_export`가 아예 발주되지 않으므로 `mark_ready()`를 호출하지 않는다.

  - `candidates[].at/at_provenance`는 evidence가 조립돼도 occurred_at으로 덮어쓰지
    않는다(2026-09-14 정정, `scenario_correction_rerun_001`로 발견 — 이슈 #39
    Required-3 재확인). 이 세션 중간에 한 번 "fixture 결함"이라고 잘못 판단해서
    `candidates[].at_provenance`를 `readout.overlay_ocr`로 고쳤던 적이 있는데,
    `scenario_correction_rerun_001`이 "candidate 재선택 없이 evidence만 바뀌어도
    at/at_provenance는 고정"이라는 걸 명확히 보여줘서 그 fixture 수정은 되돌렸다 —
    두 revision 모두 원래 값 그대로 `recording.filename_time`이 맞다.
"""
import json
from pathlib import Path

from daesingo.case import jobs
from daesingo.case.adapters import MockFixtureAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.view import build_case_view

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "plate_reread_001"


def _load_case_fixture() -> dict:
    path = MOCK_ROOT / "case" / f"scenario_{SCENARIO_ID}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _build_case_and_candidate(adapter: MockFixtureAdapter, hints: dict, manifest_summary: dict) -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_p001", hints=hints, manifest_summary=manifest_summary)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_p001", input_fingerprint="sha1:p001-coarse-search")

    # candidates[].at/at_provenance는 evidence 확정 후에도 view.py가 덮어쓰지 않으므로
    # (2026-09-14 정정) 여기서 fixture의 최종 값을 직접 공급한다.
    raw_candidates = adapter.get_candidate_events()
    candidates = [
        Candidate(
            candidate_id=c["candidate_id"],
            at="2026-08-29T20:10:12+09:00",
            at_provenance="recording.filename_time",
            observed=c["summary"],
            thumb_ref=c["thumbnail_ref"],
            rank=c["rank"],
            representative_ms=c["span"]["representative_ms"],
        )
        for c in raw_candidates
    ]
    case.receive_candidates(candidates)
    case.select_candidate("candidate_p001")
    return case


def test_plate_reread_pending_and_resolved_match_fixture():
    fixture = _load_case_fixture()
    pending_view, resolved_view = fixture["case_views"]
    assert pending_view["stage"] == resolved_view["stage"] == "EVIDENCE_REVIEW"

    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    case = _build_case_and_candidate(adapter, pending_view["hints"], pending_view["manifest_summary"])

    first_jobs = [
        jobs.issue_plate_read(case, input_fingerprint="sha1:p001-plate-read-clip_p001"),
        jobs.issue_overlay_time_read(case, input_fingerprint="sha1:p001-overlay-read-clip_p001"),
        jobs.issue_fine_verify(case, input_fingerprint="sha1:p001-fine-verify-as_p001_fine"),
    ]
    # v1은 처음 세 job의 결과(번호판 abstain 포함)가 이미 evidence에 반영된 시점이다 — 8-8이 할 정산을
    # 테스트가 대신한다.
    for job in first_jobs:
        case.settle_job(job["job_id"], "REFLECTED")

    evidence_records = adapter.get_evidence_records()
    evidence_reports = adapter.get_requirement_reports("EVIDENCE")
    assert len(evidence_records) == len(evidence_reports) == 2  # 전제 확인 — v1(abstain)/v2(재판독 성공)

    # ── v1: 번호판 abstain → 자동 재판독 발주(force_rerun=true) ──────────────
    evidence_v1, evidence_v2 = evidence_records
    report_v1, report_v2 = evidence_reports
    assert "vehicle_number" not in evidence_v1  # 전제 확인 — location과 같은 방식(키 부재)의 abstain

    # `jobs.issue_plate_reread()`를 직접 호출하지 않고 실제 `EvidenceNeeds.items` →
    # Job Intent 자동 매핑 경로(`jobs.issue_needed_jobs()`)를 통해 재판독을 발주한다 —
    # evidence가 만든 Need를 case가 실제로 소비한다는 것까지 이 fixture로 검증한다.
    evidence_needs_v1, evidence_needs_v2 = adapter.get_evidence_needs()
    assert [item["kind"] for item in evidence_needs_v1["items"]] == ["PLATE_REREAD"]
    assert evidence_needs_v2["items"] == []  # 재판독 성공 후에는 더 이상 Need가 없다
    reread_jobs = jobs.issue_needed_jobs(case, evidence_needs_v1)
    assert len(reread_jobs) == 1
    reread_job = reread_jobs[0]

    view_pending = build_case_view(
        case,
        evidence_record=evidence_v1,
        plate_readouts=adapter.get_plate_readouts(),
        requirement_report_evidence=report_v1,
        notices=pending_view["notices"],
    )

    assert view_pending["stage"] == pending_view["stage"]
    assert view_pending["case_rev"] == pending_view["case_rev"]
    assert view_pending["progress"] == pending_view["progress"]
    assert view_pending["candidates"] == pending_view["candidates"]
    assert view_pending["evidence"] == pending_view["evidence"]
    assert view_pending["requirements_evidence"] == pending_view["requirements_evidence"]
    assert view_pending["requirements_package"] is None
    assert view_pending["package"] is None
    # job_id는 `CaseAggregate.next_job_id()`가 매번 새 uuid로 발급하는 값이라(§3-B, 항상
    # 새 job_id) fixture의 고정 문자열과 같을 수 없다 — job_id를 뺀 나머지 필드만 비교한다
    # (`test_scenario_happy_smoke.py`의 rev1 테스트도 같은 이유로 running_jobs를 fixture와
    # 직접 비교하지 않고 실제 생성된 job_id로 직접 구성한다).
    assert [{k: v for k, v in j.items() if k != "job_id"} for j in view_pending["running_jobs"]] == [
        {k: v for k, v in j.items() if k != "job_id"} for j in pending_view["running_jobs"]
    ]
    assert view_pending["notices"] == pending_view["notices"]

    # ── v2: 재판독 성공 → EvidenceRecord supersede, case_rev만 오르고 stage는 그대로 ──
    case.bump_revision()
    case.settle_job(reread_job["job_id"], "REFLECTED")  # 재판독 결과 반영(8-8이 할 정산을 테스트가 대신)

    view_resolved = build_case_view(
        case,
        evidence_record=evidence_v2,
        plate_readouts=adapter.get_plate_readouts(),
        requirement_report_evidence=report_v2,
        notices=resolved_view["notices"],
    )

    assert view_resolved["stage"] == resolved_view["stage"]
    assert view_resolved["case_rev"] == resolved_view["case_rev"]
    assert view_resolved["progress"] == resolved_view["progress"]
    assert view_resolved["candidates"] == resolved_view["candidates"]
    assert view_resolved["evidence"] == resolved_view["evidence"]
    assert view_resolved["requirements_evidence"] == resolved_view["requirements_evidence"]
    assert view_resolved["requirements_package"] is None
    assert view_resolved["package"] is None
    assert view_resolved["running_jobs"] == []
    assert view_resolved["notices"] == resolved_view["notices"]
