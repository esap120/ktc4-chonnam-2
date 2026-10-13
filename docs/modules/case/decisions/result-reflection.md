# Worker T2 결과 반영 — `reflect_execution()` · 처리한 `execution_id` · `ProducedReader`

> **상태: 결정 · 구현** · 결정일 2026-10-11 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-8(`../design-refinement-w7-baseline.md`), #245 D-5, Runtime Tech Spec §12.2, RT-04(b) `ResultReflector`(`src/daesingo/common/jobs/reflection.py`), RT-09(#296)
> case 반영 함수의 모양 · 중복 판단 · kind별 반영은 case 결정 범위다. T2 transaction(반영 → 후속 enqueue → `case_applied_at` 표식)과 port 모양은 Runtime 소유(Tech Spec §12.2)이고, 모듈 결과가 process 밖 어디에 남는지는 8-6 2단계(RT-10 Gate)다. 이 문서는 case 쪽만 둔다.

## 1. 목표 · 범위

Worker가 terminal execution 하나를 넘기면 case가 한 번만, 기다리던 job일 때만 결과를 반영하고 후속 JobRecord를 돌려준다. RT-09 첫 비동기 E2E가 fake handler · fake reader로 이 경로를 쓴다.

**범위 밖:** 결과 내용의 저장 위치(8-6 2단계) · 판독 · Fine · export kind 반영(8-6 2단계 뒤) · 후보 수신 뒤 자동 선택과 판독 · Fine 발주(동기 경로도 반영 함수 밖에서 한다 — worker 배선 때) · 이전 후보 결과의 선택 context 대조(6.6순위 조건 2 — 판독 · Fine 반영과 함께) · case timeout.

## 2. 흐름

```
[Worker T2] 호출자 transaction
  reflect_execution(outcome, store, reader, timelines)
    load_for_update(case_id)                        ← case 행 먼저 잠금
    processed_executions에 execution_id 있음 → ALREADY_APPLIED (저장 없음)
    job이 이 case 것 · kind 일치 · 반영기 있음 확인 (아니면 ValueError)
    awaits_result(job_id)=False → NOT_APPLIED(reason = 정산 사유)
    kind별 반영 (내용은 reader(conn, kind, produced))
    processed_executions[execution_id] = job_id · save
    → APPLIED + 이번에 append한 JobRecord
  composition root: 후속 enqueue · case_applied_at 표식 (reflect_terminal)
```

## 3. 결정

1. **case 공개 함수는 `reflection.reflect_execution()`이고 Runtime 타입을 모른다.** 입력 `ExecutionOutcome`(execution_id · job_id · case_id · kind · attempt · status · produced · failure_kind), 출력 `ReflectionOutcome`(status · reason · appended_job_records)은 Runtime `ReflectionInput` · `ReflectionResult`와 1:1이다. composition root가 옮긴다(예시: `tests/case/test_result_reflection_mysql.py`의 `_CaseReflector`). read port(`jobexecution-read-port.md`)와 같은 경계다.
2. **처리한 `execution_id`는 aggregate `state` JSON의 `processed_executions: {execution_id: job_id}`에 둔다.** 정산 기록(`running-jobs-derivation.md` 결정 5)과 같은 이유다 — case당 수십 개 이하이고 이미 case 행을 잠근 뒤 aggregate와 함께 읽고 쓴다. 새 테이블 · migration이 없다. `case-store-mysql.md` D5의 「처리한 `execution_id` 테이블」은 이것으로 대신한다. 옛 행에 키가 없으면 빈 dict다.
3. **판단 순서는 「같은 execution」 → 「배선 확인」 → 「기다리는 job인가」다.**
   - 이미 처리한 execution이면 `ALREADY_APPLIED` — T1 · T2 사이 Worker가 죽거나 T2 commit 응답을 잃어 Runtime이 다시 넘긴 경우(Tech Spec §12.2).
   - 이 case가 발주하지 않은 job · kind 불일치 · 반영기가 없는 kind는 `ValueError`(배선 오류). **반영기가 없는 kind를 조용히 `REFLECTED`로 정산하지 않는다** — 결과를 버린 채 「반영됨」이 남는다.
   - 기다리지 않는 job(8-9 `awaits_result`)이면 `NOT_APPLIED`이고 reason은 정산 사유(`CANCELLED` · `SUPERSEDED` · `STOPPED_WAITING`)다. 다른 경로(동기 경로 · 다른 execution)로 `REFLECTED`된 job이 오면 Runtime reason에 없는 값이라 `ValueError`로 드러낸다 — job 하나에 T2로 오는 terminal은 하나다(STALE은 T2로 오지 않는다).
