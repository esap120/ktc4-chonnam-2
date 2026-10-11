# ADR-EVIDENCE-009: 상황 응답 전 진행 범위와 사라진 사건 확인 단계 (#171 B · B-2)

> 상태: **ACCEPTED**
>
> 결정일: `2026-09-29`
>
> Decider / Owner: 김준영 (`evidence` Owner · PM)
>
> 동의: 유소연(`case`, 필수 동의) · 의견: 신유민(`web`) · 김대원(Wireframe)
>
> 적용 범위: 사용자 확인 UX 변경에 따른 [`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md) §2.5·§5.4의 재검토. **rule catalog는 바꾸지 않는다**
>
> 근거: 결정 카드 [#171](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/171)의 `[B] 결정` · `[B-2] 결정` 댓글과 Case 동의 댓글 · [`core-user-flow.md`](../../../product/core-user-flow.md) §10·§15·§20

## 1. 목적

ADR-005 §5.4는 「사용자 확인 단계(§8·§15)의 구성이 바뀌면 이 ADR을 고치지 않고 새 결정으로 기록한다」고 정했다. #145 결과 중심 흐름에서 ADR-005 §2.5가 말한 확인 2단계 중 ① §8 `[이 사건 맞아요]`가 사라졌고, #171이 그 자리를 어떻게 메우는지 정했다. 이 ADR은 그 재검토 결과를 evidence 관점에서 기록한다.

## 2. 결정

### 2.1 B — 상황 응답 전 진행 범위 (A안)

- 상황 응답 전에도 `IncidentClip`·OCR·`TimeResolution` 등 **상황 응답과 독립적인 작업은 진행**한다.
- 실제 사용자 응답 전에는 **최종 `EvidenceRecord`·`ReportPackage`를 완성하지 않는다.**
- 응답 전에 만든 관찰 결과는 보존하고, 응답 뒤 **같은 selection context**에서 조립에 재사용한다.
- `NOT_OBSERVED`는 선행 관찰 대상으로 확대하지 않는다. `NOT_OBSERVED`는 ADR-EVIDENCE-007대로 `EvidenceRecord` 이전에 끝나는 정상 결과다.

### 2.2 B-2 — 응답 기록 시점과 사건 전제 보완

- 신고 상황 응답은 **결과 화면에서 사용자가 실제로 응답 버튼을 누른 시점**에 기록한다. 진행 화면에서는 묻지 않는다.
- 무응답은 `NOT_ASKED`로 유지하고, **시스템이 임의로 `USER_UNSURE`를 만들지 않는다.**
- 별도 「이 사건 맞아요」 확인 단계는 다시 만들지 않는다.
- 사건 전제는 결과 화면의 사건 근거 장면(`preview_ref`)과 handoff 시점의 별도 `USER_REVIEWED`로 보완한다.
- `situation_response`와 `USER_REVIEWED`는 서로 다른 사용자 행위로 유지한다.

## 3. evidence rule에 미치는 영향 — 없음

| 항목 | 처리 |
| --- | --- |
| `package.evidence.situation_response` | ADR-005 D2-c 그대로 — `NOT_ASKED → UNKNOWN`(fail-closed), `USER_UNSURE → WARN`. 응답 전에는 Package가 나가지 않는다 |
| 사건 전제(「이 영상이 그 사건이다」) | 여전히 rule로 판정하지 않는다. ADR-005 §2.5에서 이 전제를 받치던 §8 선택이 사라졌으므로, 이제 **evidence 밖의** `preview_ref` 근거 표시와 `USER_REVIEWED`가 받친다. evidence가 사건 전제를 검증하지 못하는 한계(ADR-005 §7)는 그대로 남는다 |
| `USER_REVIEWED` | evidence 입력이 아니다. case가 기록하는 별도 gate이며 `EVIDENCE_SUFFICIENT`·`PACKAGE_READY`와 합치지 않는다 |
| rule catalog | 변경 없음. 이 ADR은 revision을 발행하지 않는다 |

## 4. 영향을 받는 기존 결정

| 문서 | 절 | 표시 |
| --- | --- | --- |
| ADR-005 | §2.5 확인 2단계 표의 §8 행 | §8 `[이 사건 맞아요]` 단계는 더 이상 없다 — 이 ADR §3 |
| ADR-005 | §5.4 「UX 변경 시 재검토 대상」 | 이 ADR이 그 재검토다. D2-c는 유지 |

## 5. 후속 (이 ADR 범위 밖)

- Fine `UNCERTAIN` + 무응답(`evidence=null`)에서 이미 관찰된 독립 값을 CaseView에 어떤 모양으로 투영할지 — CaseView 후속(#171 C-2 후속, case 소유)
  - **진행 (2026-10-07, [#239](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/239)):** 모양은 case가 정했다(기존 `evidence` 객체, `record_id=null`). evidence는 상황 독립 세 필드만 계산하는 `resolve_independent_facts()`를 냈다(`src/daesingo/evidence/README.md`). 반환값은 EvidenceRecord가 아니다. 그래서 §2.1의 「응답 전 최종 Record 미완성」과 충돌하지 않는다.
- web → case 상황 응답·`USER_REVIEWED` command 경로 — #106
