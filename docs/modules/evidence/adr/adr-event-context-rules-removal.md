# ADR-EVIDENCE-005: 판정 주체가 없는 사건 장면·전후 상황 rule을 `FINAL_PACKAGE`에서 제거한다 (D2)

> 상태: **ACCEPTED**
>
> 결정일: `2026-09-14`
>
> Decider / Owner: 김준영 (`evidence` Owner · PM)
>
> 적용 범위: `policy/requirement-rules-v3`의 `FINAL_PACKAGE` 무조건 rule 구성, 관찰 fact 입력 경계, 통합 항목 I4 범위
>
> 근거 목록: [`reviews/14_instruction-conflict-analysis-and-doc-fixes_2026-09-14.md`](../reviews/14_instruction-conflict-analysis-and-doc-fixes_2026-09-14.md) · [`reviews/13_adr-002-003-implementation_2026-09-14.md`](../reviews/13_adr-002-003-implementation_2026-09-14.md) · [`ADR-EVIDENCE-002`](adr-first-completion-owner-decisions.md) §5.6 · [`core-user-flow.md`](../../../product/core-user-flow.md) §8·§11·§15·§18

## 1. 목적

`FINAL_PACKAGE` 무조건 rule 세 건 — `package.event.violation_visible_in_report_video`, `package.event.pre_context_present`, `package.event.post_context_present` — 을 **catalog에서 제거할 것인지** 확정한다.

세 rule은 [`ADR-EVIDENCE-002`](adr-first-completion-owner-decisions.md) §5.6이 경찰민원24 요건을 근거로 등재했으나, **판정 입력을 생산하는 주체가 제품 안에 없다.** 그 결과 공용 Scenario 전부에서 영구 `UNKNOWN`이 되어 `ReportPackage`가 하나도 발행되지 않는 상태다.

## 2. 배경

### 2.1 현재 관측되는 상태

`docs/modules/evidence/artifacts/first-completion/`의 baseline 네 건을 outcome 분포까지 확인한 결과다.

| Scenario | `FINAL_PACKAGE` overall | Package | `UNKNOWN` check | 나머지 분포 |
| --- | --- | --- | --- | --- |
| H `scenario_happy_001` | `UNKNOWN` | 0 | **이 세 건뿐** | `PASS` 13 |
| U `scenario_unknown_abstain_partial_001` | `UNKNOWN` | 0 | **이 세 건뿐** | `PASS` 10 · `WARN` 3 |
| P `scenario_plate_reread_001` | — | 0 | — | `FINAL_PACKAGE` 평가 대상 아님 |
| R `scenario_correction_rerun_001` | — | 0 | — | 위와 같음 |

**`BLOCK`은 어디에도 없다.** 실패 판정이 아니라 판정 유보다. 세 rule이 제거되면 H는 `PASS`, U는 `WARN`이 되어 두 Package가 즉시 발행된다.

### 2.2 판정 입력의 생산자가 계약 어디에도 없다

`docs/architecture/` 전체에서 `pre_context`·`post_context`·`violation_visible`·「위반 장면」·「위반 전/후」·「전후 상황」·「coverage rule」을 전수 확인했다. **생산자를 정의한 계약이 하나도 없다.** rule code 자체도 `evidence` 모듈 문서에만 존재한다. `docs/modules/recording/`은 README 골격과 메모 한 건이 전부다.

걸린 것은 두 건뿐이며 **둘 다 같은 문장이고 생산자가 아니다** — `contract-requirement-report-package.md:234`와 그 근거 ADR(`contracts/adr/adr-data-contract-call-closure-2026-09-07.md:172`)의 *"`duration + timeline_range`는 `FINAL_PACKAGE`에서 사건 전후 coverage rule을 실제 적용하는 경우 조건부"*. 이것은 **관찰이 아니라 산술 경로를 위한 asset 필드**이며, §2.3이 보이듯 ADR-002가 그 경로를 택하지 않았다.

비교 대상이 있다. 다만 2026-09-20 Owner 재확인 결과, 남아 있는 번호판·시각 가시성 fact도 **최종 `REPORT_VIDEO`를 대상으로 한 Runtime Producer는 아직 계약상 연결돼 있지 않다.**