4. **kind별 반영(이번 판).**
   - `HINT_EXTRACT` — `SUCCEEDED`면 reader가 준 단서 구조화 결과, `FAILED`면 `{"status": "FAILED"}`로 `reflect_hint_extraction(job_id=…)` — 실패해도 빈 단서로 첫 탐색을 발주한다(case-command Draft §11). 그 `COARSE_SEARCH`가 후속 JobRecord다.
   - `COARSE_SEARCH` — `SUCCEEDED`면 reader의 `{outcome, candidate_events}`: Run이 `FAILED`면 탐색 실패, 아니면 후보 수신. 실행이 `FAILED`면 reader를 부르지 않고 탐색 실패. 후보 변환은 동기 경로와 같은 `service.candidates_from_events()`다.
5. **결과 내용은 주입한 `ProducedReader`(`(conn, kind, produced) -> dict`)가 준다.** `produced`는 `(kind, ref)` 참조뿐이다. 무엇을 어디서 읽는지는 8-6 2단계가 정하고, 그때 reader를 꽂는다. reader 예외는 그대로 올라가고 아무것도 저장되지 않는다.
6. **반영했을 때만 저장한다.** `ALREADY_APPLIED` · `NOT_APPLIED`는 case를 바꾸지 않는다 — 결정적이라 재전달에도 같은 답이다.

## 4. 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| `processed_executions` 테이블(UNIQUE) | 이미 case 행을 잠그고 aggregate를 읽는다. migration · 저장소 코드가 늘고 얻는 게 적다. 이력 조회가 필요해지면 forward-only로 옮긴다 |
| 처리 기록 없이 job 정산(`REFLECTED`)만으로 재전달 판단 | 동기 경로 · 다른 execution으로 반영된 job과 같은 execution의 재전달을 구분하지 못한다. #245 D-5에서 「처리한 `execution_id`를 남긴다」고 약속했다 |
| case가 Runtime `ResultReflector`를 직접 구현 | case가 Runtime 타입에 묶인다. 어댑터는 몇 줄이다 |
| 반영기 없는 kind는 `REFLECTED`로 정산만 | 결과를 버리고 「반영됨」을 남긴다. `running_jobs`에서 빠져 화면은 끝난 것처럼 보인다 |
| 8-6 2단계(결과 저장 위치)까지 함께 | search · readout · recording Owner와 맞춰야 하고 그동안 RT-09가 막힌다 |

## 5. 테스트

- `tests/case/test_result_reflection.py` — 탐색 후보 · Run 실패 · 실행 실패, 단서 성공 · 실패(후속 `COARSE_SEARCH`), 같은 execution 재전달, 중단 · 대체 job, 다른 case job · kind 불일치 · 반영기 없는 kind · 다른 경로로 반영된 job, reader 오류 시 저장 없음.
- `tests/case/test_case_repository_contract.py::test_processed_executions_survive_save_and_load` — in-memory · MySQL.
- `tests/case/test_result_reflection_mysql.py`(MySQL opt-in, CI 필수) — 실제 Runtime `enqueue` · `claim_one` · `finish` · `reflect_terminal`에 어댑터로 꽂아 `APPLIED` → 재전달 `ALREADY_APPLIED` · `case_applied_at` 표식 · `running_jobs=[]`, rollback이면 case · 표식 둘 다 남지 않음.

## 6. 남은 것

- RT-09(#296) · RT-06(T2 재전달)이 composition root에서 이 함수를 `ResultReflector`로 꽂는다.
- 8-6 2단계: 모듈 결과 저장 위치와 실제 `ProducedReader`, export 반영기(`REPORT_VIDEO_EXPORT` · `PLATE_IMAGE_EXPORT`), adapter 제거. *(판독 · Fine 반영기는 2026-10-13 — 정산 + READY gate, `observation-storage.md` §4-5.)*
- 후보 수신 뒤 자동 선택 · 판독 · Fine 발주와 선택 context 대조(6.6순위 조건 1 · 2).
