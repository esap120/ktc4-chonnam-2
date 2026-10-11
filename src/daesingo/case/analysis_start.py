"""분석 시작 — 설명 원문 보존 · 단서 구조화 발주 · 결과 반영 · 첫 탐색 발주(`decisions/start-analysis.md`).

aggregate 수준 함수만 둔다. load · save와 append된 JobRecord 반환은 호출자(command · service)가 한다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from daesingo.case import jobs
from daesingo.case.domain import CaseAggregate, InvalidTransition
from daesingo.case.scope import build_analysis_scope
from daesingo.case.timeline_source import CaseTimelineSource

# 사용자가 유형을 고르는 입력이 없어 늘 4개 전부(spec §3-2).
TARGET_EVENT_TYPES: tuple[str, ...] = (
    "SIGNAL",
    "CENTER_LINE_CROSSING",
    "SOLID_LINE_LANE_CHANGE",
    "MOTORCYCLE_HELMET_NON_USE",
)

_HINT_FIELDS = {"time": "time_hint", "vehicle": "vehicle_hint", "situation": "situation_hint", "location": "location_hint"}


@dataclass(frozen=True)
class InitialSearchBudget:
    """첫 탐색 예산(spec §3-3). `max_cost_krw`는 설정값 — composition root가 바꿔 넘길 수 있다."""

    max_cost_krw: float = 1000.0
    max_latency_sec: float = 150.0


class AnalysisStartNotAllowed(Exception):
    """처리 가능한 원본이 없어 분석을 시작할 수 없다."""


def fingerprint(payload: dict[str, Any]) -> str:
    """첫 발주 `input_fingerprint`(spec §3-4) — 구현 이름표는 아직 섞지 않는다."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hints_from_result(result: dict[str, Any]) -> dict[str, str | None]:
    """search 단서 구조화 결과 → `hints` 4개 키. `OK`만 옮기고 빈 문자열은 `None`, `ABSTAINED` · `FAILED`는
    4개 모두 `None`(값을 지어내지 않는다). 그 밖의 상태는 결과 모양이 바뀐 것이라 `ValueError`."""
    status = result.get("status")
    if status == "OK":
        return {key: (result.get(field) or "").strip() or None for key, field in _HINT_FIELDS.items()}
    if status in ("ABSTAINED", "FAILED"):
        return dict.fromkeys(_HINT_FIELDS)
    raise ValueError(f"알 수 없는 단서 구조화 결과 상태: {status!r} (OK · ABSTAINED · FAILED)")


def issue_initial_search(
    case: CaseAggregate, *, timelines: CaseTimelineSource, budget: InitialSearchBudget
) -> dict[str, Any]:
    """case 타임라인 전체로 범위 1개를 만들고 `COARSE_SEARCH` 1건을 발주한다. 타임라인 실패는 그대로 올린다."""
    timeline = timelines.timeline_for(case.sources)
    scope = build_analysis_scope(
        case,
        scope_id=f"scope_{uuid.uuid4().hex}",
        time_ranges=[
            {
                "kind": "TIMELINE_RELATIVE",
                "timeline_ref": {"timeline_id": timeline.timeline_id, "revision": timeline.revision},
                "start_ms": 0,
                "end_ms": timeline.duration_ms,
            }
        ],
        target_event_types=list(TARGET_EVENT_TYPES),
        max_cost_krw=budget.max_cost_krw,
        max_latency_sec=budget.max_latency_sec,
    )
    content = {k: v for k, v in scope.items() if k != "scope_id"}
    return jobs.issue_coarse_search(
        case,
        scope_ref=scope["scope_id"],
        input_fingerprint=fingerprint({"kind": "COARSE_SEARCH", "scope": content}),
        scope=scope,
    )


def start_analysis(
    case: CaseAggregate, description: str, *, timelines: CaseTimelineSource, budget: InitialSearchBudget
) -> None:
    """`INTAKE`에서만(아니면 `InvalidTransition`), 처리 가능한 원본이 1개 이상일 때만(아니면 `AnalysisStartNotAllowed`) 시작한다.
    설명이 비었으면(공백만 포함) 구조화 없이 바로 첫 탐색, 아니면 `HINT_EXTRACT`를 발주한다. 검사는 상태를
    바꾸기 전에 한다."""
    if case.stage != "INTAKE":
        raise InvalidTransition(f"{case.stage}에서는 분석을 시작할 수 없다(INTAKE 전용)")
    if not case.sources:
        raise AnalysisStartNotAllowed("처리 가능한 영상이 없다")
    case.description = description
    case.start_search()
    if not description.strip():
        # 타임라인 실패는 그대로 올라간다 — aggregate는 바뀐 채지만 호출자가 save하지 않는다(Task 4).
        issue_initial_search(case, timelines=timelines, budget=budget)
        return
    jobs.issue_job(
        case,
        "HINT_EXTRACT",
        input_fingerprint=fingerprint({"kind": "HINT_EXTRACT", "description": description, "prior_hints": None}),
    )


def reflect_hint_extraction(
    case: CaseAggregate, result: dict[str, Any], *, timelines: CaseTimelineSource, budget: InitialSearchBudget
) -> bool:
    """기다리던 `HINT_EXTRACT`가 있을 때만 hints를 채우고 정산한 뒤 첫 탐색을 발주한다. 없으면(같은 결과의
    두 번째 도착) 아무것도 바꾸지 않고 `False`. 결과 상태는 상태를 바꾸기 전에 검사한다."""
    waiting = [r for r in case.waiting_job_records() if r["kind"] == "HINT_EXTRACT"]
    if not waiting:
        return False
    hints = hints_from_result(result)
    case.record_extracted_hints(hints)
    for record in waiting:
        case.settle_job(record["job_id"], "REFLECTED")
    issue_initial_search(case, timelines=timelines, budget=budget)
    return True