| 관찰 fact | 현재 Producer 상태 | 계약 상태 |
| --- | --- | --- |
| `plate_visible_in_report_video` | **미연결** — 현재 readout은 `IncidentClip`만 읽으며 최종 `REPORT_VIDEO`를 재관찰하지 않는다 | `contract-plate-overlay-readout.md`의 `input_ref.incident_clip_ref`는 존재하지만 `DerivedAsset(REPORT_VIDEO)` 입력 경로는 없음 |
| `time_overlay_visible` | **미연결** — 현재 overlay readout도 `IncidentClip` 기준 관찰이다 | 위와 동일. 최종 `REPORT_VIDEO` 재관찰 계약이 필요 |
| **사건 장면·전 상황·후 상황** | **없음** | **없음** |

즉 제거한 세 rule과 남은 두 가시성 rule의 차이는 「이미 Producer가 있다」가 아니라, **남은 두 rule은 readout 관찰 기능을 확장해 Producer를 만들 수 있는 구체적 후속(I4)이 등록돼 있다는 점**이다.

### 2.3 ADR-002가 산술 경로를 명시적으로 거절했다

§5.6 「사건 장면과 전·후 상황」이 이렇게 적는다.

> 세 rule의 입력은 AssetFacts의 `duration`/`timeline_range`가 아니라 **실제 관찰 사실**로 받는다. (…) v2는 번호판 가시성과 같은 관찰 경로를 쓰므로 그 조건부 필드를 필수로 승격시키지 않는다.

[`contract-requirement-report-package.md`](../../../architecture/contracts/contract-requirement-report-package.md) §4.6은 `duration + timeline_range`를 *"FINAL_PACKAGE에서 사건 전후 coverage rule을 실제 적용하는 경우에만"* 조건부 필수로 열어 두었다. **그 경로가 있었는데 §5.6이 택하지 않았다.**

즉 세 rule은 **생산자가 없는 경로를 스스로 고른 결과**다. 등재 시점에 「경찰민원24가 요구한다 → check를 둔다」까지는 갔으나 「누가 판정하는가」를 확인하지 않았다. Research 메모(`research/architecture-input-memo.md:94`)도 *"`RequirementReport`에서 별도 check 필요"* 까지만 적고 생산자를 적지 않았다.

### 2.4 제품은 이 판정을 사용자에게 맡기기로 이미 정했다

| 위치 | 내용 |
| --- | --- |
| `core-user-flow.md` §8 | 사용자가 후보 영상을 보고 `[이 사건 맞아요]` / `[아니에요]` / `[조금 전/후예요]` |
| 같은 문서 §11 | *"사용자는 AI의 법적 결론을 평가하는 것이 아니라 **실제 영상과 AI가 관찰한 사건 내용을 비교**한다"* |
| 같은 문서 §15 | *"**AI는 법률적 최종 판정을 요구하지 않는다.** 대신 영상에서 관찰한 상황을 사용자에게 확인시킨다"* — `[맞아요]` / `[다른 상황]` / `[잘 모르겠어요]` |
| 같은 문서 §18 | 신고요건 확인 화면이 실제로 보여주는 것은 **용량과 신고기한** — 측정 가능한 값뿐이다. 위반 전/중/후는 없다 |

**흐름 전체가 "제품은 위반 여부를 판정하지 않는다"는 전제 위에 있다.** 신고영상은 사용자가 §8에서 고르고 §15에서 확인한 결과로 내려온다 — 위반이 그 안에 있다는 것이 이미 전제된 입력이다.

### 2.5 확인은 이미 두 단계로 끝나 있다

사용자 확인은 **두 단계로 나뉘어 있고, evidence에서의 위치가 서로 다르다.** 둘을 뭉뚱그리면 안 된다.

