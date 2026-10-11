# Final Data Contract — JobRecord (Job Intent) + CaseView v1

**Status:** `Final — Accepted`

**Accepted:** 최초 수락일 확인 대기 — 동일 계약 회차라는 이유로 추정한 2026-09-04 표기를 철회한다. CALL-1·5의 2026-09-06 답변 범위는 아래에 별도로 유지한다.

**수락 근거:** §11 Consumer Review 반영 요약 — 신유민(web) 「수정요청 → 반영 완료」 · 김대원(eval) 「승인」 · 김준영 「최종 승인」. 본문에 리뷰 종료 기록이 있다. 정확한 최초 수락일·필드별 서명 범위는 확인 대기다. 과거에는 PM이 헤더를 채웠다(`adr/adr-consistency-2026-09.md` C1-13). 유소연 이견 시 되돌린다

**Architecture Contract:** v4 §5-1 ⑪ `CaseView` · ⑫ `JobRecord`

**Contract Version:** `job-record/v1` · `case-view/v1.8`

**Related ADR:** `adr/adr-job-record-case-view.md` · `adr/adr-consistency-2026-09.md` §6 R-1·R-2 · `adr/adr-data-contract-call-closure-2026-09-07.md` §4.1·§4.2·§4.3·§4.9 (v1.2 근거)

