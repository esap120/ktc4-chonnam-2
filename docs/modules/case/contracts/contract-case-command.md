# Draft Contract — Case Command (web → case)

**Status:** `Draft` — 팀 합의 전 초안. 합의되면 `docs/architecture/contracts/`로 옮기고(`contract-case-command.md` + `adr/adr-case-command.md`) 이 사본은 지운다(`docs/architecture/contracts/README.md`).

**Contract Version:** `case-command/v0` (초안) · 입력형 판본 초안 `case-command/v1`(2026-10-13, §12 — 열림 조건 충족 전에는 받지 않는다)

**Owner:** 유소연(`case`) · **Consumer 확인 대상:** 신유민(`web`)

**근거 이슈:** #106 (공용 command 표면) · #171 B-2(상황 응답 전송 경로) · #173 E-4(결과 화면 다른 후보 선택)

---

## 1. 목적

`module-architecture.md` §4-모듈6은 web을 「CaseView를 표현하고 **사용자 명령을 case에 전달**하는 UI」로 정의하지만, 계약은 읽기 방향(`web → case.get_view() → CaseView`)만 있다. 쓰기 방향이 없어서 「무엇을 보낼지는 정했는데 보낼 길이 없는」 명령이 여럿 쌓였다(#106 신유민 정리).

이 문서는 그 명령들이 **함께 쓰는 표면 모양 하나**를 정한다: 어디로 보내나 · 결과를 어떻게 돌려받나 · 실패를 어떻게 알리나. 각 명령의 도메인 규칙은 새로 정하지 않고 이미 정해진 곳을 가리킨다.

## 2. 범위

**이 판본에 넣는 command**

| `kind` | 사용자가 하는 일 | 도메인 규칙의 원문 |
| --- | --- | --- |
| `SELECT_OTHER_CANDIDATE` | 결과 화면에서 「다른 후보 보기 → 다른 후보 선택」 | `contract-correction-record.md`(`OTHER_CANDIDATE`) · #173 E-4 |
| `RECORD_SITUATION_RESPONSE` | 결과 화면 「신고 상황」에서 `[맞아요]`·`[잘 모르겠어요]`(`[다른 상황]`은 §5 — 입력형 판본) | #171 B-2 · ADR-EVIDENCE-005 |
| `MARK_REVIEWED` | 신고자료 최종 확인(`USER_REVIEWED`) | `module-architecture.md` §3-6 · CaseView 계약 B절 `user_reviewed` |
| `RUN_NOTICE_ACTION` | notice에 붙은 발주형 버튼(`GENERATE_REPORT_VIDEO` · `RETRY_PLATE_READ` · `RETRY_SEARCH` · `GENERATE_PLATE_IMAGE`) | CaseView 계약 B절 §7 「`notices[].actions[]` → 발주 매핑」 |
| `START_ANALYSIS` | 첫 화면에서 영상을 올리고(설명은 선택) 「영상에서 찾아보기」 | §11 · #247 H-2 · `decisions/start-analysis.md` |
| `STOP_ANALYSIS` | 분석 진행 화면에서 `[분석 중단]`(2026-10-11, 고도화 8-9) | #245 C-1 · C-1a · `decisions/stop-analysis.md` · `core-user-flow.md` §7 |
| `MANUAL_PLATE_INPUT` · `EDIT_EVENT_TIME` · `RECORD_SITUATION_RESPONSE`(`CORRECTED`) | 번호판 · 발생시각 직접 입력, 신고 상황 `[다른 상황]` — **입력형 판본 초안(§12)** | `contract-correction-record.md` · #235 · `core-user-flow.md` §12 · §13 · §15 |

**이 판본에 넣지 않는 것**

- **입력형 action 중 나머지**(`REVIEW_TIME` · `EDIT_HINT` · 위치 단서 수정 · 번호판 `[맞아요]`) — 규칙이 정해지지 않았다. 이유는 §12-5. 번호판 · 시각 · `[다른 상황]`은 §12 입력형 판본 초안이다.
- **초기 후보 선택** — `rank=1` 자동 선택이라 사용자 명령이 아니다(#168 결정 1, #194). 후보 command는 결과 화면에서 다른 후보를 고를 때만 쓴다(#106 신유민 09-23).
- **`rejected_candidate_ids`** — 받지 않는다(#106 결론). 개별 후보를 「아니다」로 지목하는 화면 신호가 생기면 다시 본다.
- **시간 보정 버튼 4종**(조금 전·조금 후 등) — W7 밖(#106 결론).
- **「초안 준비 중」의 중단** — 판독 · Fine job까지 멈추는지 product에 정해져 있지 않다(#245 C-1a 보류). 정해질 때까지 `STOP_ANALYSIS`는 `SEARCHING`에서만 받는다(§5).
- **transport**(HTTP 경로 · status · 직렬화) — HTTP API Contract(`docs/architecture/contracts/contract-http-api.md`, `http-api/v1`)가 정한다(2026-10-08, 고도화 8-2). 이 문서의 요청은 `POST /cases/{case_id}/commands` body에 그대로 실리고, HTTP 층은 body를 검사하지 않고 `case.handle_command()`에 넘긴다(그 계약 §5.3). 이 문서는 transport와 무관한 요청 · 응답 모양만 정한다. 인증은 두 문서 모두 범위 밖이다(Architecture §1-7 A2).

## 3. 책임 경계

- **web:** 사용자가 누른 것을 command로 보낸다. 결과 CaseView를 그대로 다시 그린다. 선택·응답을 로컬에서 확정하지 않고, readout·evidence를 직접 부르지 않는다(#106 신유민 09-23).
- **case:** command를 받아 상태 전이·기록·발주를 한다. 성공이든 실패든 **그 시점의 CaseView**를 돌려준다. 신고요건·번호판·시각 값을 command에서 판정하지 않는다(`module-architecture.md` §4-모듈5 ⑦).
- 실제 Job 실행은 command 응답에 포함되지 않는다. 발주가 됐다는 것까지만 돌려주고, 진행은 다음 CaseView의 `running_jobs[]`·`progress[]`로 본다.

## 4. 스키마

**요청**

```json
{
  "case_id": "string",
  "expected_case_rev": "int",
  "kind": "SELECT_OTHER_CANDIDATE | RECORD_SITUATION_RESPONSE | MARK_REVIEWED | RUN_NOTICE_ACTION | START_ANALYSIS | STOP_ANALYSIS | MANUAL_PLATE_INPUT | EDIT_EVENT_TIME",
  "payload": "object — kind별(§5)"
}
```

**응답**

```json
{
  "ok": "boolean",
  "error": "null | { \"code\": \"string\", \"message_key\": \"string\" }",
  "case_view": "CaseView | null — 성공이면 command 반영 후, 실패면 변경 없는 현재 값. case_id가 없을 때만 null"
}
```

- `case_view`는 **성공·실패 모두** 싣는다. stale 실패일 때 web이 따로 다시 읽지 않고 최신 화면을 그리게 하기 위해서다.
- `error.code`는 `notices[].code`와 같은 dotted-lowercase 규칙을 따른다(CaseView 계약 B절 §7). `message_key`는 web 문구 키다.
- **응답 밖으로 돌려주는 것(2026-10-05, 8-7).** case는 응답과 함께 **이번 command로 append된 JobRecord 목록**을 composition root에 돌려준다(`case.execute_command()` → `CommandResult.appended_job_records`). composition root는 이 목록마다 Runtime enqueue를 하고 HTTP 200 / 202를 정한다(HTTP API Contract §5.3). 이 목록은 **위 응답 body에 싣지 않는다** — web이 받는 모양은 위 셋 그대로다. 실패한 command는 늘 빈 목록이다. 이유와 고르지 않은 안은 `../decisions/command-appended-job-records.md`.
- **중단한 job 목록(2026-10-11, 8-9).** `STOP_ANALYSIS`가 성공하면 case는 이번 command로 `CANCELLED`로 정산한 `job_id` 목록도 돌려준다(`CommandResult.cancelled_job_ids`). composition root는 같은 transaction에서 Runtime `request_cancel(conn, job_ids)`를 부른다(Runtime Tech Spec §12.5 · #292). 새 발주가 없으므로 HTTP는 `200`이다. 이 목록도 응답 body에 싣지 않고, 실패한 command는 `[]`다.

## 5. `kind`별 payload와 규칙

| `kind` | `payload` | 허용 상태 | 성공하면 |
| --- | --- | --- | --- |
| `SELECT_OTHER_CANDIDATE` | `{ "candidate_id": "string" }` | `EVIDENCE_REVIEW` · `READY` | `OTHER_CANDIDATE` CorrectionRecord 1건, `selection_rev` +1, `case_rev` +1. `READY`였으면 `EVIDENCE_REVIEW`로 돌아가고 `user_reviewed=false` |
| `RECORD_SITUATION_RESPONSE` | `{ "value": "CONFIRMED \| USER_UNSURE" }` | 선택된 후보가 있을 때 | `situation_response` 기록(`candidate_ref`=현재 선택 후보, `responded_at`=case가 받은 시각), `case_rev` +1. `READY`였으면 `EVIDENCE_REVIEW`로 돌아간다(아래 「READY에서 다시 조립되는 변경」). 이 응답으로 Package가 준비되면 아래 「성공 뒤 `READY` 재확인」으로 `READY`가 되고 `case_rev`가 +1 더 오른다 |
| `MARK_REVIEWED` | `{}` | `READY` | `user_reviewed=true`, `case_rev` +1 |
| `RUN_NOTICE_ACTION` | `{ "notice_code": "string", "action": "GENERATE_REPORT_VIDEO \| RETRY_PLATE_READ \| RETRY_SEARCH \| GENERATE_PLATE_IMAGE" }` | 현재 CaseView의 `notices[]`에 **그 `code`를 가진 notice가 있고, 그 notice의 `actions[]`에 그 `action`이 있을 때** | CaseView 계약 B절 §7 매핑대로 새 `JobRecord` 1건 |
| `STOP_ANALYSIS` | `{}` | `SEARCHING`이고 case가 기다리는 `HINT_EXTRACT` · `COARSE_SEARCH`가 있을 때 | 그 job들을 `CANCELLED`로 정산(다른 kind는 그대로), `case_rev` +1, stage는 `SEARCHING` 그대로. CaseView는 `coarse_search`=`PARTIAL` · notice `case.analysis_stopped`(CaseView 계약 B§7). 중단된 job의 늦은 결과는 반영하지 않는다(#245 C-4) |

- **성공 뒤 `READY` 재확인(2026-09-30).** command가 성공하고 stage가 `EVIDENCE_REVIEW`면 case가 `PACKAGE_READY`(FINAL `PASS`/`WARN` + ReportPackage, #167 gate 그대로)를 다시 보고, 성립하면 같은 command 안에서 `READY`로 올린다. `READY` 전이도 `case_rev`를 올리므로 그때는 위 표의 증가분에 +1이 더해진다. transport·web이 따로 전이를 부르지 않는다 — 통로에 판단을 넣지 않는다(#106). 실패한 command 뒤에는 보지 않는다(§6).
- **`READY`에서 다시 조립되는 변경(2026-10-02, orchestration 지표 4차 측정).** `READY`에서 상황 응답(과 입력형 판본의 값 정정)을 받으면 case가 먼저 `EVIDENCE_REVIEW`로 내리고, 위 재확인이 gate가 여전히 성립할 때만 다시 올린다. 내리지 않으면 재조립으로 Package가 사라져도 `READY`로 남아 CaseView 계약 §10-9(「`stage=READY`이면 `requirements_package`가 `PASS`/`WARN`」)를 어긴다. 내려가는 것은 같은 요청의 결과라 `case_rev`를 따로 올리지 않는다(`SELECT_OTHER_CANDIDATE`와 같다) — 그래서 gate가 그대로면 응답 +1, 다시 `READY` +1로 +2다. `user_reviewed`는 그대로 둔다(필드 수정과 별개 — CaseView 계약 B절 `user_reviewed` · #173 값별 경계표). 새 초안이 되는 `SELECT_OTHER_CANDIDATE`만 되돌린다.
- `RUN_NOTICE_ACTION`의 허용 조건은 「화면에 그 버튼이 떠 있었는가」와 같다. web은 `notices[].actions[]`에 있는 값으로만 버튼을 그리므로(CaseView 계약 B절 §7), case도 같은 근거로만 받는다.
- `SELECT_OTHER_CANDIDATE`의 「새 후보 초안을 준비하는 중에는 다시 고르지 않는다」(#173 E-4 조건 1)는 case domain에 「준비 완료」 신호가 없어 이 판본에서 검사하지 않는다 — 진행 화면에서 버튼을 주지 않는 web 규칙에 기대고, worker 배선 때 case가 막는다(PR #190 — W7 기준 문서 6.6순위로 추가 중).
- `responded_at`은 web이 보내지 않고 case가 채운다 — 사용자 기기 시계를 기록값으로 쓰지 않는다.
- **`CORRECTED`(`[다른 상황]`)는 이 판본에서 받지 않는다**(`case.command.invalid_payload`) — 입력형 판본 초안 §12-3에서 연다. evidence는 `CORRECTED` 응답에 `SITUATION_CHANGE` CorrectionRecord가 정확히 1건 있어야 조립하고, 없으면 조립 자체를 거부한다(`src/daesingo/evidence/assembly.py` — `CORRECTED requires one SITUATION_CHANGE head`). 바뀐 상황을 보내는 입력형 경로가 없으므로(§2) 입력형 판본에서 둘을 한 command로 함께 연다.

## 6. 실패 코드

| `error.code` | 뜻 | 예 |
| --- | --- | --- |
| `case.command.stale_revision` | `expected_case_rev`가 현재 `case_rev`와 다르다 — 사용자가 본 화면이 이미 바뀌었다 | 다른 탭에서 먼저 후보를 바꿨다 |
| `case.command.unknown_target` | 가리킨 대상이 이 case에 없다 | 없는 `candidate_id` · 없는 `case_id` · 현재 notices에 없는 `notice_code`/`action` 조합 |
| `case.command.not_allowed` | 대상은 있지만 지금 상태에서 할 수 없다 | `CANDIDATE_REVIEW`에서 `MARK_REVIEWED` · 이미 선택된 후보를 다시 선택(무변경) |
| `case.command.invalid_payload` | payload 모양이 틀렸다 | 등재되지 않은 `value` · 필수 키 누락 |
| `case.command.invalid_value` | **입력형 판본 초안(§12-4).** 모양은 맞지만 값이 정정 기록 규칙에 맞지 않는다 — evidence 기록 전 검사(E-3)가 거부했다 | 오프셋 없는 시각 · 번호판 빈 문자열 |

- 실패하면 **아무 상태도 바뀌지 않는다** — `case_rev`·CorrectionRecord·JobRecord·선택 상태 모두 그대로다(#166과 같은 원자성).
- 검사 순서는 `invalid_payload` → `unknown_target`(case) → `stale_revision` → `unknown_target`(대상) → `not_allowed`다(입력형 판본은 마지막에 `invalid_value`, §12-4). 화면이 낡았으면 대상 검사 전에 먼저 알린다.

## 7. 불변조건

1. command 하나는 CaseView 한 번의 변경이다. 실패한 command는 변경이 없다.
2. 응답의 `case_view.case_rev`는 성공이면 요청의 `expected_case_rev`보다 크거나 같고, 실패면 현재 값이다.
3. command는 신고요건·번호판·시각 값을 판정하지 않는다. 판정 결과는 다음 CaseView 조립에서 evidence가 준 값으로만 바뀐다.
4. web은 command 응답을 받기 전까지 선택·응답을 화면에서 확정값으로 그리지 않는다.

## 8. 예시

```json
// 요청 — 결과 화면에서 다른 후보 선택
{ "case_id": "case_h001", "expected_case_rev": 3, "kind": "SELECT_OTHER_CANDIDATE",
  "payload": { "candidate_id": "candidate_h002" } }

// 응답 — 성공
{ "ok": true, "error": null,
  "case_view": { "case_id": "case_h001", "case_rev": 4, "stage": "EVIDENCE_REVIEW", "user_reviewed": false, "...": "..." } }

// 응답 — 화면이 낡음
{ "ok": false,
  "error": { "code": "case.command.stale_revision", "message_key": "command.stale_revision" },
  "case_view": { "case_id": "case_h001", "case_rev": 5, "...": "..." } }
```

## 9. 미결

- **`case_rev`로 잡히지 않는 변경.** 탐색 시작(`start_search`)·후보 선택(`select_candidate`)처럼 `case_rev`를 올리지 않는 전이가 있다(`src/daesingo/case/domain.py` docstring — `case_rev`는 「요청 시점 케이스 리비전」이다). 그 사이의 command는 stale로 잡히지 않는다. 이 판본의 command는 모두 사용자 결과 화면(`EVIDENCE_REVIEW`·`READY`)이나 notice에서 나와 영향이 작다고 보지만, 확인 필요.
- **`RUN_NOTICE_ACTION` 중복 제출.** 발주가 `case_rev`를 올리는지는 kind마다 정해져 있지 않다(재판독 발주는 올린다고 적혀 있고 나머지는 확인 필요). 올리지 않으면 같은 버튼을 두 번 눌렀을 때 stale 검사로 막히지 않는다. `idempotency_key`를 둘지 함께 정한다.
- **`error.message_key` 값 목록.** web 문구 키라 web과 함께 정한다.
- ~~**transport** — §2.~~ → **종결(2026-10-08, 고도화 8-2).** HTTP API Contract(`http-api/v1`, Final)가 정한다 — §2.

## 10. 구현할 때 맞출 것 (case 내부)

규칙이 아니라 현재 코드와의 차이다. 진입 함수는 `case.handle_command(request, *, store)`(`src/daesingo/case/command.py`)다.

- `CaseAggregate.mark_reviewed()`에는 여전히 stage 가드가 없다 — command 층이 `READY`만 받는다.
- domain이 「알 수 없는 후보」와 「지금 상태에서 불가」를 같은 `InvalidTransition`으로 던진다 — command 층이 대상을 먼저 확인해 §6의 두 코드로 나눈다.
- `RUN_NOTICE_ACTION`은 같은 kind의 가장 최근 `JobRecord`에서 `input_fingerprint`·`scope_ref`를 그대로 쓴다(`jobs.issue_needed_jobs()`와 같은 원칙). case는 fingerprint를 계산하지 않으므로 이전 발주가 없으면 `not_allowed`다 — `GENERATE_PLATE_IMAGE`처럼 처음 발주되는 kind는 fingerprint 출처가 정해질 때까지 이 경로로 열리지 않는다.
- 성공 뒤 `READY` 재확인은 `service.mark_ready_if_package_ready()`를 그대로 부른다. real(fixture) 경로는 최종 신고영상 관찰(I4, `observation_facts`)이 없어 상황 응답 뒤에도 FINAL이 `UNKNOWN`이라 `READY`에 가지 않는다(ADR-EVIDENCE-008 §6.2) — 이 재확인과 별개로 evidence 쪽 입력이 있어야 한다.
- `RECORD_SITUATION_RESPONSE`는 PR #177이 머지돼야 develop에서 동작한다.

## 11. 분석 시작 `START_ANALYSIS` (2026-10-04 초안 · 2026-10-07 구현)

> **상태: 구현(2026-10-07, 고도화 8-1) — 이 판본에 넣는다.** 결정 · 구현 범위는 `decisions/start-analysis.md`. 분석 시작을 별도 endpoint가 아니라 commands의 `kind`로 두는 방향은 #247 H-2(2026-10-04 `ACCEPTED`, HTTP API Contract §5.3), 단서 구조화 호출 창구는 #210 · #277(search public 함수)을 따른다. 응답과 별도로 `execute_command()`가 append한 JobRecord(`HINT_EXTRACT` 또는 `COARSE_SEARCH`)를 돌려주고, Worker는 `service.receive_hint_extraction_result()`로 결과를 반영한다.

**사용자가 하는 일:** 홈 화면에서 블랙박스 영상을 올리고(파일마다 따로 업로드, #247 H-5) 기억나는 상황을 자유롭게 적은 뒤 「분석 시작」(`core-user-flow.md` §5). AI가 단서를 구조화하고 탐색 범위를 구성한 뒤 바로 분석을 시작하며, 사용자는 이 내부 계획을 승인하거나 수정하지 않는다(§6).

| `kind` | `payload` | 허용 상태 | 성공하면 |
| --- | --- | --- | --- |
| `START_ANALYSIS` | `{ "description": "string" }` — 사용자가 적은 원문 그대로. 빈 문자열을 허용한다 | `INTAKE`이고, 이 case에 처리할 수 있는 영상이 1개 이상 있을 때(`manifest_summary.ok_file_count >= 1`) | 설명 원문 보존 · `INTAKE→SEARCHING` · **`HINT_EXTRACT` `JobRecord` 1건**(`COARSE_SEARCH`는 결과 반영 때). 설명이 비었으면 구조화 없이 `AnalysisScope` 1건 · `COARSE_SEARCH` 1건을 바로 발주한다. `case_rev`는 그대로다 |

**흐름**

```
START_ANALYSIS ── 원문 보존 · SEARCHING · HINT_EXTRACT 발주 ──▶ (응답: 발주 있음)
                                                        │ Worker: search public 함수 1회
                                                        ▼
               결과 반영(#245 D-5) ── hints 채움 · AnalysisScope 1건 · COARSE_SEARCH 1건 발주
```

- **원문을 그대로 받는다.** web은 원문을 파싱하거나 구조화하지 않는다 — 입력 중 실시간 파싱 결과를 보여 주지 않고(`core-user-flow.md` §5), 구조화는 AI가 한다(§4). case는 원문을 「구조화 전 단서」로 보존한다(§4-2).
- **구조화는 비동기 Job 1회다.** `decisions/intent-llm-model-selection.md` §5가 이 호출을 「요청 안에서 동기로 끝내는 것이 아니라 1회짜리 비동기 Job」으로 보고 모델을 채택했고, 동기로 붙이면 같은 문서 §7 재검토 트리거에 걸린다. command 응답은 발주까지만이고 진행은 다음 CaseView로 본다(§3).
- **호출은 search, 판단은 case다(#210 Search 의견).** 프롬프트 · structured 스키마 · provider 호출 · 실패 분류는 search public 함수가 맡는다. case는 원문을 넘기고, 결과를 `hints` 4개 키로 옮기는 매핑(6필드→4키)과 실패 처리를 맡는다. provider 사용량은 다른 Search 호출과 같은 경로로 원장에 남는다(#244 U-1).
- **결과 반영.** 결과 상태가 `OK`면 매핑대로 `hints`를 채운다(일부 필드가 비어 있을 수 있다). `ABSTAINED`(모델이 전부 보류)나 `FAILED`(호출 · 파싱 실패)면 `hints` 4개를 모두 `null`로 두고 그대로 진행한다 — 값을 지어내지 않는다. 어느 쪽이든 이어서 `AnalysisScope`를 만들고 `COARSE_SEARCH` 1건을 발주한다(빈 단서면 「시간 단서 없이 전체 찾기」, `core-user-flow.md` §5). 결과 반영은 사용자 요청이 아니라 `case_rev`를 올리지 않는다(`record_candidate_search_failure()`와 같다).
- **빈 설명을 막지 않고, 구조화도 건너뛴다(2026-10-04 case 결정).** `description`이 빈 문자열이어도 `invalid_payload`가 아니다(키가 없거나 문자열이 아니면 `invalid_payload`). 앞뒤 공백을 지운 뒤 비었으면 `HINT_EXTRACT`를 발주하지 않고 `hints` 4개를 `null`로 둔 채 `AnalysisScope` · `COARSE_SEARCH`를 바로 발주한다 — 부를 이유가 없는 provider 호출과 대기를 만들지 않고, `ABSTAINED`가 「모델이 판단을 보류함」이라는 뜻으로만 남게 한다.
- **Job 이름은 `HINT_EXTRACT`(label_key `job.hint_extract`)다(2026-10-04 case 결정).** 기존 kind의 `대상_동작` 꼴(`PLATE_READ` · `FINE_VERIFY`)과 조사 문서 · 스키마 용어(`llm-model-comparison-hint-extraction` · `IntentHintExtraction`)를 따른다.
- **구조화 실패는 notice로 알리지 않는다(2026-10-04 case 결정).** search 결과가 `FAILED`면 Worker가 그 Job을 JobExecution `FAILED` + `failure_kind`로 기록하고, 「설정이 깨져 매번 실패」는 Runtime 원장으로 알아챈다(#210 3번의 목적). 사용자 흐름은 `ABSTAINED`와 같아(빈 단서로 탐색 계속) 사용자가 할 일이 없고, 사용자가 적은 내용은 아래 `description`으로 화면에 남는다.
- **설명 원문을 CaseView 최상위 `description`(`string | null`)으로 내린다(2026-10-04 case 결정).** 구조화가 진행 중이거나 `ABSTAINED` · `FAILED`로 `hints`가 비어도 사용자가 자기 원문을 본다 — 그렇지 않으면 「기억하신 것」(web `HintRecall`)이 「없음」으로 떠, 단서를 적은 사용자에게 AI가 아무것도 이해하지 못한 것처럼 보인다(`core-user-flow.md` 「AI가 이해한 기억 단서가 맞는가?」). `hints` 안에 넣지 않는 이유는 `hints`가 「구조화된 4개」라는 뜻을 지키기 위해서다. `START_ANALYSIS` 전에는 `null`, 빈 설명이면 `""`다. CaseView 계약 변경이라 반영은 미결 1.
- **일부 영상 실패는 막지 않는다.** 읽을 수 없는 파일은 건너뛴 사실을 보여 주고 나머지로 진행한다(§23 「다른 영상은 계속 분석」). 처리할 수 있는 영상이 하나도 없을 때만 `not_allowed`다.
- **`case_rev`는 올리지 않는다** — `start_search()`가 `INTAKE→SEARCHING`에서 올리지 않는 현재 규칙 그대로다(`scenario_happy_001`: SEARCHING · `COARSE_SEARCH` 모두 `case_rev:1`). 같은 버튼을 두 번 눌러도 두 번째는 stage가 이미 `SEARCHING`이라 `not_allowed`로 막힌다 — §9 첫 항목(`case_rev`로 잡히지 않는 변경)이 이 command에서는 stage 검사로 해소된다.
- **`COARSE_SEARCH`는 1건이다.** 영상이 여러 개여도 case 타임라인 하나로 1건이다(`decisions/start-analysis.md` §3-1 — 임시로 등록 순서대로 이어 붙임). 긴 영상의 클립 분할 발주는 아직 구현되지 않았고(#168 후속), 생기면 클립별 발주로 고친다.
- 실패 코드는 §6의 네 가지를 그대로 쓴다. 새 코드를 만들지 않는다.

**예시**

```json
// 요청 — 홈 화면 「분석 시작」
{ "case_id": "case_h001", "expected_case_rev": 1, "kind": "START_ANALYSIS",
  "payload": { "description": "6시 반쯤 흰 SUV가 실선을 넘어 끼어들었어요" } }

// 응답 — 성공(발주 있음 → HTTP 202, #247 H-3). 구조화 Job이 진행 중이라 hints는 아직 비어 있다
{ "ok": true, "error": null,
  "case_view": { "case_id": "case_h001", "case_rev": 1, "stage": "SEARCHING",
                 "description": "6시 반쯤 흰 SUV가 실선을 넘어 끼어들었어요",
                 "hints": { "time": null, "vehicle": null, "situation": null, "location": null },
                 "running_jobs": [ { "job_id": "...", "kind": "HINT_EXTRACT", "label_key": "job.hint_extract", "status": "PENDING" } ],
                 "...": "..." } }
```

**닫힌 미결 (2026-10-07)**

1. **계약 반영.** 위 case 결정을 계약에 올리는 일이다 — CaseView 최상위 `description` 신설(필드 추가라 CaseView 버전을 올리고 web Consumer 확인이 필요하다), JobRecord 계약 A§7에 `HINT_EXTRACT` 등재 · A§12 `label_key` 목록에 `job.hint_extract` 추가(web 문구 필요). 신유민 확인 뒤 반영한다 — 확인 요청 #259. → **닫힘: `case-view/v1.7`(#286).**
2. **`AnalysisScope` 값의 출처.** `scope.py`는 `time_ranges` · `target_event_types` · `budget`을 호출자에게 받는다(intake 흐름이 정해지지 않았던 범위). 지금 real 경로는 영상 전체 1구간과 월요일 E2E 기본값을 쓴다(`real_e2e.py`). → **닫힘: `decisions/start-analysis.md` §3-1 · §3-2 · §3-3.**
3. **첫 발주의 `input_fingerprint`.** case는 fingerprint를 계산하지 않고 공식도 미정이다(`decisions/input-fingerprint-implementation-label-deferred.md`). `HINT_EXTRACT`와 `COARSE_SEARCH` 모두 재사용할 이전 `JobRecord`가 없다. → **닫힘: 같은 문서 §3-4.**
4. **`HINT_EXTRACT`를 얼마나 기다리는가.** 이 호출에는 `AnalysisScope`가 없어 실행 상한을 어떻게 받을지 #210 Search PR에서 정하기로 했다. 그 값을 보고 case 대기 시간(`decisions/timeout-fallback.md`)과 기다리다 멈췄을 때 빈 단서로 진행할지를 정한다. → **닫힘: 같은 문서 §3-5(90초, 빈 단서로 진행 — 동작 구현은 8-9).**
5. **선행 작업.** 빈 case 생성과 업로드마다 `manifest_summary` 갱신(고도화 8-12, #247 H-2 · H-5), search의 텍스트 structured public 함수(#210 Search 작업), Worker 결과 반영 경로 · handler 등록(#245 D-5 · D-7). → **8-12 ✅ · #277 ✅ · case 반영 진입 함수 ✅ · Worker handler는 Runtime #297.**

## 12. 입력형 판본 초안 `case-command/v1` (2026-10-13)

> **상태: 초안 — web(신유민) Consumer 확인 대기.** 열림 조건(§12-1)이 갖춰지기 전에는 case가 아래 kind를 받지 않는다(지금처럼 `invalid_payload`). 범위는 규칙이 이미 정해진 셋(번호판 · 발생시각 · `[다른 상황]`)이고, 나머지 입력형 action은 §12-5에 이유와 함께 남긴다. 근거 #235(E-1 · E-2 · E-3 결정) · `contract-correction-record.md` · `core-user-flow.md` §12 · §13 · §15 · §20.

### 12-1. 열림 조건

web이 입력형 command를 여는 조건(#235 신유민 2026-10-12)과 같다. case 구현도 2 · 3 뒤에 한다.

1. 이 판본 합의(web 확인).
2. **`correction-record/v1.2`** — `previous_value`에 `null`(값이 없던 상태) 허용(#235 E-1 · E-2). 계약 반영(PM)과 evidence 검사(`evidence/corrections.py`) 반영.
3. **evidence 기록 전 검사 공개 함수**(#235 E-3) — 값 형식 + supersede chain 연속성. case가 기록 전에 부른다.

그 전에 열면 값이 없던 상태의 첫 입력이 기록된 뒤 evidence 조립에서 거부되고, 기록은 되돌리지 않으므로(`contract-correction-record.md` §8-9) 그 case는 이후 CaseView를 만들 수 없다(#235 §1).

### 12-2. 공통 규칙

- **web은 새 값만 보낸다.** CorrectionRecord의 `kind` · `target_field` · `previous_value` · `supersedes_ref`는 case가 채운다. `previous_value`는 현재 선택 context의 지금 값(= 사용자가 본 CaseView 값)이고, 값이 없으면 `null`이다(v1.2). web이 이전 값을 보내지 않으므로 chain이 끊기지 않는다.
- **허용 상태:** 선택된 후보가 있고 `stage`가 `EVIDENCE_REVIEW` · `READY`일 때(`correction.apply_correction()`의 가드 그대로). 상황 응답 대기 중(evidence 부분 투영, `record_id=null`)에도 받는다 — #235 E-2가 이 경로를 위해 `null` 이전 값을 연다.
- **값이 지금 값과 같으면 `not_allowed`.** 기록하지 않는다(`contract-correction-record.md` §8-7 — 「이미 선택된 후보 재선택」과 같은 무변경 거부).
- **성공하면** CorrectionRecord 1건 · `case_rev` +1. `READY`였으면 `EVIDENCE_REVIEW`로 내리고 §5 「성공 뒤 `READY` 재확인」을 그대로 한다(§5 「`READY`에서 다시 조립되는 변경」).
- **Job을 발주하지 않는다.** 값 정정은 evidence 재조립만 부른다(부분 재실행 정책 표). 시각 정정으로 사후 각인 값이 바뀌면 신고용 영상 입력도 바뀌는데, 그 재발주는 #351 [R-1] 자동 발주가 맡는다(`decisions/report-video-export.md`, 배선 보류).
- **값을 판정하지 않는다**(§7-3). 번호판이 맞는지 · 시각이 그럴듯한지는 보지 않는다. 형식은 evidence 검사(E-3)에 맡기고 case가 target별 형식 규칙을 복제하지 않는다(#235 E-3).

### 12-3. kind별

| `kind` | `payload` | CorrectionRecord | 성공하면 |
| --- | --- | --- | --- |
| `MANUAL_PLATE_INPUT` | `{ "value": "string" }` | `PLATE_MANUAL_EDIT` · `vehicle_number` | 번호판 값이 입력값이 되고 `plate_display.info_state=INFO_USER_CONFIRMED`. `readout.plate_read_failed`는 붙지 않는다(#235 ①, #321) |
| `EDIT_EVENT_TIME` | `{ "value": "string — offset-aware RFC3339" }` | `EVENT_TIME_MANUAL` · `occurred_at` | 최종 발생시각의 USER_INPUT 근거가 된다(`contract-time-resolution.md` §5) |
| `RECORD_SITUATION_RESPONSE` | `{ "value": "CORRECTED", "visual_event_type": "SIGNAL \| CENTER_LINE_CROSSING \| SOLID_LINE_LANE_CHANGE \| MOTORCYCLE_HELMET_NON_USE" }` | `SITUATION_CHANGE` · `event.visual_event_type` | `situation_response=CORRECTED`와 정정 기록을 **한 command**로 남기고 `case_rev`는 +1이다. evidence는 `CORRECTED`에 `SITUATION_CHANGE` head가 정확히 1건 있어야 조립한다(`evidence/assembly.py`) |

- **화면 입구와 kind.** 번호판 `[수정]` · `[직접 입력]`(Flow §12)과 notice action `MANUAL_PLATE_INPUT`은 모두 `MANUAL_PLATE_INPUT`으로, 발생시각 수정(Flow §20)과 notice action `EDIT_EVENT_TIME`은 모두 `EDIT_EVENT_TIME`으로 보낸다. notice에 붙은 입력형 action은 `RUN_NOTICE_ACTION`으로 보내지 않는다 — `RUN_NOTICE_ACTION`은 발주형 4종 그대로다.
- **`visual_event_type`은 `CORRECTED`일 때만 필수다.** `CONFIRMED` · `USER_UNSURE`에 있으면 `invalid_payload`. 지금 값과 같은 유형이면 `not_allowed` — 그것은 `[맞아요]`다.
- **`[다른 상황]` 선택지.** `VisualEventType` 4종에서 지금 값을 뺀 것이다. 사용자에게 법적 유형을 판정시키지 않으므로(Flow §15) 화면 문구는 상황 설명으로 쓴다 — 문구는 web.
- **notice action 싣기.** `evidence.plate_abstained`는 지금 `MANUAL_PLATE_INPUT`을 비워 둔다(CaseView 계약 B§7 — 실행 경로가 없는 action은 싣지 않는다). 이 판본이 열릴 때 함께 싣는다.

### 12-4. `case.command.invalid_value`

evidence 기록 전 검사(E-3)가 거부하면 `invalid_value`이고 아무것도 기록하지 않는다(§6 원자성). 검사 순서는 `not_allowed` 다음, 기록 직전이다. `message_key`는 `command.invalid_value`(문구는 §9 미결과 함께 web이 정한다). chain 연속성 위반은 case가 `previous_value`를 채우므로 정상 경로에서는 생기지 않는다 — 생기면 배선 오류다.

### 12-5. 이 판본에 넣지 않는 입력형 action

| action · 화면 | 넣지 않는 이유 |
| --- | --- |
| `REVIEW_TIME`(시각 후보 확인) | Flow §13 「어느 기록이 맞는지 사용자에게 고르게 하는 별도 단계를 두지 않는다」와 어긋난다. CaseView 계약 B§7 행도 TimeResolution §9-2 미결에 걸려 있다 — product · evidence와 정한다 |
| `EDIT_HINT`(결과 없음 화면 「설명 고치기」) | 원문을 다시 구조화(`HINT_EXTRACT`)할지, hints patch(`TIME_HINT_EDIT`, `correction.edit_time_hint()`)로 받을지, 재탐색 발주를 같이 할지 정해야 한다 — B§7 행은 「새 Job 없음, 다음 `RETRY_SEARCH`의 입력」인데 분석 시작은 이제 원문을 받는다(§11) |
| 위치 단서 수정(Flow §14 `[위치 단서 수정]`) | CorrectionRecord `kind` 9종에 위치용이 없다 — kind 추가는 `contract-correction-record.md` 변경이다 |
| 번호판 `[맞아요]`(Flow §12) | 값을 바꾸지 않는 확인이라 CorrectionRecord로 남길 수 없다(§8-7). 「사용자 확인됨」을 어디에 기록할지 정해야 한다 |
| 신고 유형 · 위반 내용 정정(`REPORT_TYPE_CHANGE` · `event.violation_expression`) | Flow에 화면 입구가 없다 |

### 12-6. 예시

```json
// 요청 — 번호판을 읽지 못한 상태에서 직접 입력(previous_value는 case가 null로 채운다)
{ "case_id": "case_p001", "expected_case_rev": 4, "kind": "MANUAL_PLATE_INPUT",
  "payload": { "value": "12가 3456" } }

// 요청 — [다른 상황]에서 중앙선 침범을 고름
{ "case_id": "case_h001", "expected_case_rev": 3, "kind": "RECORD_SITUATION_RESPONSE",
  "payload": { "value": "CORRECTED", "visual_event_type": "CENTER_LINE_CROSSING" } }

// 응답 — 형식이 맞지 않는 시각(오프셋 없음)
{ "ok": false,
  "error": { "code": "case.command.invalid_value", "message_key": "command.invalid_value" },
  "case_view": { "case_id": "case_h001", "case_rev": 3, "...": "..." } }
```

### 12-7. 남은 것

- 열림 조건 2 · 3(§12-1) — #235 후속(PM · evidence).
- CaseView 계약 B§7 `notices[].actions[]` 매핑의 `EDIT_EVENT_TIME` · `MANUAL_PLATE_INPUT` 행을 이 kind로 가리키게 고치는 일 — 이 판본 합의 뒤.
- 구현 때 맞출 것: `CORRECTED`는 상황 응답 기록과 정정 기록이 각각 `case_rev`를 올리지 않게 한 번만 올린다(지금 `record_situation_response()` · `apply_correction()`이 각자 올린다).
