"""`kind`별 대표 실행 상태 선택 — CaseView 계약 A§10-6 · §10-7.

- 대표 job = 그 `kind`로 `job_records[]`에 가장 나중에 기록된 job(§10-7). `case_rev`는 정렬 키가 아니다.
- 그 job 안의 대표 execution = `attempt` 최댓값(§10-6). 목록 순서에 기대지 않는다.

예전엔 이 선택을 아무도 하지 않아 테스트가 `executions[-1]["status"]`를 손으로 넘겼다 —
Runtime이 해석해 건네준다고 가정했지만, JobExecution read port(#245 D-6)는 Contract 모양을
그대로 돌려주므로 case가 고른다.
"""
from __future__ import annotations

import json
from pathlib import Path

from daesingo.case.view import representative_execution_status

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"


def _job(job_id: str, kind: str, case_rev: int = 1) -> dict:
    return {"job_id": job_id, "kind": kind, "case_rev": case_rev}


def _execution(job_id: str, attempt: int, status: str) -> dict:
    return {"job_id": job_id, "attempt": attempt, "status": status}


def test_highest_attempt_wins_regardless_of_list_order():
    # backoff 중: attempt 1은 STALE, attempt 2는 QUEUED — FAILED로 깜빡이지 않는다(§10-6).
    records = [_job("job_p", "PLATE_READ")]
    executions = [_execution("job_p", 2, "QUEUED"), _execution("job_p", 1, "STALE")]

    assert representative_execution_status(records, executions, "PLATE_READ") == "QUEUED"


def test_latest_job_of_kind_wins_even_with_same_case_rev():
    # 같은 case_rev로 연속 재시도해도 job_records 순서로 고른다(§10-7 주의).
    records = [_job("job_p1", "PLATE_READ", case_rev=2), _job("job_p2", "PLATE_READ", case_rev=2)]
    executions = [_execution("job_p2", 1, "RUNNING"), _execution("job_p1", 1, "FAILED")]

    assert representative_execution_status(records, executions, "PLATE_READ") == "RUNNING"


def test_latest_job_without_execution_is_not_replaced_by_earlier_job():
    # 막 발주한 재시도 job은 아직 실행 보고가 없다 — 이전 job의 FAILED를 대신 보이지 않는다(§10-7).
    records = [_job("job_p1", "PLATE_READ"), _job("job_p2", "PLATE_READ")]
    executions = [_execution("job_p1", 1, "FAILED")]

    assert representative_execution_status(records, executions, "PLATE_READ") is None


def test_kind_without_job_has_no_status():
    records = [_job("job_o", "OVERLAY_TIME_READ")]
    executions = [_execution("job_o", 1, "SUCCEEDED")]

    assert representative_execution_status(records, executions, "PLATE_READ") is None


def test_infra_failure_fixture_final_state():
    # STALE→FAILED 뒤 재판독(CANCELLED), overlay 재판독(SUCCEEDED)까지 끝난 최종 상태.
    records = json.loads((MOCK_ROOT / "case" / "scenario_infra_failure_001.json").read_text(encoding="utf-8"))[
        "job_records"
    ]
    executions = json.loads((MOCK_ROOT / "common" / "scenario_infra_failure_001.json").read_text(encoding="utf-8"))[
        "job_executions"
    ]

    assert representative_execution_status(records, executions, "PLATE_READ") == "CANCELLED"
    assert representative_execution_status(records, executions, "OVERLAY_TIME_READ") == "SUCCEEDED"
