"""`CaseAggregate` ↔ 저장 형식 — `decisions/case-store-mysql.md` §4.

`cases` 행 칼럼(case_id · case_rev · stage · selection_rev) + `state` JSON + append-only 레코드 셋으로 나눈다.
저장소 구현(in-memory · MySQL) 둘 다 이 함수만 쓴다 — 직렬화 규칙을 한 곳에 둔다.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass
from typing import Any

from daesingo.case.domain import Candidate, CaseAggregate

STATE_VERSION = 1

_STATE_FIELDS = (
    "user_reviewed",
    "hints",
    "manifest_summary",
    "situation_response",
    "candidate_search_failed",
    "candidate_generation",
    "settled_jobs",
    "description",
    "sources",
)
_CANDIDATE_FIELDS = tuple(f.name for f in dataclasses.fields(Candidate) if f.name != "extra")


class StateVersionTooNew(RuntimeError):
    """저장된 `state_version`이 이 코드보다 크다 — 옛 코드가 새 형식을 덮어쓰지 않게 로드를 거부한다."""


@dataclass(frozen=True)
class CaseRow:
    case_id: str
    case_rev: int
    stage: str
    selection_rev: int
    state: dict[str, Any]
    job_records: list[dict[str, Any]]
    correction_records: list[dict[str, Any]]
    analysis_scopes: dict[str, dict[str, Any]]


def _candidate_to_dict(c: Candidate) -> dict[str, Any]:
    return {**copy.deepcopy(c.extra), **{name: copy.deepcopy(getattr(c, name)) for name in _CANDIDATE_FIELDS}}


def _candidate_from_dict(d: dict[str, Any]) -> Candidate:
    known = {k: copy.deepcopy(v) for k, v in d.items() if k in _CANDIDATE_FIELDS}
    extra = {k: copy.deepcopy(v) for k, v in d.items() if k not in _CANDIDATE_FIELDS}
    return Candidate(**known, extra=extra)


def to_row(case: CaseAggregate) -> CaseRow:
    state: dict[str, Any] = copy.deepcopy(case.extra_state)
    state.update({name: copy.deepcopy(getattr(case, name)) for name in _STATE_FIELDS})
    state["candidates"] = [_candidate_to_dict(c) for c in case.candidates]
    state["state_version"] = STATE_VERSION
    return CaseRow(
        case_id=case.case_id,
        case_rev=case.case_rev,
        stage=case.stage,
        selection_rev=case.selection_rev,
        state=state,
        job_records=copy.deepcopy(case.job_records),
        correction_records=copy.deepcopy(case.correction_records),
        analysis_scopes=copy.deepcopy(case.analysis_scopes),
    )


def from_row(row: CaseRow) -> CaseAggregate:
    state = copy.deepcopy(row.state)
    version = state.pop("state_version", STATE_VERSION)
    if version > STATE_VERSION:
        raise StateVersionTooNew(f"state_version {version} > {STATE_VERSION}: case_id={row.case_id!r}")
    candidates = [_candidate_from_dict(d) for d in state.pop("candidates", [])]
    known = {name: state.pop(name) for name in _STATE_FIELDS if name in state}
    return CaseAggregate(
        case_id=row.case_id,
        case_rev=row.case_rev,
        stage=row.stage,
        selection_rev=row.selection_rev,
        candidates=candidates,
        job_records=copy.deepcopy(row.job_records),
        correction_records=copy.deepcopy(row.correction_records),
        analysis_scopes=copy.deepcopy(row.analysis_scopes),
        extra_state=state,  # 남은 것 = 모르는 키
        **known,
    )