| 단계 | 사용자가 확정하는 것 | evidence에서의 위치 |
| --- | --- | --- |
| §8 사건 선택 `[이 사건 맞아요]` | **이 영상이 내가 신고하려는 사건이다** | **입력의 전제.** 선택된 후보에서 IncidentClip·REPORT_VIDEO가 만들어지므로 evidence는 이미 선택된 결과만 받는다. 판정할 rule이 없고 있어서도 안 된다 |
| §15 상황 확인 `[맞아요]` | **AI가 정리한 위반 상황 설명이 맞다** | `situation_response` → **`package.evidence.situation_response`가 판정**(ADR-002 §5.9 — `CONFIRMED`/`CORRECTED` → `PASS`, `USER_UNSURE` → `WARN`, `NOT_ASKED` → `UNKNOWN`) |

> **#171 B-2에 따른 재검토 (2026-09-29).** 위 표의 §8 `[이 사건 맞아요]` 단계는 #145 결과 중심 흐름에서 사라졌고 다시 만들지 않는다. 사건 전제는 이제 evidence 밖에서 결과 화면의 사건 근거 장면(`preview_ref`)과 handoff 시점의 `USER_REVIEWED`가 받친다. §15 행과 D2-c는 그대로다. [`ADR-EVIDENCE-009`](adr-situation-response-timing.md) §3.

`violation_visible_in_report_video`가 물으려는 「위반이 이 신고영상 안에 있는가」는 **첫 단계가 이미 확정한 입력의 전제**다. 사용자가 고르지 않은 영상은 애초에 REPORT_VIDEO가 되지 않는다. 그 위에서 두 번째 단계가 「그 위반이 어떤 상황인가」를 확인하고, 그것만 evidence의 rule이 판정한다.

즉 세 rule은 **이미 확정된 전제를 다시 묻는 것**이며, 게다가 물을 대상(관찰 fact)을 아무도 만들지 않는다.

## 3. 결정 상태

| ID | 항목 | 상태 |
| --- | --- | --- |
| D2 | 세 rule을 `FINAL_PACKAGE` 무조건 rule에서 제거한다 | **ACCEPTED** |
| D2-a | 제거 범위와 rule 수 — 15 → 12 | **ACCEPTED** |
| D2-b | 요건 확인 책임의 이관처 | **ACCEPTED** |
| D2-c | `situation_response`의 `NOT_ASKED → UNKNOWN` fail-closed 유지 | **ACCEPTED** |
| D2-d | 관찰 fact 입력 key 세 개 제거, 나머지 세 개 유지 | **ACCEPTED** |
| D2-e | 녹화 경계로 전후가 물리적으로 없는 경우 — `recording` 미결로 등재 | **OPEN (recording 소유)** |
| D2-f | 통합 항목 I4 범위를 원래대로(번호판·시각) 되돌린다 | **ACCEPTED** |

## 4. 근거

### 4.1 제품이 스스로 못 한다고 선언한 판정을 정책 엔진이 요구하고 있다

§2.4가 근거다. §15가 *"AI는 법률적 최종 판정을 요구하지 않는다"* 고 명시한 상태에서, evidence가 「위반 장면이 영상에 보이는가」를 `BLOCK` 가능한 rule로 두는 것은 제품 방향과 어긋난다. 「위반 전/중/후가 안 보인다」고 판정해 사용자를 막을 근거가 evidence에 없다.

### 4.2 판정 주체가 없으면 rule은 상태를 만들 뿐 정보를 만들지 않는다

`not_observed → UNKNOWN` 매핑 자체는 옳다. 문제는 **`not_observed`가 영구 상태라는 것**이다. 생산자가 없으므로 어떤 입력에서도 `observed_true`/`observed_false`에 도달하지 못한다. 결과적으로 세 rule은 판정을 더하지 않고 `overall`만 `UNKNOWN`으로 끌어내린다.

§2.1이 그 결과다 — 공용 Scenario 전부 Package 0건이고, 원인이 오직 이 셋이다.

### 4.3 사용자 확인이 이미 같은 요건을 덮는다

§2.5의 두 단계가 근거다. **「이 영상이 그 사건이다」는 §8 선택이 확정한 입력의 전제**이므로 evidence가 판정할 사안이 아니고, **「그 위반이 어떤 상황인가」는 `package.evidence.situation_response`가 판정한다.** 그 rule은 `NOT_ASKED`를 `UNKNOWN`으로 두어 **사용자 확인 없이는 Package가 나가지 않는다.** 요건이 무방비로 열리는 것이 아니다.

