# case Edge Case 목록

> **작성 기준:** 2026-10-07 `develop@b8c5e337` · 2026-10-08 #284 · #315 머지 반영(`develop@fa1eb87e`)
>
> **목적:** case(진행 상태 · 사용자 선택 · 작업 발주)가 만나는 경계 상황을 한곳에서 분류하고, 지금 동작 · 근거 · 다음 할 일을 추적한다. recording의 [`real-video-edge-cases.md`](../recording/real-video-edge-cases.md)와 같은 방식이다.
>
> 이 문서는 Contract가 아니다. 규칙 원문은 「근거」 칸의 결정 문서 · 계약이 소유하고, 여기서는 가리키기만 한다. 결정되지 않은 것은 `PENDING`으로 두고 이 문서에서 채우지 않는다 — 결정이 필요한 것은 §7에 모은다.

## 1. 상태 표기

| 상태 | 의미 |
| --- | --- |
| `VERIFIED` | `tests/case/` 자동 테스트가 공개 경로(domain · command · view)로 재현한다. 확인한 범위에 한정한다 |
| `DECIDED` | 결정 · 계약은 있지만 구현이 없거나 아직 develop에 없다(열린 PR이면 PR 번호를 적는다) |
| `MEASURED` | 제품 경로가 아니라 실험 하네스에서 측정했다(LLM) |
| `PENDING` | 정책 · Owner 결정이 없어 의도적으로 비워 둔 것 |

**공통 동작(모든 항목의 바탕)**
- 사용자 요청(command)은 `expected_case_rev`가 현재 값과 다르면 `stale_revision`으로 거부하고 아무것도 바꾸지 않는다(case-command 계약 §6).
- 실패한 command는 상태를 바꾸지 않는다 — 검사를 상태 변경보다 먼저 한다(같은 계약 §6).
- 실행 결과는 `case_rev`를 올리지 않고, 사용자 요청만 올린다(§3-E).

## 2. 사용자 반복 행동

