"""1차 구현 최소 기준: 공용 Fixture로 Happy Path 1개(scenario_happy_001)를 재현한다.

recording/search/readout/evidence는 아직 코드가 없으므로 `MockFixtureAdapter`로 그
모듈들의 산출물(Canonical Contract 모양)을 대신 읽는다 — case 코드 자체는 이 어댑터
인터페이스만 알고, 실제 구현이 생기면 이 어댑터만 교체하면 된다.

비교 대상: `data/mock/case/scenario_happy_001.json`의 `case_views[]`(case 자신의
Producer fixture, 정답지 역할). 이 테스트가 통과한다는 것은 "문서와 Mock JSON만 준비된
상태"가 아니라 실제 코드가 그 계약을 재현한다는 뜻이다.
"""
import json
from pathlib import Path

from daesingo.case import jobs, service
from daesingo.case.adapters import MockFixtureAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.view import build_case_view

# repo_root/data/mock — 이 값은 다른 테스트 파일과 얽히지 않게 이 파일에서 직접 계산한다
# (테스트 파일 간 relative import를 피한다).
MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"

SCENARIO_ID = "happy_001"


def _load_case_fixture() -> dict:
    path = MOCK_ROOT / "case" / f"scenario_{SCENARIO_ID}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_happy_path_rev1_searching_matches_fixture():
    fixture = _load_case_fixture()
    rev1 = fixture["case_views"][0]
    assert rev1["stage"] == "SEARCHING"

    case = CaseAggregate.intake(
        case_id=rev1["case_id"],
        hints=rev1["hints"],
        manifest_summary=rev1["manifest_summary"],
    )
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")

    view = build_case_view(
        case,
        job_executions=[{"job_id": case.job_records[0]["job_id"], "attempt": 1, "status": "RUNNING"}],
    )

    assert view["stage"] == rev1["stage"]
    assert view["case_rev"] == rev1["case_rev"]
    assert view["progress"] == rev1["progress"]
    assert view["hints"] == rev1["hints"]
    assert view["manifest_summary"] == rev1["manifest_summary"]
    assert view["candidates"] == []
    assert view["evidence"] is None


def test_happy_path_ready_matches_fixture():
    fixture = _load_case_fixture()
    # case_views: rev1 SEARCHING · rev2 EVIDENCE_REVIEW(응답 전) · rev4 READY · rev5 READY(검토 완료)
    ready = fixture["case_views"][2]
    assert ready["stage"] == "READY"
    assert ready["user_reviewed"] is False

    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)

    # ── case 스스로 진행시키는 부분 (도메인 로직) ──────────────────────────
    case = CaseAggregate.intake(case_id="case_h001", hints={}, manifest_summary={})
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")

    raw_candidates = adapter.get_candidate_events()
    candidates = [
        Candidate(
            candidate_id=c["candidate_id"],
            at=None,
            at_provenance=None,
            observed=c["summary"],
            thumb_ref=c["thumbnail_ref"],
            rank=c["rank"],
            representative_ms=c["span"]["representative_ms"],
        )
        for c in raw_candidates
    ]
    case.receive_candidates(candidates)
    case.select_candidate("candidate_h001")

    jobs.issue_plate_read(case, input_fingerprint="sha1:h001-plate-read-clip_h001")
    jobs.issue_overlay_time_read(case, input_fingerprint="sha1:h001-overlay-read-clip_h001")
    jobs.issue_fine_verify(case, input_fingerprint="sha1:h001-fine-verify-as_h001_fine")

    # ── 다른 모듈이 (아직 stub이지만) 결과를 만들어줬다고 가정 ─────────────
    evidence_record = adapter.get_evidence_record()
    requirement_evidence = adapter.get_requirement_report("EVIDENCE")
    requirement_package = adapter.get_requirement_report("FINAL_PACKAGE")
    report_package = adapter.get_report_package()

    jobs.issue_report_video_export(case, input_fingerprint="sha1:h001-report-video-export")
    # 결과 화면 「신고 상황」에서 사용자가 [맞아요]를 누른 뒤에야 Package가 나온다(#171 B-2).
    case.record_situation_response("CONFIRMED", responded_at="2026-08-24T18:22:30+09:00")
    case.mark_ready(report_package=report_package)

    view = build_case_view(
        case,
        evidence_record=evidence_record,
        plate_readouts=adapter.get_plate_readouts(),
        requirement_report_evidence=requirement_evidence,
        requirement_report_package=requirement_package,
        report_package=report_package,
    )

    # 이 1차 구현이 실제로 재현하기로 한 부분만 정답지와 비교한다(§11 제외 범위 참고 —
    # manifest_summary/hints는 이 테스트에서 임의로 비워서 시작했으므로 비교하지 않는다).
    assert view["stage"] == ready["stage"]
    assert view["case_rev"] == ready["case_rev"]
    assert view["progress"] == ready["progress"]
    assert view["candidates"][0]["situation_confirmation"] == "CONFIRMED"
    assert view["candidates"][0]["candidate_id"] == ready["candidates"][0]["candidate_id"]
    assert view["candidates"][0]["observed"] == ready["candidates"][0]["observed"]
    assert view["candidates"][0]["selected"] is True
    assert view["evidence"] == ready["evidence"]
    assert view["requirements_evidence"] == ready["requirements_evidence"]
    assert view["requirements_package"] == ready["requirements_package"]
    assert view["package"]["report_fields"] == ready["package"]["report_fields"]
    assert view["package"]["report_field_states"] == ready["package"]["report_field_states"]
    assert view["package"]["unconfirmed_fields"] == ready["package"]["unconfirmed_fields"]
    assert view["package"]["artifact_ref"] == ready["package"]["artifact_ref"]
    assert view["package"]["capabilities"] == ready["package"]["capabilities"]