### 4.4 클립 span 검산은 evidence의 신고요건 판정이 아니다

`AssetFacts`가 이미 `timeline_range`·`timeline_ref`를 싣고 evidence에 들어오므로, 「대표 사건시점의 전후가 신고영상에 포함되었는가」를 산술로 재는 경로는 기술적으로 가능하다. 실제로 공용 Mock에서 계산하면 H(`300.0~420.0`초 / 대표 `312.48`초)와 U(`600.0~660.0`초 / 대표 `615.0`초) 모두 전후가 확보된다.

그러나 그것이 재는 대상은 **「위반이 보이는가」가 아니라 「클립이 제대로 잘렸는가」** 다. 클립을 자를 때 span을 아는 것은 `recording`이고, 파일 경계 병합도 `recording`이 담당한다(`core-user-flow.md` §16). **생성한 쪽이 보장할 일을 소비하는 쪽이 검산하는 구조**이며, ADR-002 §5.6도 이 경로를 택하지 않았다(§2.3).

## 5. 결정

### 5.1 D2 — 세 rule을 제거한다

새 catalog revision에서 다음 세 rule을 `FINAL_PACKAGE` 무조건 rule 목록에서 **삭제**한다.

- `package.event.violation_visible_in_report_video`
- `package.event.pre_context_present`
- `package.event.post_context_present`

`EVIDENCE` scope의 4개 rule은 건드리지 않는다. 조건부 rule(시각 표시 3개 중 1개 선택)도 그대로다.

### 5.2 D2-a — rule 수와 catalog revision

| 항목 | 값 |
| --- | --- |
| 활성 catalog | `policy/requirement-rules-v4` |
| `supersedes_policy_ref` | `policy/requirement-rules-v3` |
| `EVIDENCE` 기본 rule 수 | 4 (무변경) |
| `FINAL_PACKAGE` 무조건 rule 수 | **15 → 12** |
| `FINAL_PACKAGE` 조건부 rule | 3개 중 정확히 1개 선택 (무변경) |

`requirement_rules_v3.json`은 **한 글자도 고치지 않고 보존한다.** v2와 같은 취급이며 이유도 같다(ADR-003 §5.5) — 고치면 `ACCEPTED` 상태인 ADR의 결정 표를 고쳐야 한다. v3는 **실행된 revision**이므로 v2보다 보존 근거가 강하다.

### 5.3 D2-b — 요건 확인 책임은 두 곳으로 간다

경찰민원24 요건 자체는 실재한다. **`RequirementReport`가 더 이상 확인하지 않는다는 사실을 숨기지 않는다.** 확인 책임은 다음으로 이관된다.

| 요건 | 확인 주체 | evidence에서의 위치 |
| --- | --- | --- |
| 이 신고영상이 사용자가 신고하려는 사건이다 | **사용자** — `core-user-flow.md` §8 사건 선택 | **입력의 전제.** rule 없음(§2.5) |
| 그 위반이 어떤 상황인가 | **사용자** — 같은 문서 §15 상황 확인 | `package.evidence.situation_response`가 판정. `NOT_ASKED → UNKNOWN` fail-closed |
| 신고영상이 대표 사건시점의 전후를 포함한다 | **`recording`** — REPORT_VIDEO 생성 책임 | 판정하지 않는다. §4.4 · D2-e |

### 5.4 D2-c — `situation_response`의 fail-closed를 유지한다

`package.evidence.situation_response`의 `NOT_ASKED → UNKNOWN`을 **그대로 둔다.** 이 rule이 **evidence에 남는 유일한 사용자 확인 관문**이 되므로, 확인이 없는 상태에서 Package가 나가면 안 된다. (§8 선택은 입력의 전제라 rule로 나타나지 않는다 — §2.5.)

`USER_UNSURE → WARN`도 유지한다. `core-user-flow.md` §15가 *"`잘 모르겠어요`도 진행을 막지 않는다"* 로 이미 정했다.

