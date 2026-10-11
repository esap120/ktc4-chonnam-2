# running_jobs case 계산 (8-11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `CaseView.running_jobs[]`를 호출자가 넘기지 않고 case가 JobRecord + 정산 기록으로 직접 계산한다. command 응답(HTTP 202)의 `case_view`에는 이번 command가 append한 job이 `PENDING`으로 들어간다.

**Architecture:** aggregate에 `settled_jobs: dict[job_id, reason]`(state JSON)를 두고, `running_jobs` = 정산되지 않은 JobRecord다. status는 그 job의 JobExecution 기록(선택 인자 `job_executions`)으로 정한다 — 기록이 없거나 `QUEUED`면 `PENDING`, 그 밖은 `RUNNING`. 같은 kind · scope_ref로 새 job을 발주하면 이전 job은 `SUPERSEDED`로 정산한다.

**Tech Stack:** Python 3.12 · pytest

**Spec:** `docs/modules/case/decisions/running-jobs-derivation.md`(이 계획과 함께 작성) · 계약 B절 §10 불변조건 5(`contract-job-record-case-view.md`) · `design-refinement-w7-baseline.md` 8-11 행

## Global Constraints

- 정산 사유 4종, 문자열 그대로: `REFLECTED` · `STOPPED_WAITING` · `CANCELLED` · `SUPERSEDED`.
- 정산은 처음 사유가 이긴다(idempotent) — 이미 정산된 job_id를 다시 정산하면 아무것도 바꾸지 않고 `False`를 돌려준다.
- 정산은 `case_rev`를 올리지 않는다.
- `running_jobs[]` 원소 모양은 계약 그대로 `{job_id, kind, label_key, status}` 네 키, 순서는 `job_records` 순서.
- `label_key` 매핑: `PLATE_READ`→`job.plate_read`, `OVERLAY_TIME_READ`→`job.overlay_time_read`, `FINE_VERIFY`→`job.fine_verify`, `REPORT_VIDEO_EXPORT`→`job.report_video_export`, `PLATE_IMAGE_EXPORT`→`job.plate_image_export`, 그 밖(`COARSE_SEARCH` 포함)→`job.generic_processing`.
- 대표 execution은 `attempt` 최댓값(A§10-6).
- 공개 함수에서 `running_jobs=` 인자를 **없앤다**(`build_case_view` · `build_view_from_adapter` · `get_view` · `handle_command` · `execute_command`). 대신 `job_executions: list[dict] | None = None`을 받는다.
- 저장: `settled_jobs`는 `store_state._STATE_FIELDS`에 추가(state JSON). 새 테이블 · migration 없음. `STATE_VERSION`은 그대로 1(없는 키는 dataclass 기본값).
- 테스트 실행 전 PATH에 static_ffmpeg bin을 앞에 붙인다(로컬 anaconda ffmpeg 4.3.1은 ~37개 테스트를 깬다): `export PATH="$(python -c 'import static_ffmpeg,os;print(os.path.join(os.path.dirname(static_ffmpeg.__file__),"bin","win32"))'):$PATH"` — 경로가 다르면 `site-packages/static_ffmpeg/bin/` 아래를 찾는다.
- 커밋 trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. 커밋 메시지는 한국어, `feat(case): … (8-11)` 모양.
- 범위 밖: 결과 반영(`REFLECTED`)의 실제 호출(8-8), 중단 · timeout command(8-9), JobExecution 읽기 포트(D-6), #276 후속(Fine 기다림을 멈췄는데 실행이 남은 경우 표시).

## Review Focus

