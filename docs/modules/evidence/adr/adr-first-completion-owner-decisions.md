# ADR-EVIDENCE-002: 1차 완료 후 Owner 정책 결정 K1-K4

> 상태: **ACCEPTED** — K1·K2·K3·K4 전부 `ACCEPTED`
>
> 최초 결정일: `2026-09-13`
>
> Decider / Owner: 김준영 (`evidence`)
>
> 적용 범위: evidence 1차 Mock 통합 후 독립적으로 확정할 정책과 registry
>
> 근거 목록: [`reviews/10_first-completion_decisions_and_integration_2026-09-13.md`](../reviews/10_first-completion_decisions_and_integration_2026-09-13.md) §2

## 1. 목적

1차 Mock 통합에서 구현 구조는 연결됐지만, 정책값이 없어 정상 `RequirementReport`를 만들 수 없는 항목과 evidence Owner가 확정해야 할 registry 의미가 남았다. 이 ADR은 후속 목록 K1-K4의 결론을 한 곳에서 관리한다.

이 문서는 K1-K4를 차례로 논의하면서 갱신했고 2026-09-13에 네 항목을 모두 결정했다. 이후 항목이 추가되면 논의 전까지 구현 편의를 위해 채우지 않고 `PENDING_DISCUSSION`으로 남긴다.

## 2. 결정 상태

| ID | 항목 | 상태 | 결정 범위 |
| --- | --- | --- | --- |
| K1 | 첨부 용량·개수 policy | **ACCEPTED** | 대상, byte·개수 상한, 단위, 경계값, UNKNOWN/BLOCK, 출처와 버전 원칙 |
| K2 | 신고기한 policy | **ACCEPTED** | 대표시각, 2개 달력일, 경계, Asia/Seoul, 휴일 연장, 정적 달력, WARN/UNKNOWN, 근거와 버전 |
| K3 | evidence-owned 적용 rule catalog | **ACCEPTED** | catalog version, 두 scope의 기본 rule, Scenario 예외 금지, 시각 표시 분기, K1·K2 포함 위치, 신고유형별 필수성, 실행 실패 처리, 호출 경계 |
| K4 | 발생시각 이외 Correction의 `EvidenceValue.source` provenance | **ACCEPTED** | kind 확장 범위, 채택 대상, source 필드값, 파생값 제외, label fallback, 시각 경로 무변경, registry revision |

K1-K4가 모두 결정되어 ADR 전체 상태를 `ACCEPTED`로 올렸다. 각 항목 표의 상태가 해당 결정의 authoritative 상태다. 이후 변경은 §7에 따라 새 version·revision으로 처리한다.

> **후속 (2026-09-14).** K3가 열어둔 D1(Q1)이 [`ADR-EVIDENCE-003`](adr-location-absent-package.md)으로 종결됐다. **K3는 §5.4·§5.6·§5.8·§5.11·§5.12·§5.14·§5.15 일곱 절이 영향을 받는다** — 각 절에 종결 표시를 달아 두었고 v2 당시 판단은 지우지 않고 보존했다. 그중 §5.12(위치 부재가 `UNKNOWN`이 아니다)와 §5.15 Artifact 영향(D1 반영이 재실행보다 먼저)은 **구현 순서를 바꾸는 내용**이므로 반드시 읽어야 한다. 영향 범위 전체 표는 ADR-003 §5.8에 있다. K1·K2·K4는 영향을 받지 않으며 그 근거도 같은 절에 적었다.