> **UX 변경 시 재검토 대상.** 사용자 확인 단계(§8·§15)의 구성이 바뀌면 이 관문의 의미도 바뀐다. 그때는 이 ADR을 고치지 않고 새 결정으로 기록한다(§10).
>
> **재검토됨 (2026-09-29).** #171 B-2의 재검토는 [`ADR-EVIDENCE-009`](adr-situation-response-timing.md)에 기록했다. D2-c는 유지된다.

### 5.5 D2-d — 관찰 fact 입력 경계

`evaluate_requirements(..., observation_facts=...)`가 받는 key에서 셋을 뺀다.

| key | 처리 |
| --- | --- |
| `violation_visible_in_report_video` | **제거** |
| `pre_context_present_in_report_video` | **제거** |
| `post_context_present_in_report_video` | **제거** |
| `plate_visible_in_report_video` | 유지 — 최종 `REPORT_VIDEO` 관찰 Producer는 I4에서 연결 |
| `time_overlay_visible` | 유지 — 최종 `REPORT_VIDEO` 관찰 Producer는 I4에서 연결 |
| `post_stamp_applied` | 유지 — 실제 사후각인 수행 사실은 `recording` transform provenance로 확인 |

관찰 fact의 구조 검증(boolean·`subject_refs`)과 `PolicyConfigurationError` 처리는 남는 셋에 그대로 적용된다(ADR-002 §5.12).

> **#172 D-3에 따른 대체 (2026-09-29).** `plate_visible_in_report_video` 입력 key 유지는 그대로이고, 그 rule의 outcome 매핑(관찰 `false → BLOCK`)만 [`ADR-EVIDENCE-008`](adr-plate-identification-failure-boundary.md) §5.2로 `WARN`이 됐다(`policy/requirement-rules-v5`).
>
> **#280에 따른 대체 (2026-10-07).** 위 표의 `plate_visible_in_report_video` · `time_overlay_visible` 두 key는 [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)로 **읽는 rule이 없어졌다**(`policy/requirement-rules-v6`). 들어와도 판정에 영향이 없다. `post_stamp_applied` 행은 그대로다.

### 5.6 D2-e — 남는 구멍을 `recording` 미결로 등재한다 (OPEN)

「사건이 녹화 맨 앞 또는 맨 뒤에 걸려 전(후) 상황이 물리적으로 없는 경우」는 실재하는 실패 케이스다. **이 결정으로 아무도 다루지 않는 상태가 된다.**

- 소유는 `recording`(정철원)이다. REPORT_VIDEO 생성 시점에 span을 아는 유일한 모듈이다.
- `evidence`는 이 항목을 확정하지 않는다. 처리 방식(생성 실패로 볼지, 경고로 볼지, 사용자에게 보일지)은 `recording`과 `case`의 결정이다.
- 등재만 하고 닫지 않는다. 미결은 미결로 남긴다.

### 5.7 D2-f — I4 범위를 되돌린다

[`reviews/10_first-completion_decisions_and_integration_2026-09-13.md:102`](../reviews/10_first-completion_decisions_and_integration_2026-09-13.md)의 I4 정의 **「최종 신고영상의 번호판·시각 표시 여부를 실제 관찰로 전달」을 그대로 유지한다.**

ADR-002 §5.15가 지적한 「I4 범위를 사건 장면·전후 상황까지 넓혀야 한다」는 **이 결정으로 해소된다** — 넓힐 대상이 사라졌다. [`reviews/14_…`](../reviews/14_instruction-conflict-analysis-and-doc-fixes_2026-09-14.md) §5-①의 I4-b 제안도 함께 폐기된다.

**다만 I4 자체는 여전히 필요하다.** 제거 후 `plate_visible_in_report_video`가 무조건 rule에 남는 **유일한 관찰 입력**이 되는데, 현재 공용 입력에서 `mock_only: true`로 주입되고 있어 Mock에서만 값이 있다. **실제 Runtime에서는 I4가 끝나기 전까지 이 rule이 `not_observed → UNKNOWN`이 되어 Package가 다시 막힌다.**