> **`case-view/v1.8` 변경 (2026-10-07, 이슈 [#239](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/239), 유소연 결정 · 신유민(web) 확인 · 김준영(evidence) 확인).** `evidence.record_id`가 `string` → `string | null`이 된다. Fine `UNCERTAIN` + 상황 응답 전(`AWAIT_SITUATION_RESPONSE`)에는 EvidenceRecord가 없어도 이미 확보한 상황 독립 값을 기존 `evidence` 객체에 **부분 투영**하고, 그때 `record_id = null`이다. 규칙은 §10 불변조건 15가 소유한다. 새 필드 · 새 enum 값은 없다. 응답 대기 신호 `case.situation_response_pending`은 원래 발동 조건(`evidence` non-null + `NOT_ASKED` + `package == null`)으로 붙는다.
>
> **`case-view/v1.7` 변경 (2026-10-06, 이슈 [#274](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/274), 유소연 결정 · 신유민(web) 모양 확인 · 김준영(evidence) 확인).** ① `package.report`(`{title, description}`)를 신설한다 — 최종 신고문을 `ReportPackage.report`(`contract-requirement-report-package.md` §8.3)에서 그대로 옮긴다. case는 문장을 만들거나 고치지 않고, 내부 provenance인 `report.template_ref`는 내리지 않는다. `package`가 있으면 둘 다 non-null `string`이고 `description`은 줄바꿈(`\n`)이 들어간 평문이다(마크업 없음). 신고문 수정은 입력형 command 판본에서 따로 다룬다. ② 최상위 `description`(`string|null`)을 신설한다 — 사용자가 분석 시작 때 적은 설명 원문이다(case-command Draft §11 case 결정, 이슈 [#259](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/259) 신유민 확인). 분석 시작 전에는 `null`, 빈 설명이면 `""`. `package.report.description`(최종 신고문)과 이름만 같고 다른 값이다. 분석 시작 command가 아직 없어 지금 Producer는 항상 `null`을 낸다. ③ JobRecord A§7 `kind`에 `HINT_EXTRACT`(자연어 단서 구조화 발주), A§12 `label_key`에 `job.hint_extract`를 등재한다(열린 enum 등재라 `job-record/v1` 유지). #274 본문의 「#239 · #184와 같은 판본」 계획은 두 이슈가 다른 모듈 답변 대기라 이 판본에서 분리했다.

> **표기 정합 (2026-10-05, [#245](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/245) C-3 · [#248](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/248) Q-1 · [#265](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265) §9, 유소연) — 버전 유지 `case-view/v1.6`, 구현 동작 변경 없음.** ① **중단된 job은 실제 실행 상태와 상관없이 `progress[].state=PARTIAL`이다** — 마지막 attempt가 `STALE`(매핑상 `FAILED`)이어도 실패로 보이지 않는다. 규칙은 B절 §7 `progress[].state` 행. ② B절 §5 schema에 `contract`(`"CaseView"`) · `contract_version`을 등재한다 — 구현(`view.py`)은 이미 싣고 있었고, 다른 계약(AnalysisScope 등)도 schema에 두는 관례를 따른다.

> **표기 정합 (2026-10-04, [#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247) H-4 · [#245](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/245) C-3, 유소연 답변 · 김준영 결정) — 버전 유지 `case-view/v1.6`, 필드 · schema · enum 변경 없음.** `running_jobs[]`는 Runtime에서 실제 `RUNNING`인 모든 실행의 목록이 아니라 **case가 아직 결과를 기다리는 job 목록**이다. B절 §10 불변조건 5의 「`running_jobs`가 비어 있으면 진행 중인 작업 없음」을 이 의미로 바로잡는다.

> **명확화 (2026-09-29, #168 클립 분할 후속 결정 · #170 F, 유소연 결정 · 서어진 답변) — 버전 유지 `case-view/v1.6`.** v1.5 ③의 「최근 `CANDIDATE_SEARCH` Run」은 **탐색 intent 하나 = Run 하나**를 전제로 쓴 표현이다. 인라인 상한 안의 일반 영상은 지금처럼 클립 1개 = Run 1개이므로 그 규칙이 그대로 성립한다. 상한을 넘는 긴 영상을 클립으로 나누면 **하나의 탐색 intent가 여러 클립 Run**을 가지며, 그때 투영·자동 선택의 단위는 Run이 아니라 **그 intent의 성공한 클립 Run 묶음**이다. 상세는 §6 `candidates[].rank` 행과 §7 `RESUME_SEARCH` 행. 스키마·serialization은 바뀌지 않고 단일 Run 동작도 바뀌지 않으며, 클립 분할은 아직 구현되지 않았다(real E2E는 클립 1개 경로, #200). 묶음에서 `rank` 값을 어떻게 채울지는 클립 분할을 도입할 때 정하므로(§7 `미결 유지`), 그때 필드 의미가 바뀌면 버전을 올린다.

> **`case-view/v1.6` 변경 (2026-09-28, 이슈 #47, 유소연 결정 · 신유민·정철원 합의 반영).**
> ① `evidence.plate_preview_ref`(`FrameRef`|null)를 신설한다 — 현재 번호판 값의 근거 `PlateReadout`의 `best_frame.frame_ref`를 그대로 통과시킨다(`contract-plate-overlay-readout.md` §9 `case` 행 ①). `core-user-flow.md` §12의 `[번호판 이미지 보기]`·`[확대]`가 보여 줄 프레임이다. `crop_ref`는 내리지 않는다. ② `evidence.preview_ref`의 정의 행을 추가하고 타입을 `string|null`에서 `FrameRef|null`로 명시한다(`candidates[].thumb_ref`와 같은 값이라 같은 타입) — 사건 대표 썸네일이며 번호판 프레임이 아니다(#47 신유민 정정). 값은 바뀌지 않는다. ③ `JobRecord.kind`에 `PLATE_IMAGE_EXPORT`(`label_key` `job.plate_image_export`)를 등재한다. ④ `notices[].actions[]`에 `GENERATE_PLATE_IMAGE`를 추가한다(7종 → 8종). ⑤ 번호판 이미지 export 실패를 `recording.plate_image_export_failed` notice로 매핑한다. 출력 제한 전달 모양은 §13 미결로 남긴다.

> **`case-view/v1.5` 변경 (2026-09-28, 이슈 #122 · #168, 유소연 결정 · 신유민 확인).**
> ① `candidates[].rank`(int|null)를 추가한다 — search `CandidateEvent.rank`(Run 안의 순위, 1부터)를 그대로 옮기며 case가 다시 매기지 않는다. ② `candidates[]`는 `rank` 오름차순으로 내린다(배열 순서도 보장). ③ 가장 유력한 후보는 case가 **최근 `CANDIDATE_SEARCH` Run의 `rank=1`**(stale 제외)을 자동 선택하고 그 결과를 `candidates[].selected=true`로 표현한다 — 최신 후보가 아니면 임의로 고르지 않는다(core-user-flow §8). web은 진행 중 후보를 `selected`로만 판단하고 `rank`는 「다른 후보 보기」의 순서·번호 표시에만 쓴다. `ranking_score`는 calibrated confidence가 아니라 내리지 않는다. ④ `candidates[].marker_ms`(int|null)를 추가한다(이슈 #184) — search `CandidateEvent.span.representative_ms`(후보 timeline revision 기준 상대 ms)를 그대로 옮기는 후보 비교 타임라인 마커 위치다. stale 후보는 `null`(rebase 후 기존 원본 배치 유지 보장을 recording에 확인하기 전까지), 좌표를 모르면 `null`. 시간축 전체 길이 키는 recording 정의를 받은 뒤 추가한다(#184).
>
> **`case-view/v1.4` 변경 (2026-09-14, 이슈 #39 Required-3 후속 · PR 리뷰 코멘트 Q-3, 유소연·신유민 합의).**
> ① `candidates[].at_provenance`의 값 공간을 두 갈래로 정의한다 — **evidence 조립 이후**(`occurred_at` 존재)는 `occurred_at.source.kind`(`TimeResolution.resolved.source.kind`의 snapshot) pass-through이며 값 공간은 evidence가 소유한 열린 namespaced string이다(case가 별도로 닫힌 목록을 등재하지 않는다). **evidence 조립 이전**(예: `CANDIDATE_REVIEW` 단계, `at=null`)은 case가 소유하는 별도의 작은 enum이며 현재 `recording.timeline_relative_only` 1개만 등재한다. §8 예시의 `TIMELINE_ANCHOR+OFFSET`은 fixture 전수 조사 결과 실사용 0건으로 확인돼 폐기하고 실제 값으로 교체한다(§7·§8).
> ② `candidates[].at_provenance_label_key`(string|null, 신규)를 추가한다 — `stale_revision_label_key`와 같은 관례로, raw `at_provenance`가 authoritative이고 `at_provenance_label_key`는 case가 그 값을 보고 골라주는 순수 표시용 파생값이다. web은 raw 문자열을 직접 해석하지 않고 이 키로만 문구를 고른다(§10-12와 같은 원칙). 필드는 항상 존재하고(Y) 값만 `null`일 수 있다 — 매핑이 안 되는 raw 값은 `null`로 내려보내며 "미등록 값"과 "값 자체가 case에 알려지지 않음"을 별도 케이스로 나누지 않는다(§10-14).
> ③ `at_provenance_label_key` 매핑표를 신설한다(§7) — web이 처음 제안한 「post-evidence 12건은 `occurred_at.source.label_key`(=`event_time_display.source_label_key`) pass-through」 가설을 fixture 16개 스냅샷 전수 대조로 검증한 결과 **성립하지 않아 기각**했다(`scenario_correction_rerun_001` rev0→rev1에서 `at_provenance`는 `recording.filename_time`으로 불변인데 `event_time_display.source_label_key`만 `time.source.filename`→`time.source.user_correction`으로 바뀌는 사례가 결정적 반증 — 이슈 #39 Required-3과 같은 종류의 독립성 문제라, pass-through를 채택하면 그 버그의 변종이 `_label_key` 레이어에서 재발할 위험이 있었다). 대신 관측된 raw 값 3종(`recording.filename_time` 10건 · `readout.overlay_ocr` 2건 · `recording.timeline_relative_only` 2건) 각각에 대해 case 소유의 독립 매핑을 신설한다. 미등록 값은 `label_key=null`로 web이 fallback 처리한다.
> ④ `at=null`(pre-evidence) candidate의 표시 우선순위를 확인한다 — 값이 없는 상태(「시각 미확정」)가 출처 문구보다 먼저 보여야 한다는 web 제안이 case 원칙(값 없음이 `INFO_UNKNOWN`으로 먼저 표시되는 `report_field_states` 패턴)과 충돌이 없음을 확인했다. 필드 순서 자체를 스키마가 강제하지는 않는다(web 렌더링 재량).
> fixture는 `data/mock/case/` 7개 파일의 candidates 14곳(post-evidence 12 · pre-evidence 2)에만 영향이 있고 다른 모듈 fixture 재검수가 필요 없어 별도 Mock Pack 버전 없이 scoped commit으로 반영한다(선례: 이슈 #47/#48 `report_field_states`). **fixture·case 코드(domain/view) 반영은 이 커밋의 범위 밖이며 후속 커밋에서 진행한다.**
>
> **`case-view/v1.3` 변경 (2026-09-10, 이슈 #31/#33 반영 · case 통합 초안, 신유민·김준영 PR 리뷰 확인 대상).**
> ① `candidates[].situation_confirmation` 값 공간을 `NOT_ASKED | CONFIRMED | REJECTED | UNKNOWN`에서 **`NOT_ASKED | CONFIRMED | CORRECTED | USER_UNSURE`로 정정**한다 — `EvidenceRecord.situation_response`(`evidence-record/v1.3`) 값 공간과 맞춘다. `REJECTED`/`UNKNOWN`은 실제로 쓰인 적 없는 placeholder였다(§7).
> ② `candidates[].situation_confirmation`의 파생 출처를 확정한다 — `EvidenceRecord.situation_response.value`가 있으면 그대로 projection(`CONFIRMED`/`CORRECTED`/`USER_UNSURE`), 없으면 `NOT_ASKED`. `CorrectionRecord`가 Draft라 이 필드가 대신한다던 기존 문구(A절 참고 각주)는 철회한다 — `CorrectionRecord`는 v1.1로 Final이 됐고 이제 두 계약(`EvidenceRecord.situation_response` + `CorrectionRecord{kind=SITUATION_CHANGE}`)이 각자의 책임으로 함께 존재한다(§7).
> ③ `progress[].state=CANCELLED`는 새 값으로 만들지 않고 **기존 `PARTIAL`로 흡수**한다 — `JobExecution.status=CANCELLED`(`job-execution/v1.1`)는 부분 결과를 남길 수 있어도 완결이 아니므로 이미 있는 `PARTIAL` 의미와 같다(§7, `CONTRACT_CONFLICTS.md` 불명확 항목 9 종결). `JobExecution→CaseView` 상태 projection 표에 `CANCELLED→PARTIAL`을 추가한다(§13).
> ④ `evidence.report_type_display`에 `info_state`/`source_label_key`를 추가한다 — `docs/modules/evidence/decisions/safety-report-policy-v1.md`(SafetyReportType registry, ACCEPTED)가 나와 `CONTRACT_CONFLICTS.md` 불명확 항목 4의 잔여 부분이 해소됐다. 파생은 `case_type_display`/`violation_display`와 같은 (1) 규칙을 따른다(§7).
> ⑤ `package.report_field_states`를 신설한다 — `report_fields`(평면 map)와 나란히 **필드별 `{info_state, source_label_key}`**를 제공한다(신유민 PR #28 요청, `CONTRACT_CONFLICTS.md` 불명확 항목 10 종결). `unconfirmed_fields`는 이제 `report_field_states[field].info_state ∈ {INFO_AI_ESTIMATED, INFO_NEEDS_REVIEW, INFO_UNKNOWN}`인 필드명의 파생 목록으로 **정의를 명확히 한다**. **주의 — 파생 로직 자체는 새로 만드는 게 아니지만(§10 불변조건 6과 같은 원칙), `safety_report_type`/`violation_expression`은 이번 v1.3 이전에는 `report_field_states`(및 그 기반인 `report_type_display.info_state`)가 아예 없어 `unconfirmed_fields` 계산에 들어가지 못했다 — 그래서 기존 fixture 중 이 두 필드가 `INFO_AI_ESTIMATED`인 경우 `unconfirmed_fields`에 새로 추가된다(예: `scenario_happy_001`). 이는 규칙 정의를 명확히 한 자연스러운 결과이며 별도 정책 변경이 아니다.** §6·§7·§10에 반영.
> ⑥ `notices[].actions[]` 값 공간을 5종에서 **7종으로 확장**한다 — `EDIT_HINT`·`RETRY_SEARCH`를 추가한다(이슈 #31 W-1, 신유민). `scenario_empty_001`의 `search.no_candidates` notice가 이 두 값을 이미 쓰고 있었는데 값 공간에 등록돼 있지 않아, "미등록 값은 버튼을 렌더하지 않는다"는 기존 규칙대로면 후보 0건 화면에 탈출 버튼이 하나도 뜨지 않는 상태였다 — 단서 수정·재검색이 그 화면의 유일한 경로라 이 gap은 실사용을 막는 결함이었다. §7에 반영.
> ⑦ `progress[]`의 step 집합 규칙을 확정한다(이슈 #31 W-7, 신유민) — §7에 신설 규칙 추가, `scenario_relative_rebase_001`(8단계 전부 PENDING 표시 → 3단계로 축소) 수정. 같은 이슈의 W-5(`scenario_correction_rerun_001`에 `readout.overlay_not_present` notice 누락)·W-6(`scenario_plate_reread_001` rev4가 다음 행동을 가리키는 필드 없이 막다른 화면이던 것)도 함께 수정한다 — `readout.overlay_not_present` notice를 rev2·rev3에 추가하고, `plate_reread_001` rev3·rev4의 `progress[]`에 `package_assembly: PENDING`을 추가하고 rev4에 `case.report_video_not_generated`(INFO, `actions:["GENERATE_REPORT_VIDEO"]`) notice를 추가했다.

> **`CaseView`는 v4에서 부록이 아니라 Core Contract ⑪이다**(v4 §5 머리말 · §4-모듈5 ⑥). 아래 절 제목의 「부록-A / 부록-B」는 ADR 작성 당시 표기이며, 계약의 위상은 Core Contract다.

> **재판독 발주 규칙 등재 (2026-09-08 반영 · 유소연 2026-09-07 결정).** A절 §7에 「`PLATE_REREAD` Need → `kind=PLATE_READ` + `force_rerun=true`(무조건) · 새 `job_id` · 기존 `ReadoutRun` 갱신 없음」을 등재했다. 값 목록·스키마는 바뀌지 않아 `job-record/v1`을 유지한다. 근거 `adr/adr-data-contract-call-closure-2026-09-08.md` §4.1.

> **Fine 발주·Report Video export `kind` 등재 및 `purge_case` 경계 확정 (2026-09-09 · Decider 유소연, Mock Pack 심층 검토 §12 후속).** A절 §7에 `FINE_VERIFY`(Fine/시각 검증 발주)와 `REPORT_VIDEO_EXPORT`(신고용 파생영상 생성 발주)를 등재한다. `purge_case()`는 `contract-analysis-source-derived.md` §8이 이미 `purge_case(case_id) -> DeletionReport` 직접 호출로 정의했고 `DeletionReport`에 `job_id`가 없으므로, **`JobRecord`/`JobExecution` 경계 밖의 관리 동작으로 유지**하고 별도 `kind`를 만들지 않는다. `label_key`는 §12에 `job.fine_verify`·`job.report_video_export`를 추가한다. 값 목록·스키마는 바뀌지 않아 `job-record/v1`을 유지한다(열린 enum 등재).

> **`case-view/v1.2` 변경 (2026-09-07)** — 유소연(`case` Owner) 결정, 김준영(`evidence`)·신유민(`web`) 확인. 근거와 기각안은 `adr/adr-data-contract-call-closure-2026-09-07.md` §4.1(B01)·§4.2(B02)·§4.9(`thumb_ref`)에 있다. A절 `JobRecord`는 `job-record/v1` 그대로이며 §7의 `kind` 값 등재와 §10 불변조건 5만 늘었다(열린 enum·불변조건 추가라 버전 유지).
> ① `info_state` 파생 입력 세 개 확정(`needs_review` 출처 · `occurred_at` 변환 · 위치 대표값) ② `location_display`에 `coord`·`search_keyword` 별도 필드 ③ `requirements`를 `requirements_evidence` / `requirements_package` 두 객체로 분리, report 선택 3단계 ④ web 소비 규칙(`info_state`만 본다) ⑤ `candidates[].thumb_ref`는 `FrameRef`. **B01·B02 Pending은 종결됐다.**

> **`case-view/v1.1` 변경 (2026-09-06)** — 회신 반영 당시 B절만 바뀌었다. ① `stage=READY` 정의 확정 ② `requirements.readiness`를 `RequirementReport.overall` 값 공간으로 축소 ③ `user_reviewed` 신규 ④ 세 값 display에 `info_state`·`source_label_key` 신규 ⑤ 당시 `requirements.scope`는 PM 제안/Owner 확인 대기로 정정했고 v1.2에서 두 객체 분리로 대체됐다.
> `progress[].state` · `notices[].severity` · `running_jobs[].label_key` · `package.*` 타입 · `evidence`의 `case_type_display`/`report_type_display`/`violation_display`/`preview_ref`는 기존 Closure 판본을 보존한 것이다. **네 evidence 필드는 삭제 의도가 없음을 Owner가 확인했다(2026-09-07, W02 잔여 종결)** — 유지한다.

## A. `JobRecord` (Job Intent)

### 1. 계약 목적

case가 발주한 작업(Job Intent) 1건을 append-only로 기록해, 부분 재실행과 캐시(입력 지문 일치 시 재사용)가 이 위에서 동작하게 하는 계약이다. 실행 중 상태(Job Execution)는 본 계약의 범위 밖이며 runtime이 소유하는 별도 계약으로 이관된다(ADR-부록A §6, §13).

### 2. Producer / Consumer

**Producer**: case (유소연) — Job Intent 부분만

**Consumer**: `common/runtime` — 실행(`JobExecution`)이 이 의도를 받는다 · `eval` — 발주/재실행 집계 · `web`(신유민) — `CaseView` 경유 간접 소비

**관련 Owner**: runtime/common — 주요 Owner 김준영, 구현 담당 정철원 (2026-09-04 백엔드 회의 확정)

### 3. 책임 경계

**Producer(case)가 보장하는 것**

- 작업 1건당 하나의 Intent 기록: job_id, case_id, case_rev, kind, input_fingerprint, force_rerun, 발주 시점
- 새 시도/재실행은 새 기록 추가(append-only), 기존 기록 in-place 수정 없음
- `scope_ref`가 존재하면 유효한 AnalysisScope.scope_id를 가리킴

**Consumer(web)가 기대할 수 있는 것**

- CaseView.running_jobs를 통한 간접 조회(job_id/kind/label_key/status)

**이 Contract가 보장하지 않는 것**

- 실행 상태(status/attempt/cost/produced/failure_kind) — 별도 `JobExecution` 계약 범위
- 재시도 성공 보장
- heartbeat/lease/retry/backoff/DB 구조 등 Runtime 내부 구현 세부

### 4. 조사에서 확인된 제약

| 제약 | 근거 |
| --- | --- |
| Job=추가만(append-only) | v1 R&R 표 |
| failure_kind는 모듈 접두어로 구분 | v1 p.20 |
| corrections.kind는 JobRecord.kind와 다른 값 공간 | v1 p.28 |
| Job Intent/Execution 책임 분리가 v4/Ops 문서와 정합 | ADR-부록A 결정1 |

### 5. 확정 Contract 스키마 (JSON) — Job Intent 부분

json

```json
{  "job_id": "string",  "case_id": "string",  "case_rev": "int",  "kind": "string",  "scope_ref": "string | null",  "input_fingerprint": "string",  "force_rerun": "boolean",  "requested_at": "ISO8601"}
```

> status/attempt/cost/produced/failure_kind는 별도 `JobExecution` 계약으로 이관한다. `JobExecution`은 runtime/common이 소유하며 주요 Owner는 김준영, 구현 담당은 정철원이다. 실행 상태 enum은 `QUEUED / RUNNING / SUCCEEDED / FAILED / STALE`로 고정한다. **(2026-10-02 · 표기 정합, 버전 유지)** `job-execution/v1.1`(2026-09-10)에서 `CANCELLED`가 추가돼 현재 6값이다 — 값 목록의 정본은 `contract-job-execution.md` §6이다.
> 

### 6. 필드 정의

| 필드 | 타입 | 필수 | 의미 | 근거/상태 |
| --- | --- | --- | --- | --- |
| job_id | string | Y | 고유 식별자, 재사용 없음 | 확인됨 |
| case_id / case_rev | string / int | Y | 소속 Case 및 발주 시점 리비전 | 확인됨 |
| kind | string(모듈 접두어 확장형) | Y | 작업 종류 | ADR 결정3, 절충안 유지 |
| scope_ref | string | null | N (신규) | 참조하는 AnalysisScope.scope_id | ADR 결정4, 신유민 요청 반영 |
| input_fingerprint | string | Y | 캐시 판단 지문 | 확인됨 |
| force_rerun | boolean | Y (신규) | true면 fingerprint 동일해도 재실행 | ADR 결정2, A안 확정 |
| requested_at | ISO8601 | Y | 발주 시점 | 확정 — 발주 시점 필드명을 `requested_at`으로 고정 |

### 7. Enum / State / Special Value

- `kind`: 확인된 값 `COARSE_SEARCH`, `PLATE_READ`, `OVERLAY_TIME_READ`(2026-09-07 등재, 유소연), **`FINE_VERIFY`**·**`REPORT_VIDEO_EXPORT`**(2026-09-09 등재, 유소연), **`PLATE_IMAGE_EXPORT`**(2026-09-28 등재, 유소연, 이슈 #47), **`HINT_EXTRACT`**(2026-10-06 등재, 유소연, 이슈 #259). 전체 목록은 모듈 접두어 규칙에 따라 계속 등재 (닫힌 enum 아님)
  - `FINE_VERIFY`는 search의 `AnalysisRun.operation=VISUAL_VERIFY` 실행을 발주한다. `COARSE_SEARCH`(↔`AnalysisRun.operation=CANDIDATE_SEARCH`)와 이미 문자열이 다른 선례를 따라, `case`가 쓰는 Coarse/Fine 업무 명칭을 그대로 쓴다(`operation` 값과 1:1 문자열 일치를 요구하지 않는다 — 그 요구는 §7의 `PLATE_READ`/`OVERLAY_TIME_READ`↔`ReadoutRun.operation`에만 명시돼 있다).
  - `REPORT_VIDEO_EXPORT`는 `DerivedAsset`(`derived_role=REPORT_VIDEO`) 생성을 발주한다(`contract-analysis-source-derived.md` §7.3·§7.5). export 실패는 그 계약 §9의 `REPORT_VIDEO_EXPORT_FAILED`(`JobExecution.failure_kind`, SCREAMING_SNAKE 열거값)를 **그대로 옮기지 않는다** — `case`가 B절 §7 「notices[].code 표기」 규칙에 따라 `recording.report_video_export_failed`로 매핑해 `CaseView.notices[].code`에 싣는다(2026-09-10 정정, 이슈 #26 A-⑤. `failure_kind`는 실행 상태를 나타내는 별도 값공간이라 표시용 `notices[].code`와 casing이 다를 수 있다).
  - `PLATE_IMAGE_EXPORT`는 `DerivedAsset`(`derived_role=PLATE_IMAGE`) 생성을 발주한다 — `REPORT_VIDEO_EXPORT`의 자매 kind다(이슈 #47). **발주 시점은 `REPORT_VIDEO_EXPORT`와 같은 최종 Package 조립 시점이며, 사용자 번호판 확인 여부로 막지 않는다**(#47 Q3). 생성 입력은 `PlateReadout.best_frame.frame_ref` + `best_frame.plate_bbox_xywh`(`contract-plate-overlay-readout.md` §9 `case` 행 ②)와 IncidentClip ref이며 `crop_ref`·`associated_region`은 넘기지 않는다. `PlateReadout`이 없으면 발주하지 않는다(입력 부재는 export 실패가 아니다). export 실패는 recording이 제안한 `PLATE_IMAGE_EXPORT_FAILED`(recording 계약 등재 대기)를 `REPORT_VIDEO_EXPORT`와 같은 규칙으로 `recording.plate_image_export_failed`에 매핑해 `notices[].code`에 싣는다. 30MB 같은 첨부 용량 수치는 case가 알지 않는다 — 제한 충족은 recording이 한 execution 안에서 시도하고(#47 Q5), 제한 값을 요청에 싣는 모양은 B절 §13 미결이다.
  - `HINT_EXTRACT`는 분석 시작 때 사용자가 적은 설명 원문을 구조화된 `hints`로 바꾸는 호출을 발주한다(case-command Draft §11 · #210). 실패해도 notice를 만들지 않고 빈 단서로 진행한다(같은 Draft의 case 결정). 발주 경로(`START_ANALYSIS`)는 Draft 미결이 닫힌 뒤 생긴다.
  - **`purge_case()`는 `JobRecord`를 통해 발주하지 않는다.** `contract-analysis-source-derived.md` §8이 `purge_case(case_id) -> DeletionReport`를 직접 호출로 정의하고 `DeletionReport`에 `job_id`가 없으므로, Job Intent/Execution 비동기 흐름 밖의 관리 동작으로 취급한다(2026-09-09, 유소연).
  - `PLATE_READ`와 `OVERLAY_TIME_READ`는 **항상 별도 `job_id`로 발주**한다. `ReadoutRun.operation`(`contract-readout-run.md` §6)과는 같은 이름의 값끼리 대응한다 — `PLATE_READ↔PLATE_READ`, `OVERLAY_TIME_READ↔OVERLAY_TIME_READ`. 한쪽에만 값을 추가하지 않는다.
  - `PLATE_REREAD`는 `EvidenceNeeds.kind`의 값이며 `JobRecord.kind` 값이 아니다(값 공간이 다르다 — §4 「corrections.kind는 JobRecord.kind와 다른 값 공간」과 같은 이유).
  - **재판독 발주 규칙 (2026-09-07 확정 · Decider 유소연 · 확인 신유민·김준영).** `EvidenceNeeds.kind=PLATE_REREAD` Need를 발주로 옮길 때 `case`는 **`kind=PLATE_READ`를 유지하고 `force_rerun=true`를 조건 없이 붙인다.** 별도 kind를 만들지 않는다. `PLATE_REREAD` Need는 사건 interval ref를 그대로 제공하므로 입력이 원판독과 같은 것이 기본값이고, fingerprint 구성에 case/kind가 포함된다고 가정할 수 없으므로 조건부 `force_rerun`은 재판독을 조용히 누락시킨다. 재판독은 **새 `job_id`**(새 `JobRecord`)로 발주하며 새 execution이 새 `ReadoutRun` 1건을 만든다 — **기존 `ReadoutRun`을 갱신하지 않는다.** 인프라 재시도(`STALE`)는 다른 층위다: 같은 `job_id` · 새 `execution_id` · `attempt` 증가(`contract-job-execution.md` §9-2). abstain 결과는 계속 `ReadoutRun.outcome=SUCCEEDED`이며(`contract-readout-run.md` §9-5) cache hit 회피는 `outcome`이 아니라 `force_rerun`으로 한다. 원판독/재판독 중 「현재 값」 선택은 B03 결정대로 `case`/`CaseView` projection 소관이다. §9의 `job_61` 예시가 이 형태다. 근거·기각안 `adr/adr-data-contract-call-closure-2026-09-08.md` §4.1.
- `force_rerun`: 기본값 `false`. **동일 `(case_id, kind, input_fingerprint)`**이고 `force_rerun=false`인 요청에 기존 **SUCCEEDED** 결과가 있으면 재사용한다. `FAILED`/`STALE`은 cache hit가 아니다. `force_rerun=true`이면 새 실행이다. 기존 `adr-job-record-case-view.md` A절 §7의 조건을 복원한 것이며 fingerprint에 case/kind가 포함됐다고 추정하지 않는다.

### 8. 정상 예시

json

```json
{  "job_id": "job_51",  "case_id": "case_3",  "case_rev": 4,  "kind": "COARSE_SEARCH",  "scope_ref": "scope_2026_0912_001",  "input_fingerprint": "sha1:...",  "force_rerun": false,  "requested_at": "2026-09-01T18:00:00Z"}
```

### 9. 실패 / 부분성공 / UNKNOWN 예시

Job Intent 자체는 성공/실패 상태를 갖지 않는다(§실행 결과는 Job Execution 계약 소관). 아래는 강제 재실행 케이스:

json

```json
{  "job_id": "job_61",  "case_id": "case_3",  "case_rev": 5,  "kind": "PLATE_READ",  "scope_ref": null,  "input_fingerprint": "sha1:same-as-before",  "force_rerun": true,  "requested_at": "2026-09-02T09:10:00Z"}
```

### 10. 불변조건

1. 동일 job_id는 재사용되지 않는다
2. 캐시 재사용 조건은 A절 §7을 따른다(동일 case_id·kind·input_fingerprint의 성공 결과에 한정).
3. `scope_ref`가 존재하면 유효한 scope_id를 참조한다
4. 실행 상태 필드(status 등)는 본 계약에 포함되지 않는다 — Job Execution 계약 참고
5. **readout 계열 Job 1 execution : `ReadoutRun` 1건 (1:1)** — `case`의 orchestration 불변조건이다(유소연 · 신유민, 2026-09-07). `readout`은 `JobExecution`을 모르므로 readout이 보장하는 것은 「public 함수 호출 1회 = `ReadoutRun` 1건」이고, 1:1은 worker 구현 규칙 「1 execution 안에서 readout public 함수를 정확히 1회 호출한다」(`contract-job-execution.md` §9-9)로 성립한다. `run_id`는 `job_id`처럼 재사용되지 않는 1회성 식별자이나 `execution_id`와 **같은 identity가 아니다**. 근거 `adr/adr-data-contract-call-closure-2026-09-07.md` §4.3    **예외(2026-09-10, 유소연·신유민, 이슈 #26 B-readout-3):** `status=STALE`인 실행은 run이 없을 수 있다 — worker가 readout 호출을 완료하지 못하고 소멸한 경우. `scenario_infra_failure_001`의 attempt 1(STALE, `produced=[]`)이 이 예외의 fixture 근거다.
6. **execution 대표 상태 — 「대표 execution = `attempt` 최댓값」**(2026-09-10, 유소연·신유민, 이슈 #26 B-web-7). 한 `job_id`에 `attempt`가 여럿이면 `CaseView.progress[]`·`running_jobs[]`는 **가장 큰 `attempt`의 `JobExecution.status`**를 그 job의 대표 상태로 투영한다. 재시도 중 이전 attempt가 `STALE`/`FAILED`였다는 사실 자체는 대표 상태에 노출하지 않는다 — attempt 1이 STALE로 판정된 순간에도 `progress[]`는 곧바로 `FAILED`로 깜빡이지 않고, attempt 2가 `QUEUED`/`RUNNING`인 동안 해당 job은 계속 진행 중으로 보인다. 모든 attempt가 소진된 뒤에야(재시도 없음, 마지막 attempt가 terminal 실패) 대표 상태가 `FAILED`로 전환된다. `scenario_infra_failure_001`의 두 스냅샷(`case_rev:1`=RUNNING, `case_rev:2`=최종 attempt 2 FAILED 이후)이 이미 이 규칙과 일치하며 이번에 fixture를 수정하지 않는다.
7. **job_id 대표 상태 — 「대표 job = 가장 나중에 발주된 job」**(2026-09-13, 유소연·신유민, PR 리뷰 코멘트 반영). `RESUME_SEARCH`/`RETRY_PLATE_READ`/`RETRY_SEARCH`처럼 재개·재시도가 전부 새 `job_id`로 발주되는 정책(§7) 때문에, 같은 `kind`의 `JobRecord`가 여럿인 상태는 예외가 아니라 정상 경로다. 이 경우 `CaseView.progress[]`·`running_jobs[]`는 **`requested_at`이 가장 늦은(= append-only `job_records[]` 배열에서 그 `kind`로 가장 나중에 기록된) job**의 대표 상태를 그 `kind`의 대표 상태로 투영한다. 이전 job의 terminal 상태(`FAILED`/`CANCELLED`/`PARTIAL` 등)는 대표 상태에 남기지 않는다 — 항목 6의 attempt 단위 규칙을 job_id 단위로 확장한 것이다. `notices[]`도 같은 원칙을 따른다 — 같은 step에 여러 job이 각자 notice를 발생시켰다면 가장 나중 job이 발생시킨 notice만 대표 목록에 남기고 이전 job의 notice는 제거한다. `scenario_infra_failure_001`의 `plate_read`(`job_x001_plate`→`job_x001_plate_reread`)와 `notices[]`의 `readout.overlay_presence_undetermined`→`readout.overlay_ocr_failed` 교체가 이 규칙의 fixture 근거다.
   **주의 — `case_rev`를 정렬 키로 쓰지 않는다.** `JobRecord.case_rev`는 발주 시점 case 리비전의 스냅샷일 뿐 issuance 순서를 보장하지 않는다 — 같은 stage 안에서 후속 candidate 재선택이나 단계 전이 없이 같은 `kind`를 연속 재시도하면 두 `JobRecord`가 같은 `case_rev`를 가질 수 있다. 지금 Mock Pack 7개 시나리오는 같은 `kind` 쌍마다 `case_rev`가 우연히 매번 달라(`scenario_infra_failure_001`: 1→3·1→4, `scenario_plate_reread_001`: 2→3) 이 경우를 노출하지 않았을 뿐, 계약이 이를 막아두지 않는다.

### 11. Consumer Review 반영 요약

| Consumer | 상태 | 반영 내용 |
| --- | --- | --- |
| 신유민(web) | 수정요청 → 반영 완료 | scope_ref 신규 추가(Q4), kind 표시 보완 요구는 부록-B에서 label_key/fallback으로 확정(Q3) |
| 김대원(eval) | 승인 | 반영 사항 없음 |
| 김준영(evidence/runtime/PM) | 최종 승인 | Job Intent/Execution 분리, force_rerun, JobExecution Owner/status/cache semantics 최종 확정 |

### 12. 후속 구현 범위

- `JobExecution` Producer/Owner: runtime/common, 주요 Owner 김준영, 구현 담당 정철원 — 2026-09-04 백엔드 회의에서 확정
- `JobExecution.status`: `QUEUED / RUNNING / SUCCEEDED / FAILED / STALE` (v1 당시. `job-execution/v1.1`에서 `CANCELLED` 추가 — 정본 `contract-job-execution.md` §6)
- heartbeat/lease/retry/backoff/DB 구조는 Runtime 구현 세부이며 본 Job Intent 계약의 closure를 막지 않는다.
- kind 표시용 `label_key`/fallback은 부록-B `CaseView` 계약에서 확정한다. 등재된 `label_key`: `job.plate_read` · `job.overlay_time_read`(2026-09-07 추가) · `job.fine_verify` · `job.report_video_export`(2026-09-09 추가) · `job.plate_image_export`(2026-09-28 추가, 이슈 #47) · `job.hint_extract`(2026-10-06 추가, 이슈 #259). `COARSE_SEARCH`는 아직 전용 `label_key`가 없어 `job.generic_processing` fallback을 그대로 쓴다(유소연 확인, 우선순위 낮음 — 필요해지면 `job.coarse_search`로 등재). 미등록 kind는 `job.generic_processing` fallback(B절 §12).

---

## B. `CaseView`

### 1. 계약 목적

web이 화면을 그리기 위해 읽는 유일한 통합 상태다. evidence/package는 이제 safe projection으로 제공되며, web은 요건을 재계산하지 않는다(v1 p.28).

### 2. Producer / Consumer

**Producer**: case (유소연)

**Consumer**: web(신유민), (+김대원, 영상 UI)

**관련 Owner**: evidence(김준영) — safe projection의 의미 경계 및 authoritative 값 소유

### 3. 책임 경계

**Producer(case)가 보장하는 것**

- web이 CaseView 하나만 보면 화면을 그릴 수 있음
- evidence/package는 원본 계약을 그대로 통과시키지 않고 case가 재구성한 값만 제공(ADR-부록B 결정1)
- stage는 5개 값으로 닫힌 enum

**Consumer(web)가 기대할 수 있는 것**

- 요건 충족 여부는 case/evidence가 이미 계산해서 제공
- evidence/package의 내부 구현 변경으로부터 격리된 안정적인 표시용 필드

**이 Contract가 보장하지 않는 것**

- web 또는 case가 Evidence/RequirementReport의 authoritative 판단을 재계산하는 것 — 금지
- raw confidence, 내부 provenance, 중간 추론값 등 Evidence 내부 구현 세부의 직접 노출
- heartbeat/lease/retry/backoff 등 Runtime 내부 실행 세부

### 4. 조사에서 확인된 제약

| 제약 | 근거 |
| --- | --- |
| web은 요건을 재계산하지 않는다 | v1 p.28 원문 |
| evidence/package는 safe projection이어야 함 | ADR-부록B 결정1, 김준영 확정 |
| checks[]는 RequirementReport 그대로 | 이전 회차 확정 |

### 5. Contract 스키마 (JSON)

> **B01·B02 종결 (2026-09-07).** `info_state` 파생 입력과 `requirements_*` 선택 규칙은 §7이 소유한다. 근거 `adr/adr-data-contract-call-closure-2026-09-07.md` §4.1·§4.2. 기존 유형/preview 네 필드는 유지로 확인됐다(같은 문서 §4.10).

json

```json
{  "contract": "CaseView",  "contract_version": "case-view/v1.8",  "case_id": "string",  "case_rev": "int",  "stage": "INTAKE | SEARCHING | CANDIDATE_REVIEW | EVIDENCE_REVIEW | READY",  "user_reviewed": "boolean",  "description": "string | null",  "manifest_summary": {    "file_count": "int",    "ok_file_count": "int",    "failed_file_count": "int",    "duration_sec": "number",    "range": "[string, string] | null"  },  "hints": { "time": "string|null", "vehicle": "string|null", "situation": "string|null", "location": "string|null" },  "progress": [ { "step": "string", "state": "PENDING | RUNNING | DONE | FAILED | PARTIAL" } ],  "candidates": [    { "candidate_id": "string", "rank": "int|null", "marker_ms": "int|null", "at": "string", "at_provenance": "string", "at_provenance_label_key": "string|null", "observed": "string", "thumb_ref": "FrameRef (fr_<opaque-id>) | null", "selected": "boolean", "timeline_revision": "int", "stale_revision": "boolean", "stale_revision_label_key": "string|null", "situation_confirmation": "NOT_ASKED | CONFIRMED | CORRECTED | USER_UNSURE" }  ],  "evidence": {    "record_id": "string | null",    "case_type_display": { "code": "string|null", "label": "string|null", "needs_review": "boolean", "info_state": "INFO_AI_ESTIMATED | INFO_SOURCE_VERIFIED | INFO_USER_CONFIRMED | INFO_NEEDS_REVIEW | INFO_UNKNOWN", "source_label_key": "string|null" },    "report_type_display": { "code": "string|null", "label": "string|null", "needs_review": "boolean", "info_state": "INFO_AI_ESTIMATED | INFO_SOURCE_VERIFIED | INFO_USER_CONFIRMED | INFO_NEEDS_REVIEW | INFO_UNKNOWN", "source_label_key": "string|null" },    "violation_display": { "code": "string|null", "label": "string|null", "needs_review": "boolean", "info_state": "INFO_AI_ESTIMATED | INFO_SOURCE_VERIFIED | INFO_USER_CONFIRMED | INFO_NEEDS_REVIEW | INFO_UNKNOWN", "source_label_key": "string|null" },    "plate_display": { "value": "string|null", "needs_review": "boolean", "info_state": "INFO_AI_ESTIMATED | INFO_SOURCE_VERIFIED | INFO_USER_CONFIRMED | INFO_NEEDS_REVIEW | INFO_UNKNOWN", "source_label_key": "string|null" },    "event_time_display": { "value": "ISO8601|null", "needs_review": "boolean", "info_state": "INFO_AI_ESTIMATED | INFO_SOURCE_VERIFIED | INFO_USER_CONFIRMED | INFO_NEEDS_REVIEW | INFO_UNKNOWN", "source_label_key": "string|null" },    "location_display": { "value": "string|null", "needs_review": "boolean", "info_state": "INFO_AI_ESTIMATED | INFO_SOURCE_VERIFIED | INFO_USER_CONFIRMED | INFO_NEEDS_REVIEW | INFO_UNKNOWN", "source_label_key": "string|null", "coord": "{ lat: number, lon: number } | null", "search_keyword": "string|null" },    "user_edited": "boolean",    "preview_ref": "FrameRef|null",    "plate_preview_ref": "FrameRef|null",    "review_needed": "boolean",    "reason_code": "string|null"  },  "requirements_evidence": { "readiness": "PASS | WARN | BLOCK | UNKNOWN", "checks": [] },  "requirements_package": { "readiness": "PASS | WARN | BLOCK | UNKNOWN", "checks": [] },  "package": {    "package_ref": "string|null",    "report_fields": "object<string, string|null>",    "report_field_states": "object<string, { info_state: INFO_AI_ESTIMATED|INFO_SOURCE_VERIFIED|INFO_USER_CONFIRMED|INFO_NEEDS_REVIEW|INFO_UNKNOWN, source_label_key: string|null }>",    "unconfirmed_fields": "string[]",    "artifact_ref": "string|null",    "capabilities": "string[]",    "warnings": "string[]",    "report": "{ title: string, description: string }"  },  "running_jobs": [ { "job_id": "string", "kind": "string", "label_key": "string", "status": "PENDING | RUNNING" } ],  "notices": [    { "code": "string", "severity": "INFO | WARN | ERROR", "blocking": "boolean", "message_key": "string", "actions": "string[]" }  ]}
```

> `requirements_evidence`·`requirements_package`·`package`·`evidence`는 각각 `null`일 수 있다(조건은 §7·§10). 위 evidence/package는 safe projection 경계를 따른다. case는 Evidence/ReportPackage의 authoritative 값을 재판정하거나 confidence를 자체 threshold로 재해석하지 않고, 확정된 값·검토 필요 여부·사유를 UI 표시 형태로만 변환한다. raw confidence, 내부 provenance, 중간 추론값은 기본 노출하지 않는다. `candidates[].thumb_ref`는 `FrameRef`이며 web은 recording을 직접 호출하지 않는다 — 실제 이미지는 case가 recording lookup을 거쳐 projection한다(`FrameRef` 필드 계약은 `contract-source-asset-media-stream.md` §5·§7, **이미지 전달 형태는 그 계약 §9-6 Pending**, §13).
> 

### 6. 필드 정의

| 필드 | 타입 | 필수 | 의미 | 상태 |
| --- | --- | --- | --- | --- |
| contract | string | Y | 항상 `"CaseView"` | **등재(2026-10-05)** — 구현은 이미 싣고 있었다 |
| contract_version | string | Y | 이 계약 버전 문자열(현재 `case-view/v1.8`) | **등재(2026-10-05)** — 같음 |
| stage | enum(5) | Y | Case 진행 단계. `READY`는 「`PACKAGE_READY` 파생 gate가 성립한 시점」 | **확정** (신유민 Q3 답변 · READY 정의는 유소연 2026-09-06) |
| user_reviewed | boolean | Y | 사용자가 최종 확인을 마쳤는지. v4 §3-6의 `USER_REVIEWED`를 내려보내는 통로이며 `stage`와 **별개 축**이다 | **확정** (유소연 2026-09-06) |
| description | string\|null | Y(키 항상 존재) | 사용자가 분석 시작 때 적은 설명 원문 그대로. 분석 시작 전 `null`, 빈 설명이면 `""`. 단서 구조화가 진행 중이거나 실패해 `hints`가 비어도 사용자가 자기 원문을 보게 하려는 값이다. `package.report.description`(최종 신고문)과 다른 값 | **신규(v1.7, #259)** |
| evidence.record_id | string \| null | Y(키) | 투영한 `EvidenceRecord.record_ref.ref`. 상황 응답 대기 부분 투영(§10 불변조건 15)이면 `null` — EvidenceRecord가 아직 없다는 뜻이다. web은 이 값으로 부분 결과를 구분할 수 있다 | **변경(v1.8, #239)** — v1.7까지 `string` |
| evidence.*_display.info_state | enum(5) | Y | 값의 정보 상태. 파생 규칙과 입력은 §7이 소유한다 | **확정** (enum 2026-09-06 · 파생 입력 2026-09-07, B01 종결) |
| evidence.*_display.needs_review | boolean | Y | `evidence`가 값과 함께 내려준 검토 필요 여부(`EvidenceValue.needs_review`)를 그대로 옮긴 값. `event_time_display`는 `occurred_at.resolution_status == NEEDS_REVIEW`를 옮긴다. **web은 이 값으로 분기하지 않는다**(§7) | **확정** (유소연·신유민·김준영 2026-09-07) |
| evidence.*_display.source_label_key | string \| null | Y | `EvidenceValue.source.label_key`(사건시각은 `occurred_at.source.label_key`)를 화면 라벨 키로 노출. `location_display`에서는 대표값 `value`의 출처만 뜻한다. web은 이 키로 문구를 고르고 `kind` 문자열을 직접 해석하지 않는다 | **확정** (유소연·신유민 2026-09-06 · 2026-09-07) |
| evidence.location_display.coord | `{lat, lon}` \| null | Y(키) | `EvidenceRecord.location.coord.value`를 대표값과 **별도로** 내려보낸다. 포맷은 web | **확정** (유소연·신유민·김준영 2026-09-07) |
| evidence.location_display.search_keyword | string \| null | Y(키) | `EvidenceRecord.location.search_keyword.value`. 대표값으로 승격하지 않는다 | **확정** (2026-09-07) |
| evidence.preview_ref | `FrameRef` \| null | Y(키) | **사건 대표 썸네일.** 선택된 후보의 `candidates[].thumb_ref`와 항상 같은 값이다. **번호판 프레임이 아니다** — 번호판 프레임은 `plate_preview_ref` | **확정** (2026-09-28, 이슈 #47 — 2026-09-07 유지 결정의 정의 행 추가) |
| evidence.plate_preview_ref | `FrameRef` \| null | Y(키) | 현재 번호판 값의 근거 `PlateReadout`의 `best_frame.frame_ref`. 근거 판독은 `EvidenceRecord.vehicle_number`의 `source.ref` → `support_refs` 순서로 처음 나오는 `kind=plate_readout` ref다 — case가 판독을 고르지 않고 evidence가 준 연결을 따른다. 재판독 뒤에는 재판독 결과의 프레임이다. 번호판 값이 없거나(판독 abstain) PlateReadout 근거가 없으면 `null`. `crop_ref`는 내리지 않는다(opaque identity, 조회 handle 아님). 여러 프레임 넘겨보기(`frame_results[]`)는 `[프로토타입]` 범위라 싣지 않는다 | **신규(v1.6)** (2026-09-28, 이슈 #47) |
| evidence.review_needed | boolean | Y | 여섯 개 `*_display.needs_review`의 OR 집계(object-level). 파생 규칙 §7 | **확정** (2026-09-09, 유소연) |
| requirements_evidence | object \| null | Y(키) | 현재 basis의 scope=`EVIDENCE` `RequirementReport` projection `{readiness, checks}`. 선택 규칙 §7. 미실행이면 `null` | **확정** (유소연 2026-09-07, B02 종결) |
| requirements_package | object \| null | Y(키) | 현재 basis의 scope=`FINAL_PACKAGE` `RequirementReport` projection `{readiness, checks}`. 미실행·파생물 미생성이면 `null` | **확정** (유소연 2026-09-07, B02 종결) |
| requirements_*.readiness | enum(4) | Y(객체 안) | 해당 `RequirementReport.overall`의 projection. case가 재계산하지 않는다 | **확정** (유소연 2026-09-06) |
| candidates[].rank | int \| null | Y(키) | search `CandidateEvent.rank` 그대로(Run 안의 순위, 1부터). `candidates[]`는 이 값 오름차순이다. 가장 유력한 후보 자동 선택의 기준이며(최근 Run의 `rank=1`, stale 제외), 선택 결과는 `selected`로 표현한다. web은 순서·번호 표시에만 쓴다. **클립 분할된 탐색 intent(2026-09-29 명확화, #168):** 성공한 클립 Run들의 후보를 하나의 논리적 후보 집합으로 보고, case가 `ranking_score` 내림차순·동점이면 원본 timeline 기준 시각이 이른 순으로 줄 세운다(`contract-analysis-run-candidate-event.md` §6-2 8). `candidates[]` 배열 순서와 자동 선택(묶음 순서의 첫 후보, stale 제외)은 이 묶음 순서를 따른다. 묶음에서 이 필드에 무엇을 싣는지는 `미결 유지`(§7 `RESUME_SEARCH` 행) — 다만 web이 번호로 쓰므로 보이는 후보 안에서 겹치면 안 된다. `ranking_score` 자체는 계속 내리지 않는다 | **신규(v1.5, 2026-09-28)** — 이슈 #122 · #168, 유소연 결정 · 신유민 확인 · 클립 묶음 명확화 2026-09-29(#168 후속) |
| candidates[].marker_ms | int \| null | Y(키) | 후보 비교 타임라인의 마커 위치(ms). search `CandidateEvent.span.representative_ms`(그 후보 timeline revision 기준 상대 offset)를 그대로 옮기며 case가 계산·보정하지 않는다. `stale_revision=true`면 `null`(rebase가 기존 원본 배치를 유지한다는 보장이 recording에서 확인되기 전까지), 좌표를 모르면 `null` — web은 `null`이면 마커를 찍지 않는다. `span.start_ms`·`end_ms`는 사건 길이가 아니라 넓은 후보 창이라 내리지 않는다 | **신규(v1.5, 2026-09-28)** — 이슈 #184, 유소연 답변 · 김대원 요청 |
| candidates[].thumb_ref | FrameRef \| null | Y(키) | 후보 대표 frame의 `FrameRef`(`fr_<opaque-id>`). 위치를 ID에 인코딩하지 않는다 | **확정** (정철원·유소연·신유민 2026-09-07) |
| candidates[].timeline_revision | int | Y | 이 candidate 생성 시점에 참조한 `RecordingTimeline.revision`(`CandidateEvent.span.timeline_revision` 투영). rebase 이후에도 mutate하지 않는다(B09) | **확정** (유소연, `docs/modules/case/decisions/candidate-stale-revision-display.md`, 이슈 #18 위임 · 이슈 #26 B-web-8로 정식 등재) |
| candidates[].stale_revision | boolean | Y | `timeline_revision`이 현재 `RecordingTimeline.revision`과 다르면 `true`. case가 매 투영 시점에 비교하는 파생값 | **확정** (같은 문서 · 이슈 #26 B-web-8로 정식 등재) |
| candidates[].stale_revision_label_key | string \| null | Y | `stale_revision=true`일 때 「과거 timeline revision 기준」 문구를 고를 표시 키. `stale_revision=false`면 `null`. `*_display.source_label_key`와 같은 원칙 — web은 이 키로 문구를 고르고 `stale_revision` boolean만으로 문구를 직접 만들지 않는다. v1.1 등록값은 `candidate.stale_timeline_revision` 1개(단일 문구, 향후 세분화 시 값만 추가) | **확정(2026-09-10, 유소연, 이슈 #26 B-web-8 후속)** — A-⑤·B-web-8에서 신유민이 지적한 「label_key 없으면 web이 문구를 임의로 만든다」 gap을 닫는다. `docs/modules/case/decisions/candidate-stale-revision-display.md` 갱신 |
| candidates[].situation_confirmation | enum(4) | Y | "아직 미확인"(`NOT_ASKED`)과 "잘 모르겠어요"(`USER_UNSURE`)를 같은 null로 합치지 않기 위한 projection. `EvidenceRecord.situation_response.value`가 있으면 그대로 옮기고(`CONFIRMED`/`CORRECTED`/`USER_UNSURE`), 없으면 `NOT_ASKED`다 | **확정(v1.3, 2026-09-10)** — 값 공간을 `evidence-record/v1.3`의 `situation_response`와 맞춤(이슈 #33). 원래 유소연 결정(`docs/modules/case/decisions/generic-warn-package-and-situation-response.md`, 이슈 #25)의 후속 |
| candidates[].at_provenance | string | Y | 이 후보의 시각(`at`)을 어떻게 구했는지 나타내는 raw 값. **두 갈래**: evidence 조립 이후엔 `occurred_at.source.kind` pass-through(evidence 소유, 열린 namespace), 조립 이전엔 case 소유의 별도 enum(현재 `recording.timeline_relative_only` 1개). web은 이 값을 직접 해석하지 않고 `at_provenance_label_key`로만 분기한다 | **정정(v1.4, 2026-09-14)** — §8 예시 `TIMELINE_ANCHOR+OFFSET`은 fixture 실사용 0건으로 확인돼 폐기. 두 갈래 정의는 PR 리뷰 코멘트 Q-3, 유소연·신유민 합의 |
| candidates[].at_provenance_label_key | string \| null | Y | `at_provenance` raw 값을 보고 case가 고르는 표시용 키. `stale_revision_label_key`와 같은 원칙 — raw가 authoritative, 이 키는 순수 파생값. 매핑 안 되는 raw는 `null` | **신규(v1.4, 2026-09-14)** — 이슈 #39 Required-3 후속, PR 리뷰 코멘트 Q-3, 유소연·신유민 합의. 매핑표는 §7 |
| package.report_field_states | object<string, {info_state, source_label_key}> | Y(키, **5개 전부 항상 존재** — §10 불변조건 13) | `report_fields`와 나란히 필드별 정보 상태를 제공. 매핑표·값 공간은 §7 | **신규(v1.3)** — 신유민 PR #28 요청, `CONTRACT_CONFLICTS.md` 불명확 항목 10 종결 |
| package.report | `{ title: string, description: string }` | Y(`package`가 non-null이면) | 최종 신고문. `ReportPackage.report.title` · `description`을 그대로 옮긴다 — 둘 다 non-null, `description`은 줄바꿈을 포함한 평문. `report.template_ref`는 내리지 않는다. 최상위 `description`(같은 v1.7 신규, #259 — 사용자 입력 원문)과 다른 값 | **신규(v1.7, #274)** |
| manifest_summary.ok_file_count / failed_file_count / duration_sec | int/int/number | Y | 파일 등록 성공·실패 수, 전체 구간 길이. count/duration은 항상 제공하고 정상 영상이 없으면 range=null | 확정 |
| evidence.* (projection 필드 전반) | object | 선택 | 화면 표시용 evidence 요약 | safe projection 원칙 확정; 세부 필드 합의는 §13 Pending |
| package.* | object | 선택 | 화면 표시용 package 요약 | safe projection 원칙 확정; 세부 필드 합의는 §13 Pending |
| notices[].code/severity/blocking/message_key/actions | string/string/bool/string/array | Y(배열은 빈 배열 허용) | 부분 실패/경고 표시 | 신규, 신유민 요청 반영 |
| progress[].state | string | Y | 단계 상태 | **확정** — `PENDING / RUNNING / DONE / FAILED / PARTIAL`(2026-09-10 추가) |
| progress[].step 범위(2026-09-10, 유소연, `05` §12 유소연-⑦ 종결) | — | — | `progress[]`는 `product/core-user-flow.md` §3-2가 "AI 분석 진행은 별도로 표현한다"고 정한 **AI job 진행상태 전용**이다. 제품 7단계 표시(§4-1) 중 2단계("사건 설명")·3단계("범위 확인")는 AI job이 아니라 **사용자가 입력·확인하는 동기 단계**라 대응하는 `progress[].step` 값이 원래 없어야 맞다 — web은 이 두 단계를 `hints`/`manifest_summary` 등 다른 필드의 존재 여부로 "완료"를 표시하면 되고, 이는 §3-2가 금지하는 "정보 상태와 작업 상태를 같은 표시 체계로 섞는 것"이 아니다(정보 상태가 아니라 사용자 입력 여부를 보는 것). `progress[].step` 8종(`file_intake~package_assembly`)은 제품 4~7단계(사건 찾기~신고자료)만 커버하면 되고, 이는 이미 그렇다 — **누락이 아니라 원래 이렇게 설계된 것으로 확정, 신규 step 추가 불필요** |

### 7. Enum / State / Special Value

| 필드 | 확정 값 | 비고 |
| --- | --- | --- |
| stage | `INTAKE`, `SEARCHING`, `CANDIDATE_REVIEW`, `EVIDENCE_REVIEW`, `READY` | 신유민 Q3 답변 기준 최종 확정. **`READY` = 「`PACKAGE_READY` 파생 gate가 성립한 시점」**(`contract-requirement-report-package.md` §5.2). `EVIDENCE_SUFFICIENT`는 `EVIDENCE_REVIEW` 단계 안의 조건이고 `USER_REVIEWED`는 `user_reviewed` 필드가 갖는다 |
| user_reviewed | `true`, `false` | v4 §3-6 `USER_REVIEWED`. `stage`와 별개 축이며 `stage=READY`가 아니어도 `true`일 수 있다 |
| requirements_evidence / requirements_package | 객체 또는 `null` | scope별 report projection. **선택 규칙(3단계)** — ① `basis.evidence_record_ref`가 현재 `EvidenceRecord.record_ref`와 일치하는 report만 후보 ② `supersedes_ref` 체인의 head ③ 그래도 복수면 `evaluated_at` 최신. 이 규칙은 이 계약이 소유하고 `contract-requirement-report-package.md` §5.2-1은 여기를 가리킨다. `requirements_evidence=null`은 현재 basis의 Evidence 검사 미실행, `requirements_package=null`은 package-scope 검사 미실행 또는 필요한 파생물 미생성 |
| requirements_*.readiness | `PASS`, `WARN`, `BLOCK`, `UNKNOWN` | 해당 `RequirementReport.overall`과 **같은 값 공간**. `4/5` 같은 score 표현을 두지 않는다(`contract-requirement-report-package.md` §4 「단순 readiness score를 Contract에 두지 않는다」) |
| 세 gate의 출처 | — | `EVIDENCE_SUFFICIENT` = `requirements_evidence` 판정 · `PACKAGE_READY` = `requirements_package` 판정(+`package` 존재) · `USER_REVIEWED` = `user_reviewed`. **셋을 하나의 readiness로 합치지 않는다.** 별도 gate 표시값을 두려면 이 셋에서 단순 파생되는 표시값이어야 하고 새 authoritative 상태가 되면 안 된다 |
| evidence.*_display.info_state | `INFO_AI_ESTIMATED`, `INFO_SOURCE_VERIFIED`, `INFO_USER_CONFIRMED`, `INFO_NEEDS_REVIEW`, `INFO_UNKNOWN` | `core-user-flow.md` §3-1의 정보 상태 5종과 1:1. **`Observation.status`와 다른 값 공간이므로 `INFO_` 접두어로 분리한다** — 파생 코드가 두 enum을 동시에 다루는 지점에서 `NEEDS_REVIEW`/`UNKNOWN`이 겹치는 것을 막는다(유소연 2026-09-06) |
| progress[].state | `PENDING`, `RUNNING`, `DONE`, `FAILED`, `PARTIAL` | CaseView UI 상태로 확정. JobExecution 상세 상태와 분리. **`PARTIAL`(2026-09-10, 유소연, `05` §12 유소연-⑧ 부분 종결)**: 제품 정의 6개 작업상태(`core-user-flow.md` §3-2)의 "부분 완료"·**"중단" 둘 다**에 대응한다(v1.3 개정). 해당 단계의 `AnalysisRun.outcome=PARTIAL`(`contract-analysis-run-candidate-event.md` §5)을 그대로 투영하거나, `JobExecution.status=CANCELLED`(`job-execution/v1.1`, 이슈 #33 A-2로 신설)를 대표 상태로 가질 때도 `PARTIAL`로 투영한다. **새 enum 값을 만들지 않고 기존 `PARTIAL`로 흡수한 이유**: `CANCELLED`도 완결이 아니고(`job-execution/v1.1` §9 예외) 부분 결과가 있을 수 있다는 점에서 UI 표시 목적상 "부분 완료"와 구분할 실익이 이번 라운드엔 없다 — 실제 중단 사유("사용자가 멈춤" vs "일부만 됨")를 구분해야 하면 `notices[]`로 별도 표시한다. `PARTIAL`을 보여주는 demo fixture는 `scenario_infra_failure_001`의 `job_x001_plate_reread`(`JobExecution.status=CANCELLED`, `produced=[]`)로 확보됐다(2026-09-13, PR 리뷰 반영 — `04_mock_validation_report.md` §1에 등재됐던 Should-1 커버리지 갭을 닫는다). **`produced` 유무는 이 투영을 바꾸지 않는다** — 부분 결과가 전혀 없어도(`produced=[]`) `CANCELLED`는 그대로 `PARTIAL`로 투영된다. 「완결이 아니다」라는 사실 자체가 이 값의 의미이며, 중단 사유·다음 행동 안내는 `notices[]`(예: `case.plate_read_cancelled`, `actions=[RETRY_PLATE_READ]`)가 나른다 **중단된 job(2026-10-05, #245 C-3 · #248 Q-1):** 사용자 중단 command가 성공한 job은 case가 「중단된 `job_id` 집합」으로 판단해 **실제 `JobExecution` 상태와 상관없이 `PARTIAL`로 투영**한다. 협력적 중단 때문에 아직 `RUNNING`이거나, 중단 요청으로 다음 attempt를 만들지 않아 마지막 attempt가 `STALE`(아래 매핑상 `FAILED`)이어도 `FAILED`로 보이지 않는다. 그 job은 `running_jobs`에서도 빠진다(§10-5) |
| candidates[].at_provenance | 두 갈래 값 공간. **evidence 조립 이후**: `occurred_at.source.kind` pass-through — evidence가 소유한 열린 namespaced string이며 case가 별도로 닫힌 목록을 등재하지 않는다(관측값 예: `recording.filename_time`, `readout.overlay_ocr`). **evidence 조립 이전**: case 소유의 별도 enum, 현재 `recording.timeline_relative_only` 1개만 등재(열린 enum, 추가 시 값만 등재) | **정정(v1.4, 2026-09-14, 유소연·신유민)** — §8 예시 `TIMELINE_ANCHOR+OFFSET`은 fixture 전수 조사 결과 실사용 0건이라 폐기. `readout.overlay_ocr`가 `Observation.source.kind`와 문자열이 같다고 해서 같은 값 공간으로 합치지 않는다(`contract-plate-overlay-readout.md` §6 선례와 같은 원칙 — 「누가 관찰했나」와 「확정 시각의 출처」는 별개 질문) |
| candidates[].at_provenance_label_key | 표기 dotted-lowercase(`<owner>.<detail>`), `notices[].code`와 같은 규칙. **등재값**: `candidate.at_provenance.filename_time`(← `recording.filename_time`) · `candidate.at_provenance.overlay_ocr`(← `readout.overlay_ocr`) · `candidate.at_provenance.timeline_relative_only`(← `recording.timeline_relative_only`, pre-evidence). 미등록 raw는 `label_key=null` — web이 fallback 문구를 쓰며, 별도 `candidate.at_provenance_unknown` raw 마커는 두지 않는다(§10-14) | **신규(v1.4, 2026-09-14, 유소연·신유민 PR 리뷰 코멘트 Q-3 합의)** — `event_time_display.source_label_key`(=`occurred_at.source.label_key`) pass-through 가설은 fixture 16 스냅샷 전수 대조로 기각됐다(`scenario_correction_rerun_001` rev0→rev1: `at_provenance`는 불변인데 `event_time_display.source_label_key`만 `time.source.filename`→`time.source.user_correction`으로 바뀜 — 이슈 #39 Required-3과 같은 종류의 독립성). case 소유의 독립 매핑으로 대체 |
| notices[].severity | `INFO`, `WARN`, `ERROR` | 표시 강도만 의미하며 실제 차단 여부는 `blocking`으로 별도 판단 |
| notices[].code | dotted-lowercase namespaced string | **확정(2026-09-10, 유소연·신유민, 이슈 #26 A-⑤)**. 형식은 `<producing-module>.<detail>` — `case` / `evidence` / `readout` / `search` / `recording` 중 이 notice의 근거를 실제로 만든 모듈을 접두어로 쓴다. **`time`은 모듈이 아니므로 접두어로 쓰지 않는다** — 기존 `time.*` 4종은 `evidence.time_conflict_needs_notice`·`evidence.time_needs_user_confirmation`·`readout.overlay_not_present`·`evidence.time_post_stamp_required`로 정정했다(근거 모듈 기준: 시각 충돌·재확인·post-stamp는 `TimeResolution`을 만드는 evidence, overlay 부재는 관찰 자체를 만드는 readout). `JobExecution.failure_kind`(SCREAMING_SNAKE 열거값)를 `notices[].code`로 옮길 때는 **문자열을 그대로 복사하지 않고** 이 표기로 변환한다(A절 §7 참고). **2026-09-14 신규 등재(이슈 #47/#48 결과, `evidence` 김준영 승인).** `evidence.location_search_keyword_missing`(`severity:INFO`, `blocking:false`, `actions:[]`) — 지도에 붙여넣을 `search_keyword`를 만들지 못한 경우에 발동한다(`location` 자체가 없어 파생 필드 전부가 `null`인 경우 포함). **판단 기준은 `location`의 존재 여부가 아니라 `evidence.location_display.search_keyword == null`이다** — `search_keyword`가 있으면 `display_text`가 사용자 기억 문장뿐이어도 지도 붙여넣기 경로가 성립해 이 notice 대상이 아니다(§21 복사 경로와 어긋나지 않게 하기 위함). `message_key`는 `notice.location_search_keyword_missing`(문구 매핑은 신유민 — 「지도에 붙여넣을 검색어를 제공하지 못한다, 기억나는 장소를 직접 검색해야 한다」). 제품 안에 실행 경로가 없는 정보성 notice라 `actions[]`는 확장하지 않는다(기준: 실행 경로가 있으면 `action`, 없으면 문구만 — 이슈 #31 W-6과의 구분 기준과 동일). **2026-09-28 신규 등재(#171 C-2, `case` 유소연 결정).** `case.situation_response_pending`(`severity:INFO`, `blocking:false`, `actions:[]`) — Package 전 결과 화면의 「준비 전」 이유로, 상황 응답을 받기 전이라 Package가 나가지 않은 상태(ADR-EVIDENCE-005 D2-c)를 알린다. **발동 조건: `evidence`가 non-null이고, 선택된 후보의 `candidates[].situation_confirmation == NOT_ASKED`이며, `package == null`.** **2026-10-02 추가(PR #224 리뷰, 유소연):** `evidence`가 없어도 adapter가 보고한 선택 후보의 `VisualEvidenceDisposition.decision == AWAIT_SITUATION_RESPONSE`(Fine `UNCERTAIN` + 응답 전, #165)면 붙인다 — 그렇지 않으면 응답 대기가 「조립 중」과 같아 보여 web이 진행 화면에서 끝나지 않는다. 그 밖에 `evidence`가 없으면(조립 전) 붙이지 않는다. 응답 전 부분 결과는 v1.8부터 `evidence` 부분 투영(§10 불변조건 15, #239)으로 보이며, 그때는 `evidence`가 non-null이라 원래 발동 조건으로 붙는다. 위 adapter 판정 갈래는 부분 투영을 만들지 못한 경우의 대비로 남는다. `message_key`는 `notice.situation_response_pending`(문구 매핑은 신유민). 응답 버튼은 notice action이 아니라 1차 명령이라 web→case command(#106)로 열며, 그래서 `actions[]`는 비운다. **2026-09-28 등재(#172 [D] case 후속, 유소연).** `readout.plate_read_failed`(`severity:ERROR`, `blocking:true`, `actions:[RETRY_PLATE_READ]`, `message_key: notice.plate_read_failed_retry_exhausted`) — 번호판 판독이 **실행 실패**한 경우(`ReadoutRun.outcome=FAILED`, #172 D-2의 4a). 발동 조건은 `progress[]`의 `plate_read`가 `FAILED`일 때다. 동기 real 경로는 `ReadoutRun.outcome=FAILED`를, worker 경로는 `JobExecution.status`를 `plate_read` 진행 상태로 투영한다. 「읽지 못함」(글자를 못 읽음·번호판이 안 보임, `PlateReadout.status=UNKNOWN`)은 실행 실패가 아니므로 이 notice를 붙이지 않고 `plate_display.info_state=INFO_UNKNOWN`으로만 보인다 — 식별 실패와 실행 실패를 같은 표시로 합치지 않는다. 모양은 `scenario_infra_failure_001` rev2 fixture가 먼저 쓰던 값을 그대로 등재했다. **2026-10-02 추가(orchestration 지표 5차, 유소연):** `RETRY_PLATE_READ`는 발주 근거(같은 kind의 이전 `PLATE_READ` JobRecord)가 있을 때만 싣고, 없으면 `actions:[]`로 실패만 알린다 — 재시도는 이전 발주의 입력을 그대로 쓰고 없으면 거부되므로(case-command 계약 §10), 근거 없이 실으면 화면의 버튼이 늘 거부된다(아래 「실행 경로가 없는 action은 싣지 않는다」 원칙). 동기 real 경로는 판독을 Job 없이 직접 불러 이 버튼이 나오지 않는다. **2026-09-28 등재(PR #187 리뷰 후속, 유소연).** `search.candidate_search_failed`(`severity:ERROR`, `blocking:true`, `actions:[RETRY_SEARCH]`, `message_key: notice.candidate_search_failed`) — 후보 탐색 Run이 `outcome=FAILED`로 끝난 경우. search 계약상 실패 Run은 후보 0개라 후보만 보면 「찾았지만 없음」(`search.no_candidates`, SUCCEEDED + 0건)과 구분되지 않는다. case는 실패 Run으로 후보 목록을 교체하지 않고 `stage=SEARCHING`에 머물며(§7 `RESUME_SEARCH` 행: 실패 Run은 투영 대상을 바꾸지 않음), `progress[]`의 `coarse_search`를 `FAILED`로 내린다. 발동 조건은 `coarse_search`가 `FAILED`일 때이고, 다음 탐색이 성공하면 사라진다. **2026-09-29 등재(#168 [A] 후속, `case` 유소연 결정 · 신유민 요청).** `evidence.visual_event_not_observed`(`severity:INFO`, `blocking:false`, `actions:[]`, `message_key: notice.visual_event_not_observed`) — 선택된 후보의 Fine 결과가 `NOT_OBSERVED`라 evidence가 `NOT_ASSEMBLED`로 조립하지 않은 **음성 결과**(#168 [A] (a): 다음 후보를 자동 Fine하지 않고 「다른 후보 보기」로 끝낸다). 음성 결과는 `stage=EVIDENCE_REVIEW` + `evidence=null`이라 CaseView 값만으로는 조립 전과 구분되지 않으므로, 발동 조건은 **`evidence == null`이고 adapter가 보고한 선택 후보의 `VisualEvidenceDisposition.decision == NOT_ASSEMBLED`**다. 접두어는 판정을 만든 evidence(`disposition.py`)를 따른다. Fine `UNCERTAIN` 응답 대기(`AWAIT_SITUATION_RESPONSE`)는 음성이 아니므로 이 notice 대상이 아니다 — `case.situation_response_pending`으로 알린다. `evidence.visual_event_unconfirmed`(`UNCERTAIN`)와는 뜻이 달라 따로 둔다. 출구 「다른 후보 보기」는 결과 화면 1차 명령이라 `actions[]`는 비운다. **2026-09-29 등재(#197 후속 · 이슈 #31 W-1 모양, `case` 유소연).** `search.no_candidates`(`severity:INFO`, `blocking:false`, `actions:[EDIT_HINT, RETRY_SEARCH]`, `message_key: notice.search_no_candidates`) — 후보 탐색은 성공했지만(`outcome=SUCCEEDED`) 후보가 0개인 「결과 없음」. **발동 조건: `stage=CANDIDATE_REVIEW`이고 `candidates`가 비었을 때.** 탐색 실패는 `SEARCHING`에 머물러(`search.candidate_search_failed`) 이 조건에 들지 않는다. 모양은 `scenario_empty_001` fixture가 먼저 쓰던 값 그대로다. 선택 전(탐색 중 · 후보 0개)에는 downstream 값이 없으므로 case는 adapter를 조회하지 않고 evidence 이하를 `null`로 투영한다. **2026-09-30 등재(#172 D-3 case 후속, 유소연).** `evidence.plate_abstained`(`severity:WARN`, `blocking:false`, `actions:[]`, `message_key: notice.plate_abstained`) — 번호판 판독이 **보류**된 경우(일부 판독 / `NEEDS_REVIEW`, #172 D-3의 1·2). **발동 조건: `evidence.plate_display.value == null`이고, evidence가 현재 EvidenceRecord(`evidence.record_id`)를 `basis_record_ref`로 계산한 `EvidenceNeeds`에 `kind=PLATE_REREAD` 항목이 있을 때.** CaseView 값만으로는 읽지 못함(1·3, `PlateReadout.abstained=false`라 Need 없음)·실행 실패(4a, `readout.plate_read_failed`)와 같은 `INFO_UNKNOWN`으로 보여, 이 notice만 CaseView 밖의 `EvidenceNeeds`를 근거로 쓴다(case는 Need를 만들거나 해석하지 않고 존재만 본다). 이전 revision을 basis로 한 Need는 보지 않는다 — 재판독으로 값이 채워지면 사라진다. 모양은 `scenario_plate_reread_001` rev3 fixture 값이되 **`actions[]`는 비운다** — fixture의 `MANUAL_PLATE_INPUT`은 사용자 입력을 case로 보낼 입력형 command(`docs/modules/case/contracts/contract-case-command.md` §2 「다음 판본」)가 열린 뒤 싣는다(실행 경로가 없는 action은 싣지 않는다는 위 `notices[].actions[]` 원칙). 위 일곱 notice는 호출자가 공급하지 않아도 `service.derive_notices()`가 붙인다 — 다섯 개는 조립된 CaseView 값으로(응답 대기의 `case.situation_response_pending`은 adapter가 보고한 Fine 판정도 본다), `evidence.visual_event_not_observed`는 adapter가 보고한 Fine 판정으로, `evidence.plate_abstained`는 `build_view_from_adapter()`가 adapter에서 읽은 `EvidenceNeeds`로. **2026-10-04 등재(case 고도화 문서 8-14 · #244 R-1 후속, `case` 유소연).** `search.visual_verify_failed`(`severity:ERROR`, `blocking:true`, `actions:[]`, `message_key: notice.visual_verify_failed`) — 선택된 후보의 Fine(`FINE_VERIFY`)이 **실행 실패**로 끝난 경우. **발동 조건: `evidence`가 null이고, 선택 후보 Fine의 대표 `JobExecution.status`(A§10-6 · §10-7)가 terminal 실패(`FAILED` · 재시도가 끝난 `STALE`, §13 매핑에서 `FAILED`가 되는 값)일 때.** `progress[]`에 Fine step이 없어 CaseView 값만으로는 「조립 전」과 구분되지 않으므로, 음성 결과와 같은 방식으로 CaseView 밖의 입력(Fine 실행 상태)을 본다 — 실행 상태라 adapter가 아니라 `build_view_from_adapter()` · `get_view()`의 호출자가 `visual_verify_status`로 넘긴다(`running_jobs`와 같다). `CANCELLED`(사용자 중단)는 실패가 아니라 이 notice 대상이 아니다. 접두어는 Fine Run을 만드는 `search`를 따른다. 같은 후보의 Fine을 다시 발주하는 action은 위 닫힌 `notices[].actions[]` 목록에 없어 **`actions[]`는 비운다** — 출구는 결과 화면 1차 명령 「다른 후보 보기」(`SELECT_OTHER_CANDIDATE`)이고, 같은 후보 재시도 action을 열지는 web과 따로 정한다. 동기 real 경로는 Fine 예외를 아직 실행 상태로 바꾸지 않는다 — 어떤 예외를 실행 실패로 볼지는 Search failure taxonomy 접합(#244) 뒤에 정한다. `message_key` 문구 매핑은 web(신유민) 확인 대기. **2026-10-04 등재 · 구현(`case` 유소연, readout `failure-taxonomy.md` 「`CaseView.notices[].code` 매핑」 #31 A-1 그대로).** `readout.overlay_presence_undetermined` · `readout.overlay_ocr_failed`(둘 다 `severity:INFO`, `blocking:false`, `actions:[]`, `message_key: notice.overlay_presence_undetermined` · `notice.overlay_ocr_failed`) — 위 `readout.overlay_not_present`와 같은 묶음으로, overlay 판독이 정상 종료했지만 시각을 얻지 못한 갈래다. readout `observation.reason.code`(`readout.overlay.not_present` · `readout.overlay.presence_undetermined` · `readout.overlay.ocr_failed`)와 1:1이고 셋을 합치지 않는다(「화면에 시각이 없다」와 「확인하지 못했다」는 다른 말, `core-user-flow.md` §5). **발동 조건: 현재 선택 후보의 가장 나중 `OverlayTimeReadout`(A§10-7)의 `reason.code`가 위 셋 중 하나일 때.** evidence 유무와 무관하다(`scenario_infra_failure_001` rev1~3은 evidence 없이 붙는다). 실행 실패가 아니라 `progress[overlay_time_read]`는 `FAILED`가 아니다. 세 notice 모두 `build_view_from_adapter()`가 adapter에서 읽은 `OverlayTimeReadout` 목록으로 `service.derive_notices()`가 붙인다 — 매핑에 없는 reason은 지어내지 않는다 |
| notices[].actions[] | `EDIT_EVENT_TIME`, `MANUAL_PLATE_INPUT`, `GENERATE_REPORT_VIDEO`, `REVIEW_TIME`, `RETRY_PLATE_READ`, `EDIT_HINT`, `RETRY_SEARCH`, `GENERATE_PLATE_IMAGE` | **닫음(2026-09-10, 유소연, 이슈 #26 A-⑥ · 이슈 #31 W-1로 2종 추가 · 2026-09-28 이슈 #47로 `GENERATE_PLATE_IMAGE` 추가)**. SCREAMING_SNAKE 유지(발주 intent를 나타내는 값이라 `JobRecord.kind`류와 같은 표기). 값→발주 매핑은 아래 표. web은 이 값으로만 버튼을 렌더하며 값 자체를 해석하지 않는다(`running_jobs[].label_key`와 같은 원칙). **미등록 값은 fallback으로 버튼을 렌더하지 않는다**(무시) — `label_key` fallback과 달리 실행 경로가 없는 액션을 잘못 노출하는 것이 더 위험하기 때문이다 |

**`notices[].actions[]` → 발주 매핑**

| 값 | 발주/동작 |
| --- | --- |
| `EDIT_EVENT_TIME` | web이 사용자 입력을 받아 `CorrectionRecord`(Draft, N02 해소 후) 경유 시각 정정 — 현재는 case state 경유 |
| `MANUAL_PLATE_INPUT` | web이 사용자 입력을 받아 번호판 값을 직접 정정 (`vehicle_number`, `user_corrected=true`) |
| `GENERATE_REPORT_VIDEO` | `kind=REPORT_VIDEO_EXPORT` 신규 `JobRecord` 발주. 기존 `job_id` 없으면 새로 만든다 |
| `GENERATE_PLATE_IMAGE` | **신규(v1.6, 이슈 #47)**. `kind=PLATE_IMAGE_EXPORT` 신규 `JobRecord` 발주 — `GENERATE_REPORT_VIDEO`와 같은 원칙. `PlateReadout`이 없으면 이 action을 싣지 않는다(발주할 입력이 없다). recording이 「허용된 변환으로 출력 제한을 만족시킬 수 없음」을 돌려준 경우는 같은 입력으로 다시 발주해도 결과가 같으므로 이 action을 싣지 않는다(#47 Q5 — 그때는 frame·판독 선택을 바꾸는 별도 Intent) |
| `REVIEW_TIME` | web이 시각 후보들을 보여주고 사용자가 하나를 선택/확인하게 한다 — 새 Job 발주 없음, 확인만으로 `TimeResolution.resolved.verification`이 바뀐다(§9-2 미결 항목과 연결) |
| `RETRY_PLATE_READ` | `kind=PLATE_READ` 신규 `job_id` 발주. `FAILED`는 cache hit 대상이 아니므로(A절 §7 캐시 재사용은 성공 결과에 한정) `force_rerun` 불필요 — 새 `job_id`만으로 재시도가 성립한다 |
| `EDIT_HINT` | **신규(v1.3, 이슈 #31 W-1)**. web이 사용자로부터 새 검색 단서(시간대·사건 유형 등)를 입력받는다 — 새 Job 발주 없음, 다음 `RETRY_SEARCH`의 입력을 바꾸는 동작이다 |
| `RETRY_SEARCH` | **신규(v1.3, 이슈 #31 W-1)**. `kind=COARSE_SEARCH` 신규 `job_id` 발주(바뀐 단서 기준). `candidates=[]`는 cache hit 대상이 아니므로 `force_rerun` 불필요 — 새 `job_id`만으로 재검색이 성립한다(`RETRY_PLATE_READ`와 같은 원칙) |
| `RESUME_SEARCH`(`이어서 찾기`) | **신규(2026-09-13, ERD 리뷰 반영)**. `JobExecution.status=CANCELLED` 이후 조건 변경 없이 재개하는 경우도 `kind=COARSE_SEARCH` 신규 `job_id` 발주다 — 위 `RETRY_SEARCH`/`RETRY_PLATE_READ`와 같은 원칙(사용자의 새 Intent는 새 `job_id`, 같은 `job_id`+`attempt` 증가는 자동 인프라 재시도 전용). 이미 찾은 후보는 `CandidateEvent`가 search의 `AnalysisRun` 기록으로 독립적으로 남아 `job_id`를 나눠도 지워지지 않는다. **2026-09-28 정정(#168, `case` 유소연 결정):** 다만 `CaseView.candidates[]`는 **가장 최근 성공한(`outcome=SUCCEEDED`) `CANDIDATE_SEARCH` Run의 후보만** 투영한다 — `rank`는 Run 안의 순위라 여러 Run을 섞으면 `rank=1`이 겹치고, search의 재검색은 매번 영상 전체를 다시 봐 이전 Run 후보가 거의 같은 장면의 중복이 되기 때문이다. 자동 선택도 같은 Run의 `rank=1`(stale 제외)이다. 실패·중단된 Run(`FAILED` — search 계약상 후보 0개)은 투영 대상 Run을 바꾸지 않는다 — 실패를 「후보 없음」으로 보여 주지 않고, 보존된 결과와 다음 행동을 같은 맥락에 둔다(core-user-flow §4-2, PR #187 리뷰 김대원). 이전 Run 후보를 화면에 함께 보여야 하면 그때 `run_id` 투영과 중복 처리 주체를 다시 정한다(현재 case 구현도 새 검색 결과로 후보 목록을 교체한다 — `CaseAggregate.receive_candidates()`). **2026-09-29 명확화(#168 클립 분할 후속 결정, `case` 유소연 · `search` 서어진 답변):** 위 「가장 최근 성공한 Run」은 탐색 intent 하나 = Run 하나일 때의 표현이다. ① 인라인 상한 안의 영상은 클립 1개 = Run 1개로 처리하고 위 규칙을 그대로 쓴다. ② 상한을 넘는 긴 영상만 클립으로 나누며, 이때 투영 단위는 **현재 탐색 intent의 성공한 클립 Run 묶음**이다 — 묶음의 후보를 하나의 논리적 후보 집합으로 보고 `ranking_score` 내림차순·동점이면 원본 timeline 기준 시각이 이른 순으로 줄 세우며, 자동 선택은 그 순서의 첫 후보다(stale 제외, stale 처리 규칙은 위와 같음). ③ **이전 탐색 intent의 후보와 현재 intent의 후보를 섞어 새 순위를 만들지 않는다**(#170 F) — 새 intent가 성공하면 그 묶음으로 교체한다. ④ web은 후보 순위·중복을 자체 계산하지 않는다. 클립 겹침 구간의 중복은 search가 거르고(방향 합의), 순서 비교에 쓰는 `ranking_score`는 CaseView에 내리지 않는다. **`미결 유지`:** 클립 겹침 길이(실험으로 정함) · 묶음 전체를 넘겨 중복을 거르는 호출 지점 · 묶음에서 `candidates[].rank`에 싣는 값 · 일부 클립 Run만 실패했을 때 묶음을 성공으로 볼지 — 모두 클립 분할을 실제로 도입할 때 search·case가 정한다. 클립의 원본 기준 시작 시각은 case가 발주 입력으로 넘기고 search가 offset을 보정한다(`contract-analysis-run-candidate-event.md` §4-1). 상세 `docs/modules/case/decisions/job-resume-identity-policy.md`, `contract-job-execution.md`의 2026-09-13 명확화 노트 |

**`info_state` 파생 규칙 — 확정 (B01 종결, 2026-09-07)**

입력은 모두 `EvidenceRecord`(`contract-evidence-record-needs.md` §3)에서 온다. `case`는 어느 입력도 재계산·재해석하지 않는다. 근거·기각안은 `adr/adr-data-contract-call-closure-2026-09-07.md` §4.1.

**(1) `EvidenceValue` 기반 display — `plate_display` · `case_type_display` · `report_type_display` · `violation_display` · (`location_display`의 대표값 선정 후에도 동일 규칙, §7-(3))**

```
1. value == null                        → INFO_UNKNOWN
2. user_corrected == true               → INFO_USER_CONFIRMED
3. needs_review == true                 → INFO_NEEDS_REVIEW
4. source.observability == OBSERVED     → INFO_SOURCE_VERIFIED
5. 그 외 (source.observability=INFERRED) → INFO_AI_ESTIMATED
```

2가 3보다 앞서는 것은 `core-user-flow.md` §9 「한 번 `사용자 확인됨`이 된 값은 다시 묻지 않는다」 때문이다. `needs_review`는 **`evidence`가 값과 함께 내려주는 `EvidenceValue.needs_review`**다. `evidence`가 「`user_corrected=true`와 `needs_review=true` 동시 발생 금지」·「`value=null`과 `needs_review=true` 동시 발생 금지」를 보장하므로(같은 계약 §10) 순서 규칙과 boolean이 어긋나는 조합은 생기지 않는다.

**(1) 적용 범위 확정(v1.3, 이슈 #31 W-3, 유소연).** `case_type_display`(← `event.visual_event_type`)·`report_type_display`(← `event.safety_report_type`)·`violation_display`(← `event.violation_expression`)는 셋 다 `EvidenceRecord.event` 아래의 `EvidenceValue<T>`이므로 `plate_display`와 같은 (1) 규칙을 그대로 쓴다 — 별도 파생 로직이 아니다. **정정(2026-09-11, 이슈 #38 B-3, 신유민 지적·김준영 교차 확인 — 4차 검수).** `visual_event_type`과 `violation_expression`의 observability는 서로 다르다 — 이전 문구는 둘 다 `evidence.assemble()`이 항상 `source.observability=INFERRED`로 채운다고 적어 이 차이를 놓치고 있었다. `violation_expression`은 문장 자체가 항상 AI 생성이라 언제나 `INFERRED`이고, `violation_display`는 사건 유형 확정 여부와 무관하게 전 시나리오에서 `INFO_AI_ESTIMATED`다 — happy path를 포함해 신고문 화면에 「AI 추정」 표시가 뜬다. 반면 `visual_event_type`은 `search.visual_inference`(`VisualEvidence`의 `verification`/`visual_event_type` 판정)를 그대로 옮기는 passthrough라 `source.observability=OBSERVED`로 채운다 — `verification=OBSERVED`인 경우 `case_type_display=INFO_SOURCE_VERIFIED`가 되는 것은 "AI가 `VisualEvidence`의 `OBSERVED` 판정을 그대로 옮겼다"는 뜻이다. 이 정정은 fixture·결론을 바꾸지 않는다(둘 다 이미 맞았다) — 향후 이 문구를 근거로 `visual_event_type`을 `INFERRED`로 "고치는" 회귀를 막기 위한 wording 정정이다. `violation_display=INFO_AI_ESTIMATED`라는 결론은 W-3에서 신유민이 제안한 해석을 그대로 채택한 것이다.

**(2) `occurred_at` → `event_time_display`** — `occurred_at`은 `EvidenceValue`가 아니라 `{value, time_resolution_ref, resolution_status, user_corrected, source{kind,label_key}}`다. `case`는 `source`를 들여다보지 않는다.

| 조건 (위에서부터 첫 일치) | `info_state` |
| --- | --- |
| `occurred_at` 부재 | `INFO_UNKNOWN` |
| `occurred_at.user_corrected == true` | `INFO_USER_CONFIRMED` |
| `occurred_at.resolution_status == NEEDS_REVIEW` | `INFO_NEEDS_REVIEW` |
| `occurred_at.resolution_status == OK` | `INFO_SOURCE_VERIFIED` |

이 표가 안전한 것은 `evidence`가 `OK`를 **검증된 영상 화면 시각 또는 사용자 확정에만** 부여하고 파일명·metadata 계산 시각은 `NEEDS_REVIEW`로 내리기 때문이다(`contract-time-resolution.md` §4). `event_time_display.needs_review`는 `resolution_status == NEEDS_REVIEW`를 그대로 옮긴다. `source_label_key`는 `occurred_at.source.label_key`다.

**(3) `location_display` 대표값** — `EvidenceRecord.location`의 `address → place_name → user_hint` 중 **존재하는 첫 값 하나**를 `value`에 싣고 그 `EvidenceValue`를 (1)의 입력으로 쓴다. 대표값이 `user_hint`이면 `info_state = INFO_NEEDS_REVIEW`다. 여러 값을 합쳐 새 위치 문자열을 만들지 않는다. `coord`·`search_keyword`는 대표값 후보가 아니며 `location_display.coord` / `location_display.search_keyword`로 **별도** 내려보낸다(좌표 포맷은 web). `source_label_key`는 대표값 `value`의 출처만 뜻한다. 셋 다 없으면 `value = null`, `INFO_UNKNOWN`.

**(4) `needs_review`와 `info_state`의 관계** — 독립 필드다(동치 불변식이 아니다). `needs_review`는 「값은 있지만 사용자 확인이 필요한 경우」에만 참이다. **web 소비 규칙: web은 `info_state`만 보고 표시하며 `needs_review`를 직접 해석하지 않는다.** 「값이 없어 입력이 필요한 상태」와 「값이 있는데 검토가 필요한 상태」는 `INFO_UNKNOWN` / `INFO_NEEDS_REVIEW`로 이미 갈라진다.

`source.observability`는 `contract-evidence-record-needs.md`의 `EvidenceValue.source`가 소유한다. **`case`가 `source.kind` 문자열을 보고 관찰/추론을 스스로 분류하지 않는다** — 그건 `case`가 정책 판단을 하는 것이라 §3 「authoritative 판단을 재계산하지 않는다」에 걸린다.

`source_label_key`는 `EvidenceValue.source.label_key`(사건시각은 `occurred_at.source.label_key`)를 그대로 통과시킨 값이며 키 네임스페이스는 `evidence`가 소유한다. 대응 키가 없으면 `null`로 두고 web이 fallback 문구를 쓴다.

**`progress[]`의 step 집합 규칙 — 확정 (v1.3, 2026-09-10, 유소연, 이슈 #31 W-7)**

`progress[]`가 담는 step 개수가 시나리오마다 8/7/5/3개로 갈려 있던 것을 정리한다. 규칙: **이 case가 밟을 계획인 step만 담되, "계획"의 기준은 시나리오가 실제로 다루는 모듈 범위다.** 구체적으로:

1. 이 시나리오가 다루는 모든 모듈이 최종적으로 `package_assembly`까지 이어질 수 있는 경우(`happy`·`correction_rerun`·`plate_reread`·`unknown_abstain_partial`), **도달 여부와 무관하게 8단계 전부**를 싣는다 — 아직 도달하지 않은 step은 `PENDING`으로 표시한다.
2. 시나리오 카탈로그가 특정 모듈을 `modules_intentionally_absent`로 명시했다면, 그 모듈에 대응하는 step은 **`PENDING`으로도 넣지 않고 배열에서 아예 뺀다** — 이 CaseView는 애초에 그 단계에 도달할 계획이 없기 때문이다(예: `infra_failure_001`은 evidence 모듈이 없어 `evidence_assembly`부터 이후 3단계를 빼고, `relative_rebase_001`은 readout·evidence 모듈이 모두 없어 `plate_read`부터 이후 5단계를 뺀다).
3. `candidates=[]`로 이 case의 진행이 구조적으로 멈춘 경우(`empty_001`)도 2와 같은 취급이다 — 이후 step은 이 case 생애주기에서 일어날 계획 자체가 없다.
4. **(2026-10-02, PR #224 리뷰, 유소연)** `evidence=null`인 `EVIDENCE_REVIEW`에서 adapter가 선택 후보의 Fine 판정을 보고하면 그것으로 정한다. 음성 결과(`NOT_ASSEMBLED`, #168 [A])는 IncidentClip~package를 시작하지 않으므로 3과 같은 취급이다 — `file_intake`·`coarse_search`·`candidate_review` 3단계만 싣는다. 상황 응답 대기(`AWAIT_SITUATION_RESPONSE`, #165)는 관찰(OCR·시간 source)을 마치고 조립만 응답을 기다리므로 1대로 8단계를 싣는다 — `plate_read`·`overlay_time_read`는 보고된 실행 상태가 없으면 `DONE`, `evidence_assembly` 이후는 `PENDING`. 판정이 없으면 기존대로다. **(2026-10-04, 8-14, 유소연)** 판정 없이 선택 후보 Fine이 **실행 실패**한 경우(`search.visual_verify_failed`와 같은 조건)도 IncidentClip~package가 시작되지 않으므로 음성 결과와 같은 3단계다.

정리 전에는 `relative_rebase_001`이 자신의 카탈로그 선언(readout·evidence 모듈 전체 부재)과 다르게 8단계를 `PENDING`으로 전부 실어 규칙 2를 어기고 있었다 — 3단계(`file_intake`·`coarse_search`·`candidate_review`)로 정정했다. `plate_reread_001`은 evidence/package 모듈이 실제로 존재하는 시나리오인데 `package_assembly`가 빠져 있어 규칙 1 위반이었다 — rev3·rev4 양쪽에 `package_assembly: PENDING`을 추가했다(이 gap이 바로 W-6의 "다음에 뭘 해야 할지 알 수 없는 막다른 화면" 문제의 절반이었다 — 나머지 절반은 `notices[]`에 `case.report_video_not_generated`(INFO, `actions:["GENERATE_REPORT_VIDEO"]`)를 추가해 닫았다).

**`evidence.review_needed` 파생 규칙 — 확정 (2026-09-09, 유소연, Mock Pack 심층 검토 §12 후속)**

`review_needed`(object-level)는 `evidence`(record 단위 `EvidenceRecord`)가 아니라 **`case`가 아래 여섯 개의 `*_display.needs_review`로부터 파생하는 값**이다: `case_type_display` · `report_type_display` · `violation_display` · `plate_display` · `event_time_display` · `location_display`.

```
review_needed = (case_type_display.needs_review OR report_type_display.needs_review OR violation_display.needs_review
                  OR plate_display.needs_review OR event_time_display.needs_review OR location_display.needs_review
                  OR plate_display.info_state==INFO_NEEDS_REVIEW OR event_time_display.info_state==INFO_NEEDS_REVIEW
                  OR location_display.info_state==INFO_NEEDS_REVIEW OR case_type_display.info_state==INFO_NEEDS_REVIEW
                  OR violation_display.info_state==INFO_NEEDS_REVIEW
                  OR report_type_display.info_state==INFO_NEEDS_REVIEW)   # v1.3, report_type_display에 info_state 추가되며 포함
```

즉 **여섯 개 중 하나라도 `needs_review=true`이거나, `info_state`를 가진 필드 중 하나라도 `INFO_NEEDS_REVIEW`이면 `true`**다(v1.3 이전에는 `report_type_display`에 `info_state`가 없어 이 항에서 제외했으나, v1.3에서 `info_state`가 추가돼 이제 `report_type_display.info_state==INFO_NEEDS_REVIEW`도 포함한다 — 이슈 #33 반영). **개정(2026-09-10, 유소연, 이슈 #26 B-web-6)** — 원래는 `needs_review`만 OR했는데, B절 §7-(3) 「대표값이 `user_hint`면 `INFO_NEEDS_REVIEW`」가 `needs_review`를 거치지 않고 바로 `info_state`를 정하는 경로라 원래 식이 이 조합을 놓쳤다(`scenario_happy_001`의 `location_display`가 `needs_review=false`인데 `info_state=INFO_NEEDS_REVIEW`인 사례로 발견). `review_needed`가 "검토 필요한 게 하나라도 있는가"의 요약이라는 원래 의도를 지키기 위해 `info_state` 경로도 포함시켰다 — `needs_review`와 `info_state`가 독립 필드라는 원칙(B절 §7 (4))은 그대로 유지하고, 집계식만 두 경로를 모두 본다. `reason_code`는 `true`가 된 원인이 하나면 그 필드에 대응하는 코드(예: `evidence.event_time_needs_review`, `evidence.location_needs_review`)를, 둘 이상이면 `evidence.multiple_fields_need_review`를 쓴다. `needs_review`·`info_state` 자체를 재계산하지 않으며(§10 불변조건 6과 같은 원칙), object-level `review_needed`와 필드별 값들은 같은 축의 집계일 뿐 서로 다른 정책을 추가하지 않는다.

**`package.report_field_states` — 신설 (v1.3, 2026-09-10, 이슈 #31 A-2 · 신유민 PR #28 요청)**

`report_fields`(평면 `object<string, string|null>`)는 필드 단위 상태(에러/치환/검토 필요 등)를 실을 자리가 없었다(`CONTRACT_CONFLICTS.md` 불명확 항목 10). `report_field_states`를 나란히 추가해 필드별 `{info_state, source_label_key}`를 제공한다. **값 공간은 기존 여섯 `*_display.info_state`와 같다** — 새 상태를 만들지 않는다.

`report_fields`/`report_field_states`의 키와 `evidence.*_display` 출처 대응표:

| `report_fields` 키 | 출처 |
| --- | --- |
| `vehicle_number` | `plate_display` |
| `occurred_at` | `event_time_display` |
| `location` | `location_display` |
| `violation_expression` | `violation_display` |
| `safety_report_type` | `report_type_display` |

`case_type_display`는 `report_fields`에 대응 키가 없다 — 안전신문고 신고 양식에 들어가지 않는 내부 사건 분류 표시이기 때문이다(실제 신고문에 들어가는 것은 `safety_report_type`/`violation_expression`이다). `case`가 `report_fields`/`report_field_states`를 만들 때 이 대응표의 값을 그대로 옮긴다(재계산 없음) — evidence/case 경계의 값 공간을 늘리지 않는다.

**`unconfirmed_fields` 파생 규칙 — 명확화(v1.3)**

```
unconfirmed_fields = [ field for field in report_field_states
                        if report_field_states[field].info_state
                           ∈ {INFO_AI_ESTIMATED, INFO_NEEDS_REVIEW, INFO_UNKNOWN} ]
```

`INFO_SOURCE_VERIFIED`·`INFO_USER_CONFIRMED`인 필드는 `unconfirmed_fields`에 넣지 않는다. `vehicle_number`/`occurred_at`/`location`은 v1.2에서도 이미 `info_state`를 가졌으므로 이 세 필드는 규칙 적용 결과가 바뀌지 않는다. `safety_report_type`/`violation_expression`은 v1.3에서 `report_type_display.info_state`가 처음 생기면서 이번에 `unconfirmed_fields` 계산에 들어간다 — 위 위험 안내 참고.

### 8. 정상 예시

json

```json
{  "case_id": "case_3", "case_rev": 4, "stage": "EVIDENCE_REVIEW", "user_reviewed": false,  "manifest_summary": { "file_count": 42, "ok_file_count": 40, "failed_file_count": 2, "duration_sec": 4680, "range": ["18:03", "19:21"] },  "hints": { "time": "18:30 전후", "vehicle": "흰색 SUV", "situation": "백색 실선 crossing 가능성", "location": "미금역 근처" },  "progress": [ { "step": "SCOPE", "state": "DONE" }, { "step": "COARSE", "state": "DONE" }, { "step": "FINE", "state": "RUNNING" } ],  "candidates": [ { "candidate_id": "c1", "at": "18:31:48", "at_provenance": "recording.filename_time", "at_provenance_label_key": "candidate.at_provenance.filename_time", "observed": "백색 실선 + 흰 SUV가 선을 넘어 인접차로 진입", "thumb_ref": "fr_7c2e91", "selected": true } ],  "evidence": {    "record_id": "ev_88",    "plate_display": { "value": "12가 3476", "needs_review": false, "info_state": "INFO_SOURCE_VERIFIED", "source_label_key": "plate.source.overlay_ocr" },    "event_time_display": { "value": "2026-08-24T18:31:48+09:00", "needs_review": true, "info_state": "INFO_NEEDS_REVIEW", "source_label_key": "time.source.filename_time" },    "location_display": { "value": "미금역 사거리 인근", "needs_review": true, "info_state": "INFO_NEEDS_REVIEW", "source_label_key": "location.source.visual_inference", "coord": null, "search_keyword": "미금역 사거리" },    "review_needed": true,    "reason_code": "LOCATION_LOW_CONFIDENCE"  },  "requirements_evidence": { "readiness": "WARN", "checks": [] },  "requirements_package": null,  "package": null,  "running_jobs": [ { "job_id": "job_52", "kind": "PLATE_READ", "label_key": "job.plate_read", "status": "RUNNING" }, { "job_id": "job_53", "kind": "OVERLAY_TIME_READ", "label_key": "job.overlay_time_read", "status": "PENDING" } ],  "notices": []}
```

> 사건시각이 파일명 계산값이라 `resolution_status=NEEDS_REVIEW` → `INFO_NEEDS_REVIEW`다(`core-user-flow.md` §13의 「파일 기록으로 계산한 시각」 화면과 대응). 위치는 `address`/`place_name`이 있어 대표값이 되었고 `search_keyword`는 별도 필드로 내려갔다. package-scope 검사가 아직 없어 `requirements_package=null`이다.

### 9. 실패 / 부분성공 / UNKNOWN 예시

json

```json
{  "case_id": "case_9", "case_rev": 2, "stage": "CANDIDATE_REVIEW", "user_reviewed": false,  "manifest_summary": { "file_count": 12, "ok_file_count": 10, "failed_file_count": 2, "duration_sec": 2400, "range": ["09:00", "09:40"] },  "hints": { "time": "아침 출근길", "vehicle": null, "situation": "신호위반 목격", "location": null },  "progress": [ { "step": "SCOPE", "state": "DONE" }, { "step": "COARSE", "state": "DONE" } ],  "candidates": [],  "evidence": null,  "requirements_evidence": null,  "requirements_package": null,  "package": null,  "running_jobs": [],  "notices": [    { "code": "PLATE_ABSTAINED", "severity": "WARN", "blocking": false, "message_key": "notice.plate_abstained", "actions": ["MANUAL_PLATE_INPUT"] }  ]}
```

### 10. 불변조건

1. `case_rev`는 반영 시점 리비전이며, 더 최신 case_rev 존재 시 stale
2. `evidence`/`package`가 선택/완료 이전이면 null
3. `package`가 non-null이면 `requirements_package`가 non-null이고 `requirements_package.readiness ∈ {PASS, WARN}`이다 (`contract-requirement-report-package.md` §5.2·§8.1의 Package 생성 조건의 귀결. B02 종결 2026-09-07)
4. `evidence`/`package`는 EvidenceRecord/ReportPackage의 원본 필드를 그대로 포함하지 않는다(safe projection만 포함)
5. `running_jobs[]`는 **case가 아직 결과를 기다리는 job 목록**이다 — Runtime에서 실제 `RUNNING`인 실행 전체가 아니다. `running_jobs=[]`는 **case가 더 기다리는 job이 없다**는 뜻이며, baseline web polling은 이때 멈출 수 있다. 실행 terminal 기록과 case 반영 · 후속 발주 사이, 자동 retry의 backoff 동안에도 그 job은 빠지지 않는다. 반대로 사용자 중단 · case timeout처럼 case가 기다리기를 멈춘 job은 Runtime execution이 협력적 중단 때문에 아직 `RUNNING`이어도 `running_jobs`에서 빠진다 (2026-10-04 표기 정합, #247 H-4 · #245 C-3)
6. `info_state`는 §7의 확정 규칙으로만 파생한다. `case`가 threshold나 source 분류를 독립 정책으로 추가하지 않는다 (B01 종결 2026-09-07)
7. `stage=READY`는 `PACKAGE_READY` 파생 gate가 성립한 시점이며, gate 자체는 `RequirementReport`/`ReportPackage`가 소유한다. `case`는 gate를 재계산하지 않는다
8. **`user_reviewed`(workflow) · `evidence.user_edited`(record 단위) · `info_state=INFO_USER_CONFIRMED`(필드 단위 `user_corrected` 파생)는 서로 다른 세 가지 사실이며 하나로 합치지 않는다.** `contract-time-resolution.md` §10 항목 5 「`user_corrected`는 `USER_REVIEWED` workflow 상태와 동일하지 않다」와 같은 구분이다
9. `stage=READY`이면 `requirements_package`가 non-null이고 `readiness ∈ {PASS, WARN}`이다. `READY`가 `PACKAGE_READY` 파생 gate이고 그 gate는 현재 basis의 `FINAL_PACKAGE` scope report로만 성립한다 (B02 종결 2026-09-07)
10. `requirements_evidence`·`requirements_package`는 §7의 3단계 선택 규칙을 통과한 report만 싣는다. **이전 basis(`EvidenceRecord.record_ref`가 다른) report는 현재 판정으로 대체 사용하지 않는다.** 사용자 수정 직후 재검사 전이면 `null`이 정상이다
11. `EVIDENCE_SUFFICIENT` / `PACKAGE_READY` / `USER_REVIEWED`를 하나의 readiness 값으로 합쳐 내려보내지 않는다
12. web은 `info_state`로만 표시 분기한다. `needs_review`를 직접 해석하지 않는다
13. **`package.report_field_states`는 `_REPORT_FIELDS` 5개 키(`safety_report_type`·`occurred_at`·`location`·`vehicle_number`·`violation_expression`)를 항상 전부 갖는다.** 값을 만들 수 없는 필드도 키 자체를 생략하지 않고 `{info_state: INFO_UNKNOWN, source_label_key: null}`로 채운다(2026-09-14, 이슈 #47/#48 결과 — `report-package/v1.1`이 `report_inputs.location`을 `null`로, 그리고 그 `null`을 「위치 정보가 없다는 확정된 사실」로 정의한 것에 대응하는 case 쪽 조건. `evidence` 김준영 결정 + `case` 유소연 조건 수용). `scenario_unknown_abstain_partial_001`의 `pkg_u001.report_field_states.location`이 이미 이 모양(`{info_state: INFO_UNKNOWN, source_label_key: null}`)이다.
14. **`candidates[].at_provenance`가 authoritative이고 `at_provenance_label_key`는 그 값에서 case가 파생하는 표시 전용 값이다.** web은 `at_provenance` raw 문자열을 직접 해석하지 않고 `at_provenance_label_key`로만 문구를 고른다(§10-12와 같은 원칙, `stale_revision`/`stale_revision_label_key` 관계와 동형). `at_provenance_label_key`는 키 자체는 항상 존재하고(Y) 값만 `null`일 수 있다 — 매핑되지 않는 raw 값이 와도 필드를 생략하지 않는다(§10-13과 같은 표기 원칙). `at_provenance`와 `event_time_display.source_label_key`(=`occurred_at.source.label_key`)는 서로 다른 질문에 답하는 독립된 값이며 correction 등으로 한쪽만 바뀔 수 있다 — 하나가 다른 하나의 pass-through라고 가정하지 않는다(2026-09-14, 이슈 #39 Required-3 후속, 유소연·신유민 PR 리뷰 코멘트 Q-3 합의).
15. **상황 응답 대기 부분 투영 (v1.8, #239).** 선택 후보의 Fine 판정이 `AWAIT_SITUATION_RESPONSE`(Fine `UNCERTAIN` + 응답 전)이면 EvidenceRecord가 없어도 `evidence`를 싣고 `record_id = null`로 둔다. 값의 원천은 evidence `resolve_independent_facts()`가 만든 상황 독립 값(`occurred_at` · `vehicle_number` · `location`)이다 — case는 판독에서 번호판 · 시각 · 위치를 다시 만들지 않는다. `plate_display` · `event_time_display` · `location_display` · `preview_ref` · `plate_preview_ref` · `user_edited`는 조립된 경우와 같은 규칙으로 채운다. 상황에 종속되는 `case_type_display` · `report_type_display` · `violation_display`는 `{code: null, label: null, needs_review: false, info_state: INFO_UNKNOWN, source_label_key: null}`이고, `review_needed` · `reason_code`는 독립 필드만으로 파생된다. 이때 `requirements_evidence` · `requirements_package` · `package`는 `null`이고 `situation_confirmation`은 `NOT_ASKED`로 남는다 — 무응답을 `USER_UNSURE`로 바꾸지 않는다(#171 B-2). 응답 뒤 같은 selection context로 조립하면 `record_id`가 채워지고 상황 독립 값은 부분 투영 때와 같다. `evidence.plate_abstained`는 EvidenceRecord를 basis로 한 `EvidenceNeeds`가 근거라 부분 투영에서는 붙지 않는다

### 11. Consumer Review 반영 요약

| Consumer | 상태 | 반영 내용 |
| --- | --- | --- |
| 신유민(web) | 수정요청 → 반영 완료 | evidence/package safe projection 필드 확정, stage/progress enum 확정, manifest_summary/notices/running_jobs 표시 계약 보완 |
| 김대원(eval) | 승인 | 반영 사항 없음 |
| 김준영(evidence/PM) | 최종 승인 | safe projection 원칙, case의 재계산 금지, projection 필드 의미 경계 및 최종 스키마 승인 |
| 유소연(case Owner) · 신유민(web) | **v1.1 확정 (2026-09-06)** | CALL-1 A안 수용 + `INFO_` 접두어(유소연) · A안 채택과 `source_label_key` display별 배치(신유민) · CALL-5 (1)(2)(3) 확정(유소연). 김준영 이견 없음 |

### 12. Closure 완료 사항

- evidence/package: safe projection·재판정 금지 원칙을 유지한다. 세부 필드 합의는 §13의 Pending으로 분리한다.
- `progress.state`: `PENDING / RUNNING / DONE / FAILED`로 확정.
- `running_jobs.label_key`: 필수 제공. web은 `kind` 문자열을 직접 해석하지 않으며, 미등록/알 수 없는 kind는 `job.generic_processing` fallback을 사용한다.
- `notices.severity`: `INFO / WARN / ERROR`로 확정. 실제 차단 여부는 `blocking`이 결정한다.
- `manifest_summary`: file_count/ok_file_count/failed_file_count/duration_sec는 항상 제공하고, 정상 영상이 하나도 없으면 `range=null`을 허용한다.

**v1.1에서 추가로 닫힌 것 (2026-09-06)**

- `stage=READY`: `PACKAGE_READY` 파생 gate 성립 시점으로 확정. `ownership.md` §7-④가 「통합 전 case Owner가 확인한다」로 넘긴 미결이 닫혔다.
- `requirements.readiness`: `RequirementReport.overall`의 projection으로 확정하고 값 공간을 `PASS/WARN/BLOCK/UNKNOWN`으로 축소.
- `user_reviewed`: v4 §3-6 `USER_REVIEWED`를 내려보내는 통로 확정.
- `info_state` · `source_label_key`: 세 값 display의 필드 채택을 유지. 파생 규칙의 완결성은 당시 Pending B01이었고 v1.2(2026-09-07)에서 종결됐다.
- **종결 철회 — `requirements.scope`:** PM의 단독 확정을 제안/Owner 확인 대기로 되돌렸다(B02). 기존 R-7은 과거 결정 기록이며 현재 수락 근거가 아니다.

**v1.2에서 닫힌 것 (2026-09-07 · 유소연 결정 · 김준영·신유민 확인 · `adr/adr-data-contract-call-closure-2026-09-07.md`)**

- **B01 종결:** `needs_review`는 `evidence`가 값과 함께 제공, `occurred_at` 4단계 변환, 위치 대표값 `address→place_name→user_hint`, `coord`·`search_keyword` 별도 필드, `needs_review`↔`info_state` 독립 + web은 `info_state`만 본다.
- **B02 종결:** `requirements`를 `requirements_evidence` / `requirements_package`로 분리. 선택 3단계는 §7이 소유. 세 gate 분리. §10-3·§10-9 확정, §10-10~12 추가.
- **`thumb_ref`:** `FrameRef`(`fr_` 계열)로 확정(정철원·유소연·신유민). web→recording 직접 호출 금지.
- **W02 잔여:** 네 evidence display 필드는 삭제 의도 없음 — 유지 확정.
- `JobRecord.kind`에 `OVERLAY_TIME_READ` 등재, `label_key` `job.overlay_time_read` 추가.

### 13. 남은 미결 및 별도 종결 항목

- evidence/package projection의 세부 필드명 최종 합의 · `CorrectionRecord.target_field`와 display 필드명 정렬 → 같은 자리에서 처리한다.
- **`candidates[]`의 stale-revision 표시 필드.** `CandidateEvent.span.timeline_revision`이 현재 `RecordingTimeline.revision`과 다르면 `case`가 비교해 「과거 timeline revision 기준」임을 표시한다(B09, 2026-09-07 합의). **필드명·모양은 case Owner가 구현 시 정한다** — 여기서 임의로 만들지 않는다. `adr/adr-data-contract-call-closure-2026-09-07.md` §4.8.
- **`FrameRef` 필드 계약 — 종결 (2026-09-08).** `candidates[].thumb_ref`가 `FrameRef`라는 점과 `FrameRef`의 필드·발급·조회 capability는 `contract-source-asset-media-stream.md` §5·§7이 소유한다(`source-asset-media-stream/v1`, Consumer Review 종결). 목데이터의 `fr_` 예시도 그 계약에서 읽는다 — `mock-pack-v1-refs.md`는 폐기됐다. **`thumb_ref` 이미지 전달 형태**(URL/ref/endpoint)는 그 계약 §9-6 Pending으로 남아 있고, 호출 경계(`case → recording → projection → web`, web→recording 직접 호출 금지)는 §7에 확정돼 있다.
- ~~**재판독 발주의 `JobRecord.kind`**(A절 §7) — case Owner 결정 대기(CALL-12).~~ → **종결 (2026-09-07, 유소연).** `kind=PLATE_READ` + `force_rerun=true`(무조건) · 새 `job_id` · 기존 `ReadoutRun` 갱신 없음. A절 §7 등재. `adr/adr-data-contract-call-closure-2026-09-08.md` §4.1.
- ~~**Fine 발주·Report Video export의 `JobRecord.kind` 미등재**(`04_mock_validation_report.md` §3.3-1) — case Owner 결정 대기.~~ → **종결 (2026-09-09, 유소연).** `FINE_VERIFY`·`REPORT_VIDEO_EXPORT` A절 §7 등재, `label_key` `job.fine_verify`·`job.report_video_export` 추가. `purge_case()`는 `JobRecord` 밖의 관리 동작으로 확정(§8 참고).
- ~~**`CaseView.evidence.review_needed` 파생 규칙 미명시**(`04_mock_validation_report.md` §3.2-3) — case Owner 결정 대기.~~ → **종결 (2026-09-09, 유소연).** 규칙과 근거는 B절 §7 「`review_needed` 파생 규칙」에 등재.
- ~~**`candidates[].at_provenance`/`at_provenance_label_key` 값 공간 미등재**(PR 리뷰 코멘트 Q-3, 신유민 지적) — case Owner 결정 대기.~~ → **종결 (2026-09-14, 유소연·신유민).** 값 공간 두 갈래 정의·`at_provenance_label_key` 신설·매핑표 §7 등재. fixture 반영(`data/mock/case/` 14곳)은 별도 후속 커밋.
- **`PLATE_IMAGE_EXPORT` 출력 제한 전달 모양 — 미결 (이슈 #47).** 첨부 용량 상한은 evidence 정책(ADR-EVIDENCE-002 §3)이 소유하고, case는 그 값을 해석·계산하지 않고 중계만 한다. 요청에 싣는 모양(`max_byte_size` 같은 정수 실행 제약 / evidence 정책을 가리키는 versioned constraint ref)은 evidence·recording·case가 함께 정한다. 「출력 제한을 만족시킬 수 없음」과 일반 생성 실패의 구분 방식도 recording failure taxonomy에서 정해진 뒤 notice 매핑을 확정한다. **실제 발주 코드는 recording의 PLATE_IMAGE export capability 구현 뒤에 붙인다.**
- 최초 수락일 — Owner가 기억하지 못해 **확인 불가**로 유지한다(헤더).
- **별도 종결 항목 —** JobExecution → CaseView 상태 projection: `QUEUED→PENDING`, `RUNNING→RUNNING`, `SUCCEEDED→DONE`, `FAILED/STALE→FAILED`, **`CANCELLED→PARTIAL`(v1.3 추가, `job-execution/v1.1`의 `CANCELLED` 신설에 대응)**. 중단된 job은 상태와 상관없이 `PARTIAL`이다(§7 `progress[].state` 행, 2026-10-05).

### 14. v1.3에서 닫힌 것 (2026-09-10 · 유소연 통합 초안 · 신유민·김준영 PR 리뷰 확인 대상, 이슈 #31/#33)

- `candidates[].situation_confirmation` 값 공간을 `evidence-record/v1.3`의 `situation_response`와 맞춰 `NOT_ASKED | CONFIRMED | CORRECTED | USER_UNSURE`로 정정. 파생 출처(§7) 명시.
- `progress[].state`의 "중단" 표현: 새 enum 값 없이 `CANCELLED→PARTIAL`로 흡수(`CONTRACT_CONFLICTS.md` 불명확 항목 9 종결).
- `evidence.report_type_display`에 `info_state`/`source_label_key` 추가(`CONTRACT_CONFLICTS.md` 불명확 항목 4 잔여 해소, SafetyReportType registry 근거).
- `package.report_field_states` 신설 + `report_fields` 키 매핑표 + `unconfirmed_fields` 파생 규칙 명확화(`CONTRACT_CONFLICTS.md` 불명확 항목 10 종결).

### 15. v1.4에서 닫힌 것 (2026-09-14 · PR 리뷰 코멘트 Q-3, 유소연·신유민 합의)

- `candidates[].at_provenance` 값 공간을 두 갈래(evidence 조립 이후 pass-through / 이전 case 소유 enum)로 정의. §8 예시의 미사용 `TIMELINE_ANCHOR+OFFSET` 폐기.
- `candidates[].at_provenance_label_key`(string|null) 신설. `event_time_display.source_label_key` pass-through 가설은 fixture 전수 대조로 기각, case 소유의 독립 매핑표(`recording.filename_time`·`readout.overlay_ocr`·`recording.timeline_relative_only` 3종)로 대체.
- §10 불변조건 14 추가 — raw/label_key authoritative 관계, 필드 항상 존재 원칙.
- fixture 반영(`data/mock/case/` 7개 파일 14곳)은 이 v1.4 확정의 후속 작업으로 별도 진행한다.