**지금 어떤 반복에도 횟수 상한이 없다.** 제품 원칙은 「탐색 비용은 사용자 행동(새 탐색 · 다른 후보 선택)에만 묶여 늘어나고, 제품이 스스로 탐색을 반복하지 않는다」뿐이다(`core-user-flow.md` 「결과 화면에서 다른 후보를 선택할 수 있다」 앞 문단). 비용이 드는 반복의 상한은 §7-1(#311).

| Edge case | 지금 동작 | 비용 | 상태 | 근거 · 다음 증거 |
| --- | --- | --- | --- | --- |
| 다른 후보 선택을 계속 함(A→B→C…) | `EVIDENCE_REVIEW` · `READY`에서 허용. 매번 `OTHER_CANDIDATE` CorrectionRecord · `selection_rev` 상승 · 새 신고자료 초안. 이미 선택된 후보 · 목록에 없는 후보는 거부 | 새 후보마다 판독 · Fine 발주 | `VERIFIED` | `test_correction.py`(reselect 계열) · `test_command.py` · #173 E-4 |
| 같은 후보로 되돌아옴(A→B→A) | 같은 후보 목록 세대(`candidate_generation`) 안이면 이전 관찰(Fine · 판독)을 재사용 | 추가 없음 | `VERIFIED` | `decisions/reselect-observation-reuse.md` · `test_correction_partial_rerun.py` |
| 재탐색(`RETRY_SEARCH`)을 계속 누름 | 이전 `COARSE_SEARCH`와 같은 입력으로 새 job 발주(notice에 버튼이 떠 있을 때만). 같은 kind · scope의 이전 job은 대체 처리 | 매번 Coarse 전체 비용 | `VERIFIED`(발주) · 상한 `PENDING` | `test_command.py` notice action · 대체는 `test_job_settlement.py` · 상한 §7-1 · #311 |
| 번호판 다시 판독(`RETRY_PLATE_READ`)을 계속 누름 | 판독 실행 실패 notice가 떠 있고 이전 `PLATE_READ`가 있을 때만 새 job 발주 | 매번 판독 비용 | `VERIFIED`(발주) · 상한 `PENDING` | `test_command.py` · `test_plate_read_failure_projection.py` · 상한 §7-1 · #311 |
| 같은 필드를 계속 정정(시각 등) | 정정마다 새 CorrectionRecord, `supersedes_ref`로 체인. 다른 후보를 고르면 후보에 묶인 체인은 새로 시작 | 재조립만(관찰 재사용) | `VERIFIED`(domain) · command 경로는 `DECIDED` | `test_correction.py` supersede 계열 · 입력형 command는 case-command 「다음 판본」 |
| 상황 응답을 계속 바꿈(맞아요 ↔ 잘 모르겠어요) | 응답마다 덮어쓰고 `case_rev` 상승. `READY`에서 받으면 `EVIDENCE_REVIEW`로 내렸다 다시 확인. `[다른 상황]`(`CORRECTED`)은 이 판본에서 거부 | 재조립만 | `VERIFIED` | `test_situation_response.py` · `test_command.py`(READY에서 응답 · `CORRECTED` 거부) · case-command 계약 §5 |
| 같은 버튼을 두 번 빠르게 누름 | 두 번째 요청은 `expected_case_rev`가 이미 올라 `stale_revision` | 없음 | `VERIFIED` | `test_command.py` stale 계열 |
| 최종 확인(`MARK_REVIEWED`)을 반복 · READY 전에 누름 | `READY`에서만 받고 그 밖은 `not_allowed` | 없음 | `VERIFIED` | `test_command.py` |

## 3. 동시성 · 결과 도착 순서

| Edge case | 지금 동작 | 상태 | 근거 · 다음 증거 |
| --- | --- | --- | --- |
| 오래된 화면에서 제출 | `stale_revision` + 현재 CaseView를 같이 돌려준다 | `VERIFIED` | `test_command.py` |
| 같은 case에 두 요청이 동시에 씀 | 저장 시 `cases` 행 `FOR UPDATE` — 뒤 요청이 기다린다 | `DECIDED`(#282) | `decisions/case-store-mysql.md` · MySQL opt-in 테스트 |
| 저장된 기록 앞부분이 바뀐 채 저장 시도 | `AppendOnlyViolation`, 아무것도 쓰지 않음(호출자가 예외를 삼키고 commit해도) | `DECIDED`(#282) | #282 Runtime 리뷰 반영 테스트 |
| 같은 실행 결과가 두 번 도착 | `execution_id` 기준으로 한 번만 반영 | `DECIDED` | #245 D-5 · 구현 8-8 |
| 재시도로 대체된 job의 결과가 늦게 도착 | 대표 job은 가장 나중 job — 이전 job은 대체(`SUPERSEDED`)로 정산, 늦은 결과는 반영하지 않음 | `VERIFIED`(대체 정산) · 늦은 결과 guard `DECIDED` | `test_job_settlement.py` · `decisions/running-jobs-derivation.md` · 늦은 결과 guard는 8-9 |
| 사용자가 중단 · 다른 후보로 바꾼 뒤 이전 결과 도착 | 중단된 `job_id` 집합 + 현재 선택 context 대조로 거른다 | `DECIDED` | #245 C-1a · C-4 · 구현 8-9 |
| 실행은 끝났는데 case 반영 전 · 재시도 대기 중 | `running_jobs`에 남아 polling이 멈추지 않는다 | `VERIFIED` | `test_running_jobs_view.py` · 계약 B§10 불변조건 5 |
| 사용자가 중단했는데 실행이 아직 RUNNING | case는 더 기다리지 않는다 — `running_jobs`에서 뺀다 | `VERIFIED`(정산된 job 제외) · 중단 command `PENDING` | `test_running_jobs_view.py` · 불변조건 5 · 중단 command는 8-1 · 8-9 |

## 4. 실패 · 시간 초과

| Edge case | 지금 동작 | 상태 | 근거 · 다음 증거 |
| --- | --- | --- | --- |
| 후보 탐색 실패 | `SEARCHING`에 머물고 `search.candidate_search_failed`(ERROR · blocking, `RETRY_SEARCH`). 「결과 없음」으로 보이지 않게 한다 | `VERIFIED` | `test_candidate_search_failure.py` · PR #187 · #197 |
| 후보 0개(탐색 성공) | `CANDIDATE_REVIEW` + `search.no_candidates`(INFO, `EDIT_HINT` · `RETRY_SEARCH`) | `VERIFIED` | `test_scenario_empty_smoke.py` |
| 번호판 판독 실행 실패 | `readout.plate_read_failed`(ERROR · blocking). 「다시 판독」은 이전 발주가 있을 때만 | `VERIFIED` | `test_plate_read_failure_projection.py` · #172 [D] 4a |
| 번호판을 읽었지만 값이 없음 · 일부만 읽음 | `evidence.plate_abstained`(WARN, 막지 않음) — 실행 실패와 구분 | `VERIFIED` | `test_derived_notices.py` · #172 D-3 |
| 실패 뒤 사용자가 번호판을 직접 입력 | 그 값으로 Package까지 가고 실패 notice를 거둔다 | `DECIDED` | #235 E-1 결정 · case 후속 코드는 계약 반영 PR 뒤 |
| 화면 시각 판독: overlay 없음 · 판단 불가 · OCR 실패 | `readout.overlay_*` 3종(INFO) — 「시각이 없다」와 「확인 못 함」을 섞지 않는다 | `VERIFIED` | `test_overlay_notices.py` |
| Fine 실행 실패(재시도 소진) | evidence가 없을 때 `search.visual_verify_failed`(ERROR · blocking), 출구는 「다른 후보 보기」 | `VERIFIED` | `test_visual_verify_failed_notice.py` · 8-14 |
| Fine 음성(위반 관찰 안 됨) | `evidence.visual_event_not_observed`(INFO). 다음 후보를 자동으로 확인하지 않는다 | `VERIFIED` | `test_not_observed_notice.py` · #168 [A] |
| Fine `UNCERTAIN` → 사용자 응답 대기 | `case.situation_response_pending`(INFO). 응답 전 Package 없음 | `VERIFIED` | `test_await_situation_response.py` · #165 · #171 |
| 응답 대기 중 독립 관찰값(번호판 등)을 먼저 보여 줌 | `evidence.record_id: null` 부분 투영 | `DECIDED` | #239 case 결정 · web 확인(2026-10-07) · evidence 함수 대기 |
| case가 Fine을 기다리다 멈췄는데 attempt 2가 아직 실행 중 | 화면 표시 미정 | `PENDING` | #276 후속 |
| 각 Job timeout(Coarse 클립당 150초 · Fine 후보당 70초 등) | 값은 잠정 결정, case 대기 timeout 구현은 없음 | `DECIDED` | `decisions/timeout-fallback.md` · 구현 8-9 |
| 신고용 영상 · 번호판 이미지 export 실패 | notice 매핑은 계약에 있음, export 자체가 미구현 | `DECIDED` | 계약 v1.6 · recording C-07 · #47 · #280 |

## 5. 빈 상태 · 경계 입력

| Edge case | 지금 동작 | 상태 | 근거 · 다음 증거 |
| --- | --- | --- | --- |
| 영상 없이 case만 만들어짐 | `INTAKE`, 8단계 모두 `PENDING`, 후보 · evidence 없음 | `VERIFIED` | `test_empty_case.py` · `decisions/empty-case-and-manifest.md` |
| 처리 가능한 영상 0개로 분석 시작 | `not_allowed`로 거부, 아무것도 저장하지 않음(영상 없음 · 처리 불가 영상만) | `VERIFIED` | `test_start_analysis_command.py` · case-command §11 · `decisions/start-analysis.md` |
| 빈 설명으로 분석 시작 | 단서 구조화 생략, 바로 탐색(공백만 있어도 같음) | `VERIFIED` | `test_analysis_start.py` · `test_start_analysis_command.py` · case-command §11 |
| 선택 전 화면 조회 | downstream 값을 조회하지 않고 evidence · package `null` | `VERIFIED` | `test_view_before_selection.py` |
| 위치를 못 구함 | `location` 키가 없어도 깨지지 않음, `evidence.location_search_keyword_missing` notice | `VERIFIED` | `test_view_location_missing.py` · `test_derived_notices.py` · #48 |
| 후보의 시간축이 갱신돼 예전 기준이 됨 | `stale_revision` 표시 · 마커 숨김 | `VERIFIED` | `test_candidate_marker.py` · `decisions/candidate-stale-revision-display.md` |
| 2줄 번호판을 일부만 읽음 → 번호판 이미지 | `best_frame`이 없어 번호판 이미지를 발주하지 않음(선택 첨부라 막지 않음) | `DECIDED` | #280 case 동의(2026-10-07) · 첫 발주 경로 미구현 |
| Package가 나오기 전 신고문 | 미완성 신고문을 만들지 않음 — `package: null` | `VERIFIED` | `test_await_situation_response.py` · `test_empty_case.py` · #286 |

## 6. LLM — 자연어 단서 구조화

case에서 LLM을 부르는 곳은 분석 시작 때 단서 구조화(`HINT_EXTRACT`) 한 번이다. 발주(`START_ANALYSIS`)와 결과 반영(`service.receive_hint_extraction_result()` — 반영 뒤 첫 탐색까지 발주)이 구현 · 테스트돼 있다(#315). Worker 배선은 Runtime #297.

| Edge case | 지금 동작 | 상태 | 근거 · 다음 증거 |
| --- | --- | --- | --- |
| 구조화 실패 · 전부 보류(`FAILED` · `ABSTAINED`) | 4개 단서 모두 `null`로 두고 탐색을 이어 간다. notice 없음 | `VERIFIED` | `test_hint_extraction.py` · `test_analysis_start.py` · case-command §11 |
| 결과 모양이 바뀜(알 수 없는 status) | `ValueError`로 멈춤 — 조용히 빈 단서로 넘어가지 않는다 | `VERIFIED` | `test_hint_extraction.py` |
| 무관한 잡담 · 인젝션 · 모순 · 여러 사건 혼합 · 상대 시간 등 17개 카테고리 | 3.8 Flash 기본값 기준 카테고리별 83~100% | `MEASURED` | `experiments/intent-llm-model-comparison/results/consistency-robustness-v3.md` · `luna-reasoning-effort-v3.md` |
| 모순된 정보(앞 값 · 뒤 값) | 마지막 값 + `confidence: low` 정책. 측정상 가장 약한 카테고리(83%) | `MEASURED` | `decisions/intent-hint-robustness-policy.md` |
| 출력 한도 초과(내부 추론이 길어짐) | Search 함수가 `FAILED`(`RESPONSE_INVALID`)로 돌려줌 → 빈 단서. 측정상 500회 중 1회 | `MEASURED` | #278 · #277 |
| `confidence: low`일 때 재입력 유도 | 화면 흐름 미정 | `PENDING` | #266 |
| 실사용 문장에서의 정확도 | 합성 데이터로만 측정 | `PENDING` | model-selection §13 한계 |

## 7. 결정이 필요한 것

### 7-1. 비용이 드는 반복의 상한 — `PENDING`

§2의 재탐색 · 다시 판독 · 새 후보 선택은 누를 때마다 실행 비용이 든다. 지금은 횟수 상한도 case당 비용 상한도 없다(`AnalysisScope.budget.max_cost_krw`는 탐색 한 번의 상한이지 case 전체의 상한이 아니다 — `decisions/budget-krw-normalization.md`).

- **정할 것:** 상한을 둘지, 둔다면 단위(횟수 · case당 비용)와 값, 넘었을 때 화면(버튼 숨김 · 안내 문구).
- **case 제안(결정 아님):** 같은 입력의 재발주(같은 후보 재판독 · 같은 범위 재탐색)는 횟수로, 사용자가 범위를 바꾼 새 탐색 · 새 후보는 case당 비용으로 묶는다. 같은 입력을 반복해도 결과가 바뀔 가능성이 낮아 횟수가 맞고, 새 범위 · 새 후보는 사용자가 원하는 탐색이라 비용으로 보는 편이 낫다.
- **누가:** 비용 · 남용 정책이라 case 혼자 정하지 않는다 — PM(제품) · Runtime(비용 장부) · web(화면)과 정한다. 결정 카드 [#311](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/311).

### 7-2. 이미 다른 곳에서 추적 중인 결정

| 항목 | 추적 |
| --- | --- |
| 응답 대기 중 Fine attempt 2 실행 중 표시 | #276 후속 |
| `confidence: low` 재입력 유도 | #266 |
| ~~분석 시작 command(분석 범위 출처 · 첫 발주 fingerprint · 단서 구조화 대기 시간)~~ → 종결(#315) | `decisions/start-analysis.md` · 대기 시간 동작은 8-9 |
| 중단 command · case timeout 구현 | 8-9 · #292 |