2026-09-20 Owner 재확인으로 I4의 선행 조건도 분명해졌다. 현재 readout 계약은 `IncidentClip`을 입력으로 읽는 경로만 정의하고 있어, 최종 `REPORT_VIDEO(DerivedAsset)`의 번호판·시각 가시성을 다시 관찰하는 Producer는 아직 없다. 따라서 I4는 단순 배선이 아니라 **REPORT_VIDEO를 관찰 대상으로 받을 수 있는 readout 입력 계약/capability 확장 → 관찰 결과를 case가 evidence의 `observation_facts`로 전달**하는 순서로 닫아야 한다. `post_stamp_applied`는 별개로, recording이 실제 각인을 수행한 경우 transform provenance에서 적용 사실을 확인한다.

> **#280에 따른 대체 (2026-10-07).** 위 두 문단의 「I4 자체는 여전히 필요하다」는 MVP에서 성립하지 않는다. #280에서 readout·recording·case가 위 순서의 어느 단계도 MVP 일정으로 잡을 수 없다고 답했고, §2.2가 두 rule을 남긴 전제(「구체적 후속이 등록돼 있다」)가 깨졌다. [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)이 두 rule을 §4.2와 같은 이유로 MVP `FINAL_PACKAGE`에서 뺐다. I4를 다시 열 조건은 그 ADR §8에 있다.

## 6. 검토한 대안

| 대안 | 기각 이유 |
| --- | --- |
| **② `not_observed → WARN`으로 완화** | 판정 주체가 여전히 없어 영구 `WARN`이 된다. 아무도 해소할 수 없는 상시 경고는 정보가 아니라 소음이다. 사용자 고지로 내려가면 「늘 떠 있는 경고」가 되어 §15의 「모르겠다는 대답에 벌을 주지 않는다」 방향과도 어긋난다 |
| **③ 산술(span) 판정으로 전환** | §4.4. 재는 대상이 rule 이름·`reason_code`(`event.violation_visibility`)와 다르고, ADR-002 §5.6이 이 경로를 명시적으로 거절했다. 무엇보다 생성한 쪽(`recording`)이 보장할 일이다 |
| **④ 관찰 경로를 신설(AI 또는 사람이 영상 판정)** | 위반 가시성 판정은 MVP 범위 밖이다. `product-spec.md` §5 Won't 방향이고, §15가 「AI는 법률적 최종 판정을 요구하지 않는다」로 이미 정했다 |
| **⑤ 현행 유지** | 공용 Scenario의 Package가 영구히 0건이다. Consumer(`case`·`web`)가 참조할 `ReportPackage` 예시가 Artifact에서 사라진 상태가 고착된다 |
| **⑥ rule은 두고 `EVIDENCE` scope로 이동** | scope만 바꿔도 판정 주체 문제가 그대로다. `EVIDENCE_SUFFICIENT` gate가 대신 막힌다 |

## 7. 결과와 trade-off

### 긍정적 결과

- **H는 `PASS`, U는 `WARN`으로 Package가 즉시 발행된다.** 공용 Artifact에 `ReportPackage` 실물 예시가 회복된다.
- [`ADR-EVIDENCE-003`](adr-location-absent-package.md) §9의 기대 —「U의 `FINAL_PACKAGE` overall = `WARN`」「`PACKAGE_READY` 성립」— 이 **공용 U에서 성립한다.** D1의 증명이 test-derived 입력에 의존하지 않게 된다.
- ADR-003 §7이 기대한 「`WARN` + 사용자 notice가 있는 Package」 최소 케이스가 재실행 Artifact에서도 살아난다.
- `FINAL_PACKAGE` rule 15개 중 3개가 줄어 판정 경로가 단순해진다.
- 통합 항목 I4가 원래 범위로 돌아가 후속 목록이 실제 작업과 일치한다.

### 감수하는 비용과 한계