1. **방금 발주한 job이 202 응답에 `PENDING`으로 보인다** — `RUN_NOTICE_ACTION` 성공 응답의 `case_view.running_jobs`에 새 job_id가 `PENDING`으로. → Task 2 테스트.
2. **재시도로 대체된 이전 job이 계속 남지 않는다** — 같은 kind · scope_ref 재발주 뒤 running_jobs에는 새 job 하나만. → Task 1 · Task 2 테스트.
3. **정산 기록이 저장소 왕복 뒤에도 남는다** — in-memory 저장소 save → load 뒤 `settled_jobs` 유지. → Task 1 테스트.
4. **후보를 받으면 탐색 job이 빠진다** — `receive_candidates` · `record_candidate_search_failure` 뒤 COARSE_SEARCH가 running_jobs에 없다. → Task 1 테스트.
5. **실행이 terminal인데 아직 반영 전이면 빠지지 않는다**(불변조건 5) — execution `FAILED`/`SUCCEEDED`/`STALE`이어도 정산 전이면 `RUNNING`으로 남는다. → Task 2 테스트.

---

## File Structure

- Modify `src/daesingo/case/domain.py` — `JOB_SETTLE_REASONS`, `CaseAggregate.settled_jobs`, `settle_job()`, `waiting_job_records()`; `receive_candidates()` · `record_candidate_search_failure()`가 COARSE_SEARCH를 `REFLECTED`로 정산.
- Modify `src/daesingo/case/jobs.py` — `issue_job()`이 같은 kind · scope_ref의 기다리는 job을 `SUPERSEDED`로 정산.
- Modify `src/daesingo/case/store_state.py` — `_STATE_FIELDS`에 `"settled_jobs"`.
- Modify `src/daesingo/case/view.py` — `JOB_LABEL_KEYS`, `derive_running_jobs()`, `build_case_view(job_executions=…)`.
- Modify `src/daesingo/case/service.py` · `src/daesingo/case/command.py` — 인자 교체.
- Tests: `tests/case/test_job_settlement.py`(신규), `tests/case/test_running_jobs_view.py`(신규), `tests/case/test_command.py`(추가), smoke 3개 수정.

---

### Task 1: 정산 기록 (domain · jobs · store_state)

**Files:**
- Modify: `src/daesingo/case/domain.py`
- Modify: `src/daesingo/case/jobs.py:37-65`
- Modify: `src/daesingo/case/store_state.py:19-26`
- Test: `tests/case/test_job_settlement.py`

**Interfaces:**
- Produces: `JOB_SETTLE_REASONS: tuple[str, ...]`(domain), `CaseAggregate.settled_jobs: dict[str, str]`, `CaseAggregate.settle_job(job_id: str, reason: str) -> bool`, `CaseAggregate.waiting_job_records() -> list[dict]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_job_settlement.py`

```python
"""JobRecord 정산 기록 — `decisions/running-jobs-derivation.md`."""

import pytest

from daesingo.case import jobs
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import CaseStore


def _case() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_settle", hints={}, manifest_summary={})
    case.start_search()
    return case


def _candidate(cid: str) -> Candidate:
    return Candidate(candidate_id=cid, at=None, at_provenance=None, observed="", thumb_ref=None, rank=1)


def test_new_job_is_waiting():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    assert case.waiting_job_records() == [job]


def test_settled_job_is_not_waiting():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    assert case.settle_job(job["job_id"], "CANCELLED") is True
    assert case.waiting_job_records() == []
    assert case.settled_jobs == {job["job_id"]: "CANCELLED"}


def test_first_reason_wins():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.settle_job(job["job_id"], "STOPPED_WAITING")
    assert case.settle_job(job["job_id"], "REFLECTED") is False
    assert case.settled_jobs[job["job_id"]] == "STOPPED_WAITING"


def test_settle_does_not_bump_case_rev():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    rev = case.case_rev
    case.settle_job(job["job_id"], "REFLECTED")
    assert case.case_rev == rev


def test_unknown_reason_is_rejected():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    with pytest.raises(ValueError):
        case.settle_job(job["job_id"], "DONE")


def test_unknown_job_id_is_rejected():
    with pytest.raises(ValueError):
        _case().settle_job("job_missing", "REFLECTED")


def test_reissue_same_kind_and_scope_supersedes_previous():
    case = _case()
    old = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    new = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    assert case.settled_jobs == {old["job_id"]: "SUPERSEDED"}
    assert case.waiting_job_records() == [new]


def test_different_scope_or_kind_does_not_supersede():
    case = _case()
    a = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    b = jobs.issue_coarse_search(case, scope_ref="scope_b", input_fingerprint="sha1:b")
    c = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert case.waiting_job_records() == [a, b, c]


def test_receiving_candidates_reflects_coarse_search():
    case = _case()
    search = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.receive_candidates([_candidate("cand_a")])
    assert case.settled_jobs == {search["job_id"]: "REFLECTED"}


def test_search_failure_reflects_coarse_search():
    case = _case()
    search = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.record_candidate_search_failure()
    assert case.settled_jobs == {search["job_id"]: "REFLECTED"}


def test_settled_jobs_survive_store_round_trip():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="scope_a", input_fingerprint="sha1:a")
    case.settle_job(job["job_id"], "CANCELLED")
    store = CaseStore()
    store.register(case)
    assert store.get_case(case.case_id).settled_jobs == {job["job_id"]: "CANCELLED"}
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/case/test_job_settlement.py -q` → `AttributeError: … 'waiting_job_records'` 등으로 FAIL.

