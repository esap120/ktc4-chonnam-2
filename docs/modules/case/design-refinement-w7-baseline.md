# case 설계 고도화 — W7 Quality/Risk Burn-down 기준 문서

**날짜:** 2026-09-19 · **작성:** 유소연 · **브랜치:** `docs/design-refinement`

**목적:** "모듈별 설계 고도화" 요청의 case 몫. **W7 Quality/Risk Burn-down 단계에서 실제 고도화를 진행할 때 그대로 쓰일 기준 문서**다 — 여기서 우선순위를 정해두면 W7에서 다시 처음부터 뭘 할지 고민하지 않는다.

W5/W6 Real E2E 공지와는 별개의 기존 요청이지만, 오늘(2026-09-18) 진행한 Real E2E 작업(`feature/case-mock-real-service-adapter`)에서 실제로 드러난 병목·실패 유형을 반영해서 우선순위를 조정했다 — 추측이 아니라 오늘 직접 실행해서 관찰한 것들이다.

> **상태 갱신 (2026-09-30)** — 1순위 ✅ · 2순위 → PR #177(case 구현) · 3순위 → 이슈 #210(호출 창구 조율, 모델은 멘토 피드백 후) · 3.5순위 ✅ 종결(#74, 구현 Deferred) · 6순위 ✅ case 몫 종결(transport는 이번엔 web 진행, #106) · 6.5순위 ✅ → PR #206(계약 Draft) · PR #216(`handle_command`) · 7순위 🔄 5차 측정까지(`experiments/orchestration-metrics-2026-09-30.md`, 2026-10-02 — 「바로 가능」·「작은 계측」 3개 + 「필요한 Job 발주 누락률」 완료, 「새 인프라 필요」 3개 남음). 나머지는 아래 본문 그대로.
>
> **상태 갱신 (2026-10-04)** — 8순위 신설: Runtime/Ops 구현 전 필수 Decision(#244 ~ #248)에 case가 확인 댓글로 약속한 후속 작업. 각 카드가 결정되기 전에는 착수하지 않는다. 결정 없이 할 수 있던 것은 선반영했다 — 8-14 · 8-15 ✅, 8-10 · 8-16 일부, 8-1 분석 시작 초안(case-command Draft §11).
>
> **상태 갱신 (2026-10-05)** — 카드 5장(#244 ~ #248)이 2026-10-04 모두 `ACCEPTED`로 닫혔다. case 제안(#245 C-1a B · C-4, #246 S-4 FrameRef, #247 H-4 `running_jobs` 정의)이 채택돼 다른 Owner 문서에 반영됐다. 8순위는 이제 착수할 수 있다. HTTP API Contract Draft(#265)의 case 경계 리뷰에서 나온 할 일(8-17 · 8-18)을 더했다.
>
> **상태 갱신 (2026-10-06)** — 8순위에서 결정 없이 할 수 있던 항목을 끝냈다: 8-4 · 8-5 · 8-18(#269), 8-7(#268) ✅, 8-12 · 8-17 case 쪽(#270) ✅, 8-6 1단계 설계(#267)는 리뷰 반영 뒤 머지 대기. 7순위 orchestration 지표 4 · 5차(#234) 머지. 3순위 모델은 Gemini 3.8 Flash로 확정(#278). 남은 8순위(8-1 · 8-2 · 8-8 · 8-9 · 8-10 · 8-11 · 8-13 · 8-16)는 #265 머지 · 8-6 구현 · recording 영속화 · Search PR(#210)을 기다린다.

## 0. 범위 정의 — case가 직접 할 것과 아닌 것을 먼저 나눈다

Real E2E에서 발견한 항목을 "case 작업 중에 나왔다"와 "case가 고쳐야 한다"를 섞지 않는다. 아래 §1의 항목은 전부 case가 주도할 수 있는 것(단독이거나, case 주도 + 타 모듈 조율)만 담는다. case 파트가 아닌 것은 §2에 별도로 분리해서 "case가 의존하고 있는 외부 블로커"로만 표시한다.

## 1. 우선순위 목록

### 1순위 — Candidate span → Recording 변환 로직 설계 — ✅ 종결(2026-09-20)

**문제(해소됨):** `real_e2e.py`는 recording fixture가 이미 알고 있는 `span_resolutions[0]`을 그대로 재사용해서 `recording.resolve_span()`을 불렀다. search의 `CandidateSpan`을 recording의 `resolve_span(timeline_ref, requested_range)` 입력으로 바꾸는 진짜 변환 로직이 없어서, fixture 밖의(새 영상의) candidate span은 이 경로를 아예 못 탔다.

**해소 내용:** `candidate.span`(`timeline_id`/`timeline_revision`/`start_ms`/`end_ms`)을 `timeline_ref`/`requested_range`(ms→sec)로 변환하는 코드를 추가했다. 조율이 필요할 거라 예상했던 "정확히 어떤 값을 어떻게 넘길지"는 실제로는 **이미 `contract-analysis-scope.md` §12 B08이 정해둔 규칙**(recording의 `SpanResolution`은 초 단위 유지, ms↔초 변환은 recording 경계에서 명시적으로)을 그대로 구현하면 되는 문제였다 — search·recording Owner와 새로 합의할 필요가 없었다. `happy_001` fixture의 candidate span과 기존 `span_resolutions[0]`이 값이 정확히 같아(300.0~420.0초) 오늘 시나리오 결과는 회귀 없이 그대로다. TDD로 candidate span을 fixture에 없는 범위로 바꾸면 `RecordingCapabilityError`가 나는 것까지 확인했다.

**여전히 범위 밖(4순위와 별개로 남는 것):** 이건 "case가 search 결과를 정직하게 recording에 넘기는가"만 고친 것이다. **recording이 임의의 새 영상에 대해 실제로 `resolve_span()`을 풀어주는지(fixture가 아닌 real 구현)는 recording Owner 몫이고 아직 안 됐다** — 정철원님이 준비하는 대표 영상이 recording 쪽에 실제 `SpanResolution`으로 등록돼 있어야 이 변환의 결과가 성공한다.

**참고:** `src/daesingo/case/real_e2e.py`, `docs/modules/case/decisions/orchestration-service-layer.md` §7, PR #116

### 2순위 — situation_response / observation_facts 워크플로우

> **2026-09-30:** situation_response 기록·전달은 PR #177(evidence 테스트 반영 대기). observation_facts(최종 영상 관찰, I4)는 producer가 없어 case 몫이 아니다(ADR-EVIDENCE-008 §6.2) — I4가 없는 동안 real 경로 FINAL은 `UNKNOWN`이다.

**문제:** 오늘 데모(`demo_happy_001.py`)에서 실제로 관찰됨 — `situation_response`/`observation_facts`가 없어서 `FINAL_PACKAGE` 판정이 `UNKNOWN`에 걸리고 `build_report_package()`가 `PackageNotReady`를 던진다. `package`가 항상 `null`이다.

**왜 2순위(1순위와 병렬 가능):** 최종 신고 패키지 생성의 핵심 결손 — 다른 걸 아무리 잘해도 이게 없으면 신고 패키지를 영원히 못 만든다.

**이미 있는 것:** `Candidate.situation_confirmation` 필드가 case 도메인에 이미 있다(`NOT_ASKED` 상태). 워크플로우 자체는 case 몫이 맞다.

**조율 필요:** 사용자에게 실제로 묻는 UI는 web 몫이라 case 혼자 못 끝낸다. evidence의 정책(확정 안 된 situation 처리)과도 연결.

**참고:** `docs/modules/case/experiments/w6-real-e2e-happy-001.md` "알려진 단순화 2"

### 3순위 — Intent LLM 통합

> **2026-09-30:** 1차 구현(09-24)은 case 모듈 경계 위반(프롬프트·provider 호출이 case 안)으로 머지 전 되돌렸다. 호출 창구 위치는 이슈 #210에서 search와 조율 중이고, 모델 선정·평가 체계는 멘토 피드백 후 확정(`미결 유지`). 아래 「API 키/모델 ID 확정이 유일한 외부 의존」은 더 이상 맞지 않는다.
>
> **2026-10-04:** #210 Search 의견(a) — 프롬프트 · structured 스키마 · provider 호출 · 실패 분류는 search public 함수, case는 원문 전달 · 6필드→4키 매핑 · 실패 처리. 결과는 `OK` / `ABSTAINED` / `FAILED`로 나뉘고 intent 모델은 Coarse · Fine과 다른 설정 키를 쓴다. case는 [동의 답글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/210#issuecomment-5979330944)을 달았고, 호출은 **1회짜리 비동기 Job**으로 붙인다(`decisions/intent-llm-model-selection.md` §5). 흐름은 case-command Draft §11 `START_ANALYSIS` 초안(분석 시작 → 단서 구조화 Job → 결과 반영 때 `COARSE_SEARCH` 발주). **Search PR(텍스트 structured public 함수) 대기** — 매핑 코드 · 실험 하네스 import 변경 · Job 배선은 그 뒤다(배선은 #245 D-5 · D-7도 필요).
>
> **2026-10-05:** 모델 선정 · 평가 체계의 `미결 유지`를 해제했다 — **Gemini 3.8 Flash 확정**(`decisions/intent-llm-model-selection.md` §13). 멘토 피드백 Q1(judge 신뢰도 검증) · Q2(지식 증류로 robustness-v3 100케이스 증강, 5회 반복 일관성) · Q3(confidence 실험)과 #213의 단일 점수(정확도 × 일관성, `decisions/intent-llm-eval-target-thresholds.md` §1.0)로 판단했다 — 3.8 Flash 0.941 vs Flash-Lite 0.884. 연동은 그대로 Search public 함수(#210) 대기.

**문제:** `CaseAggregate.intake()`가 여전히 구조화된 `hints`만 파라미터로 받는다. 원문 자연어를 구조화하는 실제 호출이 `domain.py`/`scope.py` 어디에도 없다.

**왜 3순위:** case의 헤드라인 책임(`tech-spec.md` §1)이자 실사용자 입력 경로의 시작점이지만, `docs/case-llm-model-comparison-20260916` 브랜치에 하네스·locked dataset·Elice 연동이 이미 준비돼 있어서 상대적으로 빨리 붙일 수 있다(API 키/모델 ID 확정이 유일한 외부 의존).

**서브 항목 (A4와 동시에 결정해야 함, 따로 뗄 수 없음):**
- **원 입력 텍스트 저장 여부/위치** — *(2026-10-04: 원문 보존은 Draft §11 `START_ANALYSIS`에 반영 — case aggregate에 두고 #245 D-1 case table로 영속화. CaseView 최상위 `description`으로 내리기로 case 결정 — 계약 반영은 §11 미결 1, web 확인 #259.)* `CorrectionRecord`는 `previous_value → new_value`(수정 전/후 값)만 기록하고 사용자가 실제로 입력한 원문은 어디에도 안 남는다. "원 입력 → 최초 추출 → 수정 → 최종값"을 사건 단위로 재현하려면 A4를 만들 때 같이 결정해야 한다.
- **UsageRecord 구현 요청(common/runtime)** — *(2026-10-04: #244 U-1로 넘어감 — search provider adapter가 시도마다 common/runtime의 `UsageSink`에 기록하고 UsageRecord Producer는 common/runtime. case가 따로 채우지 않는다. #244 결정 대기.)* LLM 호출 원본 로그(프롬프트·응답·모델명·비용·latency)를 남길 계약이 문서(`module-architecture.md`)엔 있지만 코드는 아직 없다(`common/job_execution.py` 확인함). case가 자체 로그를 새로 만들기보다 common/runtime에 `UsageRecord` 구현을 요청하고 case는 거기 맞춰 채우는 쪽을 제안한다.

**참고:** `docs/case-llm-model-comparison-20260916` 브랜치 전체, `research/llm-model-comparison-hint-extraction.md`

### 3.5순위 — Correction 로그 재사용 정책 미결 5건 종결

**상태:** ✅ 종결 — Issue #74 PM 결정(2026-09-20): 정책 방향 채택, 구현은 Deferred. ~~Issue #74에 case 제안 초안을 코멘트로 게시 완료(2026-09-19). PM 승인 대기 중.~~

**내용:** 동의 문구/저장 위치, 익명화 수준의 Contract화, 보관기간, 철회 처리, 1단계(평가)/2단계(학습) 고지 분리 — 5건. 배포 전 self-review(`docs/management/pre-deploy-security-review.md`)가 이미 이 항목의 실제 구현 여부를 확인하도록 돼 있어서, 배포 직전에 처음 정하면 구현과 문구를 동시에 고쳐야 하는 위험이 있다.

**참고:** `docs/modules/case/decisions/correction-log-reuse.md`, Issue #74, Issue #71(영상 자산 lifecycle — 경계 분리됨)

### 4순위 — `real_e2e.py` 시나리오 확장 (1/7 → 7/7)

**문제:** 지금 recording→search→readout→evidence real 연결은 `scenario_happy_001` 하나로만 검증됐다. correction rerun(supersede 체인), plate reread, unknown/abstain, infra failure(재시도), relative rebase, empty — Mock이 이미 커버하는 6개 시나리오는 Real 경로로 하나도 안 됐다.

**왜 4순위:** 1순위(A3)가 풀려야 이어서 할 수 있다. 새 능력을 여는 게 아니라 기존 걸 더 넓게 검증하는 확장 작업.

**참고:** `src/daesingo/case/real_e2e.py`, `tests/case/test_real_e2e.py`

### 5순위 — asset_refs 선택 로직

**문제:** `real_e2e.py`의 `asset_refs`도 recording fixture 객체가 이미 아는 목록을 그대로 재사용한다 — "이 case에 어떤 asset_facts가 관련 있는지"를 스스로 판단하는 로직이 없다.

**왜 5순위:** 작고, 2순위(situation_response/observation_facts)가 먼저 풀려야 의미가 커진다 — 패키지 조립 자체가 막혀 있는 동안은 다듬어도 효과가 잘 안 보인다.

### 6순위 — HTTP 진입점 / transport — ✅ case 몫 종결(2026-09-30)

**문제:** `case.get_view(case_id, store=store)`는 만들었지만(오늘 완료) 이걸 실제로 네트워크에 노출하는 FastAPI 같은 transport 계층이 없다.

**왜 6순위:** case 단독 결정 사안이 아니다 — `api/` 모듈(현재 껍데기만 있음) 또는 web 쪽 몫일 가능성이 높다. "만들기"보다 "누가 만들지부터 확인"이 먼저라 순서상 뒤로 미룬다(급하지 않다는 뜻은 아님).

**해소 내용(누가 만드는가):** transport는 case 몫이 아니다. `src/daesingo/api/README.md`가 `api/`(FastAPI composition root)의 Owner를 김준영으로 적고 있고, 코드는 아직 없다. web 구현 일정(목요일) 때문에 이번에는 **신유민(`web`)이 진행**하기로 했다 — 통로는 case 공개 함수를 부르기만 하고, 검사·실패 코드는 case에 둔다(이슈 #106 [코멘트](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/106#issuecomment-5907616288)). case가 transport에 붙인 조건은 셋이다: 통로에 판단을 넣지 않는다 · case 공개 함수만 부른다 · 긴 작업을 요청 안에서 돌리지 않는다.

**case 쪽 진입 함수:** 읽기 `case.get_view()`, 쓰기 `case.handle_command()`(PR #216, `contract-case-command.md` Draft v0). transport가 부를 대상은 이 둘이다.

**여전히 범위 밖:** HTTP 경로·인증·직렬화는 transport를 만드는 쪽이 정한다. 인증 방식은 미결이다(`module-architecture.md` §1-7 A2). `api/` Owner(김준영)와 web 구현의 관계 정리도 case가 정하지 않는다.

**참고:** `src/daesingo/case/service.py`(`get_view`), `src/daesingo/case/command.py`(`handle_command`), `src/daesingo/case/store.py`(`CaseStore`), `docs/modules/case/experiments/w6-real-e2e-happy-001.md` 완료 증빙 표, 이슈 #106

### 6.5순위 — web→case 공용 command 표면 (구 "후보 선택 제출 command 노출") — ✅ case 몫 종결(2026-09-30)

**문제:** `case.select_candidate()`는 이미 구현·E2E 테스트까지 됐지만(`domain.py:125`, `test_real_e2e.py`), 이걸 여는 외부 command 계약이 없다 — web이 `CaseView` 계약만 보고는 후보를 어떻게 제출해야 하는지 알 수 없다(이슈 #106).

**2026-09-20 스코프 확장(신유민 지적, 이슈 #106).** `select_candidate` 하나만의 문제가 아니다 — `apps/web/src/contracts/actionIntent.ts` 주석("아직 발주를 보낼 경로(case worker)가 없지만")이 그대로 보여주듯, 아래 셋 다 "무엇을 보낼지는 계약이 정했는데 보낼 길이 없다"는 같은 결손이다:

| | 준비된 것 | 없는 것 |
| --- | --- | --- |
| `select_candidate` | domain 구현 + E2E | command 미개방 |
| `USER_REVIEWED` | `module-architecture.md` §4-모듈6 ②에 "web이 전달"로 명시 · `domain.py`에 상태 전환 있음 | 전달 경로 없음 |
| `notices[].actions[]` 중 JOB 3종 | `ACTION_INTENT`에 발주 내용까지 계약 확정 | 보낼 경로(case worker) 없음 |

뿌리는 `module-architecture.md` §4-모듈6가 read 방향(`web → case.get_view()`)만 계약으로 정의하고, write 방향("사용자 명령을 case에 전달")은 계약 자체가 없다는 데 있다. `select_candidate` 전용으로 좁게 열면 `USER_REVIEWED` 열 때 같은 논의를 반복한다 — 그래서 이번엔 셋이 같이 탈 수 있는 **command 표면의 모양**(어디로 보내나 · 결과를 어떻게 돌려받나 · 실패를 어떻게 알리나)을 먼저 정하는 쪽으로 범위를 넓힌다. 세 command의 세부 페이로드까지 지금 다 정하자는 게 아니다.

**왜 이 순위:** 6순위(HTTP 진입점/transport)와 같은 계열이다 — 표면 아래 "도메인 로직은 있는데 네트워크로 노출하는 경로가 없다"는 결손이 같고, 실제 노출은 6순위가 막고 있는 "누가 transport를 만드는가"에 그대로 종속된다. 표면을 web이 직접 붙일지 `api/` 모듈을 세울지도 6순위와 같은 이유로 지금 정하지 않는다("만들기보다 누가 만들지부터"). 다만 월요일 Real E2E 블로커는 아니다(`test_real_e2e.py`가 python에서 직접 호출) — 김대원 판단에 동의 완료(이슈 #106 코멘트).

> **2026-09-30:** 누가 transport를 만드는가는 6순위에서 정리됐다 — 이번에는 web이 진행하고, case는 진입 함수까지만 둔다.

**결정된 것 (`select_candidate` 한정):** — 2026-09-30 이후 판본은 `contract-case-command.md`가 원문이다. 초기 선택은 `rank=1` 자동 선택이라 command가 아니게 됐고(#168 결정 1), 결과 화면의 다른 후보 선택은 `SELECT_OTHER_CANDIDATE`(`OTHER_CANDIDATE` CorrectionRecord, `case_rev` +1)로 열렸다. 실패는 `notices[].code`가 아니라 command 응답의 `error.code`(`case.command.*`)로 알린다. 아래는 09-20 당시 기록이다.
- `notices[].actions[]` 7종에 넣지 않고 별도 command로 연다 — `notices[].actions[]`는 notice에 매인 복구 액션 전용이라 1차 명령을 끼워 넣지 않는다. 기존 도메인 시그니처(`candidate_id`)를 그대로 쓴다.
- `case_rev`는 안 오른다(선택=새 요청 아님, 기존 결정 유지). `stage`는 `CANDIDATE_REVIEW`→`EVIDENCE_REVIEW`로 전이된다.
- 실패 시(`candidate_id` 불일치 등) 대응하는 `notices[].code`는 아직 없어 이번에 새로 정한다.
- `rejected_candidate_ids`는 **받지 않는다** — 지금 화면(`CandidatesScreen`)엔 개별 후보를 지목하는 버튼이 없고(§8이 정의하는 "아니오"는 "조금 전/후"(고른 후보의 시간 보정)·"다 아니에요"(전체 거절) 둘뿐, 개별 지목이 아님), `candidates[].selected=false`로 이미 파생 가능하다(신유민 확인, 이슈 #106). 후보 카드별 "이건 아니에요"가 생기면 그때 재검토.

~~**미결:** command 표면 모양(전송 경로·응답·실패 신호) 자체 — `select_candidate`·`USER_REVIEWED`·JOB 3종이 공유할 형태를 case가 초안 작성해야 한다. transport owner(`api/` 또는 web)가 정해지는 6순위와 별개로, 표면 모양은 case가 먼저 정할 수 있다.~~

**해소 내용:** 표면 모양은 `contract-case-command.md`(Draft v0, PR #206)로 정했다 — 요청 `{case_id, expected_case_rev, kind, payload}` → 응답 `{ok, error, case_view}`, command 4종(`SELECT_OTHER_CANDIDATE` · `RECORD_SITUATION_RESPONSE` · `MARK_REVIEWED` · `RUN_NOTICE_ACTION`). 진입 함수는 `case.handle_command()`(PR #216)다.

**여전히 남은 것:** 계약은 아직 `Draft`다 — web 합의 뒤 `docs/architecture/contracts/`로 옮긴다. 입력형 action(`EDIT_EVENT_TIME` 등)은 다음 판본이고, 계약 §9 미결(`case_rev`로 잡히지 않는 변경 · `RUN_NOTICE_ACTION` 중복 제출 · `message_key` 목록)은 그대로다.

**참고:** 이슈 #106, PR #206, PR #216, `docs/modules/case/contracts/contract-case-command.md`

### 6.6순위 — worker 배선 시 재선택 가드 (#173 E-4 후속)

**문제:** #173 E-4로 결과(`READY`) 화면에서도 다른 후보 선택을 허용했다(원자성·전이는 PR #189). E-4의 조건 두 개는 case가 비동기 Job 결과를 받는 경로가 생겨야 강제할 수 있어, 지금은 아래처럼 미뤄 뒀다(#173 [댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/173#issuecomment-5865032697)).

| 할 일 | 지금 | worker 배선 때 |
| --- | --- | --- |
| **현재 선택 후보의 evidence만 투영** — ✅ 선반영(PR #191) | `build_case_view()`가 `EvidenceRecord.basis.candidate_ref`·`selection_rev`를 현재 선택과 비교해, 다르면 evidence·RequirementReport·ReportPackage를 투영하지 않는다(`evidence=null`) | 추가 작업 없음. web은 `EVIDENCE_REVIEW`+`evidence=null`일 때만 진행 화면을 띄우므로(`selectScreen.ts`) **아래 조건 1의 전제**다 |
| 조건 1 — 새 후보 준비 중 재선택 금지 | Flow §8-1대로 web 진행 화면이 재선택 동작을 제공하지 않는 규칙에 기댄다(신유민 확인 요청: PR #189 [댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/189#issuecomment-5865059619)) | 새 선택에 대해 발주한 Job의 `JobExecution` 완료 여부로 case가 `check_reselect()`에서 거부 |
| 조건 2 — 늦게 온 이전 후보 결과 버리기 | 결과를 동기로만 받아 해당 없음 | 결과물의 `candidate_id`(readout `ReadRequest`, Fine `VisualEvidence`)를 현재 선택 후보와 대조해 다르면 버림. JobRecord 계약 변경은 필요 없음(관찰 결과는 후보에 묶이고, 사용자 입력만 선택 context에 묶인다) |

**왜 이 순위:** 6순위(transport)·6.5순위(command 표면)와 같은 계열로, worker가 생기기 전에는 강제할 대상 자체가 없다. 추측으로 막으면 상황 응답 대기(준비 중이 아님)와 구분하지 못한다.

> **2026-09-30 선반영(worker 없이 할 수 있는 것):** `READY` 전이는 현재 선택 context의 결과일 때만 한다 — `mark_ready_if_package_ready()`가 evidence의 `basis.candidate_ref`·`selection_rev`를 CaseView와 같은 기준(#191)으로 확인한다. 예전엔 이전 선택의 Package로도 `READY`가 돼, stage는 `READY`인데 CaseView evidence·package는 `null`이 될 수 있었다(#216 테스트 중 mock adapter로 재현). 위 조건 1·2(준비 중 재선택 금지 등)는 그대로 worker 배선 몫이다.

**참고:** 이슈 #173 · #166 · PR #189

### 7순위 — Orchestration 평가 지표

> **2026-09-30 1차 측정:** 아래 「바로 가능」·「작은 계측」 3개를 러너(`scripts/measure_case_orchestration.py`)로 구현했다. 「불필요한 재실행률」은 `force_rerun` 비율이 아니라 같은 입력의 중복 호출로 쟀다(`force_rerun=True`는 재판독·재시도처럼 필요한 재실행이라 근사로 쓸 수 없다). 「잘못된 stage transition」은 `InvalidTransition` 횟수가 아니라 불변식 위반으로 쟀다(예외는 막힌 시도이지 잘못된 전이가 아니다 — #167은 예외 없이 통과했다). 결과·baseline·측정 안 한 칸은 `experiments/orchestration-metrics-2026-09-30.md`. 「새 인프라 필요」 4건은 그대로다.
>
> **2026-09-30 2차 측정:** 「다른 후보 선택」 축을 합성 rank2로 추가했다(3,276 세션). `RealAdapter`가 evidence 조립 때 1차 탐색을 다시 부르던 것을 ①로 찾아 고쳤다(① 994 → 0). 남은 칸은 #177·#203·#209 머지 뒤 다시 돈다.
>
> **2026-09-30 3차 측정:** A→B→A로 돌아올 때 같은 탐색 결과의 관찰을 재사용하도록 정했다(`decisions/reselect-observation-reuse.md`, ③ 322 → 0, PR #218·#230).
>
> **2026-10-02 4차 측정:** #177·#203·#209 머지로 상황 응답 · 응답 대기 · 후보 0개 · 탐색 실패 · READY 시점 행동을 열었다(10,241 세션, command 대상 행동은 `handle_command` 경유). 선택 전 값 정정 · 탐색 실패 뒤 시간 단서 정정의 흔적 · READY인데 Package 없음(#202가 막지 않은 하강 쪽)을 찾아 고쳤다(② 4,122 → 0, PR #234). 남은 것: 크래시 767(번호판 직접 입력 706 · 응답 대기 중 정정 61 — 둘 다 PR #212), 측정 안 한 칸 4(worker·입력형 command 판본 대기), 아래 「새 인프라 필요」 4개.
>
> **2026-10-02 5차 측정:** 「필요한 Job 발주 누락률」을 정의했다 — 단계는 함수 호출로 「반드시 불려야 하는 단계 ⊆ 호출」(④, 정책 표 「다시 도는 것」 칸), `JobRecord`는 계약이 발주를 정한 notice 버튼에서만(④-b, CaseView 계약 B절 §7). ④ 0 · ④-b 421/1,335 → 0(번호판 다시 판독 버튼이 real 경로에서 근거 `PLATE_READ` JobRecord 없이 실려 늘 거부되던 것 — 근거가 있을 때만 싣도록 수정). 알려진 결함 2종을 넣어 ④만 잡는 것을 확인했다. EvidenceNeeds 자동 재판독은 #172 결정 뒤.

**문제:** 지금까지 이야기한 평가(intent-llm-model-comparison 등)는 전부 "LLM이 내용을 잘 뽑았는가"만 잰다. "Case가 올바르게 오케스트레이션했는가"는 따로 재는 게 없어서, 나중에 "LLM은 잘 답했는데 Case가 잘못 재실행했다"와 "Case는 맞는데 모델이 잘못 추출했다"를 구분할 수 없다.

**지표 후보 7개, 실현 가능성으로 3단 분류(`job_records`/`correction_records`/`InvalidTransition`을 다시 확인해서 나눔):**

| 분류 | 지표 | 비고 |
| --- | --- | --- |
| **바로 가능** | correction 후 필요한 단계만 재실행되는 비율 | `case.correction_records`(어떤 필드 고쳤는지) + `case.job_records`(그 뒤 뭘 재발주했는지) 대조 + 기존 부분 재실행 정책 표 기준 |
| **작은 계측 추가로 가능** | 잘못된 stage transition 0건 | `domain.py`에 `InvalidTransition` 예외가 이미 있음 — 지금은 그냥 죽기만 하고 카운트가 안 남는다. 잡아서 세기만 하면 됨 |
| **작은 계측 추가로 가능** | 불필요한 재실행률 | `job_records.force_rerun` 비율로 근사 시작 가능 |
| **새 인프라 필요** | 정상 workflow completion rate | 여러 case에 걸쳐 집계해야 하는데 `CaseStore`가 in-memory뿐이라 case가 끝나면 데이터가 사라짐(persistence 필요, A1 인접) |
| ~~새 인프라 필요~~ → **5차 측정에서 정의(2026-10-02)** | 필요한 Job 발주 누락률 | 「필요한」 = 정책 표 「다시 도는 것」(단계, ④) · CaseView 계약 B절 §7 버튼 → 발주 매핑(`JobRecord`, ④-b). worker·EvidenceNeeds 자동 발주는 측정 안 한 칸 |
| **새 인프라 필요** | stale 결과 적용 오류 | `JobExecution`(A1, common/runtime) 필요 |
| **새 인프라 필요** | case당 latency/token/cost | `UsageRecord`(3순위 서브 항목과 동일 — common/runtime) 필요 |

**왜 7순위:** "바로 가능" 1건, "작은 계측" 2건은 사실 비용이 낮아서 더 앞에서 같이 해도 되지만, 나머지 4건이 A1/UsageRecord(둘 다 case 파트 아님)에 종속적이라 전체 항목으로는 뒤로 뒀다.

### 8순위 — Runtime/Ops 필수 Decision(#244 ~ #248) 후속

**문제:** api · worker가 별도 process가 되면서(Ops §2) case의 동기 · in-memory 전제가 깨진다. Runtime/Ops 카드 5장에 case 확인 댓글을 달면서 case가 맡겠다고 한 일을 여기 모은다. **2026-10-04 카드 5장이 모두 `ACCEPTED`로 닫혀 착수할 수 있다** — 결정은 case 댓글과 같은 방향으로 났다(각 카드 「최종 결정란」).

**case 댓글:** [#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244#issuecomment-5978870101) · [#245](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/245#issuecomment-5978830198) · [#246](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/246#issuecomment-5978917389) · [#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247#issuecomment-5978955168) · [#248](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/248#issuecomment-5978979193)

**문서 (case 소유)**

| # | 할 일 | 출처 |
| --- | --- | --- |
| 8-1 | 🔄 **분석 시작 구현(2026-10-07) — `START_ANALYSIS` · 단서 반영 진입 함수 · 타임라인 port(임시: 등록 순서 이어 붙이기). 결정 `decisions/start-analysis.md`. 중단 command는 남음.** case-command Draft에 분석 시작 · 중단 command 추가 — 이름 · payload · 허용 상태, 시작 command가 hints를 어디서 받는지 포함. **분석 시작은 초안 작성(2026-10-04, Draft §11 — #210 Search 의견 반영 · case 결정 4건(`HINT_EXTRACT` · 실패 notice 없음 · 빈 설명은 구조화 생략 · CaseView `description`) · 남은 미결 5건)**, 중단은 C-1a 결정 뒤 | #245 C-1 · #247 H-2 |
| 8-2 | ✅ **2026-10-08 case-command §2 반영 — HTTP API Contract(`http-api/v1`, Final) §5.3을 가리킨다.** case-command Draft §2 transport 줄을 HTTP API Contract(RD-05)를 가리키도록 수정 — Contract는 `docs/architecture/contracts/contract-http-api.md`(Draft, #265). #265 merge 뒤 그 경로로 고친다 | #247 H-6 |
| 8-3 | ✅ CaseView 계약에 `running_jobs[]` 정의 추가 — 「case가 아직 결과를 기다리는 job」, 실행 종료부터 case 반영까지 · backoff 중에도 유지, 중단 · timeout으로 기다리기를 멈춘 job은 제외. **2026-10-04 B절 §10 불변조건 5로 반영됨**(#263, common/runtime이 case 답변대로 정합) | #247 H-4 |
| 8-4 | ✅ **2026-10-06 CaseView 계약 B절 §7 반영(#269).** CaseView 계약에 「중단된 job은 실제 실행 상태와 상관없이 `PARTIAL`로 투영」 추가 — 마지막 attempt가 `STALE`이어도 `FAILED`로 보이지 않게 | #245 C-3 · #248 Q-1 |
| 8-5 | ✅ **2026-10-06 budget 결정 문서 반영(#269).** `decisions/budget-krw-normalization.md` 「남은 것」에 정규화 층(cost를 계산하는 Search)과 `amount=null`은 0이 아니라는 원칙 반영 | #244 U-2 |
| 8-18 | ✅ **2026-10-06 CaseView 계약 B절 §5 · §6 반영(#269).** CaseView 계약 B절 §5 schema에 `contract` · `contract_version` 등재 — 구현(`view.py`)은 이미 싣고 있고, 다른 계약 8개(SourceAsset · AnalysisScope 등)도 schema에 두는 관례다(2026-10-05 case 결정, #265 §9) | #265 |

**구현 (case 코드)**

| # | 할 일 | 출처 |
| --- | --- | --- |
| 8-6 | 🔄 **1단계 구현(2026-10-06) — `MySQLCaseRepository` · in-memory 복사본 load · `CaseStore` facade. 처리 execution · 중단 job 테이블(8-8 · 8-9)과 adapter 제거(2단계)는 남음.** 설계: `decisions/case-store-mysql.md`(#267, Runtime §9 확인 완료). `CaseStore` MySQL 구현 — case마다 adapter를 들고 CaseView 때마다 adapter에서 다시 읽는 구조도 함께 바꾼다. 영속화 대상: Case aggregate(`Candidate.thumb_ref` 포함) · JobRecord · `scope_ref`가 가리키는 AnalysisScope · 처리한 `execution_id`. **첫 비동기 Real E2E의 선행**이고 8-7 ~ 8-11은 이 위에서 한다 | #245 D-1 · #246 S-4 |
| 8-7 | ✅ **2026-10-06 `execute_command()` → `CommandResult.appended_job_records`(#268, 결정 `decisions/command-appended-job-records.md`).** command 처리가 「이번 command로 append한 JobRecord 목록」을 응답 body 밖으로 돌려준다 — composition root의 dispatch와 HTTP 202/200 판단에 쓴다 | #245 D-2 · #247 H-3 |
| 8-8 | 결과 반영 함수를 `execution_id` 기준 idempotent로. 8-6 1단계 후속: COARSE_SEARCH 첫 발주 경로는 `issue_coarse_search(scope=…)`로 AnalysisScope를 남겨야 한다(지금은 데모 · 스크립트만 발주) · adapter 캐시가 rollback된 case_rev를 기억할 수 있다(2단계 adapter 제거 때 함께). | #245 D-5 |
| 8-9 | 중단 command 처리 + 「중단된 `job_id` 집합」으로 늦은 결과를 거르는 guard. 6.6순위 조건 2(현재 선택 context 대조)와 함께 동작한다 | #245 C-1a · C-4 |
| 8-10 | JobExecution read port 연결 + attempt 최댓값 선택(CaseView 계약 A§10-6)을 case가 구현. `view.py`의 「최신 attempt 선택은 runtime이 건네준다」 주석 수정. **선택 규칙 · 주석 수정은 선반영(2026-10-04, `view.representative_execution_status()`)** — read port 연결만 D-6 뒤 | #245 D-6 · #248 Q-1 |
| 8-11 | 🔄 **구현(2026-10-06) — JobRecord 정산 기록으로 case가 계산, 실행 기록 없으면 `PENDING`. 결정: `decisions/running-jobs-derivation.md`. #282 머지 뒤 PR.** `running_jobs` 투영을 8-3 정의대로 구현 — `handle_command()`가 `running_jobs`를 호출자에게 받지 않고 case가 직접 계산한다. **command 응답의 `case_view`에는 이번 command로 append한 job이 들어 있어야 한다**(HTTP 202 직후 polling이 멈추지 않게, #265 §5.3 · §7-2). 응답을 만드는 시점에는 enqueue 전이라 실행 기록이 없으므로, JobRecord는 있고 실행 기록이 없는 job은 `PENDING`으로 싣는다 | #247 H-4 · #265 |
| 8-12 | ✅ **2026-10-06 구현 — `create_case()` · `record_source_registered()`(#270, 결정 `decisions/empty-case-and-manifest.md`).** 빈 case 생성 경로 — `CaseAggregate.intake()` 필수 인자(`hints` · `manifest_summary`) 정리, adapter 없이 등록, 업로드마다 `manifest_summary` 갱신 | #247 H-2 |
| 8-13 | source asset을 `RealVideoAdapter`의 local path 대신 recording 공개 함수로 조회 | #246 S-3 |
| 8-14 | ✅ `FINE_VERIFY` 실행 실패의 notice · action 정하기 — **2026-10-04 `search.visual_verify_failed`**(ERROR · blocking · `actions:[]`, 출구는 「다른 후보 보기」, CaseView 계약 등재). 실행 상태는 호출자가 `visual_verify_status`로 넘긴다. 동기 real 경로의 Fine 예외 → 실행 실패 분류는 Search failure taxonomy 접합(#244) 뒤 | #244 R-1 |
| 8-15 | ✅ **2026-10-04 overlay 판독 결과 notice 3종**(`readout.overlay_not_present` · `_presence_undetermined` · `_ocr_failed`)을 case가 붙인다 — readout `failure-taxonomy.md` 매핑 그대로, 현재 선택 후보의 가장 나중 판독 기준. 이 카드들의 후속은 아니고 8순위 검토 중 찾은 공백(코드가 붙이지 않았고 CaseView 계약 등재도 둘 빠짐) | readout `failure-taxonomy.md` |
| 8-16 | ✅ **2026-10-07 — 반영 함수 + `service.receive_hint_extraction_result()`(첫 탐색 발주까지). Worker 배선은 Runtime #297.** 단서 구조화(`HINT_EXTRACT`) 결과 반영 — **결과 반영 함수만 선반영(2026-10-04, `service.receive_hint_extraction()`)**. 결과 모양은 #210 Search 의견 가정, 발주 · 배선은 Search PR · D-5 뒤. 3순위와 같은 일 | #210 · 3순위 |
| 8-17 | 🔄 **case 쪽 완료(2026-10-06) — `INTAKE`에서만 받고 아니면 `SourceNotAccepted`(#270). HTTP 매핑은 #265.** source 연결은 `INTAKE`에서만 받는다 — 분석 시작 뒤 추가 업로드는 거부. product에 분석 시작 뒤 업로드 흐름이 없고 `START_ANALYSIS` 초안도 `INTAKE` 전용이다(2026-10-05 case 결정, #265 §9). 거부 status · code 모양은 HTTP Contract가 정한다 | #265 |

**case가 정할 미결** — 정하기 전에는 위 해당 항목을 끝냈다고 부르지 않는다.

- 「초안 준비 중」(`core-user-flow.md` 230행)에 중단할 때 판독 job까지 멈추는가 — product에 정해져 있지 않다(#245 C-1a에서 보류). 8-1 · 8-9
- ~~timeout된 job을 `running_jobs`에서 빼는가~~ → **뺀다(2026-10-04, B절 §10 불변조건 5).** timeout 뒤 늦게 반영된 결과는 web이 다시 조회할 때 보인다.
- 파일별 upload에서 `manifest_summary.failed_file_count`가 무엇을 세는가 — 계약 정의는 「파일 등록 실패 수」인데 #265는 거부된 upload를 기록 없이 버려(422) 셀 수 없다. case 제안: 손상 파일은 recording이 `availability=UNAVAILABLE`로 등록 · 연결해 case가 세고, 파일 이름은 web이 upload 응답으로 보여 준다(CaseView에는 파일 목록이 없다). recording · web과 정한다(#265 §9). 8-12
- budget guard가 「계산 불가」(`amount=null` 포함)일 때 발주를 막는가 계속하는가 — guard 구현 때 정한다(#244 U-2)
- 시작 command payload 모양 — 8-1과 함께 정한다

**다른 Owner 쪽 반영** — case가 고치지 않고 결과만 확인한다. **2026-10-05 세 건 모두 반영 확인.**

| 할 일 | 소유 | 카드 |
| --- | --- | --- |
| ✅ 「현재 `case_rev`와 맞는 결과만 반영」 문구를 「case가 현재 context에 유효하다고 판단한 결과만 반영」으로 — JobExecution §9-8 · §2 case Consumer 행, `module-architecture.md` §4-모듈5 ④ · §8-2 | common/runtime (Architecture 문서 포함) | #245 C-1a |
| ✅ C-4 문구를 「중단된 `job_id` 집합에 있는 job의 결과는 반영하지 않는다」로 — Runtime Tech Spec §12.2 · §12.5 | common/runtime | #245 C-4 |
| ✅ process 경계를 넘는 recording 상태 목록에 CaseView FrameRef 3종(`thumb_ref` · `preview_ref` · `plate_preview_ref`) 포함 — #246 S-4 「case 보완 채택」 | recording | #246 S-4 |

**왜 8순위:** 전부 Runtime 결정에 종속된 배선 작업이었다. 2026-10-04 결정이 모두 나서 이제 착수할 수 있고, 8-6(case store MySQL)이 Real E2E 비동기 전환(M5)의 선행이라 이 섹션 안에서는 가장 먼저 한다.

**참고:** 이슈 #244 · #245 · #246 · #247 · #248, 목록 #251, evidence PR #253, CaseView 정합 PR #263, HTTP API Contract Draft PR #265

## 2. case가 의존하는 외부 블로커 (case 파트 아님, 참고용)

case가 직접 고칠 수 없고, 각 모듈 Owner의 작업을 기다리거나 그 결과를 그대로 쓰는 항목이다. 이 문서의 우선순위 대상이 아니다.

| 항목 | 소유 | 현재 상태 |
| --- | --- | --- |
| Worker/실행 인프라(`get_job_executions()` 등) | `common/runtime`(정철원 구현) | `worker/` 폴더가 비어있음. `service.py`의 `fetch_case_view_inputs()`가 이 메서드를 아예 안 부르므로 오늘 E2E 목표엔 영향 없었음 |
| search/readout 내부 실제 AI·OCR | 각 모듈 Owner | 여전히 `FixtureSearchService`/`FixtureOcrProvider` — 오늘 증명한 건 "파이프라인 배선이 안 끊긴다"이지 "AI 품질이 좋다"가 아님 |
| `time_source_candidates` 공개 함수 미노출 | `recording` | `RecordingFixture` pydantic 모델에 이 필드 자체가 없음. `real_e2e.py`가 raw fixture로 우회 중 |

## 3. 별도로 이미 결정 완료된 것

- **Agent framework(LangGraph/Google ADK) 도입 기준** — 지금은 도입하지 않기로 결정. 재검토 트리거 4개 명시. → `docs/modules/case/decisions/agent-framework-adoption-criteria.md`
- **input_fingerprint의 implementation label 조합** — 요구사항 자체는 유효하나, `case`에 fingerprint 기반 캐시/dedup 로직 자체가 아직 없고 search/readout의 `list_impls()`도 미구현이라 지금은 만들지 않기로 결정(이슈 #77). 재검토 트리거 2개 명시. → `docs/modules/case/decisions/input-fingerprint-implementation-label-deferred.md`

## 4. 오늘 Real E2E 실행 근거

이 문서의 §1 우선순위는 다음 실행 결과를 근거로 한다(2026-09-18, `feature/case-mock-real-service-adapter`):

- `src/daesingo/case/real_e2e.py` — recording→search→readout→evidence real 연결 구현
- `docs/modules/case/experiments/w6-real-e2e-happy-001.md` — `scenario_happy_001` real E2E 실행 로그
- `docs/modules/case/decisions/orchestration-service-layer.md` §6·§7·§8 — search/evidence/`get_view()` real 교체 과정에서 확인한 것들

(위 3개 파일은 이후 develop에 병합됐다.)

## 5. 완료 조건 — 이 문서의 각 항목을 "끝났다"고 부르는 기준

이번 고도화 작업은 다음 사이클을 한 단위로 삼는다:

```
조사 문서 → 선택안과 근거 → eval dataset → baseline 측정 → 개선안 구현 → 동일 dataset 재평가 → ADR
```

**"도입하지 않음"도 정상적인 완료 조건이다.** 사이클이 반드시 "구현"까지 가야 끝나는 게 아니다 — 조사 후 "지금 구조가 이미 충분하고, 바꾸면 오히려 재현성·테스트성이 나빠진다"는 결론도 완료다. `decisions/agent-framework-adoption-criteria.md`가 이미 이 패턴을 실제로 증명했다 — 조사 문서(§2 출처) → 선택안과 근거(§3 대조표) → ADR(재검토 트리거 포함, §4)까지 거쳤고, eval dataset/baseline 측정 단계는 "측정할 대상 자체가 없다"(agent framework를 실제로 붙여보지 않고도 판단 가능한 정성적 기준)는 이유로 정당하게 생략했다. case의 현재 구조는 이미 단순하고 deterministic한데, 여기서 괜히 Agent framework로 바꾸면 재현성·테스트성이 오히려 나빠질 수 있다는 게 바로 그 판단의 핵심 근거였다.

**어떤 항목에 전체 사이클이 필요한지, 어떤 항목은 생략 가능한지:**

| 항목 | 사이클 적용 범위 | 이유 |
| --- | --- | --- |
| 7순위(Orchestration 평가 지표) | 전체 사이클 | "개선"이 실제로 측정 가능한 수치 변화라 baseline/재평가가 의미 있다 |
| 3순위(Intent LLM 통합) | 전체 사이클(이미 진행 중) | `intent-llm-model-comparison` 실험이 이미 eval dataset(locked v1)·baseline 측정 단계를 밟고 있다 |
| 1·2·4·5·6·6.5·8순위(A3/D8/B5/B6/A2) | 축약 — 조사 문서/선택안/구현/테스트까지만 | 순수 배선·설계 작업이라 "eval dataset로 개선폭을 측정"할 대상 자체가 없다(정답/오답이 명확한 정합성 문제) — 테스트 통과 여부가 곧 검증이다 |
| 3.5순위(correction 로그 정책) | 사이클 밖 — 정책/승인 프로세스 | 성능 개선이 아니라 동의·법무 성격이라 이 사이클이 안 맞는다. Issue #74의 완료 조건 체크리스트를 그대로 따른다 |

새 항목이 이 문서에 추가될 때도 "성능/품질 개선 항목인지, 순수 배선 항목인지, 정책 항목인지"를 먼저 구분하고 맞는 사이클(또는 생략)을 적용한다.
