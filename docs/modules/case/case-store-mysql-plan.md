# CaseStore MySQL 영속화 1단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** case 상태(aggregate · JobRecord · CorrectionRecord · AnalysisScope)를 MySQL에 저장하고, 호출자 transaction에 참여하는 저장소로 바꾼다. 기존 테스트는 in-memory 저장소로 그대로 돈다.

**Architecture:** `CaseRepository` Protocol(`insert` / `load(lock=…)` / `save`)에 구현 둘 — `InMemoryCaseRepository`(load가 늘 복사본)와 `MySQLCaseRepository`(SQLAlchemy Core, 호출자의 `Connection`, commit 안 함). 기존 `CaseStore`는 **repository · conn · AdapterRegistry를 묶는 facade**로 바꿔 `get_view(case_id, store=…)` · `execute_command(…, store=…)` 시그니처를 유지한다. 쓰기 경로는 `load_for_update` → 변경 → **성공했을 때만** `save`.

**Tech Stack:** Python 3.12 · SQLAlchemy Core 2.x(ORM 없음) · PyMySQL(sync) · Alembic(forward-only) · MySQL 8.4 · pytest · uv(`uv.lock`)

**Spec:** `docs/modules/case/decisions/case-store-mysql.md`(#267 머지, Runtime §9 확인 결과 포함)

**spec과 다른 점 하나:** spec §6은 진입점 인자를 `repository, conn, adapters`로 바꾸자고 했다. 이 계획은 `store=` 인자를 유지하고 `CaseStore`가 셋을 묶는다 — 호출부 수십 곳의 시그니처를 바꾸지 않으려는 것이다. composition root는 요청마다 `CaseStore(repository=MySQLCaseRepository(), adapters=registry, conn=connection)`을 만든다. 동작(복사본 load, 성공 시에만 save, 저장소는 commit하지 않음)은 spec 그대로다.

## Global Constraints

- DB: MySQL 8.4 하나 · InnoDB · utf8mb4. 접근 계층 SQLAlchemy Core 2.x, driver PyMySQL(sync), **ORM 없음**(runtime-tech-spec §4.4).
- **저장소는 commit · rollback하지 않는다.** transaction은 호출자(composition root) 소유(#245 D-2, runtime-tech-spec §12.1).
- 테이블 이름: `cases` · `job_records` · `correction_records` · `analysis_scopes`(spec §4). id 칼럼은 `ascii_bin`. `case_id` VARCHAR(128), `job_id` · `correction_id` VARCHAR(191), `analysis_scopes` PK `(case_id, scope_id)`.
- 레코드 테이블은 append-only — 저장된 앞부분이 바뀌면 `AppendOnlyViolation`.
- 잠금: 쓰기 `lock="update"`(`SELECT … FOR UPDATE`), 읽기 `lock="share"`(`FOR SHARE`). Case와 Runtime 행을 함께 잠그는 경로는 **case 행 먼저**.
- `state` JSON의 모르는 키는 보존(round-trip), 없는 키는 dataclass 기본값. `state_version`이 코드보다 크면 로드 오류.
- Alembic: forward-only. 앱 시작 때 migration을 돌리지 않는다. 배치 `migrations/case/` · version table `case_alembic_version`은 **잠정(provisional)** — Runtime Implementation Plan · RD-12f에서 바뀔 수 있다.
- 의존성은 공용 `pyproject.toml`에 한 버전만, `uv.lock` 갱신(CI가 `uv sync --locked`).
- MySQL 통합 테스트는 `DAESINGO_MYSQL_URL`이 있을 때만 돈다(없으면 skip). CI는 바꾸지 않는다.
- 회귀 기준: 기존 전체 테스트(develop 기준 1,587 passed)가 in-memory로 통과.
- 범위 밖: 처리한 `execution_id` · 중단 `job_id` 테이블(8-8 · 8-9), Runtime enqueue, adapter 제거(2단계), CI MySQL.

## Review Focus

1. **거부된 command는 아무것도 저장하지 않는다** — `load_for_update`한 뒤 거부되면 `save`가 없어야 한다(다음 load에 흔적 없음). → Task 4 테스트.
2. **load한 객체를 고치고 save를 빠뜨리면 반영되지 않는다** — in-memory도 복사본이라 MySQL과 같게 동작해야 한다. → Task 2 계약 테스트.
3. **같은 case 동시 쓰기는 줄을 선다** — 두 연결이 `lock="update"`로 같은 case를 잡으면 뒤의 것이 기다린다. → Task 7 MySQL 테스트.
4. **새 코드가 쓴 `state` 키를 옛 코드가 지우지 않는다** — 모르는 키 round-trip. → Task 1 테스트.
5. **너무 긴 · 비ASCII `case_id`는 insert 전에 거부한다**(VARCHAR(128) ascii_bin에서 잘리거나 깨지지 않게). → Task 2 계약 테스트.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `src/daesingo/case/domain.py` (수정) | `CaseAggregate.analysis_scopes` · `extra_state`, `Candidate.extra`, `record_analysis_scope()` |
| `src/daesingo/case/jobs.py` (수정) | `issue_coarse_search(…, scope=None)`가 scope를 aggregate에 남김 |
| `src/daesingo/case/store_state.py` (신규) | aggregate ↔ 저장 형식 직렬화(순수 함수) |
| `src/daesingo/case/store.py` (재작성) | 오류 타입, `CaseRepository` Protocol, `InMemoryCaseRepository`, `AdapterRegistry`, `CaseStore` facade |
| `src/daesingo/case/store_mysql.py` (신규) | SQLAlchemy 테이블 정의 · `MySQLCaseRepository`(sqlalchemy를 이 파일에서만 import) |
| `src/daesingo/case/adapters.py` (수정) | `RealAdapter.bind_case` · `RealVideoAdapter.bind_case` |
| `src/daesingo/case/service.py` · `command.py` (수정) | 쓰기 경로 load_for_update → save |
| `migrations/case/` (신규) | Alembic env(잠정) · 첫 migration |
| `tests/case/test_store_state.py` · `test_case_repository_contract.py` · `test_store_mysql.py` · `conftest.py` (신규) | 직렬화 · 계약(두 구현) · MySQL 전용 |
| 기존 테스트 · `scripts/measure_case_orchestration.py` · `demo_happy_001.py` (수정) | 「등록한 객체를 직접 고치고 확인」하던 곳을 load/save · 재조회로 |
| `docs/…` (수정) | ERD case 부분, spec 상태, 8-6, 로컬 실행 방법 |

---

### Task 1: aggregate 직렬화 (`store_state.py`) + AnalysisScope 보관

**Files:**
- Modify: `src/daesingo/case/domain.py` (`Candidate` · `CaseAggregate` 필드, 메서드 추가)
- Modify: `src/daesingo/case/jobs.py:68-69` (`issue_coarse_search`)
- Create: `src/daesingo/case/store_state.py`
- Test: `tests/case/test_store_state.py`

**Interfaces:**
- Produces:
  - `CaseAggregate.analysis_scopes: dict[str, dict]`, `CaseAggregate.extra_state: dict[str, Any]`, `Candidate.extra: dict[str, Any]`
  - `CaseAggregate.record_analysis_scope(scope: dict) -> None` — 같은 `scope_id`에 다른 내용이면 `ValueError`
  - `jobs.issue_coarse_search(case, *, scope_ref: str, input_fingerprint: str, scope: dict | None = None) -> dict`
  - `store_state.STATE_VERSION = 1`
  - `store_state.StateVersionTooNew(RuntimeError)`
  - `store_state.to_row(case) -> CaseRow`, `store_state.from_row(row: CaseRow) -> CaseAggregate`
  - `CaseRow` (frozen dataclass): `case_id: str, case_rev: int, stage: str, selection_rev: int, state: dict, job_records: list[dict], correction_records: list[dict], analysis_scopes: dict[str, dict]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_store_state.py`

```python
"""aggregate ↔ 저장 형식 직렬화 — `decisions/case-store-mysql.md` §4."""

from __future__ import annotations

import copy

import pytest

from daesingo.case import jobs
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store_state import STATE_VERSION, StateVersionTooNew, from_row, to_row


def _case() -> CaseAggregate:
    case = CaseAggregate.empty("case_state001")
    case.start_search()
    scope = {"scope_id": "s1", "time_ranges": [], "target_event_types": [], "hint": {}, "budget": {}, "contract_version": "x"}
    jobs.issue_coarse_search(case, scope_ref="s1", input_fingerprint="sha1:c", scope=scope)
    case.receive_candidates([Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="o", thumb_ref="fr_1", rank=1)])
    case.select_candidate("cand_a")
    return case


def test_round_trip_keeps_every_field():
    case = _case()
    back = from_row(to_row(case))
    assert back == case
    assert back.candidates[0].thumb_ref == "fr_1"
    assert back.analysis_scopes["s1"]["scope_id"] == "s1"


def test_row_splits_columns_records_and_state():
    row = to_row(_case())
    assert (row.case_id, row.stage, row.selection_rev) == ("case_state001", "EVIDENCE_REVIEW", 1)
    assert row.state["state_version"] == STATE_VERSION
    assert "job_records" not in row.state and "analysis_scopes" not in row.state
    assert [r["kind"] for r in row.job_records] == ["COARSE_SEARCH"]


def test_unknown_state_keys_survive_round_trip():
    row = to_row(_case())
    state = copy.deepcopy(row.state)
    state["future_field"] = {"x": 1}
    state["candidates"][0]["future_candidate_field"] = "y"
    back = from_row(type(row)(**{**row.__dict__, "state": state}))
    again = to_row(back)
    assert again.state["future_field"] == {"x": 1}
    assert again.state["candidates"][0]["future_candidate_field"] == "y"


def test_missing_state_key_takes_default():
    row = to_row(_case())
    state = {k: v for k, v in row.state.items() if k != "candidate_generation"}
    back = from_row(type(row)(**{**row.__dict__, "state": state}))
    assert back.candidate_generation == 0


def test_newer_state_version_is_refused():
    row = to_row(_case())
    state = {**row.state, "state_version": STATE_VERSION + 1}
    with pytest.raises(StateVersionTooNew):
        from_row(type(row)(**{**row.__dict__, "state": state}))


def test_scope_is_immutable_per_id():
    case = _case()
    with pytest.raises(ValueError):
        case.record_analysis_scope({"scope_id": "s1", "time_ranges": ["changed"]})
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/case/test_store_state.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'daesingo.case.store_state'`

- [ ] **Step 3: domain · jobs 구현**

`src/daesingo/case/domain.py`의 `Candidate`(필드 목록 끝, `representative_ms` 아래)에 추가:

```python
    # 저장된 상태에 있었지만 이 코드가 모르는 키(새 코드가 쓴 필드). 다시 저장할 때 그대로 쓴다 —
    # rollback한 옛 코드가 새 필드를 지우지 않게(`decisions/case-store-mysql.md` §4).
    extra: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
```

`CaseAggregate`(필드 목록 끝, `candidate_generation` 아래)에 추가:

```python
    # COARSE_SEARCH가 쓴 AnalysisScope(`scope_id` → scope). JobRecord는 `scope_ref`만 들고 있어, process가
    # 바뀌어도 scope를 다시 읽을 수 있게 aggregate에 남긴다(#246 S-4). CaseView 비노출. scope는 불변.
    analysis_scopes: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 저장된 상태의 모르는 최상위 키 — `Candidate.extra`와 같은 이유. CaseView 비노출.
    extra_state: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
```

`CaseAggregate`에 메서드 추가(`record_source_registered` 아래):

```python
    def record_analysis_scope(self, scope: dict[str, Any]) -> None:
        """scope는 불변이다 — 같은 `scope_id`로 다른 내용이 오면 거부한다."""
        scope_id = scope["scope_id"]
        existing = self.analysis_scopes.get(scope_id)
        if existing is not None and existing != scope:
            raise ValueError(f"AnalysisScope는 바꿀 수 없다: {scope_id!r}")
        self.analysis_scopes[scope_id] = dict(scope)
```

`src/daesingo/case/jobs.py`의 `issue_coarse_search`를 바꾼다:

```python
def issue_coarse_search(
    case: CaseAggregate, *, scope_ref: str, input_fingerprint: str, scope: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`scope`를 주면 aggregate에 남긴다(#246 S-4) — 주지 않는 기존 호출(fixture · 스크립트)은 그대로 둔다."""
    if scope is not None:
        if scope["scope_id"] != scope_ref:
            raise ValueError(f"scope_ref와 scope_id가 다르다: {scope_ref!r} != {scope['scope_id']!r}")
        case.record_analysis_scope(scope)
    return issue_job(case, "COARSE_SEARCH", scope_ref=scope_ref, input_fingerprint=input_fingerprint)
```

- [ ] **Step 4: `store_state.py` 구현**

```python
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
```

- [ ] **Step 5: 통과 확인 + case 회귀**

Run: `python -m pytest tests/case/test_store_state.py tests/case -q -p no:cacheprovider`
Expected: 새 테스트 6개 PASS, 기존 case 테스트 전부 PASS(필드 추가뿐이라 회귀 없음)

- [ ] **Step 6: Commit**

```bash
git add src/daesingo/case/domain.py src/daesingo/case/jobs.py src/daesingo/case/store_state.py tests/case/test_store_state.py
git commit -m "feat(case): aggregate 직렬화(store_state)와 AnalysisScope 보관 (8-6)"
```

---

### Task 2: `CaseRepository` Protocol · `InMemoryCaseRepository` · 계약 테스트

**Files:**
- Modify: `src/daesingo/case/store.py` (오류 타입 · Protocol · in-memory 구현 추가. `CaseStore`는 Task 3에서 바꾼다 — 이 Task에서는 건드리지 않는다)
- Create: `tests/case/conftest.py`
- Test: `tests/case/test_case_repository_contract.py`

**Interfaces:**
- Consumes: Task 1의 `to_row` · `from_row` · `CaseRow` · `StateVersionTooNew`
- Produces:
  - 오류: `CaseNotFound(KeyError)`, `CaseAlreadyExists(ValueError)`, `AppendOnlyViolation(RuntimeError)`, `InvalidCaseId(ValueError)`
  - `CaseRepository` Protocol: `insert(conn, case) -> None`, `load(conn, case_id, *, lock: Literal["share", "update"] = "share") -> CaseAggregate`, `save(conn, case) -> None`
  - `InMemoryCaseRepository()` — `conn` 무시, load는 늘 새 객체
  - `store.validate_case_id(case_id: str) -> None` — ASCII · 1~128자 아니면 `InvalidCaseId`
  - pytest fixture `repo_conn` (params `["memory", "mysql"]`, Task 7 전에는 mysql param이 skip) → `(repository, conn)`

- [ ] **Step 1: 공용 fixture 작성** — `tests/case/conftest.py`

```python
"""case 저장소 계약 테스트용 fixture — 같은 테스트를 in-memory와 MySQL 두 구현에 돌린다.

MySQL은 `DAESINGO_MYSQL_URL`(예: `mysql+pymysql://root:pw@127.0.0.1:3306/daesingo_test`)이 있을 때만 돈다.
"""

from __future__ import annotations

import os

import pytest

from daesingo.case.store import InMemoryCaseRepository


@pytest.fixture(params=["memory", "mysql"])
def repo_conn(request):
    if request.param == "memory":
        yield InMemoryCaseRepository(), None
        return
    url = os.environ.get("DAESINGO_MYSQL_URL")
    if not url:
        pytest.skip("DAESINGO_MYSQL_URL 미지정 — MySQL 통합 테스트는 opt-in")
    engine = request.getfixturevalue("mysql_engine")
    from daesingo.case.store_mysql import MySQLCaseRepository

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            yield MySQLCaseRepository(), conn
        finally:
            trans.rollback()
```

`mysql_engine` fixture는 Task 6에서 만든다 — Task 6 전에는 `DAESINGO_MYSQL_URL`을 설정하지 않고 돌린다(mysql param은 skip).

- [ ] **Step 2: 실패하는 계약 테스트 작성** — `tests/case/test_case_repository_contract.py`

```python
"""`CaseRepository` 계약 — 두 구현이 같아야 하는 동작(`decisions/case-store-mysql.md` §5 · §8)."""

from __future__ import annotations

import pytest

from daesingo.case import jobs
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import AppendOnlyViolation, CaseAlreadyExists, CaseNotFound, InvalidCaseId


def _selected_case(case_id: str = "case_repo001") -> CaseAggregate:
    case = CaseAggregate.empty(case_id)
    case.start_search()
    scope = {"scope_id": "s1", "time_ranges": [], "target_event_types": [], "hint": {}, "budget": {}, "contract_version": "x"}
    jobs.issue_coarse_search(case, scope_ref="s1", input_fingerprint="sha1:c", scope=scope)
    case.receive_candidates([Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="o", thumb_ref="fr_1", rank=1)])
    case.select_candidate("cand_a")
    return case


def test_insert_then_load_round_trips(repo_conn):
    repo, conn = repo_conn
    case = _selected_case()
    repo.insert(conn, case)
    assert repo.load(conn, case.case_id) == case


def test_load_returns_a_new_object_each_time(repo_conn):
    """고치고 save하지 않으면 반영되지 않는다 — in-memory도 MySQL과 같게(Review Focus 2)."""
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    loaded = repo.load(conn, "case_repo001", lock="update")
    loaded.user_reviewed = True
    assert repo.load(conn, "case_repo001").user_reviewed is False


def test_save_persists_changes_and_appended_records(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    case = repo.load(conn, "case_repo001", lock="update")
    jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    case.situation_response = {"value": "CONFIRMED", "responded_at": "2026-10-06T10:00:00+09:00", "candidate_ref": {"kind": "candidate_event", "ref": "cand_a"}}
    repo.save(conn, case)
    back = repo.load(conn, "case_repo001")
    assert [r["kind"] for r in back.job_records] == ["COARSE_SEARCH", "PLATE_READ"]
    assert back.situation_response["value"] == "CONFIRMED"


def test_save_refuses_changed_prefix(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    case = repo.load(conn, "case_repo001", lock="update")
    case.job_records[0] = {**case.job_records[0], "job_id": "job_tampered"}
    with pytest.raises(AppendOnlyViolation):
        repo.save(conn, case)


def test_save_refuses_removed_record(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    case = repo.load(conn, "case_repo001", lock="update")
    case.job_records.clear()
    with pytest.raises(AppendOnlyViolation):
        repo.save(conn, case)


def test_load_missing_case_is_key_error(repo_conn):
    repo, conn = repo_conn
    with pytest.raises(CaseNotFound):
        repo.load(conn, "case_missing")
    with pytest.raises(KeyError):  # 기존 `except KeyError` 호출부 호환
        repo.load(conn, "case_missing")


def test_insert_twice_is_refused(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, _selected_case())
    with pytest.raises(CaseAlreadyExists):
        repo.insert(conn, _selected_case())


def test_case_ids_differ_by_case_only_are_distinct(repo_conn):
    repo, conn = repo_conn
    repo.insert(conn, CaseAggregate.empty("case_A"))
    repo.insert(conn, CaseAggregate.empty("case_a"))
    assert repo.load(conn, "case_A").case_id == "case_A"


@pytest.mark.parametrize("bad", ["", "c" * 129, "case_한글"])
def test_invalid_case_id_is_refused_before_insert(repo_conn, bad):
    repo, conn = repo_conn
    with pytest.raises(InvalidCaseId):
        repo.insert(conn, CaseAggregate.empty(bad))
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/case/test_case_repository_contract.py -q -p no:cacheprovider`
Expected: 수집 단계 FAIL — `ImportError: cannot import name 'InMemoryCaseRepository'`

- [ ] **Step 4: `store.py`에 구현 추가** (기존 `CaseStore` 클래스 위에 넣는다)

```python
import copy
from typing import Any, Literal, Protocol

from daesingo.case.store_state import CaseRow, from_row, to_row

CASE_ID_MAX = 128  # `cases.case_id` VARCHAR(128) ascii_bin


class CaseNotFound(KeyError):
    """등록되지 않은 case_id — `KeyError`라서 기존 `except KeyError`(command의 unknown_target)가 그대로 잡는다."""


class CaseAlreadyExists(ValueError):
    pass


class AppendOnlyViolation(RuntimeError):
    """저장된 레코드의 앞부분이 바뀌거나 지워졌다 — 정상 경로에서는 나지 않는 프로그래밍 오류."""


class InvalidCaseId(ValueError):
    pass


def validate_case_id(case_id: str) -> None:
    if not case_id or len(case_id) > CASE_ID_MAX or not case_id.isascii():
        raise InvalidCaseId(f"case_id는 1~{CASE_ID_MAX}자 ASCII여야 한다: {case_id!r}")


class CaseRepository(Protocol):
    """case 저장소. `conn`은 호출자의 SQLAlchemy `Connection`이고 transaction도 호출자 것이다 —
    저장소는 commit · rollback하지 않는다(#245 D-2). in-memory 구현은 `conn`을 무시한다."""

    def insert(self, conn: Any, case: CaseAggregate) -> None: ...
    def load(self, conn: Any, case_id: str, *, lock: Literal["share", "update"] = "share") -> CaseAggregate: ...
    def save(self, conn: Any, case: CaseAggregate) -> None: ...


def check_append_only(stored_ids: list[str], current_ids: list[str], what: str) -> None:
    if current_ids[: len(stored_ids)] != stored_ids:
        raise AppendOnlyViolation(f"{what}의 저장된 앞부분이 바뀌었다")


class InMemoryCaseRepository:
    """테스트 · 로컬용. load는 늘 새 객체를 준다 — 같은 객체를 주면 save를 빠뜨려도 테스트가 통과해
    MySQL에서만 상태가 사라진다(`decisions/case-store-mysql.md` §5)."""

    def __init__(self) -> None:
        self._rows: dict[str, CaseRow] = {}

    def insert(self, conn: Any, case: CaseAggregate) -> None:
        validate_case_id(case.case_id)
        if case.case_id in self._rows:
            raise CaseAlreadyExists(f"case_id는 재등록할 수 없다: {case.case_id!r}")
        self._rows[case.case_id] = to_row(case)

    def load(self, conn: Any, case_id: str, *, lock: Literal["share", "update"] = "share") -> CaseAggregate:
        try:
            row = self._rows[case_id]
        except KeyError:
            raise CaseNotFound(f"등록되지 않은 case_id: {case_id!r}") from None
        return from_row(copy.deepcopy(row))

    def save(self, conn: Any, case: CaseAggregate) -> None:
        stored = self._rows.get(case.case_id)
        if stored is None:
            raise CaseNotFound(f"등록되지 않은 case_id: {case.case_id!r}")
        new = to_row(case)
        check_append_only([r["job_id"] for r in stored.job_records], [r["job_id"] for r in new.job_records], "job_records")
        check_append_only(
            [r["correction_id"] for r in stored.correction_records],
            [r["correction_id"] for r in new.correction_records],
            "correction_records",
        )
        for scope_id, scope in stored.analysis_scopes.items():
            if new.analysis_scopes.get(scope_id) != scope:
                raise AppendOnlyViolation(f"analysis_scopes {scope_id!r}가 바뀌거나 지워졌다")
        self._rows[case.case_id] = new
```

`job_records` 앞부분 비교는 `job_id`만 본다 — 같은 id의 내용이 바뀐 경우까지 막으려면 dict 비교가 필요하지만, MySQL 구현은 저장된 행을 다시 쓰지 않으므로(INSERT만) 두 구현의 동작이 같도록 id만 비교한다.

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/case/test_case_repository_contract.py -q -p no:cacheprovider`
Expected: memory param 전부 PASS, mysql param 전부 SKIP(`DAESINGO_MYSQL_URL 미지정`)

- [ ] **Step 6: Commit**

```bash
git add src/daesingo/case/store.py tests/case/conftest.py tests/case/test_case_repository_contract.py
git commit -m "feat(case): CaseRepository Protocol과 in-memory 구현(복사본 load · append-only) (8-6)"
```

---

### Task 3: `AdapterRegistry` · `bind_case` · `CaseStore` facade

**Files:**
- Modify: `src/daesingo/case/store.py` (기존 `CaseStore` 교체)
- Modify: `src/daesingo/case/adapters.py` (`RealAdapter` · `RealVideoAdapter`에 `bind_case`)
- Test: `tests/case/test_case_store_facade.py`

**Interfaces:**
- Consumes: Task 2의 `InMemoryCaseRepository` · `CaseRepository` · `CaseNotFound`
- Produces:
  - `AdapterRegistry()`: `put(case_id: str, adapter: ModuleAdapter | None) -> None`, `for_case(case_id: str, case: CaseAggregate | None = None) -> ModuleAdapter | None` — 등록 안 됐으면 `None`, `case`를 주면 `bind_case(case)`가 있는 adapter에 붙인다
  - `CaseStore(repository: CaseRepository | None = None, adapters: AdapterRegistry | None = None, conn: Any = None)`
    - `register(case, adapter=None) -> None` (insert + adapter 등록)
    - `get_case(case_id) -> CaseAggregate` (share load, 복사본)
    - `load_for_update(case_id) -> CaseAggregate`
    - `save(case) -> None`
    - `get_adapter(case_id, case: CaseAggregate | None = None) -> ModuleAdapter | None`
  - `RealAdapter.bind_case(case) -> None`, `RealVideoAdapter.bind_case(case) -> None`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_case_store_facade.py`

```python
"""`CaseStore` facade — repository · conn · adapter registry를 묶는다(`decisions/case-store-mysql.md` §5)."""

from __future__ import annotations

from daesingo.case.domain import CaseAggregate
from daesingo.case.store import AdapterRegistry, CaseStore, InMemoryCaseRepository


class _BindingAdapter:
    def __init__(self) -> None:
        self.bound = None

    def bind_case(self, case):
        self.bound = case


def test_get_case_returns_copy_and_save_persists():
    store = CaseStore()
    store.register(CaseAggregate.empty("case_f001"))
    case = store.load_for_update("case_f001")
    case.start_search()
    assert store.get_case("case_f001").stage == "INTAKE"
    store.save(case)
    assert store.get_case("case_f001").stage == "SEARCHING"


def test_get_adapter_binds_the_loaded_case():
    store = CaseStore()
    adapter = _BindingAdapter()
    store.register(CaseAggregate.empty("case_f002"), adapter)
    case = store.get_case("case_f002")
    assert store.get_adapter("case_f002", case) is adapter
    assert adapter.bound is case


def test_unregistered_adapter_is_none():
    store = CaseStore()
    store.register(CaseAggregate.empty("case_f003"))
    assert store.get_adapter("case_f003") is None
    assert store.get_adapter("case_never") is None


def test_store_wraps_given_repository_and_registry():
    repo, registry = InMemoryCaseRepository(), AdapterRegistry()
    store = CaseStore(repository=repo, adapters=registry, conn=None)
    store.register(CaseAggregate.empty("case_f004"))
    assert repo.load(None, "case_f004").case_id == "case_f004"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/case/test_case_store_facade.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'AdapterRegistry'`

- [ ] **Step 3: `store.py`의 기존 `CaseStore`를 교체**

모듈 docstring 첫 문단을 「case 저장소 — repository(in-memory · MySQL) · adapter registry · `CaseStore` facade. `decisions/case-store-mysql.md`.」로 바꾸고, 기존 `CaseStore` 클래스를 지운 자리에 넣는다:

```python
class AdapterRegistry:
    """case_id → adapter(process 메모리). adapter는 2단계에서 없앨 대상이라 DB에 넣지 않는다.

    `RealAdapter` · `RealVideoAdapter`는 생성 때 받은 aggregate를 들고 있다. load가 늘 새 객체를 주므로
    요청마다 방금 로드한 aggregate를 `bind_case`로 다시 붙인다(spec §5)."""

    def __init__(self) -> None:
        self._by_case: dict[str, ModuleAdapter | None] = {}

    def put(self, case_id: str, adapter: ModuleAdapter | None) -> None:
        self._by_case[case_id] = adapter

    def for_case(self, case_id: str, case: CaseAggregate | None = None) -> ModuleAdapter | None:
        adapter = self._by_case.get(case_id)
        if adapter is not None and case is not None and hasattr(adapter, "bind_case"):
            adapter.bind_case(case)
        return adapter


class CaseStore:
    """repository · conn · adapter registry를 묶는다. 진입점(`get_view` · `execute_command` · `create_case` ·
    `record_source_registered`)은 이것 하나를 받는다 — composition root는 요청 transaction마다
    `CaseStore(repository=MySQLCaseRepository(), adapters=registry, conn=connection)`을 만든다.
    기본값은 in-memory(테스트 · 로컬)."""

    def __init__(
        self,
        repository: CaseRepository | None = None,
        adapters: AdapterRegistry | None = None,
        conn: Any = None,
    ) -> None:
        self.repository: CaseRepository = repository if repository is not None else InMemoryCaseRepository()
        self.adapters = adapters if adapters is not None else AdapterRegistry()
        self.conn = conn

    def register(self, case: CaseAggregate, adapter: ModuleAdapter | None = None) -> None:
        """`adapter=None`은 빈 case(`service.create_case()`)다 — 선택 전에는 adapter를 조회하지 않는다."""
        self.repository.insert(self.conn, case)
        self.adapters.put(case.case_id, adapter)

    def get_case(self, case_id: str) -> CaseAggregate:
        return self.repository.load(self.conn, case_id, lock="share")

    def load_for_update(self, case_id: str) -> CaseAggregate:
        return self.repository.load(self.conn, case_id, lock="update")

    def save(self, case: CaseAggregate) -> None:
        self.repository.save(self.conn, case)

    def get_adapter(self, case_id: str, case: CaseAggregate | None = None) -> ModuleAdapter | None:
        return self.adapters.for_case(case_id, case)
```

- [ ] **Step 4: adapter에 `bind_case` 추가** — `src/daesingo/case/adapters.py`의 `RealAdapter`(클래스 시작 `:272` 부근)와 `RealVideoAdapter`(`:506` 부근) 각각 `__init__` 바로 아래에:

```python
    def bind_case(self, case: CaseAggregate) -> None:
        """요청마다 방금 로드한 aggregate를 붙인다(`store.AdapterRegistry`). 캐시는 객체 동일성이 아니라
        `case_rev` · `candidate_generation` 값으로 판단하므로 그대로 동작한다."""
        self._case = case
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/case/test_case_store_facade.py tests/case/test_case_repository_contract.py -q -p no:cacheprovider`
Expected: PASS. (이 시점에 다른 case 테스트 일부는 복사본 load 때문에 실패한다 — Task 4 · 5에서 고친다. 이 Task에서는 위 두 파일만 확인한다.)

- [ ] **Step 6: Commit**

```bash
git add src/daesingo/case/store.py src/daesingo/case/adapters.py tests/case/test_case_store_facade.py
git commit -m "feat(case): CaseStore facade(repository · conn · AdapterRegistry)와 adapter bind_case (8-6)"
```

---

### Task 4: 쓰기 경로 — load_for_update → 성공 시에만 save

**Files:**
- Modify: `src/daesingo/case/service.py` (`create_case` · `record_source_registered` · `get_view`)
- Modify: `src/daesingo/case/command.py` (`execute_command`)
- Test: `tests/case/test_store_write_paths.py`

**Interfaces:**
- Consumes: Task 3의 `CaseStore.get_case` · `load_for_update` · `save` · `get_adapter(case_id, case)`
- Produces: 진입점 시그니처는 그대로(`get_view(case_id, *, store, …)`, `execute_command(request, *, store, …)`, `create_case(*, store)`, `record_source_registered(case_id, source_asset, *, store)`). 동작만 바뀐다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_store_write_paths.py`

```python
"""진입점이 저장소를 load_for_update → save로 쓰는가 — 거부된 command는 저장하지 않는다(Review Focus 1)."""

from __future__ import annotations

from daesingo.case import command, service
from daesingo.case.domain import Candidate
from daesingo.case.store import CaseStore


def _store_with_two_candidates() -> tuple[CaseStore, str]:
    store = CaseStore()
    case_id = service.create_case(store=store)
    case = store.load_for_update(case_id)
    case.start_search()
    case.receive_candidates([
        Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="", thumb_ref=None, rank=1),
        Candidate(candidate_id="cand_b", at=None, at_provenance=None, observed="", thumb_ref=None, rank=2),
    ])
    case.select_candidate("cand_a")
    store.save(case)
    return store, case_id


class _NoDownstream:
    """선택 뒤 CaseView가 adapter를 조회하므로 downstream 값이 없는 adapter를 붙인다 — `ModuleAdapter` Protocol
    (`adapters.py`)의 조회 메서드를 전부 「없음」으로 답한다."""

    def get_candidate_events(self): return []
    def get_candidate_search_outcome(self): return None
    def get_analysis_scopes(self): return []
    def get_evidence_record(self): return None
    def get_evidence_records(self): return []
    def get_requirement_report(self, scope): return None
    def get_requirement_reports(self, scope): return []
    def get_evidence_needs(self): return []
    def get_report_package(self): return None
    def get_plate_readouts(self): return []
    def get_overlay_time_readouts(self): return []
    def get_plate_read_status(self): return None
    def get_visual_evidence_decision(self): return None
    def get_job_executions(self): return []


def test_successful_command_is_persisted():
    store, case_id = _store_with_two_candidates()
    store.adapters.put(case_id, _NoDownstream())
    rev = store.get_case(case_id).case_rev
    result = command.execute_command(
        {"case_id": case_id, "expected_case_rev": rev, "kind": "SELECT_OTHER_CANDIDATE", "payload": {"candidate_id": "cand_b"}},
        store=store,
    )
    assert result.response["ok"] is True
    saved = store.get_case(case_id)
    assert [c.candidate_id for c in saved.candidates if c.selected] == ["cand_b"]
    assert saved.correction_records[-1]["kind"] == "OTHER_CANDIDATE"


def test_rejected_command_leaves_no_trace():
    store, case_id = _store_with_two_candidates()
    store.adapters.put(case_id, _NoDownstream())
    before = store.get_case(case_id)
    result = command.execute_command(
        {"case_id": case_id, "expected_case_rev": before.case_rev, "kind": "MARK_REVIEWED", "payload": {}},
        store=store,
    )
    assert result.response["ok"] is False
    assert store.get_case(case_id) == before


def test_record_source_registered_is_persisted():
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(case_id, {"availability": "AVAILABLE"}, store=store)
    assert store.get_case(case_id).manifest_summary["file_count"] == 1
```


- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/case/test_store_write_paths.py -q -p no:cacheprovider`
Expected: `test_successful_command_is_persisted` · `test_record_source_registered_is_persisted` FAIL(지금 코드는 `get_case`가 준 복사본을 고치고 저장하지 않는다)

- [ ] **Step 3: `service.py` 수정**

`record_source_registered`:

```python
def record_source_registered(case_id: str, source_asset: dict[str, Any], *, store: CaseStore) -> None:
    """(docstring 그대로)"""
    case = store.load_for_update(case_id)
    case.record_source_registered(source_asset)
    store.save(case)
```

`get_view`의 본문 마지막 세 줄을 바꾼다:

```python
    case = store.get_case(case_id)
    adapter = store.get_adapter(case_id, case)
    return build_view_from_adapter(
        case, adapter, running_jobs=running_jobs, notices=notices, visual_verify_status=visual_verify_status
    )
```

`create_case`는 그대로다(`store.register(...)`가 insert).

- [ ] **Step 4: `command.py`의 `execute_command` 수정** — 로드한 aggregate로 view를 만들고, 성공했을 때만 저장한다:

```python
    view_kwargs = {"store": store, "running_jobs": running_jobs, "notices": notices}
    case_id = request.get("case_id") if isinstance(request, dict) else None

    def current_view() -> dict[str, Any] | None:
        try:
            return get_view(case_id, **view_kwargs)
        except KeyError:
            return None

    def view_of(case: CaseAggregate) -> dict[str, Any]:
        return build_view_from_adapter(case, store.get_adapter(case.case_id, case), running_jobs=running_jobs, notices=notices)

    try:
        _check_payload(request)
    except _Rejected as rejected:
        return CommandResult(_response(rejected.reason, current_view() if isinstance(case_id, str) else None))

    try:
        case = store.load_for_update(case_id)
    except KeyError:
        return CommandResult(_response("unknown_target", None))

    view = view_of(case)
    if request["expected_case_rev"] != case.case_rev:
        return CommandResult(_response("stale_revision", view))

    jobs_before = len(case.job_records)
    try:
        _HANDLERS[request["kind"]](case, request["payload"], view)
    except _Rejected as rejected:
        return CommandResult(_response(rejected.reason, view))
    if case.stage == "EVIDENCE_REVIEW":
        mark_ready_if_package_ready(case, store.get_adapter(case_id, case))
    store.save(case)
    appended = copy.deepcopy(case.job_records[jobs_before:])
    return CommandResult(_response(None, view_of(case)), appended)
```

import에 `build_view_from_adapter`를 더한다: `from daesingo.case.service import build_view_from_adapter, get_view, mark_ready_if_package_ready`. 기존 주석(#167 gate 재확인 설명)은 `mark_ready_if_package_ready` 줄 위에 그대로 둔다.

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/case/test_store_write_paths.py tests/case/test_case_store_facade.py tests/case/test_case_repository_contract.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/daesingo/case/service.py src/daesingo/case/command.py tests/case/test_store_write_paths.py
git commit -m "feat(case): 진입점 쓰기 경로를 load_for_update → 성공 시 save로 (8-6)"
```

---

### Task 5: 「등록한 객체를 직접 고치고 확인」하던 호출부 이전

**Files:**
- Modify: `tests/case/test_command.py`, `tests/case/test_empty_case.py`, `tests/case/test_get_view_entrypoint.py`, `tests/case/test_plate_read_failure_projection.py`, `tests/case/test_visual_verify_failed_notice.py`
- Modify: `scripts/measure_case_orchestration.py`, `src/daesingo/case/demo_happy_001.py`

**Interfaces:**
- Consumes: Task 3 · 4의 `CaseStore`(`get_case` · `load_for_update` · `save` · `adapters.put`)
- Produces: 없음(호출부 이전만)

규칙(모든 파일 공통):
1. `store.register(case, adapter)` **뒤에** 그 `case` 객체를 고치면 → `case = store.load_for_update(case.case_id)`로 다시 받고, 고친 뒤 `store.save(case)`.
2. command · 진입점을 부른 **뒤에** 등록할 때의 `case` 객체로 상태를 확인하면 → 확인 직전에 `case = store.get_case(case.case_id)`.
3. `_state(case)`로 전후를 비교하면 → `before = _state(store.get_case(case.case_id))`, 뒤도 같은 방식.
4. `store.get_case(case_id).start_search()`처럼 받은 객체를 바로 고치면 → 규칙 1.

- [ ] **Step 1: 실패 목록 확인**

Run: `python -m pytest tests/case -q -p no:cacheprovider -x --no-header -rf 2>&1 | tail -30`
Expected: 위 5개 테스트 파일에서 실패가 난다. 실패마다 원인이 규칙 1~4 중 하나인지 확인한다(그 밖의 원인이면 멈추고 보고).

- [ ] **Step 2: 테스트 헬퍼 추가** — `tests/case/test_command.py` 헬퍼 영역(`_state` 아래)에:

```python
def _reload(store: CaseStore, case: CaseAggregate) -> CaseAggregate:
    """저장소는 복사본을 준다 — command 뒤 상태는 다시 읽어서 확인한다."""
    return store.get_case(case.case_id)


def _mutate(store: CaseStore, case_id: str, fn) -> CaseAggregate:
    """등록 뒤 상태를 바꾸는 준비 단계 — load_for_update → fn → save."""
    case = store.load_for_update(case_id)
    fn(case)
    store.save(case)
    return case
```

예: `test_mark_reviewed_in_ready_sets_flag`의
```python
    store, case = _store_with_selected_case()
    case.mark_ready(report_package={"package_id": "pkg_cmd"})
```
→
```python
    store, case = _store_with_selected_case()
    case = _mutate(store, case.case_id, lambda c: c.mark_ready(report_package={"package_id": "pkg_cmd"}))
```
그리고 command 뒤 `assert case.user_reviewed is True` → `assert _reload(store, case).user_reviewed is True`.

- [ ] **Step 3: 다섯 테스트 파일에 규칙 1~4 적용**

`test_empty_case.py`의 `store.get_case(case_id).start_search()`(규칙 4) 두 곳과 `case = store.get_case(case_id)` 뒤 `case.start_search() … case.select_candidate("cand_a")`(규칙 1)를 `_mutate`와 같은 load_for_update → save로 바꾼다. 이 파일은 헬퍼를 import하지 말고 같은 세 줄을 직접 쓴다(테스트 파일끼리 import하지 않는 관례).

- [ ] **Step 4: 러너 · 데모 이전**

`scripts/measure_case_orchestration.py`의 컨텍스트 클래스(`self.case, self.real, self.n = ...` 부근, `:241-247`)를 바꾼다 — 등록한 객체를 계속 들고 있지 않고, 필요할 때 저장소에서 읽는다:

```python
        self.real, self.n = real, Counter()
        self.store = CaseStore()
        self.store.register(case, real)
        self.case_id = case.case_id

    @property
    def case(self):
        """읽기 전용 스냅샷 — 고치려면 `mutate()`를 쓴다."""
        return self.store.get_case(self.case_id)

    def mutate(self, fn):
        case = self.store.load_for_update(self.case_id)
        self.store.get_adapter(self.case_id, case)  # RealAdapter에 방금 로드한 aggregate를 붙인다
        result = fn(case)
        self.store.save(case)
        return result
```

러너에서 `ctx.case`를 고치는 호출(예: `service.receive_search_candidates(ctx.case, ctx.real)`, `case.select_top_ranked()`, `jobs.issue_coarse_search(case, …)`, domain 메서드 직접 호출)은 모두 `ctx.mutate(lambda case: …)`로 감싼다. 읽기(`any(c.selected for c in self.case.candidates)`)는 그대로 둔다.

`src/daesingo/case/demo_happy_001.py`: `store.register(case, real)`(지금 `:45`) 뒤에도 `case`를 직접 고친다(`service.receive_search_candidates(case, real)` · `case.select_top_ranked()` · `service.mark_ready_if_package_ready(case, real)`). 이 데모는 store를 `get_view` 한 번에만 쓰므로, **`store.register(case, real)` 줄을 `view = service.get_view(CASE_ID, store=store)` 바로 위로 옮긴다** — 그때까지의 변경이 한 번에 저장된다. `store = CaseStore()` 줄도 같이 옮긴다.

- [ ] **Step 5: 전체 회귀**

Run: `python -m pytest -q -p no:cacheprovider` (PATH에 static ffmpeg — `C:\Users\LG\anaconda3\Lib\site-packages\static_ffmpeg\bin\win32`)
Expected: develop 기준 1,587 + 새 테스트 전부 PASS. 그리고 러너 1회:

Run: `PYTHONPATH=src python scripts/measure_case_orchestration.py --length 2`
Expected: ①②③④④-b 모두 0(5차 측정과 같음). 0이 아니면 이전 과정에서 동작이 바뀐 것이니 멈추고 보고.

- [ ] **Step 6: Commit**

```bash
git add tests/case scripts/measure_case_orchestration.py src/daesingo/case/demo_happy_001.py
git commit -m "refactor(case): 호출부를 복사본 load · save로 이전 (8-6)"
```

---

### Task 6: 의존성 · 테이블 정의 · Alembic(잠정)

**Files:**
- Modify: `pyproject.toml` (`dependencies`), `uv.lock`
- Create: `src/daesingo/case/store_mysql.py` (이 Task에서는 테이블 정의만)
- Create: `migrations/case/alembic.ini`, `migrations/case/env.py`, `migrations/case/script.py.mako`, `migrations/case/versions/0001_case_tables.py`
- Test: `tests/case/test_store_mysql.py` (migration 확인 테스트 1개)

**Interfaces:**
- Produces:
  - `store_mysql.metadata: sqlalchemy.MetaData`, 테이블 `cases_table` · `job_records_table` · `correction_records_table` · `analysis_scopes_table`
  - Alembic head revision id `"case_0001"`
  - pytest fixture `mysql_engine`(session) — `tests/case/test_store_mysql.py`가 아니라 `tests/case/conftest.py`에 둔다(Task 2의 `repo_conn`이 쓴다)

- [ ] **Step 1: 의존성 추가**

`pyproject.toml`의 `dependencies`에 추가(공용 — Runtime도 같은 버전을 쓴다, #267 확인):

```toml
  "sqlalchemy>=2.0,<3.0",
  "pymysql[rsa]>=1.1,<2.0",  # MySQL 8.4 기본 인증(caching_sha2_password)에 rsa(cryptography) 필요
  "alembic>=1.13,<2.0",
```

Run: `uv lock` 그리고 `uv sync --extra test`
Expected: `uv.lock`에 세 패키지(+ cryptography · mako 등 전이 의존성)가 추가된다. `python -c "import sqlalchemy, pymysql, alembic"`가 성공.

- [ ] **Step 2: 테이블 정의** — `src/daesingo/case/store_mysql.py`

```python
"""case MySQL 저장소 — `decisions/case-store-mysql.md` §4 · §5. sqlalchemy는 이 파일에서만 import한다
(in-memory만 쓰는 테스트 · 스크립트가 DB 의존성 없이 돌게)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

metadata = sa.MetaData()

_ID = 128  # case_id · scope_id
_RECORD_ID = 191  # job_id · correction_id — `job_{case_id}_{kind}_{uuid8}`가 들어가게


def _id(length: int = _ID) -> sa.String:
    return sa.String(length, collation="ascii_bin")


cases_table = sa.Table(
    "cases",
    metadata,
    sa.Column("case_id", _id(), primary_key=True),
    sa.Column("case_rev", sa.Integer, nullable=False),
    sa.Column("stage", sa.String(32), nullable=False),
    sa.Column("selection_rev", sa.Integer, nullable=False),
    sa.Column("state", sa.JSON, nullable=False),
    sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
    sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

job_records_table = sa.Table(
    "job_records",
    metadata,
    sa.Column("job_id", _id(_RECORD_ID), primary_key=True),
    sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("record", sa.JSON, nullable=False),
    sa.UniqueConstraint("case_id", "seq", name="uq_job_records_case_seq"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

correction_records_table = sa.Table(
    "correction_records",
    metadata,
    sa.Column("correction_id", _id(_RECORD_ID), primary_key=True),
    sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("record", sa.JSON, nullable=False),
    sa.UniqueConstraint("case_id", "seq", name="uq_correction_records_case_seq"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

analysis_scopes_table = sa.Table(
    "analysis_scopes",
    metadata,
    sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), primary_key=True),
    sa.Column("scope_id", _id(), primary_key=True),
    sa.Column("scope", sa.JSON, nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
```

- [ ] **Step 3: Alembic env(잠정 배치)**

`migrations/case/alembic.ini`:

```ini
# 배치 · version table은 잠정(provisional) — Runtime Implementation Plan · RD-12f에서 바뀔 수 있다
# (`docs/modules/case/decisions/case-store-mysql.md` §9). 앱 시작 때 돌리지 않는다.
[alembic]
script_location = %(here)s
version_table = case_alembic_version
```

`migrations/case/env.py`:

```python
"""case 소유 migration env(잠정). URL은 `DAESINGO_MYSQL_URL`. forward-only — downgrade를 운영 경로로 쓰지 않는다."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from daesingo.case.store_mysql import metadata

config = context.config
url = os.environ["DAESINGO_MYSQL_URL"]
version_table = config.get_main_option("version_table") or "case_alembic_version"

connectable = config.attributes.get("connection") or create_engine(url)
if hasattr(connectable, "connect"):
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, version_table=version_table)
        with context.begin_transaction():
            context.run_migrations()
else:
    context.configure(connection=connectable, target_metadata=metadata, version_table=version_table)
    with context.begin_transaction():
        context.run_migrations()
```

`migrations/case/script.py.mako`: `alembic init`이 만드는 기본 템플릿을 그대로 쓴다(`python -m alembic init -t generic <임시폴더>`로 만든 파일을 복사).

`migrations/case/versions/0001_case_tables.py`:

```python
"""case 테이블 4개 — `decisions/case-store-mysql.md` §4."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "case_0001"
down_revision = None
branch_labels = None
depends_on = None


def _id(length=128):
    return sa.String(length, collation="ascii_bin")


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("case_id", _id(), primary_key=True),
        sa.Column("case_rev", sa.Integer, nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("selection_rev", sa.Integer, nullable=False),
        sa.Column("state", sa.JSON, nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    for name, id_col in (("job_records", "job_id"), ("correction_records", "correction_id")):
        op.create_table(
            name,
            sa.Column(id_col, _id(191), primary_key=True),
            sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), nullable=False),
            sa.Column("seq", sa.Integer, nullable=False),
            sa.Column("record", sa.JSON, nullable=False),
            sa.UniqueConstraint("case_id", "seq", name=f"uq_{name}_case_seq"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
    op.create_table(
        "analysis_scopes",
        sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), primary_key=True),
        sa.Column("scope_id", _id(), primary_key=True),
        sa.Column("scope", sa.JSON, nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only (runtime-tech-spec §4.4)")
```

- [ ] **Step 4: `mysql_engine` fixture** — `tests/case/conftest.py`에 추가

```python
@pytest.fixture(scope="session")
def mysql_engine():
    url = os.environ.get("DAESINGO_MYSQL_URL")
    if not url:
        pytest.skip("DAESINGO_MYSQL_URL 미지정 — MySQL 통합 테스트는 opt-in")
    sa = pytest.importorskip("sqlalchemy")
    from alembic import command
    from alembic.config import Config

    engine = sa.create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:  # 깨끗한 schema에서 시작한다 — 테스트 전용 DB만 가리켜야 한다
        for table in ("analysis_scopes", "correction_records", "job_records", "cases", "case_alembic_version"):
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
    cfg = Config(str(Path(__file__).resolve().parents[2] / "migrations" / "case" / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()
```

(`from pathlib import Path`를 conftest import에 더한다.)

- [ ] **Step 5: migration 테스트** — `tests/case/test_store_mysql.py`

```python
"""MySQL 전용 — `DAESINGO_MYSQL_URL`이 있을 때만 돈다(`decisions/case-store-mysql.md` §8)."""

from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")


def test_migration_creates_case_tables_with_ascii_bin_ids(mysql_engine):
    with mysql_engine.connect() as conn:
        tables = {r[0] for r in conn.exec_driver_sql("SHOW TABLES")}
        assert {"cases", "job_records", "correction_records", "analysis_scopes", "case_alembic_version"} <= tables
        coll = conn.exec_driver_sql(
            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cases' AND COLUMN_NAME = 'case_id'"
        ).scalar_one()
        assert coll == "ascii_bin"
```

- [ ] **Step 6: 로컬 MySQL로 확인**

```bash
docker run -d --rm --name daesingo-mysql -e MYSQL_ROOT_PASSWORD=devpw -e MYSQL_DATABASE=daesingo_test -p 3306:3306 mysql:8.4
# 준비될 때까지 `docker exec daesingo-mysql mysqladmin ping -pdevpw --silent`가 성공할 때까지 기다린다
DAESINGO_MYSQL_URL="mysql+pymysql://root:devpw@127.0.0.1:3306/daesingo_test" python -m pytest tests/case/test_store_mysql.py -q -p no:cacheprovider
```

Expected: 1 passed. `DAESINGO_MYSQL_URL` 없이 돌리면 skip.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/daesingo/case/store_mysql.py migrations/case tests/case/conftest.py tests/case/test_store_mysql.py
git commit -m "feat(case): MySQL 테이블 정의 · Alembic 첫 migration(잠정 배치) · 공용 DB 의존성 (8-6)"
```

---

### Task 7: `MySQLCaseRepository` · 계약 테스트 MySQL 통과 · MySQL 전용 테스트

**Files:**
- Modify: `src/daesingo/case/store_mysql.py` (`MySQLCaseRepository` 추가)
- Modify: `tests/case/test_store_mysql.py` (전용 테스트 추가)

**Interfaces:**
- Consumes: Task 1의 `to_row` · `from_row` · `CaseRow`, Task 2의 오류 타입 · `validate_case_id` · `check_append_only`, Task 6의 테이블 · `mysql_engine` fixture
- Produces: `MySQLCaseRepository()` — `CaseRepository` Protocol 구현. 생성자 인자 없음, 상태 없음.

- [ ] **Step 1: 실패하는 MySQL 전용 테스트 추가** — `tests/case/test_store_mysql.py`에

```python
from daesingo.case.domain import CaseAggregate


def test_rollback_leaves_nothing(mysql_engine):
    """command 하나 = case 저장이 한 commit — 실패하면 남지 않는다(runtime-tech-spec §16 item 9의 case 쪽)."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.connect() as conn:
        trans = conn.begin()
        repo.insert(conn, CaseAggregate.empty("case_rb001"))
        trans.rollback()
    with mysql_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM cases WHERE case_id = 'case_rb001'").scalar_one() == 0


def test_update_lock_makes_second_writer_wait(mysql_engine):
    """같은 case 동시 쓰기는 줄을 선다(Review Focus 3)."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.begin() as conn:
        repo.insert(conn, CaseAggregate.empty("case_lock001"))
    with mysql_engine.connect() as a, mysql_engine.connect() as b:
        ta = a.begin()
        repo.load(a, "case_lock001", lock="update")
        tb = b.begin()
        b.exec_driver_sql("SET SESSION innodb_lock_wait_timeout = 1")
        with pytest.raises(sa.exc.OperationalError) as err:
            repo.load(b, "case_lock001", lock="update")
        assert "1205" in str(err.value)  # Lock wait timeout exceeded
        tb.rollback()
        ta.rollback()
    with mysql_engine.begin() as conn:
        for table in ("analysis_scopes", "correction_records", "job_records"):
            conn.exec_driver_sql(f"DELETE FROM {table} WHERE case_id = 'case_lock001'")
        conn.exec_driver_sql("DELETE FROM cases WHERE case_id = 'case_lock001'")


def test_repository_never_commits(mysql_engine):
    """저장소는 commit하지 않는다 — 호출자가 rollback하면 save도 사라진다."""
    from daesingo.case.store_mysql import MySQLCaseRepository

    repo = MySQLCaseRepository()
    with mysql_engine.begin() as conn:
        repo.insert(conn, CaseAggregate.empty("case_nc001"))
    with mysql_engine.connect() as conn:
        trans = conn.begin()
        case = repo.load(conn, "case_nc001", lock="update")
        case.start_search()
        repo.save(conn, case)
        trans.rollback()
    with mysql_engine.connect() as conn:
        assert repo.load(conn, "case_nc001").stage == "INTAKE"
```

- [ ] **Step 2: 실패 확인** (로컬 MySQL 켠 상태)

Run: `DAESINGO_MYSQL_URL=... python -m pytest tests/case/test_store_mysql.py tests/case/test_case_repository_contract.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'MySQLCaseRepository'`

- [ ] **Step 3: 구현** — `src/daesingo/case/store_mysql.py` 끝에

```python
from datetime import datetime, timezone
from typing import Any, Literal

from daesingo.case.domain import CaseAggregate
from daesingo.case.store import (
    AppendOnlyViolation,
    CaseAlreadyExists,
    CaseNotFound,
    check_append_only,
    validate_case_id,
)
from daesingo.case.store_state import CaseRow, from_row, to_row


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MySQLCaseRepository:
    """호출자의 `Connection`에 참여한다 — commit · rollback하지 않는다(#245 D-2). 상태를 들지 않는다:
    「무엇이 이미 저장됐나」는 매번 DB에서 읽는다(spec §5). 잠금은 `cases` 행에만 건다 — case 행 먼저."""

    def insert(self, conn: Any, case: CaseAggregate) -> None:
        validate_case_id(case.case_id)
        row = to_row(case)
        now = _now()
        try:
            conn.execute(cases_table.insert().values(
                case_id=row.case_id, case_rev=row.case_rev, stage=row.stage, selection_rev=row.selection_rev,
                state=row.state, created_at=now, updated_at=now,
            ))
        except sa.exc.IntegrityError:
            raise CaseAlreadyExists(f"case_id는 재등록할 수 없다: {case.case_id!r}") from None
        self._append_records(conn, row, job_from=0, correction_from=0, existing_scopes=set())

    def load(self, conn: Any, case_id: str, *, lock: Literal["share", "update"] = "share") -> CaseAggregate:
        query = sa.select(cases_table).where(cases_table.c.case_id == case_id)
        query = query.with_for_update(read=(lock == "share"))
        head = conn.execute(query).mappings().first()
        if head is None:
            raise CaseNotFound(f"등록되지 않은 case_id: {case_id!r}")
        return from_row(CaseRow(
            case_id=head["case_id"], case_rev=head["case_rev"], stage=head["stage"],
            selection_rev=head["selection_rev"], state=head["state"],
            job_records=self._records(conn, job_records_table, case_id),
            correction_records=self._records(conn, correction_records_table, case_id),
            analysis_scopes={
                r["scope_id"]: r["scope"]
                for r in conn.execute(
                    sa.select(analysis_scopes_table).where(analysis_scopes_table.c.case_id == case_id)
                ).mappings()
            },
        ))

    def save(self, conn: Any, case: CaseAggregate) -> None:
        row = to_row(case)
        result = conn.execute(
            cases_table.update().where(cases_table.c.case_id == row.case_id).values(
                case_rev=row.case_rev, stage=row.stage, selection_rev=row.selection_rev,
                state=row.state, updated_at=_now(),
            )
        )
        if result.rowcount == 0:
            raise CaseNotFound(f"등록되지 않은 case_id: {row.case_id!r}")
        stored_jobs = self._ids(conn, job_records_table, "job_id", row.case_id)
        stored_corrections = self._ids(conn, correction_records_table, "correction_id", row.case_id)
        check_append_only(stored_jobs, [r["job_id"] for r in row.job_records], "job_records")
        check_append_only(stored_corrections, [r["correction_id"] for r in row.correction_records], "correction_records")
        stored_scopes = {
            r["scope_id"]: r["scope"]
            for r in conn.execute(
                sa.select(analysis_scopes_table).where(analysis_scopes_table.c.case_id == row.case_id)
            ).mappings()
        }
        for scope_id, scope in stored_scopes.items():
            if row.analysis_scopes.get(scope_id) != scope:
                raise AppendOnlyViolation(f"analysis_scopes {scope_id!r}가 바뀌거나 지워졌다")
        self._append_records(
            conn, row, job_from=len(stored_jobs), correction_from=len(stored_corrections),
            existing_scopes=set(stored_scopes),
        )

    @staticmethod
    def _records(conn: Any, table: sa.Table, case_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(sa.select(table.c.record).where(table.c.case_id == case_id).order_by(table.c.seq))
        return [r[0] for r in rows]

    @staticmethod
    def _ids(conn: Any, table: sa.Table, id_col: str, case_id: str) -> list[str]:
        rows = conn.execute(sa.select(table.c[id_col]).where(table.c.case_id == case_id).order_by(table.c.seq))
        return [r[0] for r in rows]

    @staticmethod
    def _append_records(conn: Any, row: CaseRow, *, job_from: int, correction_from: int, existing_scopes: set[str]) -> None:
        jobs = [
            {"job_id": r["job_id"], "case_id": row.case_id, "seq": i, "record": r}
            for i, r in enumerate(row.job_records) if i >= job_from
        ]
        corrections = [
            {"correction_id": r["correction_id"], "case_id": row.case_id, "seq": i, "record": r}
            for i, r in enumerate(row.correction_records) if i >= correction_from
        ]
        scopes = [
            {"case_id": row.case_id, "scope_id": sid, "scope": s}
            for sid, s in row.analysis_scopes.items() if sid not in existing_scopes
        ]
        if jobs:
            conn.execute(job_records_table.insert(), jobs)
        if corrections:
            conn.execute(correction_records_table.insert(), corrections)
        if scopes:
            conn.execute(analysis_scopes_table.insert(), scopes)
```

`store.py`가 `store_mysql`을 import하지 않는지 확인한다(순환 import 방지 — 방향은 `store_mysql → store`만).

- [ ] **Step 3b: JSON 칼럼 왕복 확인** — `MySQLCaseRepository.load`에서 `head["state"]` · `r[0]`이 dict로 오는지 확인한다(SQLAlchemy `JSON` + PyMySQL은 dict로 준다). str로 오면 `json.loads`를 더한다.

- [ ] **Step 4: 통과 확인**

Run: `DAESINGO_MYSQL_URL=... python -m pytest tests/case/test_case_repository_contract.py tests/case/test_store_mysql.py -q -p no:cacheprovider`
Expected: 계약 테스트 memory · mysql 두 param 모두 PASS, MySQL 전용 4개 PASS.
그리고 `DAESINGO_MYSQL_URL` 없이 전체 `python -m pytest -q -p no:cacheprovider` — mysql param은 skip, 나머지 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daesingo/case/store_mysql.py tests/case/test_store_mysql.py
git commit -m "feat(case): MySQLCaseRepository — 호출자 transaction 참여 · FOR UPDATE/SHARE · append-only (8-6)"
```

---

### Task 8: 문서 — ERD · spec 상태 · 고도화 8-6 · 로컬 실행

**Files:**
- Modify: `docs/architecture/erd-draft.md` (case 부분: L380~392 · L421)
- Modify: `docs/modules/case/decisions/case-store-mysql.md` (상단 상태 줄)
- Modify: `docs/modules/case/design-refinement-w7-baseline.md` (8-6 행)
- Modify: `docs/modules/case/README.md` (로컬 MySQL 테스트 실행 방법 — 기존 문서에 「테스트」 절이 있으면 그 아래, 없으면 끝에 짧은 절)

- [ ] **Step 1: ERD case 부분 갱신** — `docs/architecture/erd-draft.md`에서 `cases`(「상세 schema 미정」) · `job_records` · `analysis_scopes` · `correction_records`(L421 「값 저장 미정」) 행을 spec §4의 칼럼 · 키로 바꾸고, 각 행 끝에 「(2026-10-06 구현, `decisions/case-store-mysql.md` §4)」를 단다. `correction_records` 값 저장은 「계약 dict를 `record` JSON으로 그대로」로 닫는다. 다른 모듈 행은 건드리지 않는다.

- [ ] **Step 2: spec 상태 줄** — `decisions/case-store-mysql.md` 첫 인용 블록의 「상태: 설계 승인 (구현 전)」을 「상태: 1단계 구현(2026-10-06, `case-store-mysql-plan.md`). §6 진입점은 `store=` 인자를 유지하고 `CaseStore`가 repository · conn · adapters를 묶는다 — 동작은 이 문서 그대로」로 바꾼다.

- [ ] **Step 3: 고도화 8-6 행** — `| 8-6 | 🔄 **1단계 설계 …` 앞부분을 「🔄 **1단계 구현(2026-10-06) — `MySQLCaseRepository` · in-memory 복사본 load · `CaseStore` facade. 처리 execution · 중단 job 테이블(8-8 · 8-9)과 adapter 제거(2단계)는 남음.**」으로 바꾼다.

- [ ] **Step 4: 로컬 실행 방법** — `docs/modules/case/README.md`에:

```markdown
### MySQL 통합 테스트 (opt-in)

case 저장소의 MySQL 구현은 `DAESINGO_MYSQL_URL`이 있을 때만 테스트한다(CI는 아직 MySQL 없음 — Runtime Implementation Plan에서 통합).

    docker run -d --rm --name daesingo-mysql -e MYSQL_ROOT_PASSWORD=devpw -e MYSQL_DATABASE=daesingo_test -p 3306:3306 mysql:8.4
    DAESINGO_MYSQL_URL="mysql+pymysql://root:devpw@127.0.0.1:3306/daesingo_test" python -m pytest tests/case -q

테스트 fixture가 시작할 때 case 테이블을 지우고 migration을 다시 올린다 — **테스트 전용 DB만** 가리킨다. migration(잠정 배치): `DAESINGO_MYSQL_URL=... alembic -c migrations/case/alembic.ini upgrade head`.
```

- [ ] **Step 5: 확인 · Commit**

Run: `python scripts/check_boundaries.py` · `python scripts/check_contract_fixtures.py`
Expected: 둘 다 PASS

```bash
git add docs/architecture/erd-draft.md docs/modules/case/decisions/case-store-mysql.md docs/modules/case/design-refinement-w7-baseline.md docs/modules/case/README.md
git commit -m "docs(case): CaseStore MySQL 1단계 구현 반영 — ERD · spec 상태 · 8-6 · 로컬 실행 (8-6)"
```