- [ ] **Step 3: 구현**

`domain.py` — 모듈 상수(클래스 위)와 필드 · 메서드:

```python
# JobRecord 정산 사유 — case가 그 job의 결과를 더 기다리지 않게 된 이유(`decisions/running-jobs-derivation.md`).
JOB_SETTLE_REASONS = ("REFLECTED", "STOPPED_WAITING", "CANCELLED", "SUPERSEDED")
```

`analysis_scopes` 필드 바로 아래에:

```python
    # case가 더는 결과를 기다리지 않는 job(`job_id` → `JOB_SETTLE_REASONS` 중 하나). `running_jobs[]`는
    # 여기 없는 JobRecord다(계약 B§10 불변조건 5). 처음 사유가 이긴다. CaseView 비노출.
    settled_jobs: dict[str, str] = field(default_factory=dict)
```

`record_job()` 아래에:

```python
    def settle_job(self, job_id: str, reason: str) -> bool:
        """case가 `job_id`의 결과를 더 기다리지 않는다고 기록한다. 이미 정산된 job이면 처음 사유를
        유지하고 `False` — 같은 결과가 두 번 와도 같다(#245 D-5). `case_rev`는 올리지 않는다."""
        if reason not in JOB_SETTLE_REASONS:
            raise ValueError(f"알 수 없는 정산 사유: {reason!r} (등록된 사유: {JOB_SETTLE_REASONS})")
        if not any(r["job_id"] == job_id for r in self.job_records):
            raise ValueError(f"이 case가 발주하지 않은 job_id: {job_id!r}")
        if job_id in self.settled_jobs:
            return False
        self.settled_jobs[job_id] = reason
        return True

    def waiting_job_records(self) -> list[dict[str, Any]]:
        """아직 정산되지 않은 JobRecord — `running_jobs[]`의 원천. `job_records` 순서."""
        return [r for r in self.job_records if r["job_id"] not in self.settled_jobs]

    def _reflect_waiting(self, kind: str) -> None:
        for record in self.waiting_job_records():
            if record["kind"] == kind:
                self.settle_job(record["job_id"], "REFLECTED")
```

`receive_candidates()` 본문 끝과 `record_candidate_search_failure()` 본문 끝에 각각 `self._reflect_waiting("COARSE_SEARCH")`를 넣는다(stage 검사 뒤, 성공 경로에서만).

`jobs.py` `issue_job()` — `case.record_job(job_record)` 바로 앞에:

```python
    # 같은 kind · scope_ref의 기다리던 job은 이 job으로 대체된다 — 대표 job은 가장 나중 job이다(A§10-7).
    for prior in case.waiting_job_records():
        if prior["kind"] == kind and prior["scope_ref"] == scope_ref:
            case.settle_job(prior["job_id"], "SUPERSEDED")
```

