# ADR-EVIDENCE-008: 번호판 식별 실패와 실행 실패의 Requirement 경계 (#172 D · D-2 · D-3)

> 상태: **ACCEPTED**
>
> 결정일: `2026-09-29`
>
> Decider / Owner: 김준영 (`evidence` Owner · PM) — D · D-3. D-2(Readout 표현 경계)는 신유민(`readout`) 결정을 옮긴 것이다
>
> 동의: 유소연(`case`, D · D-3 필수 동의) · 의견: 정철원(`recording`)
>
> 적용 범위: 번호판 값 표현, `policy/requirement-rules-v4`의 번호판 두 rule(`evidence.vehicle_number.present` · `package.vehicle.plate_visible_in_report_video`)의 outcome 매핑, 번호판 없는 신고문·Package 경로(`report-package/v1.2` · `safety-report-policy/v1.2`)
>
> 근거: 결정 카드 [#172](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/172)의 `[D] 결정` · `[D-2] 결정` · `[D-3] 결정` 댓글 · #146 9/25 Evidence/Product Owner 답변(번호판 식별 실패를 경고 있는 UNKNOWN으로 허용) · [`ADR-EVIDENCE-002`](adr-first-completion-owner-decisions.md) §5.4·§5.6 · [`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md) §5.5·§5.7(I4)

## 1. 목적

「번호판을 읽지 못했다」는 사실이 네 가지 서로 다른 상황에서 같은 모양(값 없음)으로 나타난다. 이 ADR은 그 네 상황을 **값 표현 · Readout 표현 · Requirement outcome** 세 층에서 어떻게 구분할지 확정한다.

지키려는 것은 둘이다.

- #146이 정한 제품 방향 — 번호판 식별 실패 **자체는** 신고자료 blocker가 아니다. 부족한 정보임을 경고하면서 결과까지 준비한다.
- 그러면서도 **실행 실패가 정상적인 경고 결과로 위장되어 `READY`로 흘러가지 않게** 한다.

## 2. 배경

### 2.1 네 상황

| # | 실제 상황 |
| --- | --- |
| 1 | 번호판 영역은 보이나 문자 판독 실패 |
| 2 | 일부 문자만 판독 |
| 3 | 번호판 자체가 보이지 않음 |
| 4 | Readout 실행 실패 / 최종 영상 fact 미생산 |

### 2.2 이 결정 전의 규칙 (v4)

| rule | 조건 | outcome |
| --- | --- | --- |
| `evidence.vehicle_number.present` | 확정 차량번호 있음 / 없음 | `PASS` / `UNKNOWN` |
| `package.vehicle.plate_visible_in_report_video` | 최종 신고영상 관찰 `true` / `false` / 미관찰 | `PASS` / **`BLOCK`** / `UNKNOWN` |

v4는 1·2·3·4를 모두 「값 없음 → `UNKNOWN`」으로 합쳤고, 최종 영상에서 번호판이 안 보이는 것을 `BLOCK`으로 두었다. #146 방향과 맞지 않고, 실행 실패(4)와 판독 실패(1·2·3)를 Requirement 층에서 구분할 수 없었다.

## 3. 결정 상태

| ID | 항목 | 결정자 | 상태 |
| --- | --- | --- | --- |
| D | 번호판 값 표현 원칙 | 김준영 (+Case 동의) | **ACCEPTED** |
| D-2 | 네 상황의 Readout 표현 경계 | 신유민 (+정철원 조건) | **ACCEPTED** — readout 소유. 이 ADR은 옮겨 적기만 한다 |
| D-3 | 상황별 Requirement outcome | 김준영 (+Case 조건 반영) | **ACCEPTED** |

## 4. 결정

### 4.1 D — 값 표현

- 미확보 번호판은 **`null`/부재**로 보존한다. `"UNKNOWN"` 같은 sentinel 문자열을 차량번호로 만들지 않는다. 사용자용 「읽을 수 없음」은 표시 계층이 만든다.
- `IncidentClip` 판독 결과만으로 최종 `REPORT_VIDEO`의 번호판 가시성을 `PASS`/`BLOCK`으로 확정하지 않는다. 최종 영상 가시성은 **I4 관찰이 있을 때만** 확정한다.
- 번호판 식별 실패, I4 미관찰, Readout/I4 실행 실패는 **서로 다른 상태로 유지**한다. 같은 `WARN`으로 합치지 않는다.

### 4.2 D-2 — Readout 표현 (readout 결정, 참고)

| # | 상황 | Readout 표현 |
| --- | --- | --- |
| 1·3 | 글자를 전혀 못 읽음 / 번호판이 안 보임 | `PlateReadout` 존재, `status=UNKNOWN`, value `null`. 현재 판독은 둘을 구분하지 못해 「읽지 못함」 하나로 둔다 |
| 1·2 | 일부라도 읽음 | `PlateReadout` 존재, `NEEDS_REVIEW` + 사유 코드(`PARTIAL_PLATE_READ` 등) |
| 4a | Readout 실행 실패 | `ReadoutRun.outcome=FAILED`(`INFRA`), **`PlateReadout = None`** |
| 4b | I4 미실행 / 최종 영상 fact 없음 | 미관찰 `UNKNOWN`. 실패가 아니다 |
| — | `REPORT_VIDEO` 생성 실패 | Recording 경계(`REPORT_VIDEO_EXPORT_FAILED`). 4a와 따로 둔다 |

1·2행의 「사유 코드 등」에는 `TARGET_AMBIGUOUS`도 들어간다 — 글자를 모두 읽었어도 대상 차량 association이 애매하면 `NEEDS_REVIEW`(abstain)다(사유 값 공간은 `docs/modules/readout/decisions/failure-taxonomy.md`). Evidence는 이 값도 확정 번호판으로 승격하지 않으므로 §4.3의 「일부 판독 / `NEEDS_REVIEW`」 행과 같이 처리된다.

### 4.3 D-3 — Requirement outcome

| 상태 | Requirement |
| --- | --- |
| 차량번호 정상 확보 | `PASS` |
| 정상 판독 수행 후 번호판을 읽지 못함(1·3, `PlateReadout` 존재) | `WARN` — 값 `null`, Package blocker로 두지 않음 |
| 일부 판독 / `NEEDS_REVIEW`(1·2) | `WARN` — 검토·재판독 필요를 표시하되 blocker로 두지 않음 |
| I4가 최종 신고영상에서 번호판 식별 불가를 실제 관찰 | `WARN` — v4의 `BLOCK`을 supersede |
| I4 미실행 / 최종 영상 fact 없음(4b) | `UNKNOWN` |
| Readout 실행 실패로 `PlateReadout = None`(4a) | `UNKNOWN` — 식별 실패 `WARN`으로 치환하지 않는다. 실행 실패는 진행 상태·notice로 별도 노출 |
| `REPORT_VIDEO` 생성 실패 | Recording 경계로 유지 |

세 값의 뜻:

- **`WARN`** = 실제 판독·관찰을 수행했고 번호판 정보가 부족함을 **확인한** 경우
- **`UNKNOWN`** = 아직 판정할 수 없거나 판독 결과 자체가 없는 경우
- **실행 실패** = 위 둘과 별도로 진행 상태·notice에서 노출하는 failure 상태

`PlateReadout` 존재 여부로 1·2·3과 4a를 가르는 것은 Case 조건(#172 `[D-3] Case 의견`)이다. 부재까지 `WARN`으로 두면 4a가 1·3과 같은 `WARN` Package로 나가 case가 `READY`로 올린다 — 실행 실패가 정상 결과로 위장된다. 부재를 `UNKNOWN`으로 두면 FINAL이 `PASS`/`WARN`이 되지 않아 Package-ready와 저절로 구분되고, case는 새 gate를 만들지 않는다.

## 5. Requirement policy 반영 — `policy/requirement-rules-v5`

`requirement_rules_v4.json`은 수정하지 않고 새 revision `src/daesingo/evidence/requirement_rules_v5.json`을 발행한다(`supersedes_policy_ref: policy/requirement-rules-v4`). 바뀌는 rule은 둘이고 나머지 rule·rule 수(`EVIDENCE` 4 · `FINAL_PACKAGE` 무조건 12 + 조건부 1)는 v4 그대로다.

### 5.1 `evidence.vehicle_number.present`

| 조건 | 판별 입력 | v4 | v5 | `reason_code` |
| --- | --- | --- | --- | --- |
| `value_present` | `vehicle_number.value`가 비어 있지 않은 문자열 | `PASS` | `PASS` | `evidence.value_confirmed` |
| `readout_performed_value_absent` | 값 없음 + `provenance.input_refs`에 `plate_readout` ref 있음(= `PlateReadout` 존재) | `UNKNOWN` | **`WARN`** | `evidence.plate_unidentified` |
| `readout_absent` | 값 없음 + `plate_readout` ref 없음(= `PlateReadout = None`) | `UNKNOWN` | `UNKNOWN` | `evidence.plate_readout_missing` |

- 판별은 `EvidenceRecord`가 이미 싣는 계약 필드(`vehicle_number`, `provenance.input_refs`)만 쓴다. 새 입력 필드를 만들지 않는다.
- **판별이 기대는 불변조건:** 현재 selection의 `PlateReadout`이 Evidence 조립 입력으로 존재했을 때에만 `provenance.input_refs`에 해당 `plate_readout` ref가 들어간다. `assemble_evidence()`는 `PlateReadout`이 있으면 그 `candidate_id`·`case_id`·`incident_clip_ref`가 현재 선택과 같은지 확인한 뒤 ref를 넣고, 없으면 넣지 않는다. 이 불변조건은 `contract-evidence-record-needs.md`의 `provenance.input_refs` 설명에 적었다.
- 1·3(`status=UNKNOWN`)과 1·2(`NEEDS_REVIEW`)는 같은 `WARN`이다. 둘의 차이는 재판독 Need(`calculate_evidence_needs()` — `NEEDS_REVIEW`·abstain일 때만 `PLATE_REREAD`)와 표시 문구에서 드러나고, 이 rule은 가르지 않는다.
- 사용자가 번호판을 직접 입력하면 정정값이 `vehicle_number`에 들어와 `value_present`가 된다.

### 5.2 `package.vehicle.plate_visible_in_report_video`

| 관찰 fact | v4 | v5 | `reason_code` |
| --- | --- | --- | --- |
| `observed_true` | `PASS` | `PASS` | `readout.plate_visibility.confirmed` |
| `observed_false` | **`BLOCK`** | **`WARN`** | `readout.plate_visibility.not_visible` (v4의 `….failed`를 대체) |
| `not_observed` | `UNKNOWN` | `UNKNOWN` | `readout.plate_visibility.not_observed` |

- `observed_false`의 `reason_code`를 `failed`에서 `not_visible`로 바꾼다. 「관찰했고 안 보였다」는 실행 실패가 아니므로 `failed`라는 이름을 쓰지 않는다. 다른 두 관찰 rule(`package.time.*`)의 `reason_code`는 바꾸지 않는다.
- **Readout 실행 실패를 이 rule의 `observed_false`로 변환하지 않는다.** 실행이 실패했으면 관찰 fact가 없으므로 `not_observed → UNKNOWN`이다. `observed_false`는 I4가 최종 영상을 실제로 관찰한 결과만 가리킨다.
- `IncidentClip` 판독 결과를 이 fact로 승계하지 않는다(§4.1). I4 Producer는 아직 없다(ADR-005 §5.7).

> **#280에 따른 제거 (2026-10-07).** 이 rule은 [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)으로 MVP `FINAL_PACKAGE`에서 빠졌다(`policy/requirement-rules-v6`). 위 표는 v5의 매핑으로 보존한다. 「관찰 실패를 `observed_false`로 바꾸지 않는다」와 §4.1의 승계 금지는 I4를 다시 도입할 때도 지킨다(ADR-010 §8).

### 5.3 활성 catalog 전환

활성 catalog 선택점은 `policy_catalog.py`의 `_ACTIVE_REQUIREMENT_CATALOG_FILE` 한 곳이며 `requirement_rules_v5.json`으로 바꾼다. 출력 `policy_ref`는 로드한 파일의 값(`policy/requirement-rules-v5`)이다. v5는 신고문 policy로 `safety-report-policy/v1.2`를 참조한다(§6).

## 6. 번호판 없는 Package 경로 — 기존 결정의 구현 완성

#146 Owner 답변과 #172 D-3이 이미 「번호판 식별 실패 자체는 Package blocker가 아니다」를 정했고, #146 답변은 그때 renderer의 `vehicle_number` 필수까지 정합화 대상으로 적었다. 따라서 번호판 없는 신고문·Package 경로는 **새 Product 결정이 아니라 이 결정의 구현 범위**다.

> **작업 이력.** 이 ADR의 첫 판(PR #212 첫 커밋)은 rule 두 건만 바꾸고, Package 입력 쪽 gate 세 곳(아래 표)을 「신고문 문구·계약 개정이 필요한 후속」으로 남겼다. 그 상태에서는 1·2·3의 FINAL이 `package.report.content_length = UNKNOWN`이 되어 Package가 나오지 않았고, `core-user-flow.md` §12 「번호판을 읽지 못한 것 자체는 신고자료를 막지 않는다」와 runtime 결과가 달랐다. 리뷰에서 이를 기존 결정의 미완료로 정정해 같은 PR에서 세 gate를 함께 정렬했다.

| gate | 이전 | 이 ADR 이후 |
| --- | --- | --- |
| `report_inputs.vehicle_number` | `string` 필수 (`report-package/v1.1`) | 키 필수·값 `string \| null` — `report-package/v1.2`. `null` = 판독 수행 후 식별 못 함. sentinel 금지 |
| 신고문 template | 4종 모두 차량번호 문장 전제 (`safety-report-policy/v1.1`) | 번호판 없는 4종 추가 — `safety-report-policy/v1.2`(`decisions/safety-report-policy-v1.2.md`). 번호판 있는 4종은 글자 그대로 |
| `render_required_inputs_by_template` | 모든 mode가 `vehicle_number` 필수 | 번호판 없는 두 mode(`*_without_plate`)는 `vehicle_number` 대신 `plate_readout_performed`를 요구 |
| `build_report_package()` | plate 부재면 `package.input.vehicle_number_missing` | 부재이면서 `PlateReadout`도 없을 때만 그 오류 |

**번호판 없음을 허용하는 판별은 한 곳이다.** §5.1의 「현재 selection의 `plate_readout` ref가 `input_refs`에 있다」를 evidence rule(`WARN`/`UNKNOWN`), 렌더 입력 완전성(`plate_readout_performed`), template 선택, Package builder가 **같은 함수**로 쓴다. 그래서 두 경로가 갈린다.

```text
판독 수행 + 식별 실패 (PlateReadout 있음, 값 없음)
→ EVIDENCE WARN → 번호판 없는 template 렌더 → FINAL은 다른 blocker가 없으면 PASS/WARN
→ ReportPackage(vehicle_number=null) → READY 가능

판독 실행 실패 (PlateReadout 없음)
→ EVIDENCE UNKNOWN → 렌더 입력 불완전 → package.report.content_length UNKNOWN → FINAL UNKNOWN
→ ReportPackage 없음 → READY 불가 · case는 readout.plate_read_failed(ERROR · blocking) 투영(#193)
```

builder는 FINAL이 어떤 이유로 `PASS`/`WARN`이어도 `PlateReadout` 없는 번호판 부재 기록으로는 Package를 만들지 않는다(이중 방어).

### 6.1 provenance 판별의 안정성 검토

`input_refs`로 식별 실패와 실행 실패를 가르는 것이 계약상 안정적인지 검토했다.

| 관점 | 판단 |
| --- | --- |
| 새 필드 없이 계약 필드만 쓰는가 | 예. `provenance.input_refs`는 `evidence-record/v1.3` 필수 필드다 |
| 생산자가 하나인가 | 예. runtime에서 `EvidenceRecord`를 만드는 곳은 evidence `assemble_evidence()` 하나이고(case real 경로 `real_e2e.assemble_evidence_bundle()`도 이것을 부른다), `plate_readout` ref는 `PlateReadout` 입력이 있을 때만 들어간다. 다른 모듈이 이 배열을 채우지 않는다. 공용 Mock fixture(`data/mock/*`)의 Record는 정적 기대값이다 |
| 이전 selection의 ref가 섞일 수 있는가 | 아니다. 조립은 selection 단위로 새 Record를 만들고, `PlateReadout`의 `candidate_id`가 현재 후보와 다르면 조립을 거절한다 |
| 약한 점 | ① 의미가 「ref가 있다」는 **존재 여부**에 걸려 있어, 누군가 조립 밖에서 Record를 만들거나 `input_refs`를 편집하면 판별이 흔들린다 — Record는 immutable이고 조립 밖 생산 경로가 없어서 지금은 성립한다. ② `ReadoutRun.outcome=PARTIAL`인데 `PlateReadout`이 있는 경우는 「판독 수행」으로 본다(D-3이 `PlateReadout` 존재로 가르기로 했다) |
| 대안 | `EvidenceRecord`에 판독 상태 필드를 신설하는 것 — 계약 변경이 크고 D-3이 요구하지 않아 채택하지 않았다. 위 불변조건을 계약 문서에 명시하는 것으로 충분하다고 본다 |

### 6.2 남은 후속 (이 ADR 범위 밖)

- `evidence.plate_abstained`(1·2) notice 계약 등재·발행 — case(#172 `[D-3]` Case 의견). 1·3은 notice 없이 `INFO_UNKNOWN`으로 보인다(#193)
- 결과 화면의 「차량번호 정보가 부족할 수 있다」 안내 문구 — web(#146 답변). CaseView에는 `plate_display.info_state=INFO_UNKNOWN`과 `report_field_states.vehicle_number`가 이미 있다
- 재판독 Need의 필수성·횟수 — `contract-evidence-record-needs.md`
- 최종 `REPORT_VIDEO` 관찰 Producer(I4) — readout 입력 계약 확장 후 case 배선(ADR-005 §5.7). **I4가 없는 동안 실제 runtime의 FINAL은 `plate_visible_in_report_video`가 `not_observed → UNKNOWN`이라 번호판 유무와 관계없이 Package가 나오지 않는다.** 이 제약은 v4부터 있던 것이며 이 ADR이 바꾸지 않는다 — **#280으로 해소(2026-10-07):** [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)이 MVP에서 I4를 만들지 않기로 하고 이 rule을 `policy/requirement-rules-v6`에서 뺐다. I4 미관찰은 더 이상 Package를 막지 않는다
- 1과 3의 구분 — readout이 번호판 영역 검출을 갖기 전까지 「읽지 못함」 하나(D-2)

## 7. 영향을 받는 기존 결정

기존 ADR 본문은 고치지 않고, 해당 절에 이 ADR로 대체됐다는 표시만 단다.

| 문서 | 절 | 대체된 내용 |
| --- | --- | --- |
| ADR-002 | §5.4 `evidence.vehicle_number.present` 행 | 「없음 → `UNKNOWN`」 → `PlateReadout` 존재 여부로 `WARN`/`UNKNOWN` 분리 |
| ADR-002 | §5.6 `package.vehicle.plate_visible_in_report_video` 행 | `observed_false → BLOCK` → `WARN` |
| ADR-005 | §5.5 `plate_visible_in_report_video` 행 | 입력 key 유지는 그대로, outcome 매핑만 v5로 대체 |

## 8. 검증

`tests/evidence/test_plate_boundary_d3.py`가 §4.3 표의 각 행을 활성 catalog → FINAL → 실제 `build_report_package()` → case `mark_ready_if_package_ready()`까지 검증한다.

| 행 | EVIDENCE | FINAL | Package | READY |
| --- | --- | --- | --- | --- |
| 정상 확보 | `PASS` | `PASS` | 생성(`vehicle_number` 값) | 가능 |
| 판독 후 못 읽음(`PlateReadout` 존재, value null) | `WARN` | `PASS`/`WARN` | 생성(`vehicle_number=null`, no-plate template) | 가능 |
| `NEEDS_REVIEW` · abstain | `WARN` + `PLATE_REREAD` Need | `PASS`/`WARN` | 생성(`vehicle_number=null`, 부분 판독값 미사용) | 가능 |
| I4 `observed_false` | — | `WARN` | 생성 | 가능 |
| I4 미관찰 | — | `UNKNOWN` | 없음 | 불가 |
| 실행 실패(`PlateReadout = None`) | `UNKNOWN` | `UNKNOWN`(렌더 입력 불완전) | 없음 · builder도 거절 | 불가 — notice는 `tests/case/test_plate_read_failure_projection.py` |
| 번호판 없는 신고문 | — | — | 4 template 렌더, `UNKNOWN`·차량번호 슬롯 없음, 식별 못 함 문장 포함 | — |
| v4·v1.1 보존 | `requirement_rules_v4.json`의 `observed_false → BLOCK`, 번호판 있는 신고문 문구 v1.1 동일 | | | |

> **#280에 따른 대체 (2026-10-07).** 위 표의 I4 두 행은 v5 기준이다. `policy/requirement-rules-v6`([`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md))에는 그 rule이 없어 I4 미관찰은 FINAL을 막지 않고(Package 생성 · `READY` 가능), 관찰값이 들어와도 판정하지 않는다. `test_plate_boundary_d3.py`의 두 행은 그에 맞춰 바뀌었고, 나머지 행은 그대로다.

계약 검증은 `tests/evidence/test_contract_validation.py`가 `report-package/v1.2`의 `vehicle_number=null` 허용과 빈 문자열·키 누락 거절을 확인한다.
