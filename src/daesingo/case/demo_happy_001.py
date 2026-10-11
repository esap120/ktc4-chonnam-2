"""W5/W6 데모 스크립트 — `scenario_happy_001`이 Recording→Search→Readout→Evidence→
`CaseView`까지 실제 함수 호출로 통과하는 걸 사람이 읽을 수 있게 보여준다.

    python -m daesingo.case.demo_happy_001

`tests/case/test_real_e2e.py`/`test_get_view_entrypoint.py`(pytest)와 하는 일이
다르다 — pytest는 "값이 맞는가"를 검증하고, 이 스크립트는 파이프라인을 한 번 실행해서
실제 값을 그대로 보여주기만 한다. 회의·데모용이지 CI에서 돌리는 용도가 아니다(그래서
assert가 없다 — 검증은 pytest 몫).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from daesingo.case import jobs, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.case.store import CaseStore

MOCK_ROOT = Path(__file__).resolve().parents[3] / "data" / "mock"
SCENARIO_ID = "happy_001"
CASE_ID = "case_h001_demo"


def _step(n: int, total: int, message: str) -> None:
    print(f"[{n}/{total}] {message}")


def run() -> dict[str, Any]:
    mock = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    scope = mock.get_analysis_scopes()[0]

    # 이슈 #103 — {}로 고정하면 후보 화면의 「기억 단서와 대조」가 그릴 값이 없다.
    case = CaseAggregate.intake(case_id=CASE_ID, hints=mock.get_hints(), manifest_summary={})
    case.start_search()
    jobs.issue_coarse_search(
        case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search"
    )

    real = RealAdapter(case_id=CASE_ID, case=case, search_scope=scope, mock_root=MOCK_ROOT)

    _step(1, 4, "Recording+Search: 후보 탐색 중 (search.search_candidates 실제 호출)...")
    candidates = service.receive_search_candidates(case, real)
    # 가장 유력한 후보(rank=1)를 case가 자동 선택한다(#122, core-user-flow §8-1).
    chosen = case.select_top_ranked()
    if chosen is None:
        raise SystemExit("자동 선택할 rank=1 후보가 없습니다(후보 없음 또는 stale).")
    candidate = next(c for c in candidates if c.candidate_id == chosen)
    print(f"        -> 후보 발견: {candidate.candidate_id} ({candidate.observed})")

    _step(
        2,
        4,
        "Readout: 번호판/화면시각 판독 중 "
        "(recording.build_incident_clip + readout.read_plate/read_overlay_time 실제 호출)...",
    )
    jobs.issue_plate_read(case, input_fingerprint="sha1:h001-plate-read-clip_h001")
    jobs.issue_overlay_time_read(case, input_fingerprint="sha1:h001-overlay-read-clip_h001")
    jobs.issue_fine_verify(case, input_fingerprint="sha1:h001-fine-verify-as_h001_fine")

    _step(
        3,
        4,
        "Evidence: 증거 조립·신고요건 판정 중 "
        "(evidence.assemble_evidence/evaluate_requirements 등 실제 호출)...",
    )
    jobs.issue_report_video_export(case, input_fingerprint="sha1:h001-report-video-export")
    # 이 데모는 각 단계 결과를 adapter로 바로 읽는다 — 결과가 반영된 것이므로 기다리는 job으로 남기지
    # 않는다(`decisions/running-jobs-derivation.md`, 비동기 반영 경로는 8-8).
    for record in case.waiting_job_records():
        case.settle_job(record["job_id"], "REFLECTED")
    # Package가 실제로 준비됐을 때만 READY(#167). 상황 응답 전이면 EVIDENCE_REVIEW에 남는다.
    service.mark_ready_if_package_ready(case, real)

    _step(4, 4, "CaseView 조립 중 (case.get_view 실제 호출)...")
    # store는 복사본을 주므로 여기까지의 변경을 한 번에 등록한다(get_view가 읽는 시점).
    store = CaseStore()
    store.register(case, real)
    view = service.get_view(CASE_ID, store=store)

    print()
    print("=== CaseView 요약 ===")
    print(f"  stage:        {view['stage']}")
    plate = view["evidence"]["plate_display"]
    event_time = view["evidence"]["event_time_display"]
    violation = view["evidence"]["violation_display"]
    print(f"  번호판:       {plate['value']}  (info_state={plate['info_state']})")
    print(f"  발생 시각:     {event_time['value']}  (info_state={event_time['info_state']})")
    print(f"  위반 내용:     {violation['label']}")
    print(f"  신고요건 판정: {view['requirements_evidence']['readiness']}")
    package = view["package"]
    if package is None:
        print(
            "  최종 패키지:   아직 없음 — situation_response/observation_facts 미확보"
            "(알려진 단순화, real_e2e.py 참고. 실패 아님)"
        )
    else:
        print(f"  최종 패키지:   {package['package_ref']}")

    return view


def main() -> int:
    view = run()
    print()
    print("=== 전체 CaseView (JSON) ===")
    print(json.dumps(view, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
