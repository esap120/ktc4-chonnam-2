"""`scenario_infra_failure_001`(번호판 판독이 인프라 오류로 RUNNING→FAILED→취소를 거치는
동안 overlay 판독은 독립적으로 성공) — §11 제외 범위였던 시나리오를 4개 revision 모두
`build_case_view()` 공개 API로 fixture와 바이트 단위로 비교한다.

이 시나리오로 새로 확인/추가한 것:
  - `progress[plate_read]`/`progress[overlay_time_read]`는 (evidence가 조립된 happy path와
    달리) 항상 같이 움직이지 않는다 — 각 Job의 최신 `JobExecution.status`를
    `contract-job-record-case-view.md` 헤더 ③/§13 표(QUEUED→PENDING, RUNNING→RUNNING,
    SUCCEEDED→DONE, FAILED/STALE→FAILED, CANCELLED→PARTIAL)대로 각자 독립 projection한다
    (`view.py::_job_execution_status_to_progress_state()` 신설).
  - `EVIDENCE_REVIEW`인데 `evidence_record`가 끝내 없으면(번호판 판독 실패로 evidence가
    한 번도 조립되지 못함) `progress`가 `evidence_assembly`~`package_assembly`를 아예
    빼고 5개 항목으로 truncate된다 — `CANDIDATE_REVIEW`+빈 candidates와 같은 원칙
    (신뢰 가능한 신호가 없으면 낙관적 PENDING을 보여주지 않는다).
  - `case_rev`가 job 발주 없이도 오르는 지점(rev1→rev2)이 하나 더 있다: 번호판 판독
    Job이 재시도 끝에 최종 FAILED로 끝났다는 소식이 case에 "보고"되는 것 자체가
    `bump_revision()`의 일반 정의("단계 전이 없이도 case_rev가 오르는 경우") 안에
    들어간다 — `scenario_plate_reread_001`에서 evidence supersede 때 테스트가 직접
    `case.bump_revision()`을 호출한 것과 같은 패턴. rev2→rev3(재판독 발주,
    force_rerun=true)·rev3→rev4(overlay 재판독 발주, force_rerun=true)는 기존
    `jobs.issue_job()`의 force_rerun 자동 bump로 이미 설명된다.
  - 이 fixture의 job_records는 coarse_search/candidate 선택 이력을 아예 담지 않는다
    (plate/overlay 두 Job부터 시작) — 그래서 이 테스트는 search 단계를 domain 메서드로
    재생하지 않고, fixture가 전제하는 시작 상태(EVIDENCE_REVIEW, case_rev:1,
    candidate 1개 선택됨)를 `CaseAggregate`에 직접 구성한다. `job_x001_plate`의
    `case_rev:1`이 그 전제와 맞다(만약 search 단계를 `receive_candidates()`로 재생했다면
    2026-09-14 정정에 따라 그 시점에 이미 case_rev가 2로 오르므로 fixture와 어긋난다) —
    이 fixture가 search 단계 이력을 아예 안 담고 있어서 생긴, case가 만든 게 아닌
    사전조건 격차로 보고 여기서 다시 만들지 않는다.
"""
import json
from pathlib import Path

from daesingo.case import jobs
from daesingo.case.adapters import MockFixtureAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.view import build_case_view, representative_execution_status

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
SCENARIO_ID = "infra_failure_001"


def _load_case_fixture() -> dict:
    path = MOCK_ROOT / "case" / f"scenario_{SCENARIO_ID}.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _assert_view_matches(view: dict, expected: dict) -> None:
    assert view["stage"] == expected["stage"]
    assert view["case_rev"] == expected["case_rev"]
    assert view["progress"] == expected["progress"]
    assert view["candidates"] == expected["candidates"]
    assert expected["evidence"] is None
    assert view["evidence"] is None
    assert expected["requirements_evidence"] is None
    assert view["requirements_evidence"] is None
    assert view["requirements_package"] is None
    assert view["package"] is None
    assert [{k: v for k, v in j.items() if k != "job_id"} for j in view["running_jobs"]] == [
        {k: v for k, v in j.items() if k != "job_id"} for j in expected["running_jobs"]
    ]
    assert view["notices"] == expected["notices"]