`store_state.py` `_STATE_FIELDS`에 `"settled_jobs",`를 마지막 원소로 추가.

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/case/test_job_settlement.py -q` → PASS. 이어서 `python -m pytest tests/case -q`로 회귀 확인(이 Task만으로는 view가 아직 `running_jobs` 인자를 쓰므로 기존 테스트는 통과해야 한다). 실패가 있으면 원인을 보고서에 적는다.

- [ ] **Step 5: 커밋**

```bash
git add src/daesingo/case/domain.py src/daesingo/case/jobs.py src/daesingo/case/store_state.py tests/case/test_job_settlement.py
git commit -m "feat(case): JobRecord 정산 기록 — 대체 · 후보 수신 시 정산 (8-11)"
```

---

### Task 2: running_jobs 계산과 인자 교체 (view · service · command · 테스트)

**Files:**
- Modify: `src/daesingo/case/view.py` (`build_case_view` 시그니처 · 출력, 새 함수)
- Modify: `src/daesingo/case/service.py:180-215, 470-495` · `src/daesingo/case/command.py:150-190`
- Modify: `src/daesingo/case/adapters.py:48` 근처 docstring(“호출자가 `running_jobs`를 직접 넘김” 문구를 case가 계산한다로)
- Test: `tests/case/test_running_jobs_view.py`(신규), `tests/case/test_command.py`(추가), `tests/case/test_scenario_happy_smoke.py:44-56`, `tests/case/test_scenario_infra_failure_smoke.py:~115-130`, `tests/case/test_scenario_plate_reread_smoke.py:100-153`

**Interfaces:**
- Consumes: Task 1의 `case.waiting_job_records()` · `case.settle_job()`
- Produces: `view.JOB_LABEL_KEYS: dict[str, str]`, `view.derive_running_jobs(case, job_executions=None) -> list[dict]`; `build_case_view(..., job_executions=None, ...)`, `build_view_from_adapter(..., job_executions=None, ...)`, `get_view(..., job_executions=None, ...)`, `handle_command(..., job_executions=None, notices=None)`, `execute_command(..., job_executions=None, notices=None)` — 모두 `running_jobs` 인자는 없음.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/case/test_running_jobs_view.py`:

