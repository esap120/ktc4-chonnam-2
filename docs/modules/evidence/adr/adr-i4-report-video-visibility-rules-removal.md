# ADR-EVIDENCE-010: 최종 신고용 영상 재관찰(I4) 가시성 rule을 MVP `FINAL_PACKAGE`에서 제거한다 (#280)

> 상태: **ACCEPTED**
>
> 결정일: `2026-10-07`
>
> Decider / Owner: 김준영 (`evidence` Owner · PM)
>
> 동의: 유소연(`case`, 필수 동의) · 사실 답변: 신유민(`readout`) · 정철원(`recording`)
>
> 적용 범위: `policy/requirement-rules-v5`의 `FINAL_PACKAGE` rule 두 건(`package.vehicle.plate_visible_in_report_video` · `package.time.overlay_visible`), 관찰 fact 입력 경계, 통합 항목 I4의 MVP 범위
>
> 근거: 결정 카드 [#280](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/280)의 `[I4] 최종 결정` 댓글 · Readout Q1·Q2 · Recording Q3·Q4 · Case Q5·동의 댓글 · [`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md) §2.2·§4.2·§5.5·§5.7·§6 · [`ADR-EVIDENCE-008`](adr-plate-identification-failure-boundary.md) §4.1·§5.2·§6.2

## 1. 목적

최종 신고용 영상(`REPORT_VIDEO`)을 다시 판독해 번호판·시각 표시가 실제로 보이는지 관찰하는 일(통합 항목 I4)을 **MVP에서 만들지 않는다**는 결정에 맞춰, 그 관찰을 입력으로 받는 두 rule을 `FINAL_PACKAGE`에서 뺀다.

## 2. 배경

### 2.1 두 rule이 실제 runtime의 Package를 항상 막았다

| rule | v5에서 언제 | 관찰 `true` | 관찰 `false` | 미관찰 |
| --- | --- | --- | --- | --- |
| `package.vehicle.plate_visible_in_report_video` | **항상** | `PASS` | `WARN` | `UNKNOWN` |
| `package.time.overlay_visible` | 시각이 검증된 원본 overlay에서 확정된 경우(`OK` · `time.verified_overlay_already_present`) | `PASS` | `BLOCK` | `UNKNOWN` |

Producer가 없으므로 실제 runtime(`case/real_e2e.py`의 `observation_facts=None`)에서는 두 rule이 늘 `not_observed → UNKNOWN`이다. Package는 FINAL `overall`이 `PASS`/`WARN`일 때만 만들어지므로, 시각·신고용 영상(C-07)이 모두 풀려도 첫 rule 하나 때문에 Package가 0건으로 남는다(#280 §2 재실행 확인). Mock·web 시연이 `READY`까지 간 것은 `tests/evidence/fixtures/adapter_inputs.json`이 이 값을 `mock_only: true`로 넣어 주었기 때문이다.

### 2.2 ADR-005가 두 rule을 남긴 전제가 깨졌다

ADR-005는 Producer가 없는 rule 세 개를 지우면서 이 두 rule은 남겼다. 이유는 「readout 관찰 기능을 확장해 Producer를 만들 수 있는 **구체적 후속(I4)이 등록돼 있다**」였다(§2.2). #280에서 확인한 사실은 다음과 같다.

| 모듈 | 답변 요지 |
| --- | --- |
| readout (Q1) | 지금은 `IncidentClip`만 읽는다. `REPORT_VIDEO`를 입력으로 받으려면 입력 계약을 확장하고 「보인다/안 보인다」 관찰값을 새로 정해야 한다. 일정은 C-07 이후에야 말할 수 있다 |
| recording (Q3) | C-07(`export_report_video`) 목표 주차는 아직 확정할 수 없다. `REPORT_VIDEO` 생성 자체는 필요하다 |
| case (Q5) | ①(I4 구현)이면 관찰 Job kind 신설과 `observation_facts` 배선이 새로 필요하고, C-07·readout 확장 뒤에야 가능하다 |

즉 I4는 세 모듈이 순서대로 해야 하는 일이고, 어느 단계도 MVP 안의 일정으로 잡혀 있지 않다. ADR-005 §4.2가 지운 세 rule과 같은 상태 — 「판정을 더하지 않고 `overall`만 `UNKNOWN`으로 끌어내린다」 — 가 됐다.

## 3. 결정 상태

| ID | 항목 | 결정자 | 상태 |
| --- | --- | --- | --- |
| I4 | MVP 최종 판정에 최종 영상 가시성 rule을 남기는가 (`time.overlay_visible` 포함) | 김준영 (+Case 동의) | **ACCEPTED — ② 남기지 않는다** |

## 4. 결정

1. **MVP에서는 최종 `REPORT_VIDEO`를 다시 Readout/AI로 판독하는 I4 Producer를 만들지 않는다.**
2. 따라서 Producer가 없는 상태에서 다음 두 rule을 MVP `FINAL_PACKAGE` readiness gate로 두지 않는다.
   - `package.vehicle.plate_visible_in_report_video`
   - `package.time.overlay_visible`
3. **`not_observed → WARN` 같은 완화는 쓰지 않는다.** 관찰하지 않는 항목을 경고로 가장하지 않고 rule을 뺀다. ADR-005 §6 ②의 기각 이유(「아무도 해소할 수 없는 상시 경고는 소음」)가 그대로 적용된다.
4. **`REPORT_VIDEO` 자체는 신고 Package의 필수 자산으로 남는다.** `package.asset.report_video.exists`와 K1 용량·개수 rule은 그대로다. 이 결정은 신고용 영상을 만들지 않는다는 뜻이 아니라, 완성된 신고용 영상을 다시 AI로 검사하지 않는다는 뜻이다.
5. **`PLATE_IMAGE`는 선택 첨부(`OPTIONAL`)로 남는다.** I4를 대신하는 필수 gate로 올리지 않는다. 필수로 하면 「번호판을 읽지 못해도 막지 않는다」(Flow §12 · ADR-008)와 충돌한다. 생성 경로는 #47이 맡는다.
6. 최종 영상 가시성은 **판정하지 않는다.** 「보인다」고도 「안 보인다」고도 말하지 않는다 — `IncidentClip` 판독 결과를 최종 영상 가시성으로 승계하지 않는다는 ADR-008 §4.1은 그대로다.

## 5. Requirement policy 반영 — `policy/requirement-rules-v6`

| 항목 | 값 |
| --- | --- |
| 활성 catalog | `policy/requirement-rules-v6` (`requirement_rules_v6.json`) |
| `supersedes_policy_ref` | `policy/requirement-rules-v5` |
| `EVIDENCE` 기본 rule 수 | 4 (무변경) |
| `FINAL_PACKAGE` 무조건 rule 수 | **12 → 11** — `package.vehicle.plate_visible_in_report_video` 삭제 |
| `FINAL_PACKAGE` 시각 표시 분기 | 4갈래 중 정확히 1갈래 선택(무변경). `OK` · `time.verified_overlay_already_present` 갈래는 **rule을 추가하지 않는다**(`no_rule: true`, `removed_code: package.time.overlay_visible`) |
| 나머지 rule | v5와 같다 |

**시각 표시 갈래를 지우지 않고 `no_rule`로 둔 이유.** selector는 `TimeResolution`의 `status`·`post_stamp.reason_code`로 **정확히 한 갈래**를 고른다(ADR-002 §5.7). 갈래를 지우면 검증된 overlay로 시각을 확정한 정상 입력이 「등록되지 않은 selector 값」으로 `PolicyConfigurationError`가 된다. 갈래는 남겨 selector 검증을 그대로 유지하고, 그 갈래가 고르는 rule만 없앤다. 나머지 세 갈래(`post_stamp_applied` 두 갈래 · `display_unresolved`)는 그대로다.

**`post_stamp_applied`는 이 결정의 대상이 아니다.** 사후 각인 적용 사실은 `REPORT_VIDEO`를 만드는 `recording`의 transform provenance로 확인하는 값이고(ADR-005 §5.5), 최종 영상을 다시 판독하는 I4가 아니다. 그 fact를 전달하는 배선은 C-07과 함께 남은 일이다.

`requirement_rules_v5.json`은 **한 글자도 고치지 않고 보존한다**(ADR-005 §5.2와 같은 이유 — 실행된 revision이다). v5의 두 rule과 `observed_false → WARN`(ADR-008 §5.2)은 v5 안에 그대로 남는다.

### 5.1 관찰 fact 입력 경계

| key | v6 처리 |
| --- | --- |
| `plate_visible_in_report_video` | **읽지 않는다** — 들어와도 선택 rule이 없어 판정에 영향이 없다 |
| `time_overlay_visible` | **읽지 않는다** — 위와 같다 |
| `post_stamp_applied` | 유지 — 구조 검증(boolean · `subject_refs`)과 `PolicyConfigurationError` 처리도 그대로 |

`observation_facts` 인수와 구조 검증 경로(`_observation_fact` · `_observation_check`)는 지우지 않는다. 남은 `post_stamp_applied`가 쓰고, I4를 다시 도입할 때도 같은 경로를 쓴다. `observation_facts=None`은 그 자체로 문제가 아니다 — 관찰 rule이 선택되지 않으면 아무것도 읽지 않는다.

## 6. 검토한 대안

| 대안 | 기각 이유 |
| --- | --- |
| **① I4를 만든다** | C-07 → readout 입력 계약·capability 확장 → case 배선이 순서대로 필요하고 어느 단계도 MVP 일정이 없다(§2.2). 그동안 실제 Package는 0건이다 |
| **`not_observed → WARN`** | ADR-005 §6 ②와 같다. 아무도 해소할 수 없는 상시 경고다. #280 §1에서 다시 묻지 않기로 했다 |
| **번호판 rule만 빼고 `time.overlay_visible`은 남긴다** | Producer가 없고 미관찰이면 `UNKNOWN`인 같은 구조다. 지금 real 입력에 overlay 시각이 없어 드러나지 않았을 뿐, overlay가 검증되는 첫 사건에서 같은 dead gate가 된다 |
| **`PLATE_IMAGE`를 필수로 올려 번호판 근거를 대신한다** | 번호판을 읽지 못한 경우(`best_frame` 없음 · `PARTIAL_PLATE_READ`)에 Package가 막혀 #146 · ADR-008과 충돌한다 |
| **`IncidentClip` 판독 결과로 최종 영상 가시성을 추정한다** | ADR-008 §4.1 · Flow §12가 금지한다. 같은 판독을 두 번 세는 것이다 |

## 7. 결과와 trade-off

### 긍정적 결과

- I4 Producer가 없다는 사실만으로 실제 runtime의 FINAL이 `UNKNOWN`이 되지 않는다. 시각(#235)과 신고용 영상(C-07)이 풀리면 Package가 나올 수 있다.
- Mock·web 시연이 `mock_only` 관찰값 없이 `READY`까지 간다. Mock이 실제 runtime에 없는 Producer를 대신하던 구조가 사라졌다.
- 공용 H는 `PASS`, U는 `WARN`으로 Package가 그대로 발행된다.

### 감수하는 비용과 한계

- **최종 신고용 영상에서 번호판·시각 표시가 실제로 보이는지를 제품이 자동으로 확인하지 않는다.** 예를 들어 `REPORT_VIDEO` 생성 과정에서 화면 시각 표시가 잘리거나 번호판이 흐려져도 `RequirementReport`는 알아차리지 못한다. 그 보장은 `REPORT_VIDEO`를 만드는 `recording`(C-07)의 생성 책임과, 사용자가 결과 화면에서 신고용 영상을 직접 보는 것에 맡긴다. 이 사실을 제품 문서에서 숨기지 않는다(Flow §12).
- 번호판 근거 보완은 선택 첨부 `PLATE_IMAGE`(#47)에 기대며, 만들지 못한 경우에도 Package를 막지 않는다.
- catalog revision이 하나 더 올라간다(v5 → v6). 정책 파일이 다섯(v2~v6)이고 활성은 v6 하나이므로 활성 표기를 README에 분명히 한다.

## 8. 재도입 조건

다음이 모두 갖춰지면 두 rule을 다시 도입할 수 있다. **자동으로 되돌리지 않는다** — 새 ADR 또는 이 ADR을 대체하는 명시적 revision(v7 이상)으로 결정한다.

1. 최종 `REPORT_VIDEO`를 관찰 입력으로 받는 readout 입력 계약과 capability가 있다(#115 순서 — readout 입력 계약 확장 → case 배선 → evidence 전달).
2. 「보인다 / 안 보인다 / 관찰 실패」의 관찰 semantics가 계약에 정의돼 있다. 관찰 실패를 `observed_false`로 바꾸지 않는다는 ADR-008 §5.2 원칙을 지킨다.
3. case가 그 관찰을 `observation_facts`로 실제 runtime 경로에서 전달한다.
4. 제품적으로 재검사가 필요하다는 판단이 있다.

재도입할 때 outcome 매핑(`observed_false → WARN`/`BLOCK`, `not_observed`)은 그때 다시 정한다. v5의 매핑이 자동으로 살아나지 않는다.

## 9. 이 ADR이 결정하지 않는 것

- `REPORT_VIDEO` 생성(C-07) — `recording` 소유. 입력·출력 규격, overlay/post-stamp 처리, 용량 제약
- `PLATE_IMAGE` 생성과 출력 제한 전달 형태 — #47
- readout의 `REPORT_VIDEO` 입력 확장 — I4를 다시 열 때의 `readout` 소유 사안
- case의 I4 관찰 배선 — 같은 이유
- `post_stamp_applied` fact의 실제 runtime 배선 — C-07과 함께
- 다른 Evidence requirement 정책 — 이 ADR은 두 rule만 뺀다

## 10. 영향을 받는 기존 결정

기존 ADR 본문은 고치지 않고, 해당 절에 이 ADR로 대체됐다는 표시만 단다.

| 문서 | 절 | 대체된 내용 |
| --- | --- | --- |
| ADR-002 | §5.6 `package.vehicle.plate_visible_in_report_video` 행 · §5.7 `OK` · `time.verified_overlay_already_present` 행과 `package.time.overlay_visible` 행 | MVP `FINAL_PACKAGE`에서 선택하지 않는다 |
| ADR-005 | §5.5 `plate_visible_in_report_video` · `time_overlay_visible` 행 · §5.7 「I4 자체는 여전히 필요하다」 | 입력 key를 읽지 않는다 · I4는 MVP 범위 밖 |
| ADR-008 | §5.2 · §6.2 I4 행 · §8 「I4 미관찰」 행 | rule이 v6에 없다. 미관찰은 Package를 막지 않는다 |

`core-user-flow.md` §12의 「최종 신고용 영상에서 번호판이 보이는지」 행과 아래 문단도 이 결정에 맞춰 고쳤다.

## 11. 검증

| 확인 | 기대 | 위치 |
| --- | --- | --- |
| 활성 catalog | `policy/requirement-rules-v6`, `supersedes_policy_ref = v5` | `test_plate_boundary_d3.py` · `test_contract_units.py` |
| 두 rule code | 무조건·조건부 어디에도 없다. `FINAL_PACKAGE` 무조건 11개 | `test_i4_rules_removal.py` |
| 번호판 가시성 관찰 없음(`None` · `{}`) | 그 check가 없고 FINAL `PASS`, Package, `READY` | `test_plate_boundary_d3.py` test_4 · `test_i4_rules_removal.py` A |
| 검증된 overlay 갈래 · 관찰 없음 | 시각 표시 check 없음, FINAL `PASS` | `test_i4_rules_removal.py` B · `test_policy_decisions.py` selector |
| legacy 관찰 입력(`false` · 깨진 값) | 판정에 영향 없음 | `test_plate_boundary_d3.py` test_5 · `test_i4_rules_removal.py` B |
| 다른 gate | `REPORT_VIDEO` 없음 → `UNKNOWN` · `UNAVAILABLE` → `BLOCK` · `byte_size` 모름 → `UNKNOWN` · 발생시각 없음 → `UNKNOWN` · `post_stamp_applied` 미관찰 → `UNKNOWN` · 상황 응답 없음 → `UNKNOWN` | `test_i4_rules_removal.py` C |
| 번호판 식별 실패 경계(#172 D-3) | 판독 후 못 읽음 → `WARN` + Package · 실행 실패 → `UNKNOWN` · Package 없음 | `test_plate_boundary_d3.py` 1~3 · 6 |
| `PLATE_IMAGE` 없음 | FINAL `PASS`, Package에 `plate_image_ref` 없음 | `test_i4_rules_removal.py` |
| case real(fixture) 경로 | 상황 응답 뒤 `READY` | `tests/case/test_command.py` |
| v5 보존 | 파일 무변경, 두 rule과 `observed_false → WARN` 그대로 | `test_plate_boundary_d3.py` |

## 12. 보고

이 결정은 **신고요건 rule 목록 변경**이다. [`cross-cutting-decisions.md`](../../../management/cross-cutting-decisions.md) §B-3 · [`decisions/no-separate-signoff.md`](../decisions/no-separate-signoff.md)에 따라 **주간 회의 안건에 올린다.** 보고 요지:

> #280 — MVP에서 최종 `REPORT_VIDEO` 가시성 재검사(I4)를 뺐다. 이유: Producer와 일정이 없고, 실제 runtime Package를 영구 `UNKNOWN`으로 막는 dead gate였다. `REPORT_VIDEO` 생성은 유지하고 `PLATE_IMAGE`는 선택 첨부로 둔다. I4 Producer가 실제로 생기면 rule 재도입을 새 결정으로 검토한다(§8).

## 13. 한 줄 결정

> 최종 신고용 영상을 다시 판독하는 I4 Producer가 MVP 안에 생길 수 없으므로, 그 관찰을 요구하던 `package.vehicle.plate_visible_in_report_video`와 `package.time.overlay_visible`을 `not_observed → WARN` 같은 완화 없이 `policy/requirement-rules-v6`에서 빼고(무조건 12 → 11, 검증된 overlay 시각 갈래는 rule 없음), `REPORT_VIDEO`는 필수 자산으로, `PLATE_IMAGE`는 선택 첨부로 두며, 재도입은 Producer·계약·배선이 갖춰진 뒤 새 결정으로 한다.