def test_infra_failure_four_revisions_match_fixture():
    fixture = _load_case_fixture()
    rev1, rev2, rev3, rev4 = fixture["case_views"]
    assert [v["stage"] for v in (rev1, rev2, rev3, rev4)] == ["EVIDENCE_REVIEW"] * 4

    # ⚠️ `case`가 발주하는 job_id는 매번 새로 만드는 uuid라 fixture의 고정 job_id
    # 문자열과 절대 같을 수 없다(§3-B) — 그래서 JobExecution을 실제 생성한 job_id로
    # 찾지 않고, fixture 자체가 쓰는 고정 job_id 문자열로 직접 조회한다(job_records의
    # job_id와 이 fixture의 job_executions[].job_id가 서로 맞춰 쓰여 있다).
    adapter = MockFixtureAdapter(MOCK_ROOT, SCENARIO_ID)
    executions_by_job_id: dict[str, list[dict]] = {}
    for ex in adapter.get_job_executions():
        executions_by_job_id.setdefault(ex["job_id"], []).append(ex)

    # fixture가 전제하는 search 단계 이후 상태를 직접 구성한다(모듈 docstring 참고).
    case = CaseAggregate(
        case_id="case_x001",
        case_rev=1,
        stage="EVIDENCE_REVIEW",
        hints=rev1["hints"],
        manifest_summary=rev1["manifest_summary"],
        selection_rev=1,
        candidates=[
            Candidate(
                candidate_id=c["candidate_id"],
                at=c["at"],
                at_provenance=c["at_provenance"],
                observed=c["observed"],
                thumb_ref=c["thumb_ref"],
                rank=c["rank"],
                representative_ms=c["marker_ms"],
                selected=c["selected"],
            )
            for c in rev1["candidates"]
        ],
    )

    # case에 보고된 JobExecution 누적분. fixture execution을 case가 실제로 발주한 job_id로 옮겨
    # 싣고, 대표 상태는 `representative_execution_status()`가 case의 job_records로 고른다(A§10-6 · §10-7).
    reported: list[dict] = []

    def report(fixture_job_id: str, job: dict) -> None:
        reported.extend({**ex, "job_id": job["job_id"]} for ex in executions_by_job_id[fixture_job_id])

    def status(kind: str) -> str | None:
        return representative_execution_status(case.job_records, reported, kind)

    # ── rev1: plate_read 발주 직후, 아직 실행 결과 없음 / overlay는 이미 성공 ──────
    plate_job = jobs.issue_plate_read(case, input_fingerprint="sha1:x001-plate-read-clip_x001")
    overlay_job = jobs.issue_overlay_time_read(case, input_fingerprint="sha1:x001-overlay-read-clip_x001")
    assert plate_job["case_rev"] == overlay_job["case_rev"] == 1
    report("job_x001_overlay", overlay_job)
    case.settle_job(overlay_job["job_id"], "REFLECTED")  # overlay 성공은 rev1 시점에 이미 반영됨(8-8이 할 정산을 테스트가 대신)

    view1 = build_case_view(
        case,
        job_executions=[{"job_id": plate_job["job_id"], "attempt": 1, "status": "RUNNING"}],
        notices=rev1["notices"],
        plate_read_status=status("PLATE_READ"),  # 아직 어떤 JobExecution도 case에 보고되지 않음 → None
        overlay_time_read_status=status("OVERLAY_TIME_READ"),
    )
    assert status("PLATE_READ") is None
    _assert_view_matches(view1, rev1)

    # ── rev2: plate_read가 재시도(STALE) 끝에 최종 FAILED로 끝났다는 소식이 case에
    # 보고된다 — job 발주가 아니므로 `bump_revision()`을 직접 호출한다(모듈 docstring 근거).
    case.bump_revision()
    assert [e["status"] for e in executions_by_job_id["job_x001_plate"]] == ["STALE", "FAILED"]  # 전제 확인
    report("job_x001_plate", plate_job)
    case.settle_job(plate_job["job_id"], "REFLECTED")  # 최종 FAILED가 notice로 반영됨

    view2 = build_case_view(
        case,
        notices=rev2["notices"],
        plate_read_status=status("PLATE_READ"),  # attempt 최댓값(2)의 FAILED
        overlay_time_read_status=status("OVERLAY_TIME_READ"),
    )
    _assert_view_matches(view2, rev2)

    # ── rev3: 자동 재판독(force_rerun=true) 발주 → 곧바로 CANCELLED ─────────────
    reread_plate_job = jobs.issue_plate_reread(case, input_fingerprint="sha1:x001-plate-read-clip_x001-v2")
    assert reread_plate_job["case_rev"] == 3

    assert [e["status"] for e in executions_by_job_id["job_x001_plate_reread"]] == ["CANCELLED"]  # 전제 확인
    report("job_x001_plate_reread", reread_plate_job)
    case.settle_job(reread_plate_job["job_id"], "CANCELLED")  # 곧바로 취소됨

    view3 = build_case_view(
        case,
        notices=rev3["notices"],
        plate_read_status=status("PLATE_READ"),  # 가장 나중 job(재판독)의 CANCELLED
        overlay_time_read_status=status("OVERLAY_TIME_READ"),
    )
    _assert_view_matches(view3, rev3)

    # ── rev4: overlay도 재판독(force_rerun=true) 발주 → 성공 ────────────────────
    reread_overlay_job = jobs.issue_overlay_time_reread(case, input_fingerprint="sha1:x001-overlay-read-clip_x001-v2")
    assert reread_overlay_job["case_rev"] == 4

    assert [e["status"] for e in executions_by_job_id["job_x001_overlay_reread"]] == ["SUCCEEDED"]  # 전제 확인
    report("job_x001_overlay_reread", reread_overlay_job)
    case.settle_job(reread_overlay_job["job_id"], "REFLECTED")  # 재판독 성공이 반영됨

    view4 = build_case_view(
        case,
        notices=rev4["notices"],
        plate_read_status=status("PLATE_READ"),  # 재판독은 취소된 채 남아있다
        overlay_time_read_status=status("OVERLAY_TIME_READ"),
    )
    _assert_view_matches(view4, rev4)
