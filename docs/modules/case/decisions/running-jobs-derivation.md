# running_jobs를 case가 계산하는 방식 — JobRecord 정산 기록

> **상태: 결정 · 구현** · 결정일 2026-10-06 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-11(`../design-refinement-w7-baseline.md`), #247 H-4, HTTP API Contract Draft §5.3 · §7-2(#265)
> case 내부 상태와 CaseView 투영 방식이라 case 단독 결정 범위다. `running_jobs[]`의 정의 원문은 `../../../architecture/contracts/contract-job-record-case-view.md` B절 §10 불변조건 5이고, 이 문서는 그 정의를 어떻게 계산하는지와 고르지 않은 안만 둔다.

## 배경

지금은 `running_jobs[]`를 호출자가 리스트로 넘긴다(`get_view` · `handle_command` · `build_case_view`의 `running_jobs=` 인자). 그래서 command 응답(HTTP 202)의 `case_view`에 방금 발주한 job이 들어가지 않고, 202 직후 web polling이 「기다릴 job 없음」을 보고 멈출 수 있다(#265 §5.3 · §7-2).

case가 직접 계산하려면 「이 job을 아직 기다리는가」를 알아야 한다. JobRecord는 발주 의도만 담은 append-only 기록이라 그 답이 없다. 불변조건 5에 따르면 실행이 끝났다는 사실(JobExecution terminal)만으로도 답이 정해지지 않는다. 결과를 반영하기 전에는 빠지지 않고, 사용자가 중단하면 실행이 남아 있어도 빠진다.

## 결정

1. **aggregate에 정산 기록 `settled_jobs: dict[job_id, 사유]`를 둔다.** 사유는 4종이다.

   | 사유 | 언제 | 누가 기록 |
   | --- | --- | --- |
   | `REFLECTED` | case가 그 job의 결과(성공 · 실패)를 반영했다 | 결과 반영 경로(8-8). 지금은 후보 수신(`receive_candidates` · `record_candidate_search_failure`)이 COARSE_SEARCH에 대해 기록한다 |
   | `STOPPED_WAITING` | case timeout으로 기다리기를 멈췄다 | timeout 경로(8-9 이후) |
   | `CANCELLED` | 사용자가 중단했다 | 중단 command(8-9) |
   | `SUPERSEDED` | 같은 kind · `scope_ref`로 새 job을 발주했다 | `jobs.issue_job()` |

   처음 사유가 이긴다. 이미 정산된 job을 다시 정산하면 아무것도 바뀌지 않는다(#245 D-5의 idempotent 반영과 같은 원칙). 정산은 `case_rev`를 올리지 않는다.
2. **`running_jobs[]` = 정산되지 않은 JobRecord**이고 `job_records` 순서를 따른다.
3. **status는 그 job의 대표 JobExecution으로 정한다**(`attempt` 최댓값, A§10-6). 실행 기록이 없거나 `QUEUED`이면 `PENDING`, 그 밖은 모두 `RUNNING`이다. terminal인데 반영 전이거나 retry backoff 중이어도 case는 기다리는 중이기 때문이다. JobExecution 읽기 포트(D-6)가 아직 없어서, 실행 기록은 선택 인자 `job_executions`로 받는다. 응답을 만드는 시점에는 enqueue 전이므로 방금 append한 job은 늘 `PENDING`이다(8-11 요구).
4. **`label_key`는 kind별 등재 키를 쓴다.** 미등록 kind와 `COARSE_SEARCH`는 `job.generic_processing`으로 대신한다(A§12 · B§12).
5. **저장은 `state` JSON 안에 한다**(`store_state._STATE_FIELDS`). 새 테이블과 migration은 없다. `case-store-mysql.md` D5가 8-9에서 만들기로 한 「중단된 `job_id` 테이블」은 이 기록의 `CANCELLED` · `STOPPED_WAITING`으로 대신한다. 처리한 `execution_id` 테이블(8-8)은 execution 단위 idempotency라 따로 남는다.
6. 공개 함수의 `running_jobs=` 인자는 없앤다. 호출자가 덮어쓸 길을 남기면 계산과 다른 값이 화면에 갈 수 있다.

## 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| JobExecution 상태만으로 계산한다(terminal이면 제외) | 불변조건 5와 반대다. terminal과 반영 사이에 빠지면 polling이 반영 전에 멈추고, 중단된 job은 실행이 `RUNNING`인 동안 계속 보인다 |
| JobRecord에 정산 필드를 더한다 | JobRecord는 계약(`job-record/v1`) 객체이고 append-only다. 발주 의도와 case의 기다림 상태는 다른 사실이다 |
| 별도 append-only 테이블(`job_settlements`) | 행이 case당 수십 개 이하이고 aggregate와 함께 읽고 쓴다. 테이블과 migration을 늘릴 이득이 없다. 이력이 필요해지면 forward-only로 옮길 수 있다 |
| 같은 kind 재발주 때 이전 job을 남긴다 | 대표 job은 가장 나중 job이다(A§10-7). 남기면 재시도한 화면에 같은 작업이 둘 보이고, 이전 job의 늦은 결과는 어차피 반영하지 않는다(C-4) |
| 정산 때 `case_rev`를 올린다 | 정산만으로는 사용자가 볼 내용이 바뀌지 않는 경우가 많다(대체 · 반영은 그 경로가 따로 올린다). 실행 결과는 `case_rev`를 올리지 않는다는 §3-E 원칙과 같다 |

## 남은 것

- 결과 반영 경로마다 `REFLECTED` 기록(8-8), 중단 · timeout 기록과 늦은 결과 guard(8-9).
- JobExecution 읽기 포트(D-6)가 생기면 `job_executions` 인자를 포트 조회로 바꾼다.
- #276 후속: case가 Fine 결과를 기다리지 않게 됐는데 실행이 아직 남은 경우의 화면 표시.