> **후속 3 (2026-09-29).** [`ADR-EVIDENCE-008`](adr-plate-identification-failure-boundary.md)이 **K3의 번호판 rule 두 건의 outcome 매핑을 대체**했다(#172 D-3). 영향 절은 §5.4(`evidence.vehicle_number.present`)·§5.6(`package.vehicle.plate_visible_in_report_video`)이며 각 표 아래에 표시만 달고 원문은 보존했다. 활성 catalog는 `policy/requirement-rules-v5`가 된다. rule 수와 다른 rule은 바뀌지 않는다.

> **후속 4 (2026-10-07).** [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)이 **최종 신고용 영상 재관찰(I4) rule 두 건을 MVP `FINAL_PACKAGE`에서 뺐다**(#280). 영향 절은 §5.6(`package.vehicle.plate_visible_in_report_video`)·§5.7(`package.time.overlay_visible` 갈래)이며 각 표 아래에 표시만 달고 원문은 보존했다. 무조건 rule은 12 → 11, 활성 catalog는 `policy/requirement-rules-v6`가 된다. K1·K2·K4와 다른 rule은 바뀌지 않는다.

> **후속 2 (2026-09-14).** [`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md)가 **K3의 `FINAL_PACKAGE` 무조건 rule 세 건(사건 장면·전 상황·후 상황)을 제거**했다. 판정 입력을 생산하는 모듈이 계약 어디에도 없어 공용 Scenario 전부가 영구 `UNKNOWN`으로 막혀 있었고, 제품은 이 판정을 사용자 확인(`core-user-flow.md` §8·§15)에 맡기기로 이미 정해 두었다. **영향 절은 §5.6·§5.12·§5.14·§5.15**이며 각 절에 표시를 달고 원문은 보존했다. rule 수는 15 → 12, 활성 catalog는 `policy/requirement-rules-v4`가 된다. K1·K2·K4와 D1은 영향을 받지 않는다.

## 3. K1 — 첨부 용량·개수 policy

### 3.1 상태

**ACCEPTED — 2026-09-13**

### 3.2 배경

현재 `package.asset.report_video.size` 구현은 채택된 `report_video_max_bytes`가 없으면 `PolicyConfigurationError`를 발생시킨다. 이는 과거 Research나 Mock의 숫자를 Runtime 정책으로 임의 승격하지 않기 위한 fail-closed 동작이다.

evidence Research는 안전신문고 PC·모바일 화면에서 다음 용량 제한을 관찰했다.

- 이미지 각 30MB
- 동영상 각 130MB
- 전체 첨부 합계 180MB

김준영은 `2026-09-01` 안전신문고 UI에서 다음 개수 제한도 직접 확인했다.

- 이미지 최대 4개
- 동영상 최대 4개
- 이미지와 동영상을 합한 전체 첨부 최대 4개

개수 제한의 화면 캡처는 보존되지 않았다. 이 사실을 숨기거나 별도 증거가 존재하는 것처럼 기록하지 않는다.

### 3.3 결정 — 판정 대상

용량과 개수는 사용자의 원본이나 분석 중간 파일이 아니라 **현재 handoff용 `ReportPackage`에 실제 첨부하려는 자산 집합**을 대상으로 판정한다.

포함:

- 신고 제출용 동영상(`DerivedAsset.derived_role=REPORT_VIDEO`)
- 신고 제출용 이미지(`DerivedAsset.derived_role=PLATE_IMAGE`)
- 이후 Contract에 정식 등재되어 Package 첨부로 선택된 자산

제외:

- 사용자 외부 원본과 `SourceAsset`
- `AnalysisSource`, `IncidentClip`, thumbnail
- Package에 첨부하지 않는 OCR crop과 중간 산출물

동일한 `asset_ref`가 중복 전달되더라도 전체 용량과 개수에는 한 번만 포함한다. 어떤 자산이 Package 첨부 집합에 들어가는지는 ref prefix가 아니라 Contract의 종류·role과 실제 Package 선택으로 판단한다.

### 3.4 결정 — 용량 상한과 단위

| 규칙 | 상한 | 정확한 값 |
| --- | ---: | ---: |
| 이미지 각 파일 | 30 MB | `30,000,000 bytes` |
| 동영상 각 파일 | 130 MB | `130,000,000 bytes` |
| 전체 첨부 합계 | 180 MB | `180,000,000 bytes` |

- `MB`는 decimal로 해석한다. `MiB`로 해석하지 않는다.
- 저장과 비교는 정수 byte로 수행한다.
- `RequirementCheck.measurement.unit`은 `asset.bytes`를 사용한다.
- 화면 표시를 MB로 변환하더라도 판정은 반올림된 표시값이 아니라 원래 byte 값으로 한다.
- 상한과 같은 값은 허용한다. 즉 `actual <= limit`이면 크기 조건을 충족한다.

### 3.5 결정 — 개수 상한

| 규칙 | 상한 |
| --- | ---: |
| 이미지 파일 수 | 4개 |
| 동영상 파일 수 | 4개 |
| 전체 첨부파일 수 | 4개 |

전체 상한이 4개이므로 종류별 상한은 현재 조합에서 결과상 중복될 수 있다. 그러나 외부 UI에서 확인한 규칙의 의미와 향후 독립 변경 가능성을 보존하기 위해 세 값을 각각 정책 데이터로 유지한다.

현재 Final `report-package/v1`은 `report_video_ref` 1개와 optional `plate_image_ref` 1개만 표현한다. 따라서 현 MVP Package는 이 상한보다 좁은 최대 2개 구조다. 최대 4개 첨부를 제품 기능으로 지원하려면 이 K1 정책과 별개로 `ReportPackage.assets` Contract 변경 검토가 필요하다.

### 3.6 결정 — 판정 결과

#### 개별 파일 크기

| 입력 | 결과 |
| --- | --- |
| `byte_size=null` | `UNKNOWN` |
| `byte_size <= 해당 종류 상한` | `PASS` |
| `byte_size > 해당 종류 상한` | `BLOCK` |

#### 전체 첨부 크기

| 입력 | 결과 |
| --- | --- |
| 모든 선택 자산의 크기를 알고 있고 합계가 상한 이하 | `PASS` |
| 알려진 크기의 합만으로 이미 상한 초과 | `BLOCK` |
| 하나 이상 미측정이고 알려진 합만으로 초과를 확정할 수 없음 | `UNKNOWN` |

#### 첨부 개수

| 입력 | 결과 |
| --- | --- |
| 실제 Package 첨부 집합을 확정할 수 없음 | `UNKNOWN` |
| 이미지·동영상·전체 수가 각 상한 이하 | `PASS` |
| 어느 하나라도 해당 상한 초과 | `BLOCK` |

`UNKNOWN`은 판정 보류이고 `BLOCK`은 현재 자산으로 진행 불가다. 둘 다 `FINAL_PACKAGE`의 `PACKAGE_READY`를 성립시키지 않는다.

### 3.7 결정 — 내부 목표 용량을 두지 않음

K1에는 외부 제출 제한보다 낮은 별도 내부 목표를 두지 않는다.

- 최종 파일은 handoff 전에 실제 byte 크기를 측정할 수 있다.
- 제출 가능한 120MB 초과·130MB 이하 영상을 불필요하게 다시 압축하면 번호판과 상황 식별성이 저하될 수 있다.
- 현재는 외부 상한 이내 파일이 계산 차이 때문에 거절된다는 관찰 증거가 없다.

향후 recording 구현에서 가변 인코딩 결과의 반복 초과나 실제 업로드 거절이 관찰되면, 내부 목표는 신고요건이 아니라 `recording` Tech Spec의 생성 전략으로 별도 결정한다. 그 값은 K1의 `PASS/BLOCK` 상한으로 사용하지 않는다.

### 3.8 결정 — 근거와 버전

| 항목 | 값 |
| --- | --- |
| 외부 서비스 | 안전신문고 |
| 확인 방식 | 김준영의 공식 UI 직접 관찰 + evidence Research의 PC·모바일 화면 기록 |
| 최종 확인일 | `2026-09-01` |
| 개수 제한 증거 상태 | 직접 관찰, 화면 캡처 미보존 |
| K1 정책 식별자 | `policy/safety-report-attachment-size/v1` |

기존 Artifact가 이미 가리키는 `policy/requirement-rules-v1`의 의미를 사후 변경하지 않는다. K3은 K1 여섯 rule을 `FINAL_PACKAGE` 기본 catalog에 포함하는 새 immutable revision `policy/requirement-rules-v2`를 발행했다(§5.3·§5.10).

외부 UI 제한이 바뀌면 기존 policy를 덮어쓰지 않고 새 version을 발행한다. 과거 `RequirementReport`는 당시 `policy_ref`로 재현할 수 있어야 한다.

### 3.9 구현·검증 영향

K1 결정으로 다음 구현은 진행할 수 있다.

- 동영상 각 파일 크기 검사
- 이미지 각 파일 크기 검사
- 전체 첨부 byte 합계 검사
- 이미지·동영상·전체 개수 검사
- 각 check의 `measurement.actual/limit/unit` 출력
- 정확한 경계값, 1 byte 초과, `byte_size=null`, 일부 미측정 전체 합계 테스트
- `PASS/UNKNOWN/BLOCK`과 Package 미생성 경계 테스트

다만 다음은 K1이 단독으로 확정하지 않는다.

- `PLATE_IMAGE` 생성 요청과 크기 측정의 실제 cross-module 호출 흐름
- 이미지·영상의 codec, format, 품질, 재압축 횟수
- ~~K1 규칙을 어떤 scope·신고유형에서 기본 실행할지~~ → K3 §5.10에서 확정
- 최대 4개 첨부를 표현하기 위한 `ReportPackage` Contract 확장

`PLATE_IMAGE` 생성·측정 경계는 별도 이슈 초안 [`11_plate-image-generation-and-size-handoff_issue-draft_2026-09-13.md`](../reviews/11_plate-image-generation-and-size-handoff_issue-draft_2026-09-13.md)에서 다룬다.

## 4. K2 — 신고기한 policy

### 4.1 상태

**ACCEPTED — 2026-09-13**

### 4.2 배경과 근거 수준

현재 `package.deadline.within_policy` 구현은 채택된 deadline rule data가 없으면 `PolicyConfigurationError`를 발생시킨다. 이는 `occurred_at + 48 hours` 같은 임의 계산을 막는 fail-closed 동작이다.

evidence Research와 연결된 공식 자료에서 다음을 확인했다.

- 경찰민원24는 교통법규 위반 공익신고를 위반일로부터 2일 이내 신고하도록 안내한다.
- 안전신문고 앱 안내와 2026년 TS 한국교통안전공단 사례는 위반일 다음 날부터 2개 달력일을 세고, 말일이 주말·공휴일이면 다음 첫 평일까지 연장하는 계산을 보여준다.
- TS 사례는 `2026-03-03(화) 위반 → 2026-03-05(목)까지`, `2026-03-06(금) 위반 → 2026-03-09(월)까지`다.
- 과거 국민권익위원회 의결정보가 인용한 당시 경찰 `교통단속 처리지침`에는 기한 경과 신고를 교통질서 안내장 발송에 의한 경고처리 대상으로 둔 구조가 있었다. 이는 기한 경과와 시스템상 제출 불가능이 같지 않다는 참고 근거지만, 현재도 반드시 경고처리된다는 근거로 사용하지 않는다.
- 별도 공휴일 snapshot Research는 2026·2027 날짜를 최신 법령, 인사혁신처, 우주항공청 월력요항, 중앙선거관리위원회 자료로 교차 확인했다.

2025-06-30 발표된 `2026년 월력요항`은 당시 법령 기준 공휴일 20일을 제시했지만, 이후 노동절·제헌절과 두 날의 대체공휴일이 2026년부터 적용되었다. 따라서 오래된 월력요항을 단독 기준으로 삼지 않고 최신 법령·인사혁신처 자료로 보정한다. `2026-06-03` 제9회 전국동시지방선거도 공휴일로 지정되는 선거일이므로 포함한다.

Research PDF 본문 일부의 괄호 출처명 `공정거래위원회`는 연결된 실제 출처와 일치하지 않는다. K2의 authoritative 근거 표기는 **국민권익위원회**로 바로잡는다. Research PDF는 조사 당시 기록으로 보존하고 이 ADR에서 잘못된 기관명을 반복하지 않는다.

### 4.3 결정 — 기산 입력과 대표시각

신고기한은 `occurred_at`을 기산 입력으로 하고 `RequirementReport.evaluated_at`을 비교 시각으로 사용한다. 두 값은 모두 offset-aware RFC3339여야 하며 날짜 계산 전 `Asia/Seoul`로 변환한다.

`CandidateEvent.span.start_ms/end_ms`는 coarse 후보 창이고 그 자체가 최종 신고시각 범위가 아니다. 하나의 `occurred_at`을 만들 때 범위의 중앙값이나 끝값을 evidence가 새로 계산하지 않고, Contract가 필수로 제공하는 `representative_ms`를 사용한다. 현재 `TimeResolution`의 `BASE_PLUS_OFFSET` 계산과 같은 원칙이다.

- 정상 입력: 선택된 시간 기준값 + `representative_ms`로 단일 `occurred_at`을 만든다.
- `representative_ms` 부재: 중앙값 fallback을 만들지 않고 Contract 입력 오류로 처리한다.
- 후보 구간이 `Asia/Seoul` 자정을 가로질러 위반일 자체가 달라질 수 있으면 사용자 확인 전 `NEEDS_REVIEW`로 둔다.
- Mock·회귀 Artifact는 오늘 시각으로 다시 평가하지 않고 기록된 `evaluated_at`을 사용한다.

### 4.4 결정 — 2개 달력일과 마감 경계

| 항목 | 결정값 |
| --- | --- |
| 기간 | `2` |
| 단위 | 달력일(`CALENDAR_DAY`) |
| 초일 | 위반일 불산입 |
| Day 1 | 위반일 다음 날 |
| Day 2 | 위반일 다다음 날 |
| 주말 계산 | 토·일도 Day 1/Day 2 계산에는 포함 |
| 말일 연장 | Day 2가 토·일·공휴일이면 다음 첫 비휴일까지 |
| 사용자 기준 경계 | 마감일 전체를 포함 |

마감일 전체 포함은 구현에서 `마감일 다음 날 00:00:00 Asia/Seoul`을 exclusive upper bound로 표현한다. 즉 `evaluated_at < deadline_exclusive_at`이면 기한 내이고, 정확히 `deadline_exclusive_at`부터 기한 초과다. `23:59:59.999...` 값을 직접 만들어 정밀도 차이를 일으키지 않는다.

### 4.5 결정 — 공휴일 범위와 정적 달력

Runtime에서 외부 공휴일 API를 호출하지 않는다. evidence가 소유하는 versioned JSON에 **2026년과 2027년** 공휴일 snapshot을 미리 보관하고 deadline evaluator는 이 로컬 데이터만 읽는다.

공휴일 조사 결과를 검토해 **2026년 22일, 2027년 24일**을 채택했다. 날짜는 연도별 오름차순, 중복 없음, 실제 요일, `source_ids` 참조 무결성을 검증했고 그 결과를 [`2026·2027 대한민국 공휴일 snapshot 조사`](../research/안전신문고%20교통법규%20위반%20신고기한을%20계산할%20때%20사용할%202026년·2027년%20대한민국%20공휴일%20snapshot.md)에 남겼다.

채택 데이터는 `src/daesingo/evidence/deadline_policy_v1.json`이며 다음을 함께 가진다.

- K2 정책 식별자와 `Asia/Seoul`
- 2개 달력일·초일 불산입·마감 경계 설정
- 토요일·일요일과 휴일 연장 방식
- `2026-01-01`부터 `2027-12-31`까지의 알려진 전국 공휴일 날짜·명칭
- 공휴일 snapshot ref, 출처, 확인일, coverage
- 상태별 `PASS/WARN/UNKNOWN` 매핑

주말은 코드로 계산하고 JSON의 날짜 목록에는 확인된 전국 공휴일·대체공휴일·임시공휴일·공휴일로 지정된 선거일을 둔다. 안전신문고 신고기한에 적용된다는 직접 근거가 없는 지방공휴일은 v1 범위에서 제외한다.

2026-09-13 이후 새 임시공휴일이 지정되어도 자동 감시하거나 v1에 자동 반영하지 않는다. 이 선택은 알려진 운영 한계로 수용한다. 누락된 추가 공휴일은 실제 연장기한보다 이른 `EXCEEDED` 경고를 만들 수 있지만 K2의 `EXCEEDED`는 non-blocking `WARN`이므로 Package 준비를 막지 않는다.

2027년에 기존 v1을 덮어쓰지 않고 2027·2028년 달력을 포함하는 새 policy/calendar revision을 발행한다. 2027년 말 사건처럼 계산 과정에서 2028년 날짜가 필요하지만 새 revision이 아직 없으면 추측하지 않는다.

### 4.6 결정 — 상태와 Requirement outcome

| 입력·계산 상태 | deadline 상태 | `RequirementCheck.outcome` | 진행 |
| --- | --- | --- | --- |
| 확정된 `occurred_at`, 원래 마감일 안 | `OPEN` | `PASS` | 가능 |
| 확정된 `occurred_at`, 휴일 연장 마감일 안 | `EXTENDED` | `PASS` | 가능 |
| 확정된 `occurred_at`, 연장 포함 마감일 경과 | `EXCEEDED` | `WARN` | 경고 후 가능 |
| `occurred_at` 부재 또는 TimeResolution `UNKNOWN` | 계산 상태 없음 | `UNKNOWN` | 판정 보류 |
| 값은 있으나 TimeResolution `NEEDS_REVIEW` | 잠정 `OPEN/EXTENDED/EXCEEDED` | `WARN` | 사용자 확인 필요 |

`NEEDS_REVIEW` 값으로는 예상 마감일을 잠정 계산할 수 있지만 확정된 `PASS`로 내리지 않는다. 잠정 계산 결과와 발생시각 검토 필요 사실을 함께 드러낸다.

### 4.7 결정 — 기한 초과는 WARN이며 제출 blocker가 아님

`EXCEEDED`는 `BLOCK`이 아니라 `WARN`이다. 이를 `CaseView.notices[]`로 투영할 때는 `blocking=false`로 내려 다른 Package 조건이 충족되면 신고 자료 준비를 계속할 수 있게 한다.

권장 사용자 문구:

> **교통법규 위반 신고기한을 경과했습니다. 신고는 계속 준비·제출할 수 있지만, 과태료·범칙금 처분 대신 경고·계도 등으로 처리될 수 있습니다. 실제 처리 결과는 관할 기관의 판단에 따라 달라질 수 있습니다.**

다음 표현은 사용하지 않는다.

- `신고기한 초과 — 제출할 수 없습니다.`
- `기한을 넘기면 반드시 경고처리됩니다.`

첫 번째는 제출 가능성을 근거 없이 차단하고, 두 번째는 최신 경찰 내부 처리지침을 확인하지 않은 상태에서 결과를 단정한다.

### 4.8 결정 — 달력 누락·실패 처리

- 필요한 연도의 snapshot이 존재하고 완전하며 대상 날짜가 목록에 없으면 정상 비공휴일로 처리한다.
- 필요한 연도의 snapshot이 없거나 coverage·형식 검증에 실패하면 `PolicyConfigurationError`로 처리하고 정상 `RequirementReport`를 발행하지 않는다.
- 정책 데이터 실패를 사건 정보 부족을 뜻하는 `UNKNOWN`으로 바꾸지 않는다.
- 외부 API 실패나 네트워크 상태는 Runtime 판정에 참여하지 않는다.

### 4.9 결정 — 근거와 버전

| 항목 | 값 |
| --- | --- |
| K2 정책 식별자 | `policy/safety-report-deadline/v1` |
| 달력 식별자 | `calendar/kr-public-holidays/2026-2027/r1` |
| 시간대 | `Asia/Seoul` |
| 달력 coverage | `2026-01-01` ~ `2027-12-31` |
| 신고기한 근거 확인일 | `2026-09-13` |
| 2026·2027 공휴일 날짜 목록 | 검증 완료: 2026년 22일, 2027년 24일 |
| 공휴일 출처 확인일 | `2026-09-13` (`source_checked_at`) |
| Runtime 외부 API | 사용하지 않음 |
| 정책 데이터 위치 | `src/daesingo/evidence/deadline_policy_v1.json` |

외부 근거:

- 경찰민원24 `교통법규 위반 공익신고`: <https://minwon24.police.go.kr/epeople/trfcLwrgVltnDclr.do>
- TS 한국교통안전공단 `2026년 교통안전 공익제보단 모집 안내`: <https://main.kotsa.or.kr/portal/bbs/notice_view.do?bbscCode=notice&bbscSeqn=18381&menuCode=05010100>
- 국민권익위원회 `공익신고 차량 처분 이의 등(20180723, 시정권고)`: <https://www.acrc.go.kr/board.es?act=view&bid=1010&list_no=27380&mid=a10504010000&nPage=62&tag=>
- 국가법령정보센터 `관공서의 공휴일에 관한 규정`: <https://law.go.kr/lsInfoP.do?lsId=002404>
- 인사혁신처 `올해부터 노동절, 제헌절 공휴일로`: <https://www.mpm.go.kr/mpm/comm/newsPress/newsPressRelease/?boardId=bbs_0000000000000029&category=&cntId=4250&mode=view&pageIdx=1>
- 우주항공청 `2027년 월력요항 발표`: <https://www.kasa.go.kr/prog/plcyBrf/brief/kor/sub01_01_04/view.do?plcyBrfNo=431>
- 중앙선거관리위원회 `제9회 전국동시지방선거 주요사무일정`: <https://www.nec.go.kr/site/nec/ex/bbs/View.do?bcIdx=289351&cbIdx=1104>
- evidence Research `안전신문고 실제 신고 요건 및 초기 4종 유형 매핑 조사` 13~15절
- evidence Research [`2026·2027 대한민국 공휴일 snapshot 조사`](../research/안전신문고%20교통법규%20위반%20신고기한을%20계산할%20때%20사용할%202026년·2027년%20대한민국%20공휴일%20snapshot.md)

기존 Artifact가 가리키는 `policy/requirement-rules-v1`을 사후 변경하지 않는다. K3은 K1·K2와 정확한 calendar revision을 참조하는 새 immutable revision `policy/requirement-rules-v2`를 발행했고, `package.deadline.within_policy`를 `FINAL_PACKAGE` 기본 catalog에 포함했다(§5.3·§5.10).

### 4.10 구현·검증 영향

K2 결정으로 다음 구현은 진행할 수 있다.

- `deadline_policy_v1.json` 로드·형식·coverage 검증
- `representative_ms` 기반 `occurred_at`에서 deadline 계산
- 평일, 금요일, 연속 공휴일, 연말, 마감 직전·정확한 경계·직후 테스트
- `OPEN/EXTENDED/EXCEEDED`와 `PASS/WARN` 연결 테스트
- `occurred_at` 부재·`UNKNOWN`·`NEEDS_REVIEW` 테스트
- 달력 미포함 연도·불완전 snapshot에서 정상 Report 미발행 테스트

2026·2027 공휴일 날짜와 K2 설정 JSON은 작성했다. K2 rule의 기본 catalog 포함은 K3(§5.10)에서 확정했고 실제 연결은 K3 구현에서 수행한다. 이 ADR 결정만으로 기존 Fixture의 숫자나 rule 목록을 조용히 바꾸지 않는다.

## 5. K3 — evidence-owned 적용 rule catalog

### 5.1 상태

**ACCEPTED — 2026-09-13**

### 5.2 배경

현재 `evaluate_requirements()`는 호출자가 `rule_codes`를 직접 넘긴다. 같은 `EvidenceRecord`와 같은 정책 버전이라도 호출자가 다르면 서로 다른 검사 목록이 실행될 수 있고, 어떤 Consumer가 위치 검사나 용량 검사를 빼도 계약상 막히지 않는다.

K1·K2는 개별 rule의 **판정 내용**을 확정했을 뿐, 그 rule을 **언제 실행하는지**는 정하지 않았다. 그래서 K1 값이 확정됐어도 어떤 flow에서도 자동으로 적용되지 않는다. K3는 이 적용표를 evidence가 versioned catalog로 소유한다는 결정이다.

### 5.3 결정 — 새 policy revision을 발행한다

| 항목 | 값 |
| --- | --- |
| K3 catalog 식별자 | `policy/requirement-rules-v2` |
| 데이터 위치 | `src/daesingo/evidence/requirement_rules_v2.json` |
| 참조하는 하위 정책 | `policy/safety-report-attachment-size/v1`(K1) · `policy/safety-report-deadline/v1`(K2) · `calendar/kr-public-holidays/2026-2027/r1` · `safety-report-policy/v1` |

기존 `policy/requirement-rules-v1`의 의미는 사후 변경하지 않는다. v1을 `policy_ref`로 가진 기존 Artifact는 당시 규칙으로 재현 가능한 상태로 보존한다. v2는 새 immutable revision이며, 외부 안내나 하위 정책이 바뀌면 v2를 덮어쓰지 않고 다음 revision을 발행한다.

### 5.4 결정 — `EVIDENCE` 기본 rules

초기 4종(`SIGNAL`·`CENTER_LINE_CROSSING`·`SOLID_LINE_LANE_CHANGE`·`MOTORCYCLE_HELMET_NON_USE`)과 두 `SafetyReportType`에 **동일한 네 rule을 공통 적용**한다. 신고유형별 면제는 두지 않는다.

| rule code | `category` | 조건 | `outcome` |
| --- | --- | --- | --- |
| `evidence.vehicle_number.present` | `VEHICLE` | 확정 차량번호 있음 | `PASS` |
| | | 없음 | `UNKNOWN` |
| `evidence.occurred_at.present` | `TIME` | `resolution_status=OK` | `PASS` |
| | | `resolution_status=NEEDS_REVIEW` | `WARN` |
| | | `occurred_at` 부재 | `UNKNOWN` |
| `evidence.visual_event.present` | `EVIDENCE` | `visual_event_type` 확정 | `PASS` |
| | | `null` + `situation_response=USER_UNSURE` | `WARN` |
| | | 그 외 미확정 | `UNKNOWN` |
| `evidence.location.present` | `LOCATION` | 위치 단서 하나 이상 있음 | `PASS` |
| | | 없음 | `WARN` |

> **#172 D-3에 따른 대체 (2026-09-29).** 위 표의 `evidence.vehicle_number.present` 「없음 → `UNKNOWN`」은 [`ADR-EVIDENCE-008`](adr-plate-identification-failure-boundary.md) §5.1로 대체됐다 — 없음을 `PlateReadout` 존재 여부로 나눠 판독 후 못 읽음은 `WARN`, `PlateReadout` 부재(실행 실패 등)는 `UNKNOWN`이다(`policy/requirement-rules-v5`). 다른 세 rule은 바뀌지 않았다.

Research는 초기 4종 전부에서 번호판 식별·위반일시·발생장소를 baseline 요건으로 둔다. 안전모 미착용이라고 해서 번호판 rule을 빼지 않는다.

`EVIDENCE`에서 위치 부재를 `WARN`으로 두는 이유는 이 scope가 **증거 충분성** gate이기 때문이다. 위치는 나중에 사용자가 입력할 수 있고, 위치가 없다는 이유로 번호판 재판독이나 신고영상 생성까지 멈출 근거는 없다. ~~`FINAL_PACKAGE`에서는 같은 사실을 `UNKNOWN`으로 다르게 판정한다(§5.6).~~

> **D1 종결에 따른 변경 (2026-09-14).** 마지막 문장은 더 이상 유효하지 않다. `FINAL_PACKAGE`도 위치 부재를 **`WARN`**으로 판정한다([`ADR-EVIDENCE-003`](adr-location-absent-package.md) §5.5). 두 scope가 같은 사실을 같은 outcome으로 다루게 됐고, 「위치가 없다는 이유로 다음 단계를 멈추지 않는다」는 이 절의 논리가 `FINAL_PACKAGE`까지 그대로 이어진다. 이 rule의 EVIDENCE scope 매핑 자체는 바뀌지 않는다.

`safety_report_type`과 `violation_expression`은 `evidence-record/v1.3`에서 이미 필수이고 매핑은 [`safety-report-policy-v1.md`](../decisions/safety-report-policy-v1.md)가 소유한다. 항상 `PASS`만 나오는 존재 검사를 catalog에 추가하지 않고, Contract validation과 renderer의 fail-closed 검증에 맡긴다.

### 5.5 결정 — Scenario별 rule 생략을 허용하지 않는다

현재 통합 adapter는 P에서 `evidence.location.present`를, R에서 `evidence.visual_event.present`와 `evidence.location.present`를 뺀 목록을 넣는다. 이는 각 Mock Scenario가 보여주려는 범위만 재현한 **테스트 설정**이지 정책 예외가 아니다.

v2에서는 H/U/P/R 네 Scenario가 모두 같은 `EVIDENCE` 기본 4개를 실행한다. Scenario 차이는 rule 목록이 아니라 **결과값**으로 드러난다. adapter의 rule 목록은 Runtime 입력이 아니라 "정책 엔진이 이 목록을 선택했는가"를 확인하는 기대값으로만 남긴다.

### 5.6 결정 — `FINAL_PACKAGE` 무조건 rules

| rule code | `category` | 조건 | `outcome` |
| --- | --- | --- | --- |
| `package.asset.report_video.exists` | `ASSET` | `availability=AVAILABLE` | `PASS` |
| | | `UNKNOWN` 또는 AssetFacts 부재 | `UNKNOWN` |
| | | `UNAVAILABLE` | `BLOCK` |
| ~~`package.event.violation_visible_in_report_video`~~ | `EVIDENCE` | 관찰 `true` / `false` / 미관찰 | `PASS` / `BLOCK` / `UNKNOWN` — **D2로 제거**(아래) |
| ~~`package.event.pre_context_present`~~ | `EVIDENCE` | 위와 같음 | `PASS` / `BLOCK` / `UNKNOWN` — **D2로 제거** |
| ~~`package.event.post_context_present`~~ | `EVIDENCE` | 위와 같음 | `PASS` / `BLOCK` / `UNKNOWN` — **D2로 제거** |
| `package.vehicle.plate_visible_in_report_video` | `VEHICLE` | 위와 같음 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.location.present` | `LOCATION` | Package 표시용 위치 있음 / 없음 | `PASS` / ~~`UNKNOWN`~~ → **`WARN`**(D1) |
| `package.report.content_length` | `REPORT_CONTENT` | §5.8 | `PASS` / `BLOCK` / `UNKNOWN` — 필수 입력은 선택된 template 기준(D1) |
| `package.evidence.situation_response` | `EVIDENCE` | §5.9 | `PASS` / `WARN` / `UNKNOWN` |
| `package.asset.image.each_size` | `ASSET` | K1 §3.6 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.asset.video.each_size` | `ASSET` | K1 §3.6 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.asset.total_size` | `ASSET` | K1 §3.6 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.asset.image.count` | `ASSET` | K1 §3.6 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.asset.video.count` | `ASSET` | K1 §3.6 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.asset.total_count` | `ASSET` | K1 §3.6 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.deadline.within_policy` | `DEADLINE` | K2 §4.6 | `PASS` / `WARN` / `UNKNOWN` |

> **#172 D-3에 따른 대체 (2026-09-29).** 위 표의 `package.vehicle.plate_visible_in_report_video` 관찰 `false → BLOCK`은 [`ADR-EVIDENCE-008`](adr-plate-identification-failure-boundary.md) §5.2로 `WARN`이 됐다(`policy/requirement-rules-v5`). 관찰 `true → PASS`, 미관찰 `→ UNKNOWN`은 그대로다.

> **#280에 따른 제거 (2026-10-07).** 위 표의 `package.vehicle.plate_visible_in_report_video`는 [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)로 MVP `FINAL_PACKAGE`에서 빠졌다(`policy/requirement-rules-v6`, 무조건 12 → 11). 최종 `REPORT_VIDEO`를 다시 관찰하는 Producer(I4)를 MVP에서 만들지 않기 때문이다. `package.asset.report_video.exists`는 그대로다.

`category`는 Final Contract §3이 고정한 7개 값(`EVIDENCE`·`TIME`·`VEHICLE`·`LOCATION`·`ASSET`·`DEADLINE`·`REPORT_CONTENT`)만 사용한다. 사건 장면·전후 상황은 별도 `EVENT` category를 신설하지 않고 `EVIDENCE`로 분류한다. K3는 evidence 내부 정책이므로 Contract enum을 확장하지 않는다.

#### 사건 장면과 전·후 상황

경찰민원24 공식 안내는 위반 장면, 위반 전 상황, 위반 후 상황을 모두 요구한다. 따라서 세 rule을 v2 catalog에 등재한다. 다만 Research는 구체적인 초 수를 규정하지 않으므로 `pre_event_seconds` 같은 값을 정책 데이터로 저장하지 않는다. v2는 "대표 사건시점의 전과 후가 신고영상에 포함되었는가"까지만 판정하고, 몇 초를 확보할지는 `recording`의 생성 전략으로 분리한다.

세 rule의 입력은 AssetFacts의 `duration`/`timeline_range`가 아니라 **실제 관찰 사실**로 받는다. [`contract-requirement-report-package.md`](../../../architecture/contracts/contract-requirement-report-package.md) §4.6은 `duration + timeline_range`를 "FINAL_PACKAGE에서 사건 전후 coverage rule을 실제 적용하는 경우에만" 조건부 필수로 둔다. v2는 번호판 가시성과 같은 관찰 경로를 쓰므로 그 조건부 필드를 필수로 승격시키지 않는다. 관찰값이 없으면 임의로 `PASS`하지 않고 `UNKNOWN`으로 둔다.

> **D2 종결에 따른 정정 (2026-09-14).** **위 세 rule은 [`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md)로 제거됐다.** 이 절은 「경찰민원24가 요구한다 → check를 둔다」까지만 확인하고 **누가 그 관찰을 생산하는지를 확인하지 않았다.** 계약 문서 어디에도 사건 장면·전 상황·후 상황의 생산자가 없어(`plate_visible`·`time_overlay_visible`은 `readout` 계약이 있는 것과 대비) `not_observed`가 영구 상태가 됐고, 공용 Scenario 네 건 모두 `FINAL_PACKAGE`가 `UNKNOWN`이 되어 `ReportPackage`가 하나도 발행되지 않았다. 바로 위 문단이 산술(`duration`/`timeline_range`) 경로를 거절한 것이 그 원인의 일부다 — 생산자가 없는 경로를 택했다. 제품은 이 판정을 사용자에게 맡기기로 이미 정해 두었고(`core-user-flow.md` §8·§15, 「AI는 법률적 최종 판정을 요구하지 않는다」), 그 확인은 `package.evidence.situation_response`가 이미 판정한다. 근거·대안·이관처는 ADR-005 §4·§6.

#### 위치 — D1 종결로 대체됨 (2026-09-14)

> **이 표의 `package.location.present` 값은 v2 기준이며 D1 종결로 바뀐다.** 아래 원문은 v2를 정할 당시의 판단으로 보존한다. 현재 유효한 결정은 [`ADR-EVIDENCE-003`](adr-location-absent-package.md) §5.5이며, 새 catalog revision에서 위치 부재는 `UNKNOWN`이 아니라 **`WARN`**이다. 같은 revision이 `package.report.content_length`의 필수 입력도 함께 바꾼다 — 그러지 않으면 Package가 다시 `UNKNOWN`으로 사라진다.

`FINAL_PACKAGE`의 위치 부재를 `UNKNOWN`으로 두면 Package가 발행되지 않는다. 이는 현재 Final `report-package/v1`이 `location{display_text}`를 필수로 요구하는 상태, 그리고 `build_report_package`가 `PackageNotReady("package.input.location_missing")`을 내는 현재 동작과 일치한다.

이 값은 [`10_first-completion_decisions_and_integration`](../reviews/10_first-completion_decisions_and_integration_2026-09-13.md) D1(Q1)의 권장안 ②와 같은 방향이지만, **K3가 D1을 단독으로 종결하지 않는다.** D1이 ①(위치 없는 WARN Package 허용)로 결정되면 이 rule의 outcome 매핑을 바꾸는 새 revision을 발행한다. K3는 현재 Final Contract를 따르는 기본값을 정할 뿐이다.

**D1은 2026-09-14에 ①로 결정됐다**([이슈 #48](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/48)). 위에서 예고한 새 revision이 그 결정에 따라 발행된다.

### 5.7 결정 — 시각 표시 조건부 분기

`FINAL_PACKAGE`는 시각 표시 rule을 **정확히 하나만** 실행한다. selector는 `TimeResolution`의 `status`와 `post_stamp.reason_code`다.

| `TimeResolution.status` | `post_stamp.reason_code` | 선택 rule |
| --- | --- | --- |
| `OK` | `time.verified_overlay_already_present` | `package.time.overlay_visible` |
| `OK` | `time.user_confirmed_no_overlay_present` | `package.time.post_stamp_applied` |
| `NEEDS_REVIEW` | `time.no_verified_overlay_present` | `package.time.post_stamp_applied` |
| `UNKNOWN` | `time.no_resolvable_source` | `package.time.display_unresolved` |

`post_stamp.needed`만으로 분기하지 않는다. 현재 `resolve_time` 구현에서 `status=UNKNOWN`이면 `post_stamp.needed=false`가 되므로, `needed`만 보면 "검증된 원본 overlay가 있다"는 반대 의미로 잘못 분기한다. `needed=false`는 "각인이 필요 없다"일 뿐 "overlay가 최종 신고영상에 보인다"가 아니다.

| rule code | `category` | 조건 | `outcome` |
| --- | --- | --- | --- |
| `package.time.overlay_visible` | `TIME` | 최종 신고영상 관찰 `true` / `false` / 미관찰 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.time.post_stamp_applied` | `TIME` | 최종 신고영상 관찰 `true` / `false` / 미관찰 | `PASS` / `BLOCK` / `UNKNOWN` |
| `package.time.display_unresolved` | `TIME` | 항상 | `UNKNOWN` (`reason_code=time.source_unresolved`) |

> **#280에 따른 제거 (2026-10-07).** 위 두 표의 `OK` · `time.verified_overlay_already_present` 갈래가 고르던 `package.time.overlay_visible`은 [`ADR-EVIDENCE-010`](adr-i4-report-video-visibility-rules-removal.md)로 MVP에서 빠졌다. `policy/requirement-rules-v6`에서 그 갈래는 정확히 하나로 선택되지만 rule을 추가하지 않는다(`no_rule`). 나머지 세 갈래와 「정확히 한 갈래」 selector 검증은 그대로다.

`package.time.display_unresolved`는 "어느 시각 표시 rule을 적용할지조차 판정할 수 없다"를 드러내는 rule이다. 값을 모르는 상태를 rule 부재로 감추지 않고 `checks[]`에 남긴다.

세 rule 모두 판정 근거는 **최종 `REPORT_VIDEO`에 대한 실제 관찰**이다. `post_stamp.needed=true`라는 사실만으로 각인 완료를 추정하지 않고, `needed=false`라는 사실만으로 overlay 가시성을 추정하지 않는다. 이는 [`contract-evidence-record-needs.md`](../../../architecture/contracts/contract-evidence-record-needs.md) §4.7 「사건시각 확정 ≠ 영상 내 표시」 분리 원칙을 그대로 따른다.

사용자 입력으로 확정한 시각을 사후 각인한 경로(`time.user_confirmed_no_overlay_present`)는 각인 성공 여부만 이 rule로 판정하고, "객관적 시각 출처 없이 사용자 입력을 각인했다"는 사실은 `requires_user_notice`를 통한 non-blocking 고지로 분리한다. Research는 이 경로를 "별도 경고 후 조건부 허용"으로 두므로 사용자 입력 기반이라는 이유만으로 Package를 차단하지 않는다.

### 5.8 결정 — `package.report.content_length`의 렌더 불가 처리

| 입력 상태 | `outcome` | `reason_code` |
| --- | --- | --- |
| 렌더 성공, 길이 `5..900` | `PASS` | `report.content_length_valid` |
| 렌더 성공, 범위 밖 | `BLOCK` | `report.content_length_invalid` |
| 렌더에 필요한 확정 입력이 아직 없음 | `UNKNOWN` | `report.inputs_incomplete` |
| template·policy 자체가 깨짐 | 정상 Report 미발행 | — |

현재 구현은 `rendered_report`가 없으면 `ContractInputError`를 낸다. `FINAL_PACKAGE` 기본 catalog가 이 rule을 항상 포함하면, 위치나 발생시각이 아직 없는 상태의 `FINAL_PACKAGE` 평가가 정상 `UNKNOWN` Report 대신 통째로 실패한다. 이는 K3가 채택하는 "업무 사실 부족 ≠ 정책 엔진 오류" 원칙과 충돌하므로 v2에서 `UNKNOWN`으로 바꾼다.

렌더에 필요한 확정 입력은 `occurred_at`, Package 표시용 위치, `vehicle_number`, `violation_expression`, 그리고 template을 고르는 `situation_response`다. 이 중 하나라도 없으면 신고문을 만들지 않고 `UNKNOWN`으로 둔다. 값을 임의로 채워 길이를 맞추지 않는다.

> **D1 종결에 따른 변경 (2026-09-14).** 「Package 표시용 위치」는 더 이상 무조건 필수 입력이 아니다. 필수 입력은 **선택된 template 기준**으로 읽는다 — 장소 슬롯이 없는 template을 고르면 위치는 필수가 아니다. 값을 임의로 채우지 않는다는 원칙은 그대로이며, 장소 구절은 지어내지 않고 **뺀다**. [`ADR-EVIDENCE-003`](adr-location-absent-package.md) §5.4·§5.5.

### 5.9 결정 — 사용자 응답 분기

| `situation_response.value` | template | `outcome` | `reason_code` |
| --- | --- | --- | --- |
| `CONFIRMED` | `tmpl/safety-report-specific-v1` | `PASS` | `evidence.situation_confirmed` |
| `CORRECTED` | `tmpl/safety-report-specific-v1` | `PASS` | `evidence.situation_corrected` |
| `USER_UNSURE` | `tmpl/safety-report-generic-v1` | `WARN` | `evidence.visual_event_type_unconfirmed` |
| `NOT_ASKED` 또는 필드 부재 | 선택 불가 | `UNKNOWN` | `evidence.situation_not_asked` |

rule 이름은 기존 `package.evidence.situation_unconfirmed`에서 `package.evidence.situation_response`로 바꾼다. 하나의 rule이 확인·정정·불확실·미응답을 모두 처리하므로 `unconfirmed`라는 이름이 결과를 미리 단정한다.

`USER_UNSURE`는 `BLOCK`이 아니다. [`safety-report-policy-v1.md`](../decisions/safety-report-policy-v1.md)가 generic 신고문과 WARN Package를 이미 허용한다.

`NOT_ASKED`를 `USER_UNSURE`로 자동 치환하지 않는다. 둘은 다른 사실이다. 다만 `NOT_ASKED`를 **정상 Report 미발행**으로 두지 않고 `UNKNOWN`으로 둔다. 사용자가 아직 답하지 않은 것은 업무 사실이 없는 상태이지 정책 엔진 구성 오류가 아니다. 확인 없는 Package 생성은 `build_report_package`의 기존 `package.input.situation_unconfirmed`·`package.input.user_unsure_required` guard와 renderer의 fail-closed가 이미 막는다.

### 5.10 결정 — K1·K2 rule의 포함 위치

- K1 여섯 rule은 `FINAL_PACKAGE`에만 넣는다. K1은 "실제 Package에 첨부할 자산 집합"을 대상으로 확정됐으므로 `EVIDENCE` 단계에 적용할 대상이 없다.
- 기존 `package.asset.report_video.size`는 신고영상 한 개만 검사해 K1의 의미를 담지 못한다. v2에서는 이 code를 사용하지 않고 K1 여섯 rule로 대체한다. v1 Artifact의 기존 code는 그대로 보존한다.
- 현재 Final `report-package/v1`이 표현하는 첨부는 최대 2개이므로 개수 rule은 당분간 구조적으로 `PASS`가 된다. 그래도 K1 §3.5의 의미 보존을 위해 세 개수 rule을 모두 등재한다.
- K2 `package.deadline.within_policy`는 `FINAL_PACKAGE`에만 넣는다. 신고기한은 증거 자체의 충분성이 아니라 "지금 이 Package를 신고용으로 넘길 때의 상태"에 가깝다.

`FINAL_PACKAGE` 평가는 신고영상 생성 전후로 두 번 수행할 수 있다. 생성 전 preflight에서는 영상 관찰 rule이 `UNKNOWN`이지만 기한 `PASS`/`WARN`은 미리 사용자에게 알릴 수 있고, 생성 후 재평가에서 실제 `evaluated_at` 기준으로 다시 판정한다. 두 Report는 각각 immutable이며 필요하면 `supersedes_ref`로 연결한다.

### 5.11 결정 — 신고유형별 필수성

| 항목 | `TRAFFIC_VIOLATION` | `MOTORCYCLE_VIOLATION` |
| --- | --- | --- |
| 차량번호 확정 | 필요 | 필요 |
| 신고영상에서 번호판 식별 | 필요 | 필요 |
| 발생시각 | 필요 | 필요 |
| 신고영상 내 시각 표시 | 필요 | 필요 |
| 발생장소 | 필요 | 필요 |
| `REPORT_VIDEO` | 필수 | 필수 |
| 위반 장면·전 상황·후 상황 | 필요 | 필요 |
| `PLATE_IMAGE` | 선택 | 선택 |
| 원본 영상 동시 제출 | 선택 | 선택 |

> **D1 종결에 따른 단서 (2026-09-14).** 발생장소가 두 신고유형 모두 「필요」라는 이 표의 사실은 바뀌지 않는다. 다만 그 무게를 **Package 미발행이 지지 않는다** — 위치가 없어도 다른 요건이 충족되면 Package를 발행하고, 미확정이라는 사실은 `report_field_states`·`unconfirmed_fields`와 사용자 고지가 나른다. [`ADR-EVIDENCE-003`](adr-location-absent-package.md) §4.3·§5.1.

`PLATE_IMAGE`는 OCR 확인·사용자 검토·보조 제출에 유용하지만 신고영상의 번호판 가시성을 대체하는 필수 자산이라는 근거는 확인되지 않았다. optional을 유지한다.

원본 영상 동시 첨부를 강제하지 않는다. 사후 각인이나 재압축으로 번호판·사건 장면이 저하됐다면 권장 문구로 안내할 수 있다.

PC와 모바일로 catalog를 나누지 않는다. Package는 제목을 항상 생성하고 PC는 사용, 모바일은 미사용이라는 차이는 handoff에서만 흡수한다.

### 5.12 결정 — rule 실행 실패는 정상 Report를 만들지 않는다

다음은 업무상 `UNKNOWN`이 아니라 정책 엔진 오류다. `PolicyConfigurationError`로 처리하고 `RequirementReport`를 발행하지 않으며 `overall=ERROR`도 만들지 않는다(Final Contract §6 불변조건 10).

- 알 수 없거나 등재되지 않은 `policy_ref`
- 적용 가능한 catalog entry가 없거나 둘 이상 매칭됨
- 지원하지 않는 rule code
- 선택된 rule 목록이 비어 있음(불변조건 6)
- 같은 Report 안에서 rule code 중복(불변조건 7)
- 시각 표시 분기에서 선택된 rule이 0개이거나 2개 이상
- K1 상한 데이터 누락·형식 오류
- K2 달력 coverage 누락·형식 오류
- selector 값(`TimeResolution.status`, `post_stamp.reason_code`)의 형식 오류나 미등재 값
- 관찰 fact 자체의 구조 오류(boolean이 아님, `subject_refs` 누락 등)

반대로 다음은 정상 Report의 `UNKNOWN`이다.

- `REPORT_VIDEO`가 아직 없음
- `byte_size=null`
- 번호판·~~사건 장면·전후 상황·~~시각 표시를 아직 관찰하지 않음 → **사건 장면·전후 상황은 D2로 rule 자체가 제거됐다**([`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md))
- ~~Package 표시용 위치가 아직 없음~~ → **D1 종결로 `UNKNOWN`이 아니라 `WARN`이다**(아래)
- 발생시각을 확보하지 못함
- 사용자가 사건 유형에 아직 응답하지 않음

> **D1 종결에 따른 추가 (2026-09-14).** 이 절은 원래 「정책 엔진 오류 / `UNKNOWN` / `BLOCK`」 세 갈래만 두었다. **Package 표시용 위치 부재는 네 번째 갈래인 `WARN`이다** — 판정이 성립했고(위치가 없다는 사실이 확정됐고), 그것이 Package 발행을 막지 않으며, 미확정이라는 사실은 `report_field_states`·사용자 고지가 나른다([`ADR-EVIDENCE-003`](adr-location-absent-package.md) §5.1·§5.5). 위치 부재로 `UNKNOWN`을 내지 마라. `UNKNOWN`이면 overall이 `UNKNOWN`이 되어 Package가 사라지고 D1이 무효가 된다.

그리고 실제 판정이 성립했는데 조건을 충족하지 못하면 `BLOCK`이다.

- 영상은 존재하지만 번호판을 식별할 수 없음
- ~~사건 장면 또는 전·후 상황이 빠짐~~ → **D2로 제거.** 이 판정을 할 수 있는 모듈이 없었다([`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md) §4.2). 녹화 경계로 전후가 물리적으로 없는 경우는 `recording` 미결로 등재됐다(같은 ADR §5.6)
- 선택된 시각 표시가 실제 영상에 없음
- 첨부 크기·개수가 상한을 초과함

### 5.13 결정 — 계약과 호출 경계의 변화

`rule_codes`는 `evaluate_requirements()`의 Runtime 입력에서 제거한다. Consumer가 제공하는 것과 evidence가 결정하는 것을 다음처럼 나눈다.

| Consumer(`case`)가 제공 | evidence가 결정 |
| --- | --- |
| `EvidenceRecord` | 적용할 policy version |
| 평가 scope | 실행할 기본 rule 목록 |
| AssetFacts(Package 첨부 집합) | 조건부 rule 분기 |
| 관찰 fact(번호판·사건·전후 상황·시각 표시) | 각 `outcome`과 `reason_code` |
| `TimeResolution`(시각 표시 분기 selector) | `overall` aggregation |
| `evaluated_at` | 최종 `RequirementReport` |

**새 평가 입력이 하나 필요하다.** 시각 표시 분기 selector인 `post_stamp`는 `EvidenceRecord.occurred_at`에 투영되어 있지 않다. `occurred_at`은 `value`·`time_resolution_ref`·`resolution_status`·`user_corrected`·`source`만 가진다. 따라서 `evaluate_requirements()`가 `TimeResolution`을 직접 받도록 인수를 추가한다.

`EvidenceRecord`에 `post_stamp`를 투영하는 대안은 채택하지 않는다. 그것은 `evidence-record/v1.3` Final Contract 변경이고 K3 단독으로 결정할 범위가 아니다. 함수 인수 추가는 evidence 내부 순수 함수 경계의 변경이며 새 Runtime wire schema를 만들지 않는다. `case`는 이미 `TimeResolution`을 보유하고 있다.

이 catalog는 evidence가 소유한다. Consumer는 rule 목록을 고르지 않고, `measurement`나 정책 수치로 `outcome`/`overall`을 재계산하지 않는다(불변조건 11).

### 5.14 근거와 확인 상태

| 항목 | 값 |
| --- | --- |
| K3 catalog 식별자 | `policy/requirement-rules-v2` — **D1 반영은 이 값을 덮어쓰지 않고 새 revision으로 발행한다**(§7) |
| 데이터 위치 | `src/daesingo/evidence/requirement_rules_v2.json` |
| `EVIDENCE` 기본 rule 수 | 4 |
| `FINAL_PACKAGE` 무조건 rule 수 | 15 — D1은 rule을 더하거나 빼지 않고 두 rule의 판정만 바꾼다. **D2가 세 rule을 제거해 12가 된다**([`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md) §5.2) |
| `FINAL_PACKAGE` 조건부 rule | 3개 중 정확히 1개 선택 |
| 결정일 | `2026-09-13` |

외부 근거:

- evidence Research `안전신문고 실제 신고 요건 및 초기 4종 유형 매핑 조사` §3(핵심 증거)·§4(첨부 영상 위반일시 표시)·§5(초기 4종 전부 번호판 baseline)·§6(신고내용 4개 항목)·§7(PC·모바일 입력값)·§15(baseline rule 표)
- evidence Research `Timestamp / Evidence Policy` §11(사후 각인 조건부 제공)·§12(과도하지 않은 출처 안내)·§14(원본 동시 제출 강제하지 않음)
- evidence Research `신고문 / Package / Handoff`
- [`contract-requirement-report-package.md`](../../../architecture/contracts/contract-requirement-report-package.md) §3(`category` 값 공간)·§4.6(ASSET 판정 입력)·§6(불변조건 6·7·10·11)
- [`contract-evidence-record-needs.md`](../../../architecture/contracts/contract-evidence-record-needs.md) §4.6·§4.7
- [`safety-report-policy-v1.md`](../decisions/safety-report-policy-v1.md)

**확인하지 않은 것.** 위 Research가 인용한 경찰민원24·안전신문고·정부민원안내콜센터 페이지의 현행 내용을 이번 결정에서 독립적으로 재확인하지 않았다. K3의 rule 구성은 조사 시점 기록에 근거한다. K1·K2와 같이 확인일과 근거 snapshot을 보존하고, 외부 안내가 바뀌면 v2를 덮어쓰지 않고 새 revision을 발행한다.

### 5.15 구현·검증 영향

K3 결정으로 다음 작업을 진행할 수 있다.

- `requirement_rules_v2.json` 로더와 catalog entry 선택 구현
- `evaluate_requirements()`에서 `rule_codes` 제거, `time_resolution` 인수 추가
- ~~사건 장면·전 상황·후 상황 세 rule과 관찰 fact 입력 추가~~ → **D2로 철회**([`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md)). 관찰 fact 입력은 번호판·시각 표시·사후 각인 세 key만 남는다
- `package.asset.report_video.size` → K1 여섯 rule 교체
- `package.evidence.situation_unconfirmed` → `package.evidence.situation_response` 교체와 `NOT_ASKED` `UNKNOWN` 처리
- `package.report.content_length`의 렌더 불가 `UNKNOWN` 처리 — **필수 입력은 선택된 template 기준으로 읽는다**(D1, §5.8의 단서)
- 시각 표시 selector 네 경우와 「정확히 하나 선택」 불변조건 테스트
- §5.12의 구성 오류 전부에서 정상 Report 미발행 테스트
- H/U/P/R 네 Scenario를 같은 기본 catalog로 재실행

다음은 K3가 단독으로 확정하지 않는다.

- ~~D1(Q1) 위치 결론 — 결정되면 `package.location.present` outcome 매핑의 새 revision 필요~~ → **2026-09-14 종결.** [`ADR-EVIDENCE-003`](adr-location-absent-package.md)이 ①(위치 없는 `WARN` Package 발행)로 확정했다. 새 revision은 `package.location.present`와 `package.report.content_length` **두 rule을 함께** 바꾼다
- ~~사건 장면·전후 상황 관찰값의 실제 생산·전달 경로 — 통합 항목 I4의 범위를 번호판·시각에서 사건 장면·전 상황·후 상황까지 넓혀야 한다~~ → **2026-09-14 해소.** [`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md)가 세 rule을 제거해 넓힐 대상이 사라졌다. **I4는 번호판·시각 범위 그대로 유지한다**(같은 ADR §5.7)
- `ReportPackage.assets` 확장(최대 4개 첨부)
- 전후 상황의 초 수 — `recording` Tech Spec

**Artifact 영향.** v2로 재실행하면 H/U/P/R baseline의 `policy_ref`, `checks[]` 구성, 일부 `overall`이 바뀐다. U는 `package.report.content_length`가 추가되고 H는 `package.evidence.situation_response`가 추가되며, 네 Scenario 모두 사건 장면·전후 상황 rule이 `UNKNOWN`으로 들어온다. 이는 예상된 변경이며, 기존 v1 Artifact를 조용히 덮어쓰지 않고 v2 재실행 결과임을 명시해 기록한다. 실제 관찰값이 없는 상태에서 `UNKNOWN`이 늘어나는 것을 회귀 실패로 보지 않는다.

> **D1 종결에 따른 정정 (2026-09-14).** 위 문단은 **U가 `UNKNOWN`으로 떨어져 `pkg_u001`이 사라지는 상태**를 전제로 쓰였다. v2 그대로 재실행하면 U의 `package.location.present`와 `package.report.content_length`가 모두 `UNKNOWN`이 되어 `overall=UNKNOWN`, 계약 §8.1로 Package가 없어진다. **D1 반영 후에는 그렇지 않다** — 두 rule이 각각 `WARN`과 template 기준 판정으로 바뀌어 U의 `overall`은 `WARN`이고 `PACKAGE_READY`가 성립한다([`ADR-EVIDENCE-003`](adr-location-absent-package.md) §5.5·§9). 따라서 **D1 반영을 Artifact 재실행보다 먼저 수행한다.** 순서가 뒤바뀌면 baseline이 사라진 Package를 정상 결과로 기록하게 된다.

> **위 정정 블록에 대한 정정 (2026-09-14 · D2).** 위 블록은 **위치 축만 계산했다.** U를 `UNKNOWN`으로 만드는 요인이 두 축이었는데(위치 축 2건 + 관찰 축 3건) 관찰 축은 바로 윗 문단이 이미 적고 있었음에도 결론에 넣지 않았다. 그래서 「D1이 위치 관련 `UNKNOWN` 두 건을 제거한다」(무조건 참)를 「D1 반영 후 U는 `WARN`이고 `PACKAGE_READY`가 성립한다」(관찰 축이 0건일 때만 참)로 넓혀 썼다. 실제로 D1을 반영해 재실행한 결과 U의 `package.location.present`는 `WARN`, `package.report.content_length`는 `PASS`로 **D1은 온전히 반영됐으나** 관찰 rule 3건이 `UNKNOWN`으로 남아 Package가 발행되지 않았다([`reviews/13_…`](../reviews/13_adr-002-003-implementation_2026-09-14.md) · [`reviews/14_…`](../reviews/14_instruction-conflict-analysis-and-doc-fixes_2026-09-14.md) §2). **[`ADR-EVIDENCE-005`](adr-event-context-rules-removal.md)가 그 세 rule을 제거하면서 위 블록의 기대는 조건 없이 성립하게 된다.**



## 6. K4 — 발생시각 이외 Correction의 `EvidenceValue.source` provenance

### 6.1 상태

**ACCEPTED — 2026-09-13**

### 6.2 배경

[`contract-correction-record.md`](../../../architecture/contracts/contract-correction-record.md) §6이 evidence가 소비할 semantic path 10개를 **닫힌 목록**으로 확정했다. 그중 `occurred_at` 하나만 시각이고 나머지 9개(`event.visual_event_type`·`event.safety_report_type`·`event.violation_expression`·`vehicle_number`·`location.coord`·`location.address`·`location.place_name`·`location.search_keyword`·`location.user_hint`)는 비시각 값이다.

반면 [`source-kind-registry.md`](../decisions/source-kind-registry.md) v1은 `case.user_correction`을 "TimeResolution/`occurred_at` provenance 전용"으로 적었고 label도 `time.source.user_correction` 하나뿐이다. 그래서 **사용자가 번호판이나 위치를 고쳤을 때 붙일 `source.kind`가 registry에 없다.**

세 가지가 동시에 걸려 있다.

- 현재 구현(`assembly.py`)은 비시각 9개에도 이미 `case.user_correction`을 쓴다. 코드가 틀렸다기보다 registry 설명이 시각 하나만 보고 좁게 적힌 상태다.
- [`contract-evidence-record-needs.md`](../../../architecture/contracts/contract-evidence-record-needs.md) §「`source.observability`·`source.label_key`」는 "새 `source.kind`를 추가할 때 `observability`를 함께 정한다. 분류 없는 kind는 만들지 않는다"고 요구한다. registry v1의 이 행은 `observability`가 비어 있으므로 **계약이 이미 요구하는 미결**이다.
- 같은 계약의 사용자 correction 항목은 "사용자 correction이 적용되면 `user_corrected=true`와 correction provenance를 남긴다"를 시각에 한정하지 않는다.

K4는 새 정책을 만드는 결정이 아니라, 계약이 이미 연 값 공간에 registry 의미를 맞추는 결정이다.

### 6.3 K3와의 충돌 검토

K3(§5)를 먼저 `ACCEPTED`로 기록했으므로 K4 반영 전에 접점을 확인했다. **충돌 없음.**

| 접점 | K3의 결정 | K4의 결정 | 판정 |
| --- | --- | --- | --- |
| `evidence.vehicle_number.present`(§5.4) | 확정 차량번호 있음 → `PASS` | 정정된 번호판은 `user_corrected=true`·`needs_review=false` | 정정값이 확정값으로 들어와 `PASS`. 일관 |
| `evidence.visual_event.present`(§5.4) | `visual_event_type` 확정 → `PASS` | `SITUATION_CHANGE` correction이 그 값을 채움 | 일관 |
| `evidence.location.present`(§5.4) · `package.location.present`(§5.6) | 위치 단서 존재 여부로 판정 | 위치 4종 정정이 같은 필드를 채움 | 일관 |
| `package.evidence.situation_response`(§5.9) | `CORRECTED` → `PASS` | `provenance.correction_refs` 보존 | 계약 불변조건 17이 `SITUATION_CHANGE` ref의 존재를 요구하므로 K4가 K3의 전제를 지탱한다 |
| 호출 경계(§5.13) | `rule_codes` 제거, `time_resolution` 인수 추가 | 함수 시그니처 무변경 | 무관 |

K3의 어떤 rule도 `source.kind`·`label_key`·`observability`를 판정 입력으로 읽지 않는다. §5.12의 `PolicyConfigurationError` 목록에도 provenance 항목이 없다. 따라서 K4는 `policy/requirement-rules-v2`의 새 revision을 요구하지 않는다.

### 6.4 결정 — kind를 쪼개지 않고 `case.user_correction`을 확장한다

`case.user_correction`의 의미를 "실제 반영된 **모든** 사용자 Correction 값의 provenance"로 넓힌다. `case.user_plate_correction`·`case.user_location_correction` 같은 대상별 kind를 신설하지 않는다.

대상별로 쪼개지 않는 이유는 그 정보가 이미 두 곳에 있기 때문이다. "사용자가 고쳤다"는 사실은 `user_corrected=true`가, "무엇을 고쳤다"는 사실은 `source.ref`가 가리키는 `CorrectionRecord.target_field`가 갖는다. kind를 늘리면 같은 사실이 세 번째로 중복되고, Consumer는 "사용자가 고친 값인가"를 판정하려고 kind 목록 전체를 매칭해야 한다.

### 6.5 결정 — 적용 대상은 실제 반영된 head correction뿐이다

`CorrectionRecord`가 존재한다고 해서 provenance를 붙이지 않는다. **최종 값으로 채택된 correction**에만 붙인다.

| 상황 | 처리 |
| --- | --- |
| 같은 `target_field`를 여러 번 수정 | supersede chain의 head 하나만 값과 provenance의 근거가 된다 |
| `selection_rev`가 현재 context와 다름 | 채택하지 않는다 |
| `occurred_at` correction | `TimeResolution`이 그 correction을 선택했을 때만 인정한다(§6.9) |
| `TIME_HINT_EDIT` | Search 범위 조정용이므로 최종 시각 근거로 승격하지 않는다([`contract-time-resolution.md`](../../../architecture/contracts/contract-time-resolution.md) §5) |

### 6.6 결정 — 비시각 Correction 값의 `EvidenceValue` 필드값

| 필드 | 값 | 근거 |
| --- | --- | --- |
| `source.kind` | `case.user_correction` | §6.4 |
| `source.ref` | `{kind: correction_record, ref: <correction_id>}` | 값 단위 근거. `contract-correction-record.md` §5가 표기를 고정했다 |
| `source.observability` | `OBSERVED` | 사용자가 직접 말한 값이므로 추론이 아니다. 계약은 "사용자 입력에는 별도 값을 두지 않는다 — `user_corrected=true`가 이미 그 사실을 갖고 있고, 파생 규칙에서 `observability`보다 먼저 판정된다"고 정한다 |
| `source.label_key` | `null` | §6.8 |
| `support_refs` | 해당 correction ref 포함 | 값 단위 근거 보존 |
| `user_corrected` | `true` | 계약 「사용자 correction이 적용되면 `user_corrected=true`와 correction provenance를 남긴다」 |
| `needs_review` | `false` | 불변조건 12. 사용자가 이미 확정한 값을 다시 확인시키지 않는다 |

**값 단위와 레코드 단위를 둘 다 남긴다.** `source.ref`는 "이 값 하나의 근거"이고 `provenance.correction_refs`는 "이 레코드가 반영한 correction 목록"이다. 둘은 다른 층위이므로 중복이 아니며, 불변조건 17(`situation_response=CORRECTED`이면 `SITUATION_CHANGE` ref가 `provenance.correction_refs`에 존재)이 후자를 요구하므로 하나만 남기는 선택지는 없다.

### 6.7 결정 — 정정에서 파생된 값은 확장 대상이 아니다

사용자가 `event.visual_event_type`을 고치면 거기서 유도되는 `safety_report_type`·`violation_expression`은 **사용자가 말한 값이 아니라 정책 매핑 결과**다. 이 둘은 확장 대상이 아니다.

| 값 | `source.kind` | `observability` | `user_corrected` |
| --- | --- | --- | --- |
| 사용자가 직접 고친 값 | `case.user_correction` | `OBSERVED` | `true` |
| 정정에서 유도된 `safety_report_type` | `evidence.category_mapping` | `INFERRED` | `false` |
| 정정에서 유도된 `violation_expression` | `evidence.violation_expression` | `INFERRED` | `false` |

파생값의 `source.ref`는 근거 추적을 위해 correction을 가리키되 kind와 `observability`는 매핑 주체를 그대로 드러낸다. 사용자가 유도값 자체를 따로 고친 경우(`event.safety_report_type` 또는 `event.violation_expression`을 직접 target으로 하는 correction)에는 그 head가 매핑 결과를 대체하고 위 첫 행을 따른다.

"사용자가 고쳤으니 전부 `OBSERVED`"로 뭉개지 않는다. 매핑 규칙은 [`safety-report-policy-v1.md`](../decisions/safety-report-policy-v1.md)가 소유하며 사용자 발화가 아니다.

### 6.8 결정 — `label_key`는 `null`로 두고 Consumer fallback에 맡긴다

registry v1의 기존 label `time.source.user_correction`은 **이름에 시각이 박혀 있다.** 번호판 정정값에 그대로 붙이면 CaseView가 "시각 출처: 사용자 정정"으로 표시한다. 잘못된 라벨보다 없는 라벨이 낫다.

이번 결정에서 `plate.source.user_correction` 같은 대상별 label key를 **신설하지 않는다.** UI 문구가 확정되지 않은 상태에서 키를 먼저 박으면 문구 확정 시 registry를 다시 개정해야 한다. `contract-evidence-record-needs.md`의 `label_key` 규칙이 "대응 키가 없으면 `null`이고 소비자가 fallback 문구를 쓴다"를 이미 허용하므로 계약 위반이 아니다.

Consumer는 `user_corrected=true`로 "사용자 수정함" 표시를 자체 처리할 수 있다. 나중에 대상별 키가 필요하다고 판단되면 그 이름들을 포함한 새 registry revision으로 처리한다.

### 6.9 결정 — `occurred_at` 경로와 `case.user_location_hint`는 바꾸지 않는다

**`occurred_at`은 `EvidenceValue<T>`가 아니다.** `{value, time_resolution_ref, resolution_status, user_corrected, source{kind, label_key}}` 구조이며 불변조건 15가 `observability`를 두지 않는다고 못박았다. K4의 확장은 `EvidenceValue` 컨테이너에만 적용되고 시각 경로는 다음을 유지한다.

- `source.kind`는 `case.user_correction`, `label_key`는 `time.source.user_correction`
- `observability` 없음, `source.ref` 없음, `needs_review` 없음
- 채택 판정은 `TimeResolution.provenance.selected_input_ref`가 소유한다

**`case.user_location_hint`도 건드리지 않는다.** 이 kind는 사용자가 처음 입력한 위치 단서이지 기존 값의 Correction이 아니다. `CorrectionRecord`가 없으므로 `source.ref`가 case를 가리키고 label도 `location.source.user_hint`를 유지한다. 같은 `location.user_hint` 필드를 나중에 사용자가 **고치면** 그때는 `location.user_hint` target의 correction이 생기고 §6.6을 따른다.

### 6.10 결정 — registry revision을 발행한다

| 항목 | 값 |
| --- | --- |
| registry 식별자 | `source-kind-registry` v2 |
| 데이터 위치 | [`../decisions/source-kind-registry.md`](../decisions/source-kind-registry.md) |
| v1 대비 변경 | `case.user_correction` 행 하나 — 용도를 비시각 9개 path까지 확장, `observability`에 `OBSERVED` 명시, `label_key`를 컨테이너별로 분리(`EvidenceValue`는 `null`, `occurred_at`은 `time.source.user_correction`) |
| 신규 kind | 없음 |

v1을 덮어쓰지 않는다. v1을 근거로 만들어진 기존 Artifact는 당시 의미로 재현 가능한 상태로 보존한다. registry는 닫힌 목록이 아니므로 이후 새 kind가 필요하면 같은 방식으로 revision을 올린다.

### 6.11 근거와 확인 상태

| 항목 | 값 |
| --- | --- |
| 결정일 | `2026-09-13` |
| 확장 대상 semantic path 수 | 9 (`occurred_at` 제외) |
| 신규 `source.kind` | 0 |
| 신규 `label_key` | 0 |
| Final Contract 변경 | 없음 |

근거:

- [`contract-correction-record.md`](../../../architecture/contracts/contract-correction-record.md) §5(ContractRef 표기)·§6(10개 semantic path 닫힌 목록)
- [`contract-evidence-record-needs.md`](../../../architecture/contracts/contract-evidence-record-needs.md) §3(`source.observability`·`source.label_key`·`needs_review`)·§10 불변조건 12·13·15·17
- [`contract-time-resolution.md`](../../../architecture/contracts/contract-time-resolution.md) §5(`EVENT_TIME_MANUAL`만 최종 시각 근거로 승격)
- [`source-kind-registry.md`](../decisions/source-kind-registry.md) v1
- [`safety-report-policy-v1.md`](../decisions/safety-report-policy-v1.md)(파생값 매핑 소유)

**확인한 것.** 현재 구현이 비시각 9개 경로에 이미 `case.user_correction`·`OBSERVED`·`user_corrected=true`·`label_key=null`을 쓰고 있음을 `src/daesingo/evidence/assembly.py`에서 확인했다. 즉 이 결정은 구현 변경이 아니라 registry 추인이다.

**확인하지 않은 것.** 공용 Mock Pack에는 `CorrectionRecord`가 단 하나 있고 그 `target_field`는 `occurred_at`이다. **비시각 9개 경로를 검증하는 공용 Fixture가 없다.** 따라서 이 결정의 검증은 evidence 단위 테스트 범위이며 실제 Consumer 산출물로 확인한 것이 아니다. 통합 항목 I7·I8에서 실제 case correction과 CaseView projection으로 확인한다.

### 6.12 구현·검증 영향

K4 결정으로 다음 작업을 진행할 수 있다.

- `source-kind-registry.md`를 v2로 개정하고 `case.user_correction` 행의 용도·`observability`·`label_key`를 §6.6·§6.8대로 기록
- 비시각 정정 9개 경로가 `kind`·`ref`·`observability`·`label_key`·`user_corrected`·`needs_review`를 규약대로 갖는지 단위 테스트 추가 — 현재 `test_correction_head_validates_type_chain_and_actual_application`은 `value`·`user_corrected`·`correction_refs`만 검사한다
- 정정에서 유도된 `safety_report_type`·`violation_expression`이 `INFERRED`와 매핑 kind를 유지하는지 별도 테스트(§6.7)
- 사용자가 유도값 자체를 직접 고친 경우 head가 매핑 결과를 대체하는지 테스트
- `occurred_at`이 `observability`·`source.ref`를 갖지 않는지 회귀 테스트(불변조건 15)
- `label_key=null`이 공용 validator와 `CaseView.source_label_key` 통과 경로에서 거부되지 않는지 확인

다음은 K4가 단독으로 확정하지 않는다.

- 대상별 `label_key` 신설과 그 UI 문구 — 문구 확정 후 새 registry revision에서 처리(§6.8)
- `CaseView`의 `source_label_key` fallback 표시 문구 — `case`/`web` 소유. 변경 사실을 유소연에게 통보하고 통합 항목 I8에서 projection만 확인한다
- 실제 case correction 전달 경계 — 통합 항목 I7

**Artifact 영향.** 없다. 공용 Mock의 유일한 correction은 `occurred_at` 대상이고 시각 경로는 §6.9에서 무변경이므로 H/U/P/R baseline의 `EvidenceRecord`·`RequirementReport` 값이 바뀌지 않는다. K3 v2 재실행으로 생기는 변화(§5.15)와 K4는 서로 독립이다.

## 7. 변경 규칙

- K1·K2 값을 바꿀 때 기존 version을 덮어쓰지 않고 새 policy version과 변경 근거를 남긴다.
- K2 공휴일 snapshot은 자동 갱신하지 않는다. 2027년 수동 갱신 시 새 calendar/policy revision을 발행하고 v1을 보존한다.
- K3 catalog를 바꿀 때 `policy/requirement-rules-v2`를 덮어쓰지 않고 새 revision을 발행한다. 하위 정책(K1·K2·`safety-report-policy/v1`)이 새 version을 내면 K3도 그 version을 가리키는 새 revision이 필요하다.
- K4 registry 의미를 바꿀 때 `source-kind-registry` v2를 덮어쓰지 않고 새 revision을 발행한다. 새 `source.kind`나 `label_key`를 신설하려면 그 이름도 같은 revision에 등재한다.
- 다른 Owner의 입력·출력 계약을 바꿔야 하는 경우 이 ADR에서 단독 확정하지 않고 해당 Contract Owner와 별도 검토한다.
- Research 문서는 조사 당시 기록으로 보존하며, 채택된 정책의 authoritative 위치는 이 ADR과 versioned policy data다.

## 8. 한 줄 결정

> K1은 실제 Package 첨부를 decimal byte와 명시적 개수 상한으로 검사하고 미측정은 UNKNOWN, 초과는 BLOCK으로 처리하며 별도 내부 목표는 두지 않는다. K2는 `representative_ms` 기반 발생시각을 `Asia/Seoul`에서 위반일 다음 날부터 2개 달력일로 계산하고 말일이 주말·공휴일이면 다음 첫 비휴일까지 연장하며, 2026·2027 정적 달력으로 판정해 초과는 WARN, 시각 부재는 UNKNOWN, 시각 검토 필요는 잠정 계산 후 WARN으로 처리한다. K3은 `policy/requirement-rules-v2`를 발행해 Scenario가 아닌 실제 평가 조건으로 rule을 선택하고, 초기 4종에 동일한 EVIDENCE 4개와 FINAL_PACKAGE 15개를 적용하며 시각 표시만 `TimeResolution.status`·`post_stamp.reason_code`로 정확히 하나를 분기하고, 정책·catalog·selector·관찰 fact 구성 오류에서는 정상 Report를 발행하지 않는다. K4는 `case.user_correction`을 비시각 9개 semantic path까지 확장해 실제 반영된 head correction에만 `OBSERVED`·`user_corrected=true`·`needs_review=false`와 값 단위 `source.ref`·레코드 단위 `provenance.correction_refs`를 남기고, 정정에서 유도된 값은 매핑 kind와 `INFERRED`를 유지하며, `label_key`는 `null`로 두어 Consumer fallback에 맡기고 `occurred_at`과 `case.user_location_hint` 경로는 바꾸지 않는다.