```python
"""case가 계산하는 `running_jobs[]` — 계약 B§10 불변조건 5, `decisions/running-jobs-derivation.md`."""

import pytest

from daesingo.case import jobs
from daesingo.case.domain import CaseAggregate
from daesingo.case.view import build_case_view, derive_running_jobs


def _case() -> CaseAggregate:
    case = CaseAggregate.intake(case_id="case_rj", hints={}, manifest_summary={})
    case.start_search()
    return case


def _exec(job_id: str, attempt: int, status: str) -> dict:
    return {"job_id": job_id, "attempt": attempt, "status": status}


def test_job_without_execution_is_pending():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert derive_running_jobs(case) == [
        {"job_id": job["job_id"], "kind": "PLATE_READ", "label_key": "job.plate_read", "status": "PENDING"}
    ]


def test_queued_execution_is_pending():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert derive_running_jobs(case, [_exec(job["job_id"], 1, "QUEUED")])[0]["status"] == "PENDING"


@pytest.mark.parametrize("status", ["RUNNING", "SUCCEEDED", "FAILED", "STALE", "CANCELLED"])
def test_reported_execution_before_settlement_is_running(status):
    # terminal 기록과 case 반영 사이 · retry backoff 동안에도 빠지지 않는다(불변조건 5).
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    assert derive_running_jobs(case, [_exec(job["job_id"], 1, status)])[0]["status"] == "RUNNING"


def test_representative_execution_is_max_attempt():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    executions = [_exec(job["job_id"], 2, "QUEUED"), _exec(job["job_id"], 1, "STALE")]
    assert derive_running_jobs(case, executions)[0]["status"] == "PENDING"


def test_settled_job_is_dropped_even_if_execution_running():
    case = _case()
    job = jobs.issue_plate_read(case, input_fingerprint="sha1:p")
    case.settle_job(job["job_id"], "CANCELLED")
    assert derive_running_jobs(case, [_exec(job["job_id"], 1, "RUNNING")]) == []


@pytest.mark.parametrize(
    ("issue", "label_key"),
    [
        (lambda c: jobs.issue_coarse_search(c, scope_ref="s", input_fingerprint="f"), "job.generic_processing"),
        (lambda c: jobs.issue_overlay_time_read(c, input_fingerprint="f"), "job.overlay_time_read"),
        (lambda c: jobs.issue_fine_verify(c, input_fingerprint="f"), "job.fine_verify"),
        (lambda c: jobs.issue_report_video_export(c, input_fingerprint="f"), "job.report_video_export"),
        (lambda c: jobs.issue_job(c, "PLATE_IMAGE_EXPORT", input_fingerprint="f"), "job.plate_image_export"),
    ],
)
def test_label_key_by_kind(issue, label_key):
    case = _case()
    issue(case)
    assert derive_running_jobs(case)[0]["label_key"] == label_key


def test_case_view_carries_derived_running_jobs():
    case = _case()
    job = jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f")
    view = build_case_view(case, job_executions=[_exec(job["job_id"], 1, "RUNNING")])
    assert view["running_jobs"] == [
        {"job_id": job["job_id"], "kind": "COARSE_SEARCH", "label_key": "job.generic_processing", "status": "RUNNING"}
    ]
```

`tests/case/test_command.py` 끝(8-7 블록 아래)에:

```python
# --- 202 응답의 case_view에 방금 append한 job (8-11, HTTP API Contract §5.3) ----------------


def test_command_response_view_shows_appended_job_as_pending():
    store, case = _store_with_selected_case()

    result = command.execute_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),
        store=store,
        notices=[PLATE_READ_FAILED],
    )

    appended = result.appended_job_records[0]
    # 재시도로 대체된 이전 PLATE_READ는 빠지고, 새 job만 실행 기록 없이 PENDING으로 보인다.
    assert result.response["case_view"]["running_jobs"] == [
        {"job_id": appended["job_id"], "kind": "PLATE_READ", "label_key": "job.plate_read", "status": "PENDING"}
    ]
```

(`_store_with_selected_case()`의 COARSE_SEARCH는 `receive_candidates()`가 Task 1에서 정산하므로 목록에 없다.)

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/case/test_running_jobs_view.py tests/case/test_command.py -q` → `ImportError: derive_running_jobs` 등으로 FAIL.

- [ ] **Step 3: 구현**

`view.py` — `representative_execution_status()` 근처에:

```python
# `running_jobs[].label_key` — 계약 A§12 · B§12 등재 키. 미등록 kind와 `COARSE_SEARCH`는 fallback.
JOB_LABEL_KEYS = {
    "PLATE_READ": "job.plate_read",
    "OVERLAY_TIME_READ": "job.overlay_time_read",
    "FINE_VERIFY": "job.fine_verify",
    "REPORT_VIDEO_EXPORT": "job.report_video_export",
    "PLATE_IMAGE_EXPORT": "job.plate_image_export",
}
JOB_LABEL_FALLBACK = "job.generic_processing"