def test_happy_path_before_situation_response_has_no_package():
    """응답 전(`NOT_ASKED`) 스냅샷 — ADR-EVIDENCE-005 D2-c: 확인 응답이 없으면 Package가 나가지
    않는다. evidence는 응답 전 기록(`ev_h001`)과 FINAL 판정(UNKNOWN)만 있고, 사용자가 응답한 뒤
    `ev_h001_v2`(CONFIRMED)가 supersede한다(#48 I1 완료 증거: 전후 JSON 구분)."""
    fixture = _load_case_fixture()
    before = fixture["case_views"][1]
    assert before["stage"] == "EVIDENCE_REVIEW"

    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    records = adapter.get_evidence_records()
    evidence_reports = adapter.get_requirement_reports("EVIDENCE")
    package_reports = adapter.get_requirement_reports("FINAL_PACKAGE")
    assert [r["record_ref"]["ref"] for r in records] == ["ev_h001", "ev_h001_v2"]
    assert "situation_response" not in records[0]

    case = CaseAggregate.intake(case_id="case_h001", hints=before["hints"], manifest_summary=before["manifest_summary"])
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")
    fixture_candidate = before["candidates"][0]
    raw_candidate = adapter.get_candidate_events()[0]
    case.receive_candidates(
        [
            Candidate(
                candidate_id=fixture_candidate["candidate_id"],
                at=fixture_candidate["at"],
                at_provenance=fixture_candidate["at_provenance"],
                observed=fixture_candidate["observed"],
                thumb_ref=fixture_candidate["thumb_ref"],
                rank=raw_candidate["rank"],
                representative_ms=raw_candidate["span"]["representative_ms"],
            )
        ]
    )
    case.select_candidate("candidate_h001")

    # 실제 진입점(`build_view_from_adapter()`)처럼 파생 notice까지 붙인다 — 응답 전이라
    # `case.situation_response_pending`, 검색어가 없어 `evidence.location_search_keyword_missing`.
    view = service.derive_notices(
        build_case_view(
            case,
            evidence_record=records[0],
            plate_readouts=adapter.get_plate_readouts(),
            requirement_report_evidence=evidence_reports[0],
            requirement_report_package=package_reports[0],
            report_package=None,
        )
    )

    assert package_reports[0]["overall"] == "UNKNOWN"
    assert view["package"] is None
    assert view["candidates"][0]["situation_confirmation"] == "NOT_ASKED"
    assert {k: v for k, v in view.items() if k not in ("contract", "contract_version")} == {
        k: v for k, v in before.items() if k not in ("contract", "contract_version")
    }
