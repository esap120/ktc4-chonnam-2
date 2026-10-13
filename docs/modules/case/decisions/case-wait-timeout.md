# case 대기 timeout — 타이머 없이 마감을 계산하고, 늦은 결과는 반영하지 않는다

> **상태: 결정 · 구현(탐색 `COARSE_SEARCH`만)** · 결정일 2026-10-13 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-9(`../design-refinement-w7-baseline.md`), `timeout-fallback.md`(잠정값 · 「진행 중인 Job은 강제 취소하지 않는다」), `stop-analysis.md`(같은 guard), `running-jobs-derivation.md`(정산 사유 `STOPPED_WAITING`), Runtime Tech Spec §12.2 · Provisional Baseline §3.2(RD-04b), #291(`runtime.retry.after_case_stopped_count` 의미)
> 「얼마나 기다린 뒤 부분 결과로 넘어가는가」와 「그때 어떤 job을 유지 · 취소하는가」는 case 소유다(`timeout-fallback.md`). 실행 상한 값(`AnalysisScope.budget.max_latency_sec`)은 그 문서와 #149 A안이 정했고 여기서 다시 정하지 않는다.

## 1. 목표 · 범위

탐색 job이 끝나지 않으면(Worker 사망 뒤 재시도도 소진 · 큐 적체) 사용자가 「분석 진행」에서 끝없이 기다리지 않게 한다. 마감이 지나면 case가 기다리기를 멈추고(`running_jobs`에서 빠짐), 화면은 중단과 같은 결과로 넘어간다(`core-user-flow.md` 「분석 중단·timeout·인프라 실패」 — 보존된 결과와 「이어서 찾기」).

**범위:** `COARSE_SEARCH`만.
**범위 밖:** 단서 구조화(`HINT_EXTRACT`, §5) · 판독 · Fine · export 대기(값과 화면이 없다, §5) · Runtime 실행 취소(하지 않는다).

## 2. 흐름

```
마감 = JobRecord.requested_at + scope.budget.max_latency_sec + 30초

[get_view]        마감이 지난 job은 기다리지 않는 것으로 계산 — 저장하지 않음
[command]         case 잠금 → 마감 지난 job을 STOPPED_WAITING 정산 → 검사 · 처리 → 성공하면 함께 저장
[Worker T2]       case 잠금 → (같은 execution이면 ALREADY_APPLIED) → 마감 지난 job 정산
                  → 이번 job이 그중 하나면 NOT_APPLIED(STOPPED_WAITING), 정산은 저장
```

## 3. 결정

1. **타이머를 두지 않는다. case 행을 읽는 쪽이 마감을 계산한다.** CaseView 조립은 읽기라 저장하지 않고, case 행을 잠그는 command · T2 반영이 `STOPPED_WAITING`을 남긴다. Runtime에 새 주기 작업이나 port를 요청하지 않는다. T2가 끝내 오지 않아도(재시도가 끝난 `STALE`은 case에 전달되지 않는다 — Runtime worker README) 화면은 매 조회마다 같은 계산으로 멈춘 상태를 보인다.
2. **마감 = 발주 시각 + 실행 상한 + 큐 대기 여유 30초.** 실행 상한은 그 job의 AnalysisScope `budget.max_latency_sec`(지금 150초)이다. 여유 30초는 단서 구조화 대기(`start-analysis.md` §3-5)와 같다. scope를 모르는 job에는 마감을 지어내지 않는다. 기준 시각은 `requested_at`이라 큐 대기도 마감에 든다 — 큐가 밀려 탐색이 시작되지 못하는 것도 사용자에게는 같은 기다림이다.
3. **마감 뒤 도착한 결과는 반영하지 않는다**(`NOT_APPLIED(STOPPED_WAITING)`). 정산된 job의 결과는 받지 않는다는 기존 guard(`stop-analysis.md` §3-7) 그대로다. #291에서 합의한 `runtime.retry.after_case_stopped_count`(attempt ≥ 2 ∧ `NOT_APPLIED(STOPPED_WAITING)`)가 이 경로를 센다. timeout 화면에서 결과가 저절로 바뀌지 않고, 사용자는 「이어서 찾기」로 다시 시작한다.
4. **실행은 취소하지 않는다.** `CommandResult.cancelled_job_ids`에 넣지 않는다 — `timeout-fallback.md` 「진행 중인 Job은 강제 취소하지 않고, case가 기다리는 것만 멈춘다」. 사용자 요청이 아니라 `case_rev`도 올리지 않는다(정산 기록은 `case_rev`와 무관, `running-jobs-derivation.md`).
5. **화면은 중단과 같은 모양이다.** stage는 `SEARCHING`, `coarse_search`는 `PARTIAL`(B§10 불변조건 5 「사용자 중단 · case timeout처럼 case가 기다리기를 멈춘 job」). 상태는 저장하지 않고 계산한다(`CaseAggregate.analysis_timed_out` — 가장 나중 탐색 job의 정산 사유가 `STOPPED_WAITING`).
6. **notice는 `case.analysis_timed_out`을 새로 둔다**(INFO · non-blocking · `actions:[RETRY_SEARCH]`, `message_key: notice.analysis_timed_out`). 출구는 중단과 같지만 원인이 사용자가 아니라 code를 나눈다 — 같은 code면 web이 「중단했습니다」라고 말하게 된다. 둘 중 하나만 붙고, 마지막 탐색 job의 정산 사유를 따른다. 규칙 원문은 CaseView 계약 B§7 `notices[].code` 행.
7. **command는 잠근 직후 정산한다.** 사용자가 본 timeout 화면의 「이어서 찾기」(`RUN_NOTICE_ACTION`)가 같은 기준으로 검사되고, 성공하면 그 정산도 저장된다. 마감이 지난 뒤 `STOP_ANALYSIS`는 기다리는 탐색 job이 없어 `not_allowed`다.