def derive_running_jobs(
    case: CaseAggregate, job_executions: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """case가 아직 결과를 기다리는 job(B§10 불변조건 5) = 정산되지 않은 JobRecord. status는 그 job의
    대표 execution(`attempt` 최댓값, A§10-6)이 없거나 `QUEUED`면 `PENDING`, 그 밖은 `RUNNING`이다 —
    terminal인데 아직 반영 전이거나 retry backoff 중이어도 case는 기다리는 중이다."""
    running = []
    for record in case.waiting_job_records():
        attempts = [e for e in job_executions or [] if e["job_id"] == record["job_id"]]
        status = max(attempts, key=lambda e: e["attempt"])["status"] if attempts else None
        running.append(
            {
                "job_id": record["job_id"],
                "kind": record["kind"],
                "label_key": JOB_LABEL_KEYS.get(record["kind"], JOB_LABEL_FALLBACK),
                "status": "PENDING" if status in (None, "QUEUED") else "RUNNING",
            }
        )
    return running
```

`build_case_view()`: `running_jobs` 인자를 지우고 같은 자리에 `job_executions: list[dict[str, Any]] | None = None,`. 출력 `"running_jobs": running_jobs or [],` → `"running_jobs": derive_running_jobs(case, job_executions),`.

`service.py`: `build_view_from_adapter()` · `get_view()`에서 `running_jobs` 인자 · 전달을 `job_executions`로 바꾼다. `build_view_from_adapter` docstring의 「`running_jobs`/`notices`는 … 호출자가 직접 안다」 문단은 「`running_jobs`는 case가 정산 기록으로 계산하고(`view.derive_running_jobs`), 실행 상태만 `job_executions`로 받는다. `notices`는 호출자가 직접 안다…」로 고친다.

`command.py`: `handle_command()` · `execute_command()`의 `running_jobs` 인자를 `job_executions`로 바꾸고 `view_kwargs` · `view_of()` 전달도 같이. `execute_command` docstring의 「`running_jobs`·`notices`는 `get_view()`에 그대로 넘긴다」 → 「`job_executions`·`notices`는 …」.

`adapters.py:48` 근처 문구의 「대신 호출자가 `running_jobs`를 직접 넘김」 → 「`running_jobs`는 case가 정산 기록으로 계산함」.

smoke 테스트 3개 — `running_jobs=[…]` 인자를 지운다:
- `test_scenario_happy_smoke.py`: `job_executions=[{"job_id": case.job_records[0]["job_id"], "attempt": 1, "status": "RUNNING"}]`로 바꾸고, 기존 기대값(job_id · COARSE_SEARCH · `job.generic_processing` · RUNNING)은 그대로 단언되게 한다.
- `test_scenario_infra_failure_smoke.py:~121`: 같은 방식으로 그 job의 execution `RUNNING`을 넘긴다(fixture가 RUNNING을 기대).
- `test_scenario_plate_reread_smoke.py`: `view_pending`은 인자 없이(방금 발주 → PENDING, fixture 기대와 같음). `view_resolved` 앞, `case.bump_revision()` 바로 뒤에 `case.settle_job(reread_job["job_id"], "REFLECTED")`(재판독 결과 반영 — 8-8이 할 일을 테스트가 대신) 를 넣는다. 단, 이 scenario에서 앞서 발주된 다른 job(예: 처음 PLATE_READ)이 대체되지 않고 남아 `view_resolved["running_jobs"] == []`가 깨지면, 그 job도 결과가 반영된 것이므로 같은 방식으로 `REFLECTED` 정산을 넣는다.

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/case -q` 전체. 이어서 저장소 전체 `python -m pytest -q`. 다른 테스트가 `running_jobs == []`에서 깨지면: 그 scenario에서 job 결과가 이미 반영된 시점이면 테스트에 `settle_job(…, "REFLECTED")`를 넣고, 그렇지 않으면 기대값을 계산 결과로 바꾸지 말고 보고서에 적는다(구현 버그일 수 있다). `running_jobs=` 키워드로 호출하는 곳이 남아 있지 않은지 `grep -rn "running_jobs=" src tests apps --include=*.py`로 확인.

- [ ] **Step 5: 커밋**

```bash
git add src/daesingo/case tests/case
git commit -m "feat(case): running_jobs를 case가 정산 기록으로 계산 — command 응답에 방금 발주한 job PENDING (8-11)"
```