- **경찰민원24 요건 한 건을 `RequirementReport`가 더 이상 확인하지 않는다.** 확인 책임이 사용자 확인과 `recording` 생성으로 이관될 뿐 자동 검증은 사라진다. 이 사실을 제품 문서에서 숨기지 않는다.
- **녹화 경계 케이스(D2-e)를 당분간 아무도 다루지 않는다.** 등재만 하고 닫지 않는 미결이다.
- evidence에 남는 **사용자 확인 관문이 `situation_response` 하나**가 된다. §8 선택은 입력의 전제로만 존재해 rule로 검증되지 않으므로, 선택 단계가 깨지면 evidence는 그것을 알아차리지 못한다. 단일점이며 사용자 확인 UX가 바뀌면 함께 재검토해야 한다(§5.4).
- catalog revision이 하나 더 올라간다(v3 → v4). 정책 데이터 파일이 셋(v2·v3·v4)이 되므로 활성 revision 표기를 문서에서 분명히 해야 한다.

## 8. 이 ADR이 결정하지 않는 것

- **`recording`의 REPORT_VIDEO 생성 전략과 span 정책** — 전후 몇 초를 확보할지, 녹화 경계에서 어떻게 처리할지(D2-e). `recording` Owner 소유
- **`contract-requirement-report-package.md` §4.6의 조건부 `duration + timeline_range`** — 「사건 전후 coverage rule을 실제 적용하는 경우에만」이라는 조건이 이 결정으로 성립하지 않게 된다. 필드를 계약에서 빼지 않고 **조건부 그대로 둔다.** 계약 개정 사안이 아니다
- **`package.evidence.situation_response`의 outcome 매핑** — 유지한다(§5.4). 변경은 별도 결정
- **사용자 확인 UX의 구성** — `core-user-flow.md` §8·§15 소유. 바뀌면 §5.4를 재검토
- **공용 Mock fixture 재렌더** — 통합 항목 I2(`case`)
- **`data/mock`의 Scenario 확장** — `scenario_blocked_001` 부재와 `WARN` Package 단일점은 이 결정으로 해소되지 않는다

## 9. 검증

반영 후 다음을 확인한다.

| 확인 | 기대 |
| --- | --- |
| 활성 catalog `policy_ref` | `policy/requirement-rules-v4` — 코드 상수가 아니라 로드한 catalog에서 온 값 |
| `FINAL_PACKAGE` 무조건 rule 수 | **12** |
| H의 `FINAL_PACKAGE` overall | `PASS` · `pkg_h001` 발행 · `PACKAGE_READY` 성립 |
| U의 `FINAL_PACKAGE` overall | `WARN` · `pkg_u001` 발행 · `PACKAGE_READY` 성립 |
| `situation_response` `NOT_ASKED` | `UNKNOWN` 유지 — 사용자 확인 없이 Package가 나가지 않는다 |
| 제거된 세 rule code | 어떤 Report의 `checks[]`에도 등장하지 않는다 |
| 관찰 fact 입력 | 남은 세 key만 소비한다. 제거된 key가 들어와도 rule이 없으므로 판정에 영향이 없다 |
| Artifact | baseline 4종과 `run-summary.json` 어디에도 `policy/requirement-rules-v3`가 없다 |
| `requirement_rules_v3.json` | 파일이 그대로 남아 있고 내용이 바뀌지 않았다 |

## 10. 변경 규칙

- rule catalog는 `policy/requirement-rules-v3`를 덮어쓰지 않고 새 revision을 발행한다. v2·v3 모두 보존한다.
- **관찰 경로가 실제로 생기면**(예: `recording`이 span 보장을 계약으로 내거나 영상 판정 기능이 들어오면) 이 ADR을 수정하지 않고 새 결정으로 rule 재등재를 기록한다.
- 사용자 확인 UX(`core-user-flow.md` §8·§15)가 바뀌어 §5.4의 관문 의미가 달라지면 새 결정으로 기록한다.
- D2-e는 `recording` Owner가 닫는다. `evidence`가 대신 확정하지 않는다.

## 11. 보고

이 결정은 **신고요건 rule 목록 변경**이다. [`cross-cutting-decisions.md`](../../../management/cross-cutting-decisions.md) §B-3이 별도 서명자를 두지 않는 대신 「신고요건 규칙이 바뀌면 주간 회의에 보고한다」를 조건으로 달아 두었으므로 **주간 회의 안건에 올린다.**

특히 D2-b(요건 확인 책임 이관)와 D2-e(recording 미결 등재)는 `recording`·`case` Owner가 알아야 하는 내용이다.

## 12. 구현 발주 범위