## 4. 알려진 한계

- **시계.** 마감은 `requested_at`(발주한 process의 시계)과 판정하는 process의 시계를 비교한다. API · Worker container 시계가 어긋나면 그만큼 마감이 밀리거나 당겨진다. lease처럼 DB `NOW(6)`(Runtime B-L6)를 쓰지 않는다 — case 행에 그 시각이 없다. 수 초 차이는 30초 여유 안에 든다.
- **재시도와의 관계.** Worker가 죽으면 attempt 2는 마지막 heartbeat 뒤 최대 ~82초에 시작한다(Baseline §3.2). 탐색이 길면 attempt 2는 마감 뒤에 끝나 반영되지 않는다. Runtime이 이미 case 확인을 받은 관계다(RD-04b).
- **클립 분할 전 값.** 지금 탐색은 클립 1개다. 분할하면 `timeout-fallback.md`의 「150초 × 클립 수」를 scope 예산으로 넘기는 방식에 따라 이 계산도 바뀐다.

## 5. 미결 (채우지 않는다)

- **단서 구조화(`HINT_EXTRACT`) 90초**(`start-analysis.md` §3-5)는 이번에 하지 않는다. 마감 뒤 「빈 단서로 첫 탐색 발주」에는 발주(쓰기)가 필요한데 타이머가 없으면 그 시점이 없다. Runtime은 `APPLIED`일 때만 후속 job을 enqueue한다. 또 90초는 재시도 시작 ~82초와 같은 자릿수라 살아날 분석까지 끊는다. 그래서 Search 함수의 전체 상한 60초와 Runtime 재시도에 맡기고 계속 기다린다. **한계:** 재시도까지 `STALE`로 끝나면 T2가 오지 않아 `SEARCHING`에 머문다. Runtime이 재시도가 끝난 `STALE`을 T2로 넘기는지, 또는 다른 시점을 둘지는 Runtime(정철원)과 따로 정한다.
- 판독 · Fine · export 대기 — 값(Fine 70초만 있음)과 timeout 화면이 정해지지 않았다. Fine timeout을 `search.visual_verify_failed`와 같게 보일지는 web과 정한다.
- `notice.analysis_timed_out` 문구 — web(신유민) 확인.

## 6. 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| Runtime 주기 sweep이 case timeout 함수를 부른다 | Runtime에 새 Task · 합의가 필요하다. 탐색 timeout은 발주가 필요 없어 읽을 때 계산으로 충분하다 |
| 마감 뒤라도 선택 context가 맞으면 반영 | 화면이 timeout 상태에서 저절로 바뀌고, `STOPPED_WAITING` 이름 · #291 지표 의미와 어긋난다 |
| `get_view`가 정산을 저장 | 읽기 경로가 쓰기 transaction을 갖게 된다. 계산이 같으므로 저장은 다음 쓰기에 맡겨도 화면이 같다 |
| `case.analysis_stopped`를 그대로 쓴다 | 사용자가 누르지 않았는데 「중단했다」고 말하게 된다 |
| timeout 때 Runtime 중단 요청 | `timeout-fallback.md`가 이미 하지 않기로 했다 — 비용이 나간 호출을 버리지 않는다 |
| 마감 기준을 실행 시작 시각으로 | Runtime 실행 기록이 있어야 하고, 시작조차 못 한 job(큐 적체 · Worker 부재)은 끝없이 기다린다 |

## 7. 테스트

- `tests/case/test_case_wait_timeout.py` — 마감 계산(scope 예산 · 여유, 단서 구조화 · scope 모름은 마감 없음), view(마감 전 대기 · 마감 뒤 `PARTIAL` · notice · 저장 안 함), T2(마감 전 `APPLIED` · 뒤 `NOT_APPLIED(STOPPED_WAITING)` 정산 저장 · 다른 job T2에서도 정산), command(「이어서 찾기」 · 취소 없음 · 중단 `not_allowed`).

## 8. 남은 것

- 위 §5 미결.
- 잠정값 확정 뒤(runtime 머신 재측정, `timeout-fallback.md`) 여유 30초도 다시 본다.
