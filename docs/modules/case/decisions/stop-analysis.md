# 분석 중단(`STOP_ANALYSIS`) — 탐색 job 중단 · 화면 · 늦은 결과 guard

> **상태: 결정 · 구현** · 결정일 2026-10-11 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-9(`../design-refinement-w7-baseline.md`), #245 C-1 · C-1a(B) · C-3 · C-4, Runtime Tech Spec §12.5, #292(cancel port), `core-user-flow.md` §7 「사용자가 분석을 중단한 경우」
> 중단 command의 이름 · payload · 허용 상태와 중단 뒤 case 상태 · CaseView 투영은 case 결정 범위다(#245 C-1). Runtime 쪽 전이(`QUEUED` 즉시 · `RUNNING` 협력적 중단)와 port 모양은 Runtime 소유(Tech Spec §12.5, #292)이고, 이 문서는 case 쪽만 둔다. 규칙 원문은 case-command 계약 §5 · CaseView 계약 B§7로 옮겼다.

## 1. 목표 · 범위

진행 화면의 `[분석 중단]`을 누르면 case가 즉시 기다리기를 멈추고(`running_jobs`에서 빠짐), Runtime이 같은 transaction에서 실행 중단을 요청받고, 늦게 끝난 결과는 반영되지 않는다.

**범위 밖:** 「가장 유력한 후보 초안 준비」 중 중단(판독 · Fine까지 멈추는가 — product 미결, §5) · case 대기 timeout(`STOPPED_WAITING`) · 이전 후보의 판독 · Fine 늦은 결과를 선택 context로 거르기(6.6순위 조건 2 — 그 결과를 받는 Worker 반영 함수가 8-8에서 생긴다) · Runtime 배선(RT-08(d)).

## 2. 흐름

```
[API] STOP_ANALYSIS {}
   ├─ 검사: stage=SEARCHING · 기다리는 HINT_EXTRACT/COARSE_SEARCH ≥ 1 (아니면 not_allowed)
   ├─ 그 job들을 CANCELLED로 정산 · case_rev +1 · stage는 SEARCHING 그대로
   └─ CommandResult.cancelled_job_ids = [그 job_id들]
[composition root] 같은 tx에서 request_cancel(conn, cancelled_job_ids) → commit → 200 (새 발주 없음)

[Worker T2] 중단된 job의 결과 도착 → case.awaits_result(job_id)=False → 아무것도 바꾸지 않음
```

## 3. 결정

1. **command는 `STOP_ANALYSIS`, payload `{}`, 허용 상태는 `SEARCHING`에서 기다리는 `HINT_EXTRACT` · `COARSE_SEARCH`가 있을 때.** 그 밖(다른 stage, 이미 중단함)은 `case.command.not_allowed`다. 대상은 case가 고른다 — web은 job을 모른다(HTTP API Contract §2).
2. **지정한 탐색 job만 무효화한다**(#245 C-1a B). 같은 case의 다른 kind job은 계속 기다린다. 사용자 요청이라 `case_rev`를 올린다(§3-E). 늦은 결과는 `case_rev`가 아니라 정산 기록으로 거른다.
3. **case는 Runtime port를 부르지 않고 `CommandResult.cancelled_job_ids`로 돌려준다** — `appended_job_records`(8-7)와 같은 장치다. composition root가 같은 transaction에서 `request_cancel(conn, job_ids)`를 부른다(RT-08 계획 「case가 돌려준 job 목록으로」). 실패한 command는 `[]`다.
4. **stage는 `SEARCHING`에 머문다.** 탐색 실패(`search.candidate_search_failed`)와 같은 모양이다. `CANDIDATE_REVIEW`(후보 0개)로 옮기면 `search.no_candidates`와 같아져 중단을 「후보 없음」으로 보이게 된다(core-user-flow §23). 지금 범위에서 중단된 탐색은 부분 후보를 남기지 않는다(core-user-flow §7 「현재 범위」).
5. **「분석 중단 상태」는 저장하지 않고 계산한다**(`CaseAggregate.analysis_stopped`): `SEARCHING`이고, 기다리는 탐색 job이 없고, 가장 나중 탐색 job의 정산 사유가 `CANCELLED`. 「이어서 찾기」로 새 job이 생기면 저절로 풀린다. 새 state 필드 · migration이 없다.
6. **CaseView.** `coarse_search`는 `PARTIAL`(B§7 「중단된 job은 실행 상태와 상관없이 `PARTIAL`」). 실패 뒤 다시 찾다가 중단했으면 마지막 사용자 행동인 중단을 보인다(`FAILED`를 덮는다). notice `case.analysis_stopped`(INFO · non-blocking · `message_key: notice.analysis_stopped`)를 붙이고, `actions:[RETRY_SEARCH]`는 다시 낼 `COARSE_SEARCH` 발주 근거가 있을 때만 싣는다. `이어서 찾기`는 영상 전체를 다시 보는 새 탐색 의도(core-user-flow §7)라 `RETRY_SEARCH` 발주와 같다.
7. **늦은 결과 guard = 「case가 기다리는 job의 결과만 받는다」**(`CaseAggregate.awaits_result(job_id)`). 정산된 job(`CANCELLED` · `SUPERSEDED` · `REFLECTED`)의 결과는 상태를 바꾸지 않는다 — 중단(#245 C-4), 대체된 job의 늦은 결과(A§10-7), 같은 결과의 두 번째 도착이 한 규칙이다. 이 case가 발주하지 않은 `job_id`는 프로그래밍 오류(`ValueError`)다.
   - Worker 반영 진입점 `receive_hint_extraction_result(..., job_id)`는 `job_id`가 필수다. 반영하면 그 job만 `REFLECTED`다.
   - 도메인 `receive_candidates()` · `record_candidate_search_failure()`는 `job_id`를 선택으로 받는다. 동기 real 경로 · 테스트는 job 없이 부르므로(기다리던 탐색 job 전체 정산, 기존 동작) 필수로 만들 수 없다. 탐색 결과의 Worker 반영 진입점(8-8)은 늘 넘긴다.

## 4. 알려진 한계

- **단서 구조화(`HINT_EXTRACT`) 중에 중단하면 「이어서 찾기」가 없다.** 다시 낼 `COARSE_SEARCH`가 없어 `actions:[]`이고, `START_ANALYSIS`는 `INTAKE` 전용이라 사용자가 다시 시작할 길이 없다. 중단 뒤 첫 탐색을 발주하는 action을 열지는 web과 정한다.
- 중단 뒤 실행이 checkpoint까지 진행되며 나가는 비용은 Runtime C-3 A안의 한계 그대로다.

## 5. 미결 (채우지 않는다)

- 「초안 준비 중」(`core-user-flow.md` 「가장 유력한 후보 초안 준비」)에 중단할 때 판독 · Fine job까지 멈추는가 — product에 정해져 있지 않다(#245 C-1a 보류). 정해지기 전에는 `EVIDENCE_REVIEW`에서 `not_allowed`다.
- `notice.analysis_stopped` 문구 · 화면 배치 — web(신유민) 확인.

## 6. 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| `CANDIDATE_REVIEW`(후보 0개)로 옮긴다 | `search.no_candidates`와 같은 모양 — 중단을 「후보 없음」으로 보인다. 그 notice를 억제하는 규칙이 하나 더 필요하다 |
| case가 cancel port를 직접 부른다(`CaseStore`에 주입) | Runtime 계획이 「case가 돌려준 job 목록」으로 composition root가 부르게 정했다. 발주(`appended_job_records`)와 같은 경계가 읽기 쉽다 |
| `analysis_stopped`를 state 필드로 저장 | 정산 기록에서 계산된다. 저장하면 「이어서 찾기」 때 지우는 경로가 하나 더 생긴다 |
| guard를 `CANCELLED`만 본다 | 대체 · 중복 결과도 같은 이유로 버려야 한다. 「기다리는 job만 받는다」 하나로 셋을 덮는다 |
| 반영 함수 전부 `job_id` 필수 | 동기 경로에는 job이 없다 |

## 7. 테스트

- `tests/case/test_stop_analysis.py` — command(정산 · `case_rev` · `cancelled_job_ids` · 다른 kind 유지 · 재중단 · 다른 stage · payload · stale), view(`PARTIAL` · notice · action 유무 · 이어서 찾기 뒤 해제 · 실패보다 중단 우선), guard(단서 · 후보 · 실패 결과, 대체 job, 모르는 `job_id`).
- `tests/case/test_case_repository_contract.py::test_stopped_analysis_survives_save_and_load` — in-memory · MySQL에서 중단 상태 유지.
- 기존 `test_analysis_start.py` · `test_start_analysis_command.py` — 반영 진입점에 `job_id`를 넘긴다.

## 8. 남은 것

- RT-08(d)가 `cancelled_job_ids`로 `request_cancel`을 부른다(#295) · RT-05(b)가 port를 구현한다(#292).
- 탐색 결과 Worker 반영 진입점은 `job_id`를 넘긴다(8-8).
- case 대기 timeout(`STOPPED_WAITING`)은 같은 guard 위에 올린다 — 언제 · 누가 timeout을 판정하는지는 따로 정한다.