이 ADR은 결정이고 실행 증빙의 소유자가 아니다. 반영은 별도 발주로 수행한다.

1. `src/daesingo/evidence/requirement_rules_v4.json` 발행 — v3에서 세 rule 삭제, `supersedes_policy_ref` 표기. **v3는 수정하지 않는다**
2. 활성 catalog 선택점(`policy_catalog.py`) 갱신 — 선택점은 코드에서 한 곳뿐이어야 한다(ADR-002 §5.13 · ADR-004)
3. `_observation_check`의 `reason_roots`에서 제거된 세 code 정리
4. `tests/evidence/fixtures/adapter_inputs.json`의 `final_rules` 기대값과 `requirement_observation_facts` 갱신 — 세 rule code와 세 입력 key 제거
5. 테스트 갱신 — `tests/evidence/test_policy_decisions.py`(`test_k3_catalog_selects_four_and_sixteen_rules_from_data`의 **16 → 13**, 무조건 12 + 조건부 1. 이름도 함께 고친다)와 `tests/evidence/test_mock_integration.py`의 해당 기대값
6. `python -m daesingo.evidence.mock_integration` 재실행, baseline 4종과 `run-summary.json` 갱신. **H·U에 Package가 돌아오는 것을 실제로 확인해 기록한다**
7. `src/daesingo/evidence/README.md`의 활성 catalog 표기 갱신 — 파일이 셋이 되므로 어느 것이 활성인지 한 줄로 분명히
8. [`first-completion-result.md`](../first-completion-result.md) 추적표 갱신
9. 검수 기록은 새 리뷰 보고서로 남긴다(`reviews/15_…`)

## 13. 관련 문서와 증빙

- [`ADR-EVIDENCE-002`](adr-first-completion-owner-decisions.md) §5.6(세 rule 등재와 산술 경로 거절)·§5.12(`UNKNOWN` 갈래)·§5.14(rule 수)·§5.15(I4 범위 지적)
- [`ADR-EVIDENCE-003`](adr-location-absent-package.md) §5.5·§9 — D1 검증 기대가 이 결정으로 공용 U에서 성립
- [`reviews/13_adr-002-003-implementation_2026-09-14.md`](../reviews/13_adr-002-003-implementation_2026-09-14.md) — 지시 간 불일치 최초 기록
- [`reviews/14_instruction-conflict-analysis-and-doc-fixes_2026-09-14.md`](../reviews/14_instruction-conflict-analysis-and-doc-fixes_2026-09-14.md) — 원인 분석. §5-①은 이 ADR로 폐기
- [`core-user-flow.md`](../../../product/core-user-flow.md) §8·§11·§15·§16·§18
- [`contract-requirement-report-package.md`](../../../architecture/contracts/contract-requirement-report-package.md) §4.3(precedence)·§4.6(조건부 asset 입력)·§5.2(`PACKAGE_READY`)
- `research/architecture-input-memo.md:94` — 경찰민원24 요건의 원 근거
- `docs/modules/evidence/artifacts/first-completion/` — §2.1의 관측 근거

## 14. 한 줄 결정

> 제품이 판정하지 않기로 이미 정한 사실을 정책 엔진이 `BLOCK` 가능한 rule로 요구하고 있었고, 그 판정 입력을 생산하는 모듈이 계약 어디에도 없어 공용 Scenario 전부가 영구 `UNKNOWN`으로 막혀 있었다. 사건 장면·전 상황·후 상황 세 rule을 `FINAL_PACKAGE`에서 제거하고(15 → 12) 새 catalog revision `policy/requirement-rules-v4`로 발행하며, 「이 영상이 그 사건이다」는 사용자의 §8 사건 선택이 확정한 **입력의 전제**로 두어 판정하지 않고, 「그 위반이 어떤 상황인가」는 §15 상황 확인을 판정하는 `package.evidence.situation_response`가 `NOT_ASKED → UNKNOWN` fail-closed로 계속 맡으며, 「신고영상이 대표 사건시점의 전후를 포함한다」는 생성 주체인 `recording`의 책임으로 이관하되 녹화 경계 케이스는 닫지 않고 미결로 등재한다.
