"""Worker T2 → case 반영 진입점 — 고도화 8-8, `docs/modules/case/decisions/result-reflection.md`.

Runtime Worker가 terminal execution 하나를 넘기면(Tech Spec §12.2) 호출자 transaction 안에서 case 행을 먼저 잠그고,
처리한 `execution_id`로 중복을 거르고, case가 아직 기다리는 job의 결과만 kind별로 반영한다. 후속 JobRecord는
돌려주기만 한다 — enqueue와 Runtime 「반영 완료」 표식은 composition root가 같은 transaction에서 한다.

## 여기 없는 것

- Runtime 타입(`ResultReflector` · `ReflectionInput`). case는 자기 모양(`ExecutionOutcome` · `ReflectionOutcome`)만 두고
  composition root가 옮긴다 — read port(`store.ExecutionReader`)와 같은 경계다.
- 결과 내용의 저장 위치. `produced`는 참조뿐이라 내용은 주입한 `ProducedReader`가 준다 — 어디서 읽는지는 8-6 2단계.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from daesingo.case.analysis_start import InitialSearchBudget, reflect_hint_extraction
from daesingo.case.domain import CaseAggregate
from daesingo.case.service import candidates_from_events, mark_ready_if_package_ready, utc_now
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimelineSource

# 정산 사유 중 Runtime이 「반영하지 않음」 이유로 받는 값(`ReflectionResult.reason`과 같다).
_NOT_APPLIED_REASONS = ("CANCELLED", "SUPERSEDED", "STOPPED_WAITING")


@dataclass(frozen=True)
class ExecutionOutcome:
    """Worker가 넘기는 terminal execution 사실 — T2에는 `SUCCEEDED` · `FAILED`만 온다(STALE은 Runtime 자동 retry)."""

    execution_id: str
    job_id: str
    case_id: str
    kind: str
    attempt: int
    status: Literal["SUCCEEDED", "FAILED"]
    produced: tuple[dict[str, str], ...] = ()
    failure_kind: str | None = None


@dataclass(frozen=True)
class ReflectionOutcome:
    """`APPLIED`(+ 이번에 append한 JobRecord) · `ALREADY_APPLIED`(같은 execution 재전달) · `NOT_APPLIED`(+ 정산 사유)."""

    status: Literal["APPLIED", "ALREADY_APPLIED", "NOT_APPLIED"]
    reason: Literal["CANCELLED", "SUPERSEDED", "STOPPED_WAITING"] | None = None
    appended_job_records: list[dict[str, Any]] = field(default_factory=list)


class ProducedReader(Protocol):
    """`produced` 참조 → kind별 결과 내용. 호출자 transaction의 `conn`을 받는다.

    - `HINT_EXTRACT` → search 단서 구조화 결과(`{"status": "OK|ABSTAINED|FAILED", "*_hint": …}`)
    - `COARSE_SEARCH` → `{"outcome": "SUCCEEDED|FAILED|…", "candidate_events": [CandidateEvent, …]}`

    관찰 kind(`PLATE_READ` · `OVERLAY_TIME_READ` · `FINE_VERIFY`)는 T2에서 부르지 않는다 — 정산만 하고 내용은 CaseView
    조립 때 adapter가 읽는다(`observation-storage.md` §4-2 · §4-5).
    """

    def __call__(self, conn: Any, kind: str, produced: tuple[dict[str, str], ...]) -> dict[str, Any]: ...


def reflect_execution(
    outcome: ExecutionOutcome,
    *,
    store: CaseStore,
    reader: ProducedReader,
    timelines: CaseTimelineSource,
    budget: InitialSearchBudget | None = None,
    now: datetime | None = None,
) -> ReflectionOutcome:
    """execution 하나를 반영한다. 반영했을 때만 저장하고, 예외는 그대로 올린다 — rollback · retry는 호출자 몫이다
    (#245 D-2). 이 case의 job이 아니거나 kind가 다르거나 반영기가 없는 kind면 배선 오류(`ValueError`)다.

    guard 전에 마감(`now`, 기본 현재 시각)이 지난 job을 `STOPPED_WAITING`으로 정산한다 — 마감 뒤 도착한 결과는
    `NOT_APPLIED(STOPPED_WAITING)`이고, 그 정산은 반영하지 않아도 저장한다(`decisions/case-wait-timeout.md`)."""
    case = store.load_for_update(outcome.case_id)
    if outcome.execution_id in case.processed_executions:
        return ReflectionOutcome("ALREADY_APPLIED")
    expired = case.stop_waiting_expired(now or utc_now())
    record = next((r for r in case.job_records if r["job_id"] == outcome.job_id), None)
    if record is None:
        raise ValueError(f"이 case가 발주하지 않은 job_id: {outcome.job_id!r}")
    if record["kind"] != outcome.kind:
        raise ValueError(f"kind가 다르다: JobRecord {record['kind']!r} != execution {outcome.kind!r}")
    apply = _APPLIERS.get(outcome.kind)
    if apply is None:
        raise ValueError(f"반영기가 없는 kind: {outcome.kind!r} — 결과를 버린 채 반영됨으로 남기지 않는다")
    if not case.awaits_result(outcome.job_id):
        reason = case.settled_jobs[outcome.job_id]
        if reason not in _NOT_APPLIED_REASONS:
            raise ValueError(f"다른 경로로 이미 반영된 job: {outcome.job_id!r} ({reason})")
        if expired:
            store.save(case)
        return ReflectionOutcome("NOT_APPLIED", reason=reason)

    jobs_before = len(case.job_records)
    apply(case, outcome, store=store, reader=reader, timelines=timelines, budget=budget or InitialSearchBudget())
    case.processed_executions[outcome.execution_id] = outcome.job_id
    store.save(case)
    return ReflectionOutcome("APPLIED", appended_job_records=copy.deepcopy(case.job_records[jobs_before:]))


def _apply_hint_extract(case: CaseAggregate, outcome: ExecutionOutcome, *, store, reader, timelines, budget) -> None:
    # 실행이 실패해도 빈 단서로 탐색을 이어 간다(case-command Draft §11 — 실패 notice 없음).
    result = reader(store.conn, outcome.kind, outcome.produced) if outcome.status == "SUCCEEDED" else {"status": "FAILED"}
    reflect_hint_extraction(case, result, job_id=outcome.job_id, timelines=timelines, budget=budget)


def _apply_coarse_search(case: CaseAggregate, outcome: ExecutionOutcome, *, store, reader, timelines, budget) -> None:
    if outcome.status == "FAILED":
        case.record_candidate_search_failure(job_id=outcome.job_id)
        return
    content = reader(store.conn, outcome.kind, outcome.produced)
    # 실패 Run(후보 0개)은 투영 대상을 바꾸지 않는다 — 동기 경로 `service.receive_search_candidates`와 같다.
    if str(content["outcome"]) == "FAILED":
        case.record_candidate_search_failure(job_id=outcome.job_id)
        return
    case.receive_candidates(candidates_from_events(content["candidate_events"]), job_id=outcome.job_id)


def _apply_observation(case: CaseAggregate, outcome: ExecutionOutcome, *, store, reader, timelines, budget) -> None:
    # 관찰 결과는 정산만 한다(`observation-storage.md` §4-5) — 내용은 case state에 복사하지 않고 CaseView 조립 때
    # adapter가 읽는다(§4-2). 실패 terminal도 같고, 실패 notice는 view가 read port의 실행 상태로 계산한다. 이전 후보의
    # 결과라도 기다리던 job이면 정산한다 — 투영은 선택 후보 필터가, READY는 gate의 현재 선택 확인(#191)이 막는다.
    case.settle_job(outcome.job_id, "REFLECTED")
    # command 뒤와 같은 gate다(`command.execute_command`). 관찰 결과로 Package가 준비되면 여기서 READY가 된다.
    if case.stage == "EVIDENCE_REVIEW":
        mark_ready_if_package_ready(case, store.get_adapter(case.case_id, case))


_APPLIERS = {
    "HINT_EXTRACT": _apply_hint_extract,
    "COARSE_SEARCH": _apply_coarse_search,
    "PLATE_READ": _apply_observation,
    "OVERLAY_TIME_READ": _apply_observation,
    "FINE_VERIFY": _apply_observation,
}
