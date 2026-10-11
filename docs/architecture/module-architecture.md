# 대신고 — 소프트웨어 모듈 구조 설계 v4

> **Source of Truth: `전남대학교 2팀 서비스 기획안 제출 1.3`**
>
> 이 문서는 v3의 7개 상위 모듈 경계를 유지하면서, Owner별 Architecture Input Memo와 `260831 회의 픽스안`에서 확인된 실제 제약·정책을 반영해 **모듈 책임, 호출 방향, 런타임 경계, 핵심 계약의 의미**를 구체화한 버전이다.
>
> **우선순위는 다음과 같다.**
>
> ```
> 서비스 기획안 1.3 / 팀 회의에서 확정한 Product Policy
>          ↓
> 이 문서 v4 — Architecture Decision
>          ↓
> Owner Architecture Input Memo — 근거·실측·제안
>          ↓
> Data Contract — 필드·enum·함수 시그니처 확정
>          ↓
> Module Technical Spec / 구현
> ```
>
> Owner Memo의 모든 제안을 그대로 Architecture Decision으로 승격하지 않는다. **실측으로 확인된 제약은 반영하고, 구현 선택이나 아직 근거가 약한 수치는 각 모듈 Technical Spec 또는 Data Contract 단계로 남긴다.**

> **현재 사용 상태 (2026-09-19 maintenance):** v4는 여전히 **모듈 경계·소유권·호출 방향의 Source of Truth**이며 v5로 올리지 않는다. 이후 Data Contract → Mock Pack → 모듈 구현/통합 → Logical ERD·Runtime Spec 구체화가 진행됐다. 따라서 schema·enum·fixture·DB/queue·배포 세부는 각각 Final Contract, 모듈 Decision/Tech Spec, `erd-draft.md`, `runtime/`이 소유한다. **§10-3·§11·§13의 handoff 문구는 v4 작성 당시의 이관/검토 기록으로 읽고, 현재 상태 판단에는 각 하위 SoT를 사용한다.** 이번 maintenance는 경계·Owner·호출 방향을 바꾸지 않고 상태 드리프트와 포인터만 정리한다.

---

## 개정 이력

> **버전은 v4로 유지한다.** 아래는 경계 변경이 아니라 **Data Contract 단계에서 확정된 결정을 v4에 기록**한 것이다. 전체를 다시 읽을 필요는 없다.

| 날짜 | 바뀐 곳 | 내용 | 근거 |
| --- | --- | --- | --- |
| 2026-09-05 | §5-1 ⑫ · §4-모듈5 ④⑤ · §11-4 · §12 RT8 · §5-3 | Job Intent / Job Execution 분해 확정을 반영. `JobRecord`(case) / `JobExecution`(common/runtime) / `UsageRecord`로 ⑫를 다시 씀. RT8 종결. recording 보조 구조 3개 등재 | `contracts/adr/adr-job-record-case-view.md` · `contracts/adr/adr-consistency-2026-09.md` |
| 2026-09-06 | §5-1 ⑦·⑬ · §5-3 · §4-모듈3 ③ · §11-4 | 담당자 회신으로 별도 계약 2건을 작성하고 목록에 등재. ⑦에 **`ReadoutRun`** 추가(신유민), **⑬ `CorrectionRecord`** 신설(유소연). recording 자산 계층의 opaque ref 방향과 계약 2건 작성 예정 기록(정철원). §11-4 USER_REVIEWED 소유 확인 반영. 후속 감사에서 접합 완결은 Pending으로 분리 | `contracts/adr/adr-consistency-2026-09.md` §6 · `contracts/adr/adr-readout-run.md` · `contracts/adr/adr-correction-record.md` |
| 2026-09-06 (감사 후속) | §5-1 상태 안내 · §5-3 · §11-4 안내 | 미작성 자산이 통합을 막지 않는다는 단정 철회. ref는 최소 schema 이전 작업 규약으로 한정. CaseView/recording 접합은 Pending 유지 | `contracts/adr/adr-consistency-followup-2026-09-06.md` |
| 2026-09-07 (접합부 종결) | §5-1 상태 안내 · §5-3 안내 · §11-4 안내 | 상태 안내 문구만 갱신 — 규칙·계약 목록·enum은 바꾸지 않았다. B01·B02·B03·B05·B09 종결, B06·B08 직렬화 대기, B07 자산 계약 대기를 종결 ADR로 가리킨다 | `contracts/adr/adr-data-contract-call-closure-2026-09-07.md` |
| 2026-09-08 (접합부 종결 후속) | §5-3 안내 | 상태 안내 문구만 갱신 — 규칙·계약 목록·enum은 바꾸지 않았다. B06(`SpanResolution` `failure`·`OUT_OF_TIMELINE_RANGE`)·B08(`AnalysisScope` relative range) 직렬화 종결, ② `SourceAsset`/`MediaStream`·③ 전체를 담는 recording 자산 계약 2건이 **Draft(Consumer Review 대기)**로 추가됨 | `contracts/adr/adr-data-contract-call-closure-2026-09-08.md` |
| 2026-09-08 (2차 반영) | §5-3 안내 | 상태 안내 문구만 갱신 — 규칙·계약 목록·enum은 바꾸지 않았다. 자산 계약 2건이 Consumer Review 종결로 **`Final — Accepted`(`…/v1`)**, `MissingRange.source_ref`·`AssetSpan` identity 결정 종결 | 같은 ADR §4.7~§4.10 |
| 2026-09-08 (주요 문서 동기화) | §5-3 안내 · §11-1 안내 · §11-4 포인터 | **규칙·계약 목록·enum은 바꾸지 않았다.** §5-3에 겹쳐 쌓인 과거 상태 안내 5개(「작성 예정」·「최소 schema 제공 전」·B06~B09 Pending·1차/2차 갱신)를 **2026-09-08 최종 상태 한 블록으로 합쳤다.** 위 행들의 당시 상태는 이 표가 역사 기록으로 보존한다 | 같은 ADR §4.7~§4.10 · §9 · §10.2 |
| 2026-09-19 (maintenance) | 문서 머리말 · §9-5 · §10-3 · §11 안내 · §13-2·§13-3 | **Architecture 결정 변경 없음.** 계약·Mock·구현 이후 상태 드리프트를 정리했다. `CorrectionRecord`/EvidenceNeeds·cache 규칙 등 이미 닫힌 Data Contract 항목을 현재 미결에서 제거하고, §11·§13을 historical handoff로 명시했다. Web stack은 모듈 Decision으로 이미 확정됐으므로 Architecture 미결에서 제외했다 | Final Contract 16건 현재 상태 · `modules/web/decisions/web-stack.md` · `README.md` 현재 구현 상태 · `runtime/` · `erd-draft.md` |
| 2026-10-02 (maintenance) | §4-모듈5 ④ · §5-13 · §6-2 · §8-2 · §10-2 | **Architecture 결정 변경 없음.** Final Contract와 어긋난 잔존 표현을 정합화했다. `JobExecution` status에 v1.1 `CANCELLED` 반영, §5-13의 `JobRecord` 실행 lifecycle을 `JobExecution`으로 이동, §6-2 결과 기록 대상을 `JobExecution`으로 정정, §8-2의 「case_rev mismatch → STALE」을 Contract 의미(STALE = Worker 소멸, old `case_rev` 결과는 SUCCEEDED 유지·case가 미반영)로 정정, §10-2 Search baseline을 #95 Elice 전환 이후 상태로 갱신 | `contracts/contract-job-execution.md` §6·§9 · `contracts/contract-job-record-case-view.md` A절 · `runtime/reviews/runtime-ops-consistency-audit-2026-10-02.md` A-05·A-06·B-01 |
| 2026-10-04 (maintenance) | §4-모듈5 ④ · §8-2 | **Architecture 결정 변경 없음.** 늦은 결과 배제 기준을 「현재 `case_rev`와 맞는 결과만 반영」에서 「case가 현재 context에 유효하다고 판단한 결과만 반영」(중단된 `job_id` 집합 + 현재 선택 context)으로 정합화했다. 같은 `case_rev`에서 병렬 Job이 돌기 때문이다(case Owner 유소연 요청) | `contracts/contract-job-execution.md` §9-8 · Issue #245 C-1a · `runtime/runtime-tech-spec.md` §12.2 |

---

## 이 문서를 읽는 방법

v4부터는 역할 배정이 끝났고 Owner별 기술 조사도 시작됐다. 따라서 v3의 목적이었던 “누가 어떤 모듈을 맡을지 정하기”보다 **각 Owner가 자기 경계를 구현 가능한 수준으로 이해하는 것**이 중요하다.

| 순서 | 어디를 | 왜 |
| --- | --- | --- |
| **1** | **§1 한눈에 보기 → §2 설계 원칙** | 바뀌지 않은 7개 경계와 v4에서 추가된 원칙을 이해한다 |
| **2** | **§3 주요 정책이 구조로 옮겨진 방법** | Timestamp, 사건 영상, Package, Runtime이 어디에서 처리되는지 확인한다 |
| **3** | **§4 자기 모듈** | 책임·소유 데이터·금지사항·접합부를 확인한다 |
| **4** | **§5 Core Contracts** | 다른 Owner와 맞춰야 하는 의미 수준의 계약을 확인한다 |
| **5** | **§6~§9** | 실제 호출 흐름·백그라운드·평가 구조를 확인한다 |
| **마지막** | **§11 Owner Review Required** | **historical handoff** — v4 직후 Owner 검토 기록을 볼 때만 참고한다. 현재 작업 상태는 모듈 checklist/Final Contract를 본다 |

> **중요:** v4는 Data Contract 문서가 아니다. JSON 예시는 **의미를 고정하기 위한 예시**이며 필드명·enum·nullable·DB column까지 확정하는 문서가 아니다.

---

# 1. 한눈에 보는 Final Architecture

## 1-1. 제품의 본질 한 줄

```
긴 블랙박스 영상  →  사건 후보  →  확인된 증거  →  신고용 결과물  →  안전신문고 Handoff
(Long Video       →  Event      →  Evidence     →  Report Assets  →  Handoff)
```

## 1-2. 상위 모듈은 v3와 동일하게 7개

```
                 ┌──────────────────────────────────────┐
                 │  web       단계형 작업공간 (브라우저)  │
                 └──────────────────┬───────────────────┘
                                    │  web은 case만 부른다
                                    │  ↑ CaseView
                 ┌──────────────────▼───────────────────┐
                 │  case      진행 관리 · 유일한 지휘자   │
                 └───┬──────────┬──────────┬────────────┘
                     │          │          │
┌────────────────────▼──┐  ┌────▼────────┐ │  ┌──────────────────────┐
│  search   사건 탐색    │  │  readout    │ └─▶│  evidence  증거 확정 │
│  구간 후보·시각 관찰   │  │  값 판독     │    │  규정·Package 정책    │
└───────────┬───────────┘  │ 번호판·화면시각│    └──────────────────────┘
            │              └────┬────────┘
            ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  recording   Source·Stream·시간축·구간·프레임·파생영상 계층       │
└──────────────────────────────────────────────────────────────────┘
            ▲                   ▲
            └─────────┬─────────┘  공개 함수만 호출
            ┌─────────▼──────────┐
            │  eval  성능 채점기  │  ← 제품 런타임이 아닌 개발용 패키지
            └────────────────────┘

───────────────── common/runtime infrastructure ─────────────────
FastAPI · MySQL DB Queue · Worker 1 · Job execution · Usage ·
masked logging · config · storage adapter · geocoder adapter
※ 여덟 번째 도메인 모듈이 아니다.
```

| 모듈 | 쉽게 말하면 | 다루는 사실의 종류 |
| --- | --- | --- |
| **`recording`** | 블랙박스 파일·stream이라는 현실을 다루는 곳 | **Source가 말해주는 것**과 실제 픽셀 접근 경계 |
| **`search`** | 긴 영상에서 사건 구간 후보를 찾는 곳 | **넓은 영상 범위의 픽셀이 말해주는 것** |
| **`readout`** | 좁은 화면 영역에서 값을 읽는 곳 | **번호판·화면 Timestamp가 어떻게 보이는지** |
| **`evidence`** | 관찰값을 확정하고 신고 준비 정책을 적용하는 곳 | **확정 Evidence + 신고 규정 + Package 정책** |
| **`case`** | 사용자의 의도와 전체 진행을 연결하는 곳 | **진행 상태·선택·재실행·작업 발주 의도** |
| **`web`** | 사용자가 보는 작업공간 | 도메인 상태를 소유하지 않고 `CaseView`를 표현 |
| **`eval`** | 구현 성능을 같은 기준으로 채점하는 도구 | 제품 런타임과 분리된 정답지·예측·채점 결과 |

## 1-3. v4에서도 7개인 이유

모듈 수는 팀원 수가 아니라 **서로 다른 변경 이유**로 결정한다.

```
① 제조사·container·stream·GPS·파일명·구간 처리 방식이 바뀐다 → recording
② 긴 영상 탐색 모델·프롬프트·routing이 바뀐다                → search
③ 번호판·화면시각 판독 stack이 바뀐다                         → readout
④ 증거 확정·신고 규정·유형 매핑·Package 정책이 바뀐다          → evidence
⑤ 사용자 흐름·상태·선택·부분 재실행 정책이 바뀐다               → case

실행 환경이 다른 것:
⑥ 브라우저 UI                                                   → web
⑦ 개발/오프라인 채점                                            → eval
```

`common/runtime`은 **실행 메커니즘**이지 제품 책임이 아니므로 새 모듈로 세지 않는다.

## 1-4. 이 설계 전체를 지탱하는 규칙

> **“이렇게 보인다”와 “이 값이 맞다”를 같은 곳에서 다루지 않는다.**

- `search`, `readout`, `recording`은 **관찰한다.**
- `evidence`만 **확정한다.**
- `case`는 **언제 무엇을 실행할지** 결정한다.
- `common/runtime`은 **그 작업을 실제로 실행한다.**
- `web`은 **CaseView를 표현한다.**

그리고 v4에서 하나를 추가한다.

> **“원본 Source”와 “분석/신고용 파생물”을 같은 자산으로 취급하지 않는다.**

사용자 기기의 블랙박스 원본은 외부 immutable Source다. 대신고가 만드는 분석용 사본·사건 clip·신고용 영상은 별도 파생 자산이다.

## 1-5. 배포는 여전히 모듈형 모놀리스

```
논리적으로:  도메인 모듈 7개 + common/runtime 기반
물리적으로:  FastAPI 애플리케이션 1 + Worker 1 + MySQL 1

안 만든다:
마이크로서비스 · Kubernetes · Kafka · 서비스 메시 · 이벤트 버스 ·
도메인별 별도 서버 · LangGraph 기반 전체 Orchestrator
```

긴 작업은 HTTP 요청 안에서 끝내지 않는다. API는 작업을 발주하고 `202 Accepted`를 반환하며 Worker가 처리한다.

## 1-6. 이 문서에서 쓰는 말

| 말 | 대신고에서의 뜻 |
| --- | --- |
| **Module** | 책임 하나를 가진 논리 폴더. 다른 모듈은 공개 인터페이스만 사용 |
| **Component** | 모듈 내부의 함수·클래스·파일 |
| **Data Ownership** | 어떤 도메인 값을 authoritative하게 고칠 권한이 한 곳에만 있음 |
| **Observation** | 값 + 출처 + 상태 + 근거. 확정값이 아님 |
| **Source** | 사용자가 가진 원본 또는 서비스가 참조하는 원천 자산 |
| **Managed Copy** | 서비스가 생성·복사해 삭제 권한을 가진 사본 |
| **Analysis Source** | AI 분석용으로 준비된 입력. 원본일 수도, proxy일 수도, 필요한 구간일 수도 있음 |
| **Incident Clip** | Search가 찾은 span을 Recording이 Source에서 실제로 해석해 만든 **분석/검토용 사건 구간** |
| **Report Video** | Evidence가 확정된 뒤 신고에 사용하도록 만든 최종 파생영상. 필요 시 사후 Timestamp가 여기 들어감 |
| **Contract** | 모듈 간 데이터의 의미와 책임. 세부 필드는 Data Contract에서 확정 |
| **Job Intent** | case가 “무엇을 왜 실행할지” 정한 것 |
| **Job Execution** | common/runtime이 QUEUED→RUNNING→terminal로 실제 수행하는 lifecycle |
| **CaseView** | web이 화면을 한 번에 그리는 유일한 통합 projection |

## 1-7. v4에서 명시하는 가정·결정

| # | 상태 | 내용 |
| --- | --- | --- |
| A1 | **확정** | Desktop Web 우선. 모바일 반응형은 MVP 우선순위에서 제외 |
| A2 | **현재 범위** | 인증은 MVP에 필요한 최소 수준으로 두며 인증 방식 세부는 별도 결정 |
| A3 | **확정** | FastAPI 1 + Worker 1 + MySQL 8.4 LTS/InnoDB 기반 DB Queue 구조 |
| A4 | **확정 원칙** | AI provider API 호출·payload 전송은 `search/providers/` 경계에서만 발생. `recording`은 전송 가능한 AnalysisSource와 RemoteCopy 참조/수명 정보만 관리 |
| A5 | **현재 baseline** | `readout`은 서버/로컬 처리 baseline. 외부 모델 사용 여부가 바뀌어도 모듈 경계는 유지 |
| A6 | **미결 유지** | 원본 전체/부분/proxy/로컬/분할파일 활용 중 업로드 전략은 Architecture에서 고정하지 않음 |
| A7 | **회의 확정** | Search는 사건 **시간 구간/span**을 반환하고 신고용 파일을 직접 만들지 않음 |
| A8 | **회의 확정** | 최종 Package에는 제조사 원본 파일을 기본 포함하지 않고 신고용 결과물 중심으로 구성 |
| A9 | **회의 확정 + v4 해석** | Timestamp가 원본 화면에 없으면 근거가 확정된 뒤 **Report Video에만** 사후 각인 가능. Source는 변경 금지 |

---

# 2. 설계 원칙

## 원칙 1. 기능 단계는 모듈이 아니다

`Coarse → Fine → Plate → Timestamp → Export → Rule → Package` 순서를 그대로 폴더로 만들지 않는다. 변경 이유가 같은 기능은 같은 모듈에 두고, 변경 이유가 다르면 나눈다.

## 원칙 2. 데이터의 “관찰”과 “확정”을 분리한다

| 값 | 관찰 생산자 | 최종 판단/소유 |
| --- | --- | --- |
| 파일·stream 사실 | `recording` | 사실 자체는 recording |
| 사건 후보·visual event | `search` | 선택은 `case`, 확정 Evidence는 `evidence` |
| 번호판 OCR | `readout` | `evidence` |
| Overlay Timestamp | `readout` | `evidence` |
| 파일 Timestamp 후보 | `recording` | `evidence` |
| 사용자가 선택한 후보 | 사용자 입력 | `case` |
| 신고유형·요건 상태 | `evidence` | `evidence` |

## 원칙 3. Source와 Derived를 분리한다

```
External Source Reference        ← 사용자 원본. 삭제/rename/move 금지
        │
        ├─ Managed Source Copy    ← 만들었다면 서비스가 삭제 가능
        ├─ Analysis Source        ← AI 분석용
        ├─ Incident Clip          ← 원본 기반 분석/검토 구간
        ├─ Plate Image            ← 근거/신고 보조 이미지
        └─ Report Video           ← 신고용 최종 영상
```

`purge_case()`가 삭제하는 것은 **서비스가 관리하는 사본과 파생물**이다. 사용자 외부 원본은 참조만 해제한다.

## 원칙 4. 파일과 Media Stream을 같은 것으로 보지 않는다

실제 샘플에서는 AVI 한 파일 안에 전방 video, 후방 video, audio가 동시에 존재했다. 따라서 v4는 **물리 파일(Source Asset)과 Media Stream을 개념적으로 분리**한다.

구체 스키마는 Data Contract에서 정하지만, 이후 어떤 계약도 `asset_id 하나 = video stream 하나`라는 전제를 가져서는 안 된다.

## 원칙 5. 실패 경계를 값싸게 만든다

번호판 OCR 실패 때문에 긴 영상 탐색을 다시 실행하지 않는다. 신고영상 export 실패 때문에 Evidence를 잃지 않는다. 외부 RemoteCopy 만료 때문에 기존 Search 결과를 버리지 않는다.

## 원칙 6. 유일한 지휘자는 `case`, 유일한 실행기는 `common/runtime`

- `case`는 **작업 발주 의도와 부분 재실행 정책**을 소유하고 `JobIntent`를 만든다.
- `common/runtime`은 **queue, lease, heartbeat, retry timing, execution status, stale 처리**를 담당한다.
- 도메인 모듈은 Worker lifecycle을 직접 구현하지 않는다.
- runtime은 “이 작업이 왜 필요한가”를 판단하지 않는다.
- **package import cycle을 만들지 않는다.** `case`가 Worker 구현을 import하고 Worker가 다시 case/search를 import하는 구조가 아니라, FastAPI/Worker의 **composition root**가 `JobIntent → queue → public capability`를 연결한다.

이 분리는 v3의 `case=유일한 지휘자`를 유지하면서 실제 DB Queue 운영 책임을 common으로 이동시킨다.

> **Owner Review Required:** 세부 JobRecord 필드와 캐시 행 모델은 Data Contract에서 case/common이 최종 확인한다.

## 원칙 7. `web`은 domain contract를 직접 소비하지 않는다

v3의 일부 계약 표에는 `web`이 `Observation`, `VisualEvidence`, `PlateReadout`, `TimeResolution`을 직접 소비하는 것처럼 적혀 있었다. v4에서는 이를 제거한다.

```
search/readout/evidence/recording
              ↓
          case.view
              ↓
           CaseView
              ↓
             web
```

web은 raw score, OCR threshold, 요건 규칙, Timestamp 우선순위를 해석하지 않는다.

## 원칙 8. 제품과 Eval은 같은 public capability를 쓴다

`eval_mode`를 만들지 않는다. Eval 때문에 search 내부 분기를 만들지도 않는다.

Fine/Classification capability는 **Candidate 객체에만 묶이지 않고, 검증할 영상 입력 범위를 public input으로 받을 수 있어야 한다.** 제품은 Candidate에서 그 입력을 만들고, Eval은 정답 clip/frame sequence에서 만든다.

세부 input ref 구조는 Data Contract에서 정한다.

## 원칙 9. 규정·정책과 UI 표현을 분리한다

- 신고문 의미, 신고요건, 유형 매핑, Timestamp 사후각인 허용 여부 → `evidence`
- 사용자가 보는 문구·레이아웃·버튼명·카드 배치 → `web`

web이 신고 Evidence의 의미를 다시 생성하거나 바꾸지 않는다.

---

# 3. 주요 Product Policy가 구조로 옮겨진 방법

## 3-1. 한눈에 보기

| Product/기획 개념 | v4에서의 위치 |
| --- | --- |
| Main Agent / Orchestration | `case` |
| Cheap Coarse + Fine | `search` |
| Plate Pipeline | `readout` |
| Timestamp 후보 수집 | `recording` + `readout` |
| Timestamp 최종 판정 | `evidence/time_resolve` |
| 사건 시간 구간 → 실제 영상 구간 | `recording.resolve_span` |
| 원본 기반 사건 Clip | `recording` |
| 신고용 영상 / 사후 Timestamp | Evidence 결정 → `recording` export |
| Evidence Rule / 신고 요건 | `evidence/rules` |
| 신고문 / Package / Handoff | `evidence` |
| 전체 진행 / 부분 재실행 | `case` |
| 작업 queue 실행 | `common/runtime` |
| UI | `web` via `CaseView` |
| 성능 평가 | `eval` |

## 3-2. Timestamp Resolver v4 — Overlay를 우선하되 “검증된 관찰”만 쓴다

v3의 `metadata/filename 우선 → Overlay OCR fallback` 정책은 **260831 회의 결정으로 변경**한다.

v4의 정책은 다음과 같다.

```
① recording이 FILE_METADATA / FILENAME / 제조사 metadata 후보를 모두 수집한다.
② 선택된 사건의 Source-derived Incident Clip에서 readout이 Overlay Timestamp를 읽고 검증한다.
③ evidence가 모든 후보를 비교한다.

   VERIFIED VIDEO_OVERLAY
          ↓ 있으면 최우선
   FILENAME / FILE_METADATA / 제조사 metadata 비교
          ↓
   일치하면 해당 근거로 확정
   충돌하면 FILENAME을 MVP 기본값으로 선택
   + CONFLICT provenance 보존
   + non-blocking warning
          ↓
   USER_INPUT / UNKNOWN

별도 Timestamp 확인 단계를 추가하지 않는다. 사용자는 최종 USER_REVIEWED 화면에서 값을 수정할 수 있다.
```

단, **Overlay OCR 결과가 존재한다는 이유만으로 무조건 승리하지 않는다.** 형식·단조 증가·영상 duration 정합 등 readout의 검증을 통과한 Overlay를 가장 강한 근거로 본다.

### v4에서 보존해야 하는 정보

최종 시각은 임의의 `confidence=0.82` 같은 숫자 하나보다 다음을 설명할 수 있어야 한다.

```
어떤 Source를 선택했는가
그 Source는 어떤 검증을 통과했는가
다른 Source와 값이 충돌했는가
Source의 어느 시점 + 어떤 offset으로 계산했는가
사용자가 직접 수정했는가
```

권장 개념 상태:

```
AGREED · VERIFIED · UNVERIFIED · CONFLICT · UNKNOWN
```

정확한 enum은 Data Contract에서 확정한다.

### 사후 Timestamp 각인

원본 화면에 Timestamp가 없는 경우에도 신고용 파생영상에는 확정된 시간 근거를 표시할 수 있다.

```
Source / Incident Clip
      ↓ readout · evidence
확정 TimeResolution
      ↓
Report Video export 시 사후 Timestamp 표시
```

**금지:**

```
Source → 먼저 timestamp를 그려 넣음 → readout이 그 timestamp를 OCR → evidence 확정
```

우리가 만든 표시를 다시 근거로 읽는 순환을 만들면 안 된다.

사후 각인된 영상에는 “원본 화면에 내장된 Timestamp가 아니라 확보된 시간 근거를 바탕으로 표시한 파생영상”이라는 provenance를 보존한다.

## 3-3. Search 결과와 사건 영상 생성 책임

회의에서 다음을 확정했다.

> **Search는 사건이 발생한 구간을 찾는다. Search가 신고용 영상 파일을 만들지 않는다.**

```
원본 파일 A   00:00~00:59
원본 파일 B   01:00~01:59

Search Candidate Span = 00:55~01:05
                ↓
recording.resolve_span()
                ↓
A[00:55~00:59] + B[01:00~01:05]
                ↓
Incident Clip
```

파일 경계와 stream 선택은 recording만 해결한다.

이 Incident Clip은 **분석/검토용 원본 기반 구간**이다. OCR/readout은 이 구간의 Source pixel을 사용한다.

Evidence가 확정된 뒤 신고용 `Report Video`를 별도로 export한다.

## 3-4. Plate Pipeline

기존 경계는 유지한다.

```
사건 span
  ↓
대상 association
  ↓
번호판 detection
  ↓
multi-frame 수집 / best frame
  ↓
OCR
  ↓
consensus
  ↓
accept 또는 abstain
  ↓
evidence에서 사용자 확인/수정 반영
```

`target_hint`와 `track_ref`는 **optional hint**다. search 구현이 track 정보를 제공하지 못해도 readout은 span과 사용자/시각 단서만으로 자체 association을 시도한다.

## 3-5. Visual Event와 신고 유형은 다른 값이다

다음 셋을 같은 enum으로 합치지 않는다.

```
Visual Event
  SIGNAL / CENTER_LINE_CROSSING / SOLID_LINE_LANE_CHANGE / MOTORCYCLE_HELMET_NON_USE

        ↓ evidence rule mapping

SafetyReport Report Type
  예: 교통위반(고속도로 포함) / 이륜차 위반

        ↓

Violation Expression / 신고문에 쓰는 구체 표현
```

Search는 **Visual Event**까지만 다룬다. 신고 유형과 문구는 evidence가 확정 Evidence와 규정 데이터로 만든다.

## 3-6. 신고 준비 상태를 하나로 뭉치지 않는다

```
EVIDENCE_SUFFICIENT
      ↓
PACKAGE_READY
      ↓
USER_REVIEWED
      ↓
사용자가 안전신문고에서 직접 제출
```

| 상태 | 의미 | Owner |
| --- | --- | --- |
| **EVIDENCE_SUFFICIENT** | 필요한 Evidence가 정책상 충분함 | `evidence` |
| **PACKAGE_READY** | Report Video 등 실제 handoff 산출물까지 준비됨 | `evidence`가 판정, runtime/recording 결과를 입력으로 받음 |
| **USER_REVIEWED** | 사용자가 대신고 화면에서 최종 결과를 확인함 | `case` |
| **SUBMITTED** | 안전신문고에서 실제 제출 | 대신고가 소유하지 않음 |

## 3-7. 최종 Package 정책

기본 Package는 **실제 신고에 필요한 결과물 중심**이다.

```
Confirmed Evidence
      ↓
Report Video
Plate Image (확보된 경우)
Report Input Fields
Report Text
Handoff metadata / provenance
      ↓
ReportPackage
```

- 제조사 원본 1분 파일은 기본 Package에 포함하지 않는다.
- 번호판 확인용 이미지는 확보된 경우 다운로드할 수 있다.
- 번호판 OCR이 abstain했다고 해서 모든 Package가 자동 불가능하다는 뜻은 아니다. 필수 여부는 신고유형별 Evidence Rule이 판단한다.
- 신고문은 확정 Evidence 기반의 결정론적 Template 결과다.
- UI의 배치·설명 문구는 web이 바꿀 수 있으나 Evidence 의미와 신고문 핵심 내용은 web이 재해석하지 않는다.
- 안전신문고가 handoff 이후 수행하는 재압축·재인코딩은 대신고가 보장하지 않는다. 대신고는 **export 시점까지의 lineage**를 보장한다.

---

# 4. 상위 모듈 구조

## 모듈 1. `recording` — Source / Media / Timeline 계층

### ① 한 줄 설명

**사용자 블랙박스의 파일·stream·시간축을 다른 모듈이 안전하게 사용할 수 있는 span·frame·파생자산으로 바꿔주는 최하위 도메인 모듈이다.**

### ② 실제로 하는 일

- 사용자 원본 파일/폴더를 등록하되 원본을 수정하지 않는다.
- 파일 내부의 복수 video/audio stream을 식별한다.
- 파일명·metadata·제조사 정보에서 시간 후보를 수집한다.
- 여러 파일을 하나의 RecordingTimeline으로 정렬한다.
- 절대/상대 시간 구간을 실제 파일 + stream 조각으로 해석한다.
- search/readout이 필요한 분석 source·frame·incident clip을 제공한다.
- AI provider에 필요한 compatible source를 준비한다.
- Evidence 결정 이후 Report Video를 생성한다.
- 서비스가 생성한 사본과 파생물의 retention을 관리한다.

### ③ 책임

- External Source reference 등록
- Source file probe + `MediaStream[]` 식별
- Timeline / gap / file boundary 해결
- TimeSourceCandidate 수집
- GPS 관찰값 제공(없으면 UNKNOWN)
- AnalysisSource 준비 + RemoteCopy 참조/expiry registry 관리
- **frame 조회 public capability 제공**
- Incident Clip 생성
- Report Video / Plate Image 같은 파생 자산 생성
- Managed copy / proxy / RemoteCopy metadata / derived lifecycle 관리

### ④ 소유 데이터

| 데이터 | 의미 |
| --- | --- |
| `ExternalSourceRef` | 사용자 원본에 대한 immutable reference. 서비스 삭제 대상 아님 |
| `SourceAsset` | 물리 파일 단위 사실 |
| `MediaStream[]` | 한 SourceAsset 안의 video/audio stream 사실 |
| `RecordingTimeline` | 전체 source의 시간축 |
| `TimeSourceCandidate[]` | 파일이 제공하는 시간 후보 |
| `ManagedSourceCopy` | 서버가 복사했다면 서비스가 삭제 가능한 source copy |
| `AnalysisSource` | 분석용 입력 |
| `RemoteCopy` | 외부 provider에 올라간 참조와 expiry. recording이 registry를 소유하되 provider API 호출은 search/providers |
| `IncidentClip` | Source 기반 사건 구간 |
| `DerivedAsset` | Report Video / Plate Image 등 재생성 가능한 파생물 |

### ⑤ 개념적 내부 구성요소

```
manifest
probe
streams
timeline
gps_log
analysis_source
remote
frame
clip
export
retention
```

### ⑥ Public Capability

```
register_sources(...)                         -> RecordingManifest
build_timeline(...)                          -> RecordingTimeline
rebase_timeline(...)                         -> RecordingTimeline
resolve_span(time_range, stream_selector?)   -> AssetSpan[]
read_file_facts(asset_or_span)               -> SourceFacts
read_frame(frame_ref | span, at)             -> FrameRef
prepare_analysis_source(span, profile)       -> AnalysisSource
find_remote_copy(source_ref, provider)       -> RemoteCopy?
register_remote_copy(source_ref, remote_info) -> RemoteCopy
build_incident_clip(span, options)            -> IncidentClip
export_report_video(span_or_clip, options)   -> DerivedVideo
purge_case(case_id)                           -> DeletionReport
```

함수명은 예시다. 중요한 것은 **frame 조회가 명시적 capability로 존재하고, 파일 경계 해석은 resolve_span 하나로 모이는 것**이다.

### ⑦ 의존 대상

ffmpeg/ffprobe, filesystem/object storage. 다른 도메인 모듈에 의존하지 않는다. **실제 AI provider upload/delete API는 `search/providers/`가 호출하고, recording은 반환된 RemoteCopy ref·expiry를 등록/조회한다.**

### ⑧ 알면 안 되는 것

- 사건 종류/법적 위반
- 신고 규정의 의미
- 어떤 Timestamp source가 최종 정답인지
- 어떤 AI 모델을 쓰는지
- 현재 case stage

### ⑨ 실패 경계

- 파일 하나 probe 실패 → 해당 source만 unavailable
- 특정 stream decode 실패 → 다른 stream/파일은 생존
- clip/export 실패 → Search/Evidence 결과 생존
- RemoteCopy 만료 → 필요 시 재준비 가능, 기존 AnalysisRun은 생존
- purge 시 **ExternalSourceRef의 사용자 원본은 삭제하지 않는다**
- RemoteCopy는 ref/expiry를 정리하고, provider가 명시적 delete API를 지원하면 실제 delete 호출은 `search/providers/` 경계에서 수행한다. 미지원이면 provider expiry까지 남을 수 있음을 기록한다.

### ⑩ Owner Review Required

- File ↔︎ MediaStream 실제 스키마
- stream role(front/rear/unknown) 표현
- frame_ref 형식
- source copy / proxy / remote expiry
- 업로드 전략과 profile 이름

---

## 모듈 2. `search` — 사건 탐색

### ① 한 줄 설명

**긴 영상에서 사건이 있을 가능성이 높은 구간을 찾고, 해당 구간에서 visual event 근거를 구조화하는 모듈이다.**

### ② 책임

- Recall 우선 후보 구간 생성
- Fine / Classification 수준의 visual verification
- 4종 event routing
- 실행 구현·prompt/model version 기록
- normalized usage/cost를 runtime usage와 연결
- 실패 taxonomy 기록
- 법적 판단/신고 유형 확정 금지

### ③ 중요한 v4 변경

#### Search가 파일을 만들지 않는다

Search 출력의 핵심은 `CandidateEvent.span`이다. 실제 Incident Clip은 recording이 만든다.

#### Fine은 Candidate 객체에만 묶이지 않는다

v3의 `verify_candidate(candidate_ref)`만으로는 AI-Hub frame sequence나 독립 1분 clip classification을 평가할 수 없다.

v4의 public capability는 의미상 다음을 지원한다.

```
search_candidates(scope) -> CandidateEvent[]
verify_visual(input_ref, target_hint?) -> VisualEvidence
```

제품에서는 `input_ref`가 Candidate span에서 오고, eval에서는 clip/frame sequence fixture에서 온다.

**금지:** `if eval_mode`.

### ④ 소유 데이터

| 데이터 | 성격 |
| --- | --- |
| `AnalysisRun` | 불변 실행 기록 |
| `CandidateEvent[]` | 사건 후보 span |
| `VisualEvidence` | visual 관찰 결과 |

### ⑤ 내부 구현 baseline과 Architecture 구분

현재 Search Owner 조사에서 Gemini Files API + low resolution + 무음 + Flash-Lite가 유력 baseline으로 확인됐다. 그러나 **Architecture는 “항상 proxy”를 강제하지 않는다.**

```
search가 요구하는 것 = provider-compatible AnalysisSource
그 source를 어떻게 만드는지 = recording + search profile 합의
```

- `search/providers`가 1회 업로드한 RemoteCopy를 recording registry에 등록하고 coarse/fine에서 재사용할 수 있어야 한다.
- provider expiry가 지나면 재실행 경로가 있어야 한다.
- Batch API는 제품 runtime이 아니라 **offline eval** 용도로만 고려한다.

### ⑥ Cost / Usage 원칙

`AnalysisRun`은 과거 실행을 나중에도 비교할 수 있도록 **정규화된 사용량 + 실행 당시 pricing context를 추적할 수 있어야 한다.** 구체 필드는 Data Contract에서 확정한다.

raw provider payload 자체는 sensitive data 가능성이 있으므로 장기 보존/로그 정책과 분리한다.

### ⑦ 알면 안 되는 것

- 신고 규정·Report Type
- case stage
- 확정 Evidence
- 사용자 이름/연락처
- eval의 존재

`AnalysisScope.hint.free_text`가 외부 provider로 나갈 수 있으므로 **case에서 개인정보를 제거한 구조만 넘긴다.**

---

## 모듈 3. `readout` — 번호판·화면값 판독

### ① 한 줄 설명

**Incident Clip/Frame의 좁은 영역을 읽고 근거와 불확실성을 보존하되, 값을 확정하지 않는 모듈이다.**

### ② 책임

- 대상 차량 association
- 번호판 detection
- multi-frame crop 수집
- best frame + OCR + consensus
- abstain
- Overlay Timestamp OCR
- Overlay 형식·monotonic·duration 정합 검증
- 근거 frame refs 제공

### ③ Public Capability

```
read_plate(span, target_hint?)   -> ReadoutRun, PlateReadout
read_overlay_time(span)          -> ReadoutRun, OverlayTimeReadout
list_impls()                     -> implementation labels
```

`target_hint`는 optional이다. `track_ref`가 없어도 자체 association을 시도해야 한다.

`ReadoutRun`은 2026-09-06에 별도 계약으로 확정됐다 — `architecture/contracts/contract-readout-run.md`. 판독 실행 1회의 `outcome`과 실패 단계를 기록하며, **실행이 완전히 실패해 Readout 결과가 생성되지 않아도 run은 남는다.** 실패 분류 값 집합은 계약에 복제하지 않고 `modules/readout/decisions/failure-taxonomy.md`가 소유한다.

### ④ v4 Timestamp 관계

readout은 **Overlay가 어떻게 보이는지와 검증 결과**까지만 말한다.

```
readout = "화면에서 18:31:48로 읽혔고 연속성 검증을 통과했다"
evidence = "따라서 최종 occurred_at은 이 source를 사용한다"
```

### ⑤ 알면 안 되는 것

- 최종 발생시각 source 우선순위의 구현 세부
- 신고 요건/기한
- Report Type
- 확정 번호판 값
- 사용자 workflow stage

---

## 모듈 4. `evidence` — 증거 확정 / 신고 정책 / Package

### ① 한 줄 설명

**관찰값을 제품 정책에 따라 확정하고, 신고요건을 판정하며, 신고에 넘길 결과물의 의미를 결정하는 유일한 모듈이다.**

### ② 책임

- Observation → confirmed Evidence
- Timestamp 최종 resolution
- 사용자 correction 적용
- EvidenceNeeds 계산
- Visual Event → Report Type / violation expression 매핑
- 신고 요건 검사
- Evidence sufficient 판정
- Package ready 판정
- 신고문 Template 생성
- ReportPackage 조립
- Handoff 정보 생성

### ③ Timestamp 정책

```
VERIFIED Overlay가 있으면 최우선
→ 없으면 Filename / File Metadata / 제조사 metadata 비교
→ 충돌 시 Filename 기본값 + CONFLICT provenance + non-blocking warning
→ User Input / Unknown
→ 최종 USER_REVIEWED 화면에서 수정 가능
```

하지만 우선순위는 단순 source enum 비교가 아니라 **verification + conflict + provenance**를 함께 사용한다.

최종 `TimeResolution`에 근거 없는 numeric confidence를 필수로 두지 않는다.

### ④ 신고요건의 중요한 분리

다음은 서로 다른 조건이다.

```
occurred_at가 확정되었는가
Evidence Video 화면에 시간 표시가 있는가
차량번호 문자열이 확정되었는가
Evidence 영상에서 번호판이 실제 식별 가능한가
```

예를 들어 사용자가 번호판 문자열을 직접 수정했다고 해서 **영상 안에서 번호판이 잘 보인다는 뜻은 아니다.**

### ⑤ Requirement 결과는 PASS/FAIL 하나로 충분하지 않다

기한 초과처럼 경고는 필요하지만 handoff 자체를 막지 않을 수 있는 조건이 존재한다.

따라서 의미 수준에서:

```
PASS · WARN · BLOCK
```

세 단계가 필요하다. 정확한 enum은 Data Contract에서 확정한다.

### ⑥ Package 정책

`ReportPackage`에는 기본적으로 다음을 연결한다.

```
Report Video
Plate Image (available)
Report Fields
Report Text
provenance / notices
handoff target
```

제조사 원본 파일은 기본 download package에 포함하지 않는다.

### ⑦ 알면 안 되는 것

- AI model/prompt
- OCR library
- ffmpeg command
- Worker lease/heartbeat
- 사용자가 현재 어느 화면에 있는지
- 외부 시스템에 직접 작업 발주

`evidence`는 필요한 추가 관찰이 있으면 `EvidenceNeeds` 값만 반환한다.

---

## 모듈 5. `case` — Workflow / Orchestration

### ① 한 줄 설명

**사용자 의도와 현재 진행 상태를 소유하고, 어떤 작업을 언제 발주하고 무엇만 다시 실행할지 결정하는 유일한 지휘자다.**

### ② 상태 기계

v4 기본 workflow stage:

```
INTAKE
  ↓
SEARCHING
  ↓
CANDIDATE_REVIEW
  ↓
EVIDENCE_REVIEW
  ↓
READY
```

`TIME_HINT_EDIT`, major `TIMELINE_REBASE`, candidate 변경 등에 의해 뒤 단계에서 앞 단계로 돌아갈 수 있다.

### ③ 책임

- 자연어 단서 구조화 + 사용자 수정
- 상태 기계
- Candidate selection
- **Job Intent 생성**
- rerun_policy
- EvidenceNeeds → Job Intent mapping
- stale result의 domain 적용 여부 판단
- `CaseView` projection
- `USER_REVIEWED` 상태
- correction learning log export

### ④ Job ownership v4

v3의 `JobRecord = case 소유`를 다음처럼 명확히 분리한다.

```
case
  └─ 무엇을 / 왜 / 어떤 revision으로 실행할지 결정
      ↓ Job Intent
common/runtime
  └─ QUEUED → RUNNING → SUCCEEDED / FAILED / STALE / CANCELLED
     lease · heartbeat · retry timing · available_at · execution error
      ↓ produced refs
case
  └─ 현재 context에 유효하다고 판단한 결과만 domain state에 반영
     (중단된 job_id 집합 + 현재 선택 context — case_rev 일치로 거르지 않음)
```

즉 **발주 정책은 case**, **실행 lifecycle은 common/runtime**이다.

계약 이름은 다음과 같이 확정됐다 — 발주 의도는 **`JobRecord`**(case 소유, append-only), 실행 상태는 **`JobExecution`**(common/runtime 소유)이다. `JobExecution`의 계약 Owner는 `evidence`/common Owner이고 **구현 담당은 `recording` Owner**다(2026-09-04 백엔드 회의). `CANCELLED`는 v1에서 두지 않았으나 사용자 「중단」 흐름이 확인돼 `job-execution/v1.1`(2026-09-10)에서 추가됐다. status 값과 전이는 `architecture/contracts/contract-job-execution.md`가 소유한다.

### ⑤ 소유 데이터

| 데이터 | Owner |
| --- | --- |
| `Case` | case |
| `Selection` | case |
| `CorrectionRecord` | case |
| workflow stage / `USER_REVIEWED` | case |
| Job 발주 의도 / rerun policy (`JobRecord`) | case |
| Job execution lifecycle (`JobExecution`) | common/runtime — 구현은 recording Owner |
| Evidence 값 | evidence — case가 복사해 소유하지 않음 |

### ⑥ CaseView — v4부터 Core Contract

v3에서는 산문으로만 정의됐지만 v4에서는 web의 유일한 입력이므로 Core Contract로 승격한다.

의미 수준의 최소 구조:

```json
{
  "stage": "EVIDENCE_REVIEW",
  "progress": [],
  "hints": {},
  "candidates": [],
  "evidence": {},
  "requirements": {},
  "package": {},
  "running_jobs": [],
  "notices": []
}
```

> 위는 의미 수준 구조다. 필드·enum·nullable은 계약이 확정한다 — `case-view/v1.2`(2026-09-07)는 `requirements`를 `requirements_evidence` / `requirements_package` 두 객체로 나눠 세 gate(`EVIDENCE_SUFFICIENT`·`PACKAGE_READY`·`USER_REVIEWED`)를 구분해 내려보낸다(`contracts/contract-job-record-case-view.md` B절 §7).

CaseView는 적어도 다음 상황을 web이 **추론 없이** 표현하게 해야 한다.

```
정상
후보 0개
후보/근거 low confidence
GPS 없음
Timestamp conflict
Plate abstain
Timeout / partial result
```

`best_frame`, 다른 frame refs, conflict notice 등 UI에 필요한 근거는 **원천 contract를 그대로 노출하는 것이 아니라 case가 안전한 projection으로 전달**한다.

### ⑦ 알면 안 되는 것

- 130MB 등 규정 숫자
- OCR threshold
- prompt 내용
- Overlay가 왜 우선인지 같은 evidence 정책 로직
- codec/ffmpeg 세부

---

## 모듈 6. `web` — 단계형 작업공간

### ① 한 줄 설명

**CaseView를 구조화된 카드와 단계형 흐름으로 표현하고 사용자 명령을 case에 전달하는 브라우저 UI다.**

> **채팅 인터페이스는 만들지 않는다.** 자연어 **입력**은 intake 1회뿐이고(`product/core-user-flow.md` §5), 보정은 버튼으로 받는다(§9). 단 「어떤 상황이었나요?」·「번호판을 확인해주세요」처럼 **사용자를 안내하는 짧은 문구는 각 단계에 둔다** — 없애라는 뜻이 아니다. (v3의 「대화형 작업공간」 명칭은 core-user-flow §2가 폐기했다. web Owner 확인.)

### ② 책임

- Source 선택/등록 UI
- hint 확인/수정
- 진행 상태
- Top-K candidate card
- Evidence review
- Plate frame 확대/다른 frame 보기/수정
- Timestamp conflict/출처 표시
- Requirement warning/block 표시
- Package download/copy/handoff
- `USER_REVIEWED` action 전달

### ③ 단 하나의 read dependency

```
web → case.get_view() → CaseView
```

web이 다음을 직접 계산하면 Architecture 위반이다.

```
candidate score threshold
OCR accept threshold
Timestamp source priority
신고 기한
첨부 제한
Evidence sufficient 여부
```

### ④ MVP 범위

Desktop Web 우선. 차량 내장형 환경까지 고려한 모바일 반응형 최적화는 현재 MVP에서 제외한다.

---

## 모듈 7. `eval` — Offline Evaluation Harness

### ① 한 줄 설명

**제품 런타임과 독립적으로 public capability를 호출하고, 예측과 채점을 분리해 구현을 비교하는 개발용 패키지다.**

### ② v4 내부 구조 원칙

```
eval/
  datasets/
  manifests/
  runners/       # 모델/public capability 호출 → immutable prediction
  predictions/
  scorers/       # prediction + GT → metrics
  locked_test/
  results/
```

Prediction과 Scoring을 분리한다. GT/metric 정의가 바뀌어도 유료 API prediction을 다시 만들지 않아야 한다.

### ③ Dataset Tier

| Tier | 주 대상 | 주요 평가 |
| --- | --- | --- |
| **A — AI-Hub frame sequence** | classification / target | 4종 macro metrics, confusion matrix, target correctness |
| **B — 실제/YouTube 1분 clip** | search | [Recall@K](mailto:Recall@K), FP, timestamp offset(가능한 범위), 비용/latency |
| **C — 팀원 SD 원본** | recording/readout/time | Plate, overlay, timestamp source, 실제 file/stream 경계 |

한 dataset이 모든 metric을 책임하지 않는다.

### ④ Fine/Classification 독립 실행

A tier는 Candidate가 없는 frame sequence다. 따라서 eval이 search 내부 구현을 우회하지 않고 **public Fine/Classification capability를 직접 호출할 수 있어야 한다.**

이 요구 때문에 §2 원칙 8의 `verify_visual(input_ref, ...)`가 생겼다.

### ⑤ 비용 분모 — Owner 제안을 일부만 수용

Eval Memo의 “모든 분모를 1분 clip으로 통일”은 **eval 내부 비교에는 유용하지만 제품 전체 원가 지표를 대체하지 않는다.**

v4는 둘을 동시에 보존한다.

```
Runtime / Product economics:
  cost_per_source_video_hour
  latency_per_source_video_hour
  Fine exposure ratio

Eval clip suite:
  cost_per_clip
  fp_per_clip
  processed_duration_sec
```

원시 `processed_duration_sec`를 보존하면 서로 환산할 수 있다.

### ⑥ 유지되는 원칙

- eval은 product runtime이 아니다.
- search/readout은 eval의 존재를 모른다.
- eval-only branch 금지.
- 결과는 파일 기반으로 버전 추적 가능해야 한다.
- Product UX 지표는 별도 사용자 테스트다.
- locked test의 구체 개봉 횟수/승인 정책은 운영 정책으로 별도 확정한다.

---

# 5. Core Contracts — v4 의미 수준

> **v4의 핵심 변경:** `CaseView`를 부록에서 Core Contract로 올리고, 자산 계층·Job/runtime 경계·readiness 의미를 명시한다.
>
> 세부 필드·enum·serialization은 별도의 Data Contract에서 확정한다.

## 5-1. 계약 목록

| # | Contract | Producer / Owner | Direct Consumer | v4 핵심 |
| --- | --- | --- | --- | --- |
| ① | `Observation<T>` | 관찰 생산자 | evidence / case projection | 관찰과 확정 분리 |
| ② | `SourceAsset` / `MediaStream` / `RecordingTimeline` / `AssetSpan` | recording | search/readout/case | file≠stream, 경계 해결 |
| ③ | `AnalysisSource` / `RemoteCopy` / `IncidentClip` / `DerivedAsset` | recording | search/readout/evidence/case | Source/Derived 분리 |
| ④ | `AnalysisScope` | case / eval fixture | search | 개인정보 없는 분석 의도 |
| ⑤ | `AnalysisRun` + `CandidateEvent` | search | case / eval | span + immutable run |
| ⑥ | `VisualEvidence` | search | case → evidence/readout projection | legal 판단 없음 |
| ⑦ | `PlateReadout` / `OverlayTimeReadout` / `ReadoutRun` | readout | case → evidence · eval(실패 집계) | abstain + frame evidence / 판독 실행 기록 |
| ⑧ | `TimeResolution` | evidence | case | verified source/conflict/provenance |
| ⑨ | `EvidenceRecord` + `EvidenceNeeds` | evidence | case | 유일한 confirmed values |
| ⑩ | `RequirementReport` + `ReportPackage` | evidence | case | PASS/WARN/BLOCK + handoff |
| ⑪ | **`CaseView`** | case | **web only** | UI의 유일한 read contract |
| ⑫ | `JobRecord`(Job Intent) / `JobExecution` / `UsageRecord` | `JobRecord`: case · `JobExecution`·`UsageRecord`: common/runtime | runtime / case / eval aggregation | 발주 의미 / execution lifecycle / 비용 |
| ⑬ | `CorrectionRecord` | case | evidence | 사용자 수정 provenance |

> **중요:** web은 ①~⑩을 직접 읽지 않는다. case가 필요한 값을 `CaseView`로 projection한다.

> **⑦ `ReadoutRun` · ⑬ `CorrectionRecord` 등재 (2026-09-06).** 둘 다 목록에 없는데 다른 계약이 이미 참조하던 타입이었다(2026-09-05 확인 필요 항목). **Owner가 별도 계약 작성을 수용한 뒤 등재했다** — 등재는 전체 접합 수락을 뜻하지 않는다. `ReadoutRun`의 결과·usage 연결은 2026-09-07에 종결됐다(결과 계약의 필수 `run_ref` · `UsageRecord.run_ref` authoritative — `contracts/adr/adr-data-contract-call-closure-2026-09-07.md` §4.3·§4.4). `CorrectionRecord`는 여전히 Consumer Review 대기 Draft다. 등재 근거는 `contracts/adr/adr-consistency-2026-09.md` §6 R-3·R-4.

## 5-2. `Observation<T>`

핵심 의미는 v3와 동일하다.

```
value
source
status
근거 ref
producer/run
note
```

`confidence`는 관찰 producer가 실제로 정의할 수 있는 경우 보조 필드로 둘 수 있다. **Evidence의 최종 Timestamp confidence를 근거 없는 숫자로 생성하는 용도로 쓰지 않는다.**

상태는 최소한 다음 의미를 구분한다.

```
OK / NEEDS_REVIEW / UNKNOWN / ERROR / NOT_APPLICABLE
```

## 5-3. Source / Stream / Span 계약

### SourceAsset과 MediaStream

```
SourceAsset
  ├─ video stream(front?)
  ├─ video stream(rear?)
  └─ audio stream
```

`codec`, fps, resolution처럼 stream 성격인 값을 file 하나의 단일 속성으로 가정하지 않는다.

### AssetSpan

Search가 반환한 시간 구간은 `recording.resolve_span`을 통해 **복수 파일 + 복수 stream 조각**으로 해석될 수 있다.

구체 stream selector 규칙은 Data Contract에서 확정한다.

Data Contract 단계에서 보조 구조 3개가 추가됐다 — **`TimeSourceCandidate`**(Source에서 관찰된 절대시각 후보와 provenance. 최종 판정은 하지 않는다. `case`를 거쳐 `evidence/time_resolve`가 소비한다), **`SpanResolution`**(timeline 구간 → 실제 Source/Stream 구간 변환 결과), **`TimeSourceCheck`**(후보가 없을 때의 관찰 기록). 필드는 `architecture/contracts/contract-recording-timeline-asset-span.md`가 소유한다.

> **자산 계층 계약 상태 (2026-09-08 최종).** ② 중 `SourceAsset`/`MediaStream`과 ③ 전체는 `recording` Owner(정철원)의 계약 2건이 소유하고 **둘 다 `Final — Accepted`**다 — `contract-source-asset-media-stream.md`(`source-asset-media-stream/v1` — `SourceAsset`·`MediaStream`·`FrameRef`·canonical `AssetFacts`) · `contract-analysis-source-derived.md`(`analysis-source-derived/v1` — `AnalysisSource`·`RemoteCopy`·`IncidentClip`·`DerivedAsset`). 4 Consumer(`search`·`readout`·`case`·`evidence`) Review가 종결됐다. 과거 회차의 「작성 예정」·「최소 schema 제공 전」 규약은 이 상태로 대체됐다(개정 이력 참조).
>
> **필드·enum·nullable·시그니처의 정의처는 그 두 계약이다.** v4는 의미 수준만 고정하고 값 목록을 여기에 복제하지 않는다. **자산 계층 `ContractRef.kind` 값 공간(소문자 snake_case)은 `contract-source-asset-media-stream.md` §2.1 한 곳이 소유한다** — 다른 계약과 이 문서는 그 절을 가리킬 뿐이고, Consumer는 정확 문자열로 비교한다(대소문자 무시·별칭·prefix 추론·Consumer별 변환표 금지).
>
> **ref 작업 규약 — 유지된다.** `sa_` / `ms_` / `fr_` / `as_` / `rc_` / `clip_` / `da_` 접두어 + opaque id. **위치나 role을 ID에 인코딩하지 않는다**(`ms_<source_asset_id>_<role>` · `fr_<media_stream_id>@<offset_ms>` 같은 형태를 쓰지 않는다). `source_asset_ref`와 `role`은 `MediaStream`의 별도 필드로, frame 위치는 `FrameRef`의 `media_stream_ref + source offset`으로 보존한다. video/audio stream 종류와 `FRONT`/`REAR`/`UNKNOWN` camera role도 분리한다. **Consumer가 여러 값을 이어 붙여 ref를 합성하는 것도 금지다.**
>
> **함께 종결된 접합 3건 (2026-09-08).** ① `MissingRange.source_ref`는 `ContractRef {kind, ref} | null`이고 **키는 항상 존재한다**(`span-resolution/v1.2`) — `reason`별 non-null/`null` 규칙과 허용 `kind`는 `contract-recording-timeline-asset-span.md` §10.1·§10.2가 소유한다. ② **`AssetSpan`에는 별도 identity를 추가하지 않는다** — 동일성은 composite 값으로 비교하고, 그 값을 결합·해시해 span ref를 발급하는 것도 금지다(`contract-analysis-source-derived.md` §6.3·§6.5). ③ **사건 구간의 canonical ref는 `incident_clip`이다** — readout `input_ref.span_ref`는 삭제됐고(`plate-readout/v1.2`·`overlay-time-readout/v1.2`) **합성 `span_ref`를 쓰지 않는다**. clip 생성 전 fallback과 `evidence.interval`의 참조 대상은 `contract-evidence-record-needs.md` §8.3이 소유한다.
>
> **`mock-pack-v1-refs.md`는 폐기됐다(비규범).** 자산 ref의 형식·필드·lookup·`AssetFacts`·`FrameRef`를 그 문서에서 읽지 않는다.
>
> **남은 것과 계약 차단의 구분.** 계약 의미를 막는 항목은 **0건**이다. upload 방식·proxy profile 값·retention 일수·provider별 `RemoteCopy` delete 방식은 v4 A6 미결을 유지하고, `AnalysisSource` profile 값 목록(`profile_ref` 자체는 **필수 non-null·opaque**로 확정)·`stream_selector` 직렬화·thumbnail 이미지 전달 방식은 **구현·운영 수준의 비차단 Pending**이다. 현재 종결·Pending·준비도 판정의 소유 문서는 `contracts/adr/adr-data-contract-call-closure-2026-09-08.md` §4.7~§4.10 · §9 · §10.2다.

## 5-4. `AnalysisScope`

제품 Search의 입력 방어선이라는 원칙을 유지한다.

```
시간/범위
찾을 visual event types
비식별 hint
budget
contract version
```

v4에서는 Eval의 candidate-less classification을 `AnalysisScope` 하나에 억지로 집어넣지 않는다. **Search Candidate 생성용 scope와 Fine/Classification input ref는 다른 public input 역할**로 본다.

## 5-5. `CandidateEvent`

Candidate는 파일 자체가 아니라 **사건 span + visual hint**다.

```json
{
  "candidate_id": "c1",
  "span": "<timeline range>",
  "at_display": "<timeline-derived time>",
  "at_provenance": "TIMELINE_ANCHOR+OFFSET",
  "score": 0.81,
  "thumb_ref": "frame-ref"
}
```

`at_display`는 최종 신고 occurred_at가 아니다.

## 5-6. `VisualEvidence`

- visual primitives
- target observation
- temporal order 또는 object attribute observation
- visual_event_type
- uncertainty
- `legal_status = null` 원칙 유지

`track_ref`는 있으면 좋은 hint이지 readout의 필수 key가 아니다.

## 5-7. `PlateReadout` / `OverlayTimeReadout`

### Plate

반드시 표현 가능해야 하는 것:

```
target association 근거
detection 결과
best frame
frame_results[]
consensus
abstained + reason
Observation
```

### Overlay Time

반드시 표현 가능해야 하는 것:

```
sampled frame refs
parsed timestamp observations
format validation
monotonic validation
duration/alignment validation
Observation
```

## 5-8. `TimeResolution`

v4 예시 의미:

```json
{
  "resolved": {
    "value": "2026-08-31T18:31:48+09:00",
    "source": "VIDEO_OVERLAY_OCR",
    "verification": "VERIFIED"
  },
  "considered": [
    {"source": "VIDEO_OVERLAY_OCR", "verification": "VERIFIED", "used": true},
    {"source": "FILE_METADATA", "verification": "UNVERIFIED", "used": false},
    {"source": "FILENAME", "verification": "UNVERIFIED", "used": false}
  ],
  "conflict": {"exists": true, "shown_to_user": true},
  "provenance": {"observation_ref": "overlay-readout-ref"},
  "post_stamp": {"needed": false, "reason": "ORIGINAL_OVERLAY_USED"}
}
```

구체 enum/필드명은 Data Contract에서 확정한다.

## 5-9. `EvidenceRecord`

EvidenceRecord는 다음 의미를 분리해야 한다.

```
visual_event
report_type
violation_expression
occurred_at
plate text
location observations
selected incident/span
source/derived refs
```

`occurred_at_confirmed`와 `evidence_time_visible`, `vehicle_number_confirmed`와 `plate_visible_in_evidence`는 별개 상태로 표현 가능해야 한다.

## 5-10. `RequirementReport`

단순 `4/5`만으로 상태를 끝내지 않는다.

```
check 1: PASS
check 2: WARN
check 3: BLOCK
...

Evidence sufficiency
Package readiness
```

신고기한 계산은 단순 `occurred_at + 48h`로 hard-code하지 않는다.

## 5-11. `ReportPackage`

```
report_video_ref
plate_image_refs[]        # available
report_fields
report_text
notices/provenance
handoff_info
```

원본 제조사 Source는 기본 Package member가 아니다.

## 5-12. `CaseView`

CaseView는 **원천 domain contract의 복사본이 아니라 UI projection**이다.

```json
{
  "stage": "CANDIDATE_REVIEW",
  "progress": [
    {"kind": "COARSE", "state": "DONE"},
    {"kind": "FINE", "state": "RUNNING"}
  ],
  "hints": {},
  "candidates": [],
  "evidence": null,
  "requirements": null,
  "package": null,
  "running_jobs": [],
  "notices": [
    {"kind": "TIMESTAMP_CONFLICT", "severity": "WARNING"}
  ]
}
```

web은 `notices`와 backend-projected 상태를 표현하고 raw threshold로 상태를 재판정하지 않는다. 위 JSON은 의미 수준 예시이며 실제 필드(`requirements_evidence`/`requirements_package` 분리, `notices[].severity` 값 등)는 `contracts/contract-job-record-case-view.md`가 소유한다.

## 5-13. `JobIntent` / `JobRecord` / `UsageRecord`

### JobIntent

`case`가 만드는 **도메인 발주 의미**다. 최소한 작업 종류, 대상 case/revision, 입력 ref, 실행 정책 식별에 필요한 정보를 담고 runtime 내부 상태(lease/heartbeat)는 담지 않는다.

### JobRecord / JobExecution

> **2026-10-02 표기 정합:** 이 절은 Job Intent / Execution 분해(2026-09-05) 이전 표현으로 `JobRecord`에 실행 lifecycle을 두고 있었다. 의미는 Final Contract를 따른다 — `JobRecord`는 실행 상태가 없는 Intent이고, 실행 lifecycle은 `JobExecution`이다. 필드·enum은 `contracts/contract-job-record-case-view.md` A절과 `contracts/contract-job-execution.md`가 소유한다.

`JobRecord`(case 소유, append-only)는 발주 의도를 담는다.

```
case_id / case_rev
kind
input_fingerprint
```

실행 lifecycle은 `JobExecution`(common/runtime 소유)이 담는다.

```
QUEUED → RUNNING → SUCCEEDED / FAILED / STALE / CANCELLED
attempt
produced refs
masked error/failure kind
```

`available_at` · lease / heartbeat 같은 queue scheduling 값은 Runtime persistence의 구현 세부이며 Contract 필드가 아니다. `progress`는 `CaseView` projection이다.

**발주 이유와 rerun 정책은 case**, 이 execution lifecycle persistence는 **common/runtime**이다.

### UsageRecord

외부 API 호출과 비용은 Job 비용 한 칸에만 뭉개지 않는다. 호출 단위 UsageRecord를 두고 AnalysisRun과 Job에서 참조 가능해야 한다.

최소 의미:

```
provider / model / mode(runtime|eval/batch)
processed duration
input/output usage
latency
pricing snapshot/ref
calculated cost
```

---

# 6. Architecture Diagram / Dependency Rules

## 6-1. 호출 방향

```
web       → case
case      → { recording, search, readout, evidence, geocoder adapter }
search    → recording
readout   → recording
evidence  → (도메인 모듈 아무것도 호출하지 않음)
eval      → { search, readout, recording }

case      --JobIntent--> application/runtime composition root
Worker composition root --dispatch--> domain public capability

※ common/runtime은 도메인 규칙의 의존 대상이 아니라 바깥쪽 실행 인프라다.
```

### 중요한 두 규칙

1. `search`와 `readout`은 서로 직접 호출하지 않는다.
2. `web`은 case 이외 모듈을 직접 호출하지 않는다.

## 6-2. 공통 Runtime 경계

```
FastAPI
  ↓ enqueue
MySQL Job Queue
  ↓ claim
Worker 1
  ↓ public module capability
search / readout / recording
  ↓ result ref + usage
JobExecution / UsageRecord
  ↓
case applies only if revision is current
```

Runtime은 domain module이 아니므로 `common/`에 다음 정도만 둔다.

```
db
jobs
usage
logging
config
storage adapters
```

---

# 7. 주요 Runtime Flow v4

## 7-1. Happy Path

```
[web]
Source 선택 + 사용자 단서
  ↓
[case]
INTAKE / intent 구조화
  ↓
[recording]
register_sources → probe streams → build_timeline
  ↓
[readout] detect_overlay_presence   (존재 여부만 — 값 OCR 아님)
  ↓
[case/web]
사용자 단서 확인 + 「화면 시각 표시 유무 · GPS 유무」 고지
  ↓
[case]
COARSE_SEARCH Job Intent
  ↓
[common/runtime Worker]
[search] search_candidates
  └→ [recording] prepare_analysis_source / cached RemoteCopy lookup
      [search/providers] 필요 시 upload → [recording] RemoteCopy ref 등록
  ↓
CandidateEvent[] (span 중심)
  ↓
[search] verify_visual × candidates
  ↓
[case → CaseView → web]
Top candidates
  ↓ 사용자 선택
[case] selection_rev + case_rev
  ↓
  ├────────────────────────────────────────────────────────┐
  │                                                        │
  ▼                                                        ▼
[recording] resolve_span / build_incident_clip         [readout] read_plate
  │                                                        │
  ├→ [readout] read_overlay_time                            │
  │                                                        │
  ├→ [recording] read file time candidates / GPS            │
  │                                                        │
  └────────────────────── observations ─────────────────────┘
                           ↓
                        [case]
                           ↓ values only
                       [evidence]
                resolve_time → assemble
                           ↓
            EvidenceRecord + EvidenceNeeds
                           ↓
          needs가 있으면 case가 필요한 Job만 발주
                           ↓
                 check_requirements
                           ↓
                 EVIDENCE_SUFFICIENT?
                           ↓
              Report Video가 필요한 옵션 확정
                           ↓
                    [recording]
             export_report_video
       (필요 시 확정 time 사후 각인)
                           ↓
                 [evidence]
       derived asset 포함 requirements 재검사
                           ↓
             build_report_package
                           ↓
                   PACKAGE_READY
                           ↓
                  [CaseView/web]
        영상 + 번호판 이미지 + 신고정보 + 신고문
                           ↓ 사용자 최종 검토
                case.USER_REVIEWED
                           ↓
         안전신문고 열기 / 복사 / 다운로드
                           ↓
             사용자가 직접 최종 제출
```

> **intake의 `detect_overlay_presence`는 값을 읽지 않는다.** 화면이 업로드 직후에 알려야 하는 것은 「이 영상에 화면 시각이 있다/없다」뿐이고(`product/core-user-flow.md` §5 — GPS 없음을 마지막에 알게 하지 말라는 원칙과 같은 이유), 실제 시각 값은 §7-2대로 사건 선택 이후에 읽는다.
> **프레임 수·ROI·오판율, 그리고 「overlay 없음」과 「탐지 실패」를 구분하는 방법은 미결이다** — 실제 블랙박스 샘플 검증 후 readout Technical Spec에서 확정한다(`modules/readout/decisions/overlay-presence-detection.md`). readout Owner 확인.

## 7-2. 왜 Overlay OCR을 사건 선택 이후 같이 준비하는가

v3에서는 metadata가 정상일 때 Overlay OCR을 호출하지 않는 것이 정책이었다. v4에서는 **검증된 화면 표시 시각을 우선**하기로 했으므로 선택된 사건의 Incident Clip에서 Overlay 존재/판독을 확인하는 흐름으로 바뀐다.

다만 비용을 줄이기 위한 세부 최적화—예: overlay 존재 탐지 후 OCR, 특정 제조사 layout cache—는 readout Technical Spec 영역이다.

## 7-3. Incident Clip과 Report Video는 다르다

```
Incident Clip
- Source 기반
- OCR/readout/evidence 검토용
- 우리가 사후 삽입한 Timestamp가 근거로 섞이면 안 됨

Report Video
- 신고용 최종 파생물
- Evidence 확정 이후 생성
- 필요 시 사후 Timestamp/용량 변환 적용
```

## 7-4. 부분 재실행 원칙

| 변경/실패 | 다시 실행 | 유지 |
| --- | --- | --- |
| 시간 단서 수정 | 필요한 search scope | Source/timeline |
| 다른 candidate 선택 | 해당 Fine/Incident/readout/evidence | Coarse 결과 |
| 번호판 직접 수정 | evidence/requirements | Search/readout 과거 결과 |
| 번호판 reread | plate readout만 | Search 전체 |
| 사건 span 조정 | Incident/Report Video + 관련 requirement | Search evidence 가능한 범위 |
| Report Type 변경 | evidence rule / report text / package | Search/readout |
| occurred_at 사용자 수정 | evidence/time + report video stamp 재생성 가능 | Search |
| Timeline 표시만 rebase | display time / derived timestamps | pixel Search 결과 |
| 탐색 범위 자체가 틀림 | Coarse 이후 | Source/timeline corrected state |
| RemoteCopy 만료 후 같은 분석 재실행 | RemoteCopy 준비 + 필요한 external call | 기존 immutable run/result |
| Report Video export 실패 | export/package | confirmed Evidence |

구체 invalidation matrix는 case Data Contract / Technical Spec에서 확정한다.

---

# 8. Background Job / Failure / Ops

## 8-1. 즉시 vs Background

### 즉시

- CaseView 조회
- hint 수정
- candidate 선택 명령 처리
- pure evidence recompute
- requirement recompute
- report text template
- 상태 전이

### Background

- 큰 source/proxy 준비
- RemoteCopy upload (`search/providers` 경유)
- Coarse/Fine external AI
- plate/overlay OCR이 장시간일 경우
- Incident Clip / Report Video export
- 큰 파일 I/O

## 8-2. Job 실행 규칙

```
API request
  ↓
case가 JobRecord(Intent) 발주 + expected case_rev
  ↓
application/runtime composition root가 Runtime queue에 enqueue
  ↓
Worker claims row
  ↓
JobExecution RUNNING + heartbeat
  ↓
module result
  ↓
SUCCEEDED / FAILED
  ↓
case가 현재 context에 유효하지 않다고 판단한 결과(중단된 job_id · 현재 선택과 맞지 않음)이면
execution은 SUCCEEDED 그대로 두고, case가 produced를 반영하지 않아 현재 CaseView를 덮지 않음
```

`STALE`은 old `case_rev` 결과가 아니라 **실행 중 Worker가 살아 있지 않다고 Runtime이 판정한 terminal 실행 상태**다. 상태 의미는 `contracts/contract-job-execution.md` §6 · §9-8이 소유한다. (2026-10-02 표기 정합 — 이전 문구 「case_rev mismatch이면 STALE로 처리」는 Final Contract와 충돌해 바로잡았다. 2026-10-04 — 반영 기준도 `case_rev` 일치가 아니라 case의 context 유효성 판단으로 정합, #245 C-1a.)

같은 input fingerprint를 재사용할지, reread처럼 cache bypass할지는 **case rerun policy**가 결정한다.

## 8-3. 실패 시나리오

| 실패 | 살아 있어야 하는 것 | 사용자 표현 |
| --- | --- | --- |
| Source file 일부 decode 실패 | 나머지 source/timeline | 읽을 수 없는 구간 표시 |
| Candidate 0 | 전체 case | 범위 넓히기 / 단서 수정 |
| External AI 실패 | source/timeline/기존 run | 해당 job retry |
| Fine 일부 실패 | 다른 candidate | 해당 카드 partial failure |
| Plate abstain | 선택 사건/시간/영상 | 확인 필요 + frame 보기/수정 |
| Overlay OCR 불확실 | file time candidates | Timestamp conflict/review |
| GPS 없음 | 나머지 Evidence | 위치 미확인 — 오류 아님 |
| Report Video export 실패 | confirmed Evidence | 영상 생성 retry |
| Requirement WARN | Package 가능 여부 별도 | 경고 표시 |
| Requirement BLOCK | Evidence는 보존 | 막힌 이유 표시 |
| RemoteCopy expiry | 과거 결과 | 필요 시 재업로드 |
| stale Job | 현재 최신 revision | 사용자에게 옛 결과 노출 금지 |

## 8-4. 보관/삭제

```
ExternalSourceRef      사용자 원본     → 삭제하지 않음, 참조만 해제
ManagedSourceCopy      서비스 사본     → retention 대상
AnalysisSource/proxy   분석 사본       → 짧은 retention
RemoteCopy             외부 provider    → ref/expiry는 recording이 기록; 명시적 delete는 search/providers 경유
IncidentClip           분석 파생물      → retention 대상
ReportVideo/Image      신고 파생물      → retention 대상
```

외부 provider의 48시간 같은 구체 expiry는 provider adapter가 사실로 기록하되 **우리 전체 retention 정책과 동일한 개념으로 취급하지 않는다.**

## 8-5. Logging

운영 로그에는 다음 원문을 기본적으로 남기지 않는다.

```
번호판 문자열
정확한 GPS
원본 영상 frame
외부 API payload 전문
사용자 free text 전문
```

도메인 contract의 저장 필요성과 운영 로그의 allowlist 정책을 분리한다.

---

# 9. Evaluation 구조

## 9-1. 제품 런타임과 분리

`eval`은 별도 개발용 패키지다. 제품 배포 과정에서 자동 채점하지 않는다.

## 9-2. Runner / Scorer 분리

```
Dataset + Impl
      ↓
Runner
      ↓
Immutable Prediction
      ↓
Scorer + GT version + metric version
      ↓
Result
```

이렇게 해야 정답지나 metric 정의를 수정할 때 external AI 비용을 다시 쓰지 않는다.

## 9-3. 지표

### Search

- [Recall@1](mailto:Recall@1)/3/10
- timestamp/span error
- FP/hour 또는 FP/clip — dataset 성격에 맞게 raw duration과 함께 보고
- Fine Recall / Precision / Hard-negative FPR
- Final Event [Recall@3](mailto:Recall@3)

### Classification

- recall_macro
- precision_macro
- 5×5 confusion matrix(4종 + NONE)
- target correctness
- 유형별 breakdown

### Readout

- Exact Plate Accuracy
- Wrong Accept Rate
- Abstention Recall
- Detection/Association/CER 등 diagnostics

### Timestamp

- source agreement
- offset error
- overlay validation
- UNKNOWN / CONFLICT rate

`eval`은 `recording`/`readout`의 public output을 채점한다. **최종 source 선택 규칙 자체는 `evidence`의 pure policy/unit test에서 검증**하고, 이를 위해 eval이 evidence를 import하지 않는다.

### Efficiency

반드시 **runtime economics와 eval execution cost를 섞지 않는다.**

```
Runtime: source-video-hour 기준
Eval: clip 기준 + processed_duration_sec
```

Batch 실행이면 runtime baseline 결과와 다른 mode로 기록한다.

## 9-4. Data Tier

A/B/C tier를 사용하고 각 tier에서 측정할 수 없는 metric을 억지로 계산하지 않는다.

특히 YouTube 재인코딩 clip에는 원본 metadata/GPS가 없을 수 있으므로 Timestamp source 평가를 C tier와 같은 것으로 주장하지 않는다.

## 9-5. Correction Data

case correction은 코드 import가 아니라 익명화 파일로 eval에 흘린다.

사건 단위 학습 이력을 위해 correction이 어떤 `selection_rev` / candidate context에서 발생했는지는 보존한다. **구체 필드와 supersede/current-value 규칙은 현재 `contracts/contract-correction-record.md`(`correction-record/v1.1`, Final — Accepted)가 소유한다.**

---

# 10. 기술 스택 — v4 상태

## 10-1. `[확정]`

| 항목 | v4 |
| --- | --- |
| Language | Python |
| Cloud | AWS |
| Architecture | Modular Monolith |
| Backend | FastAPI |
| Runtime | API 1 + Worker 1 |
| Queue | DB Queue |
| DB | **MySQL 8.4 LTS / InnoDB** |
| SafetyReport | 자동 제출 API 연동 안 함 |
| Source | 사용자 원본 덮어쓰기/삭제 금지 |
| Video tool | ffmpeg / ffprobe |
| UI priority | Desktop Web, mobile responsive MVP 제외 |

## 10-2. `[현재 baseline / 추천]`

| 영역 | 현재 방향 | Architecture 의미 |
| --- | --- | --- |
| Search | KTC Elice ML API(OpenAI-compatible) 경유, media는 base64 inline 전송 (Issue #95 전환 이후). 모델·transport는 Search decision이 소유 | provider adapter 내부 |
| Search media | low-resolution, no-audio profile가 유력 | profile 자체는 recording/search 계약 |
| Remote reuse | Elice 경로는 provider-side reusable object(Files API · RemoteCopy)를 전제하지 않는다. 현재 재사용은 recording의 process-local AnalysisSource reuse뿐 | 저장·재사용 범위는 하위 문서(Runtime Ops)에서 결정 |
| Readout OCR | PaddleOCR pretrained baseline | readout 내부 교체 가능 |
| Plate detection | 현 Owner baseline 후보 | readout 내부 |
| Eval result | JSON + git | 제품 DB와 분리 |
| Progress | polling 우선 | web/runtime 세부 |

## 10-3. `[현재도 미결 / 하위 문서에서 결정]`

> **2026-09-19 정리:** 이 목록은 Architecture가 값 자체를 정해야 하는 TODO가 아니라, v4가 의도적으로 하위 계층에 남긴 구현·운영 선택만 유지한다. `EvidenceNeeds` 값 공간과 Data Contract schema/enum/nullable은 Final Contract 단계에서 닫혔고, `apps/web` stack은 `modules/web/decisions/web-stack.md`에서 React 19 · TypeScript 5.8 · Vite 6으로 결정됐으므로 여기서 제거했다.

- 원본 upload/processing 전략
- Analysis profile 정확한 resolution/FPS/bitrate
- Object Storage 범위
- provider별 RemoteCopy 즉시 삭제 가능 여부
- auth 세부
- plate tracker/detector 최종 조합
- exact retention days
- H.265/provider compatibility 실제 E2E
- locked test 개봉 운영 규칙

---

# 11. v4 이후 Owner Review Required — historical handoff

> **2026-09-19 maintenance:** 이 절은 v4 작성 직후 **Data Contract 전에 각 Owner에게 넘긴 검토 체크리스트의 역사 기록**이다. 체크박스 상태를 현재 구현 완료도나 현재 blocker로 해석하지 않는다. 이후 확정된 schema·enum·projection·rerun/cache 규칙은 Final Contract/Accepted Decision이 소유하고, 실제 구현·통합 잔여는 각 모듈의 checklist/Tech Spec과 루트 `README.md` 현재 상태를 따른다. 아래 체크는 당시 Owner 확인 기록을 보존하기 위해 임의로 다시 체크하지 않는다.

## 11-1. `recording` — 정철원

> **계약 종결 후속 (2026-09-08):** 아래 체크는 Owner 점검 기록이며 v4를 막는 blocker가 아니다. 이 중 자산 모델·frame access·clip 생성 책임·public contract 유지는 recording 자산 계약 2건이 `Final — Accepted`가 되면서 계약 문장으로 확정됐다 — `contracts/contract-source-asset-media-stream.md`(`MediaStream[]`·`FrameRef`·`resolve_frame`/`read_frame`) · `contracts/contract-analysis-source-derived.md`(clip 생성·파생 자산·lifecycle). upload/proxy 전략은 A6 미결을 유지하되 **public contract가 그 뒤에 숨는다**는 방향은 두 계약이 고정했다. 체크 표시는 Owner가 직접 한다.

- [ ]  `SourceAsset ↔︎ MediaStream[]` 모델이 실제 전방/후방/오디오 샘플을 표현하는가
- [ ]  사용자 원본 reference와 Managed Source Copy의 삭제 권한이 구분되는가
- [ ]  `read_frame` 또는 동등한 frame access contract가 readout 요구를 만족하는가
- [ ]  파일 경계를 넘는 Incident Clip 생성 책임이 recording 하나에만 있는가
- [ ]  upload/proxy 전략을 바꿔도 public contract가 유지되는가

## 11-2. `search` — 서어진

- [ ]  Search 결과가 file이 아니라 span 중심이라는 경계에 문제가 없는가
- [ ]  Fine/Classification을 candidate-less input에서도 public capability로 호출할 수 있는가
- [ ]  eval 전용 branch 없이 A-tier를 실행 가능한가
- [ ]  provider compatible `AnalysisSource`와 profile 책임이 recording과 충돌하지 않는가
- [ ]  Usage/pricing snapshot에 필요한 최소 의미를 Data Contract에 제안

## 11-3. `readout` / `web` — 신유민

- [x]  `target_hint`가 optional이어도 target association 전략이 성립하는가
- [x]  Overlay Timestamp를 사건 선택 이후 검증하는 v4 흐름에 문제가 없는가
- [x]  Incident Clip과 Report Video를 구분한 상태에서 OCR 근거가 항상 Source-derived pixel인가
- [x]  CaseView가 후보0/GPS없음/conflict/abstain/partial을 표현하는 데 충분한가
- [x]  frame refs를 web에 어느 범위까지 projection할지 제안

## 11-4. `case` — 유소연

> **감사 후속 기록:** 아래 체크는 개별 Owner 결정의 당시 기록이다. `CaseView`의 정보 상태·report projection은 2026-09-07에 case Owner 결정으로 종결됐다(`contracts/adr/adr-data-contract-call-closure-2026-09-07.md` §4.1·§4.2). 09-08 closure ADR §10.2의 준비도 판정은 당시 snapshot이며, **현재 구현/E2E 상태는 루트 `README.md`와 `modules/case/checklists/`를 따른다.**

- [ ]  5-state workflow가 실제 UI 흐름을 설명하는가
- [x]  `USER_REVIEWED`를 case가 소유하는 것이 자연스러운가 — **종결(2026-09-06).** `CaseView`에 `user_reviewed: boolean`을 두고 `stage`와 별개 축으로 분리했다. `contracts/contract-job-record-case-view.md` B절 §7
- [x]  Job Intent(case) / Job Execution(common) 분리가 rerun_policy와 충돌하지 않는가 — **종결.** `contracts/adr/adr-job-record-case-view.md` 부록-A §7 불변조건
- [ ]  input fingerprint와 cache bypass 규칙은 Data Contract에서 구체화
- [ ]  CaseView를 web 유일 read contract로 유지 가능한가

## 11-5. `eval` — 김대원

- [x]  runner/scorer 분리와 A/B/C tier 구조 확인
- [ ]  standalone Fine/Classification public capability가 실제 A-tier 요구를 만족하는가
- [ ]  runtime source-hour와 eval clip metric 병존에 문제 없는가
- [x]  prediction immutable / re-score 구조에 필요한 최소 version fields 제안
- [x]  locked test 개봉 운영안은 별도 운영 정책으로 제안

## 11-6. `evidence` / Runtime Ops — 김준영

- [x]  Verified Overlay 우선 Timestamp 정책이 회의 픽스안을 정확히 반영하는가
- [x]  Visual Event / Report Type / violation expression 분리가 규정 조사와 맞는가
- [x]  EVIDENCE_SUFFICIENT / PACKAGE_READY 구분이 충분한가
- [x]  PASS/WARN/BLOCK 의미를 Data Contract에서 구체화
- [x]  Job execution lifecycle와 UsageRecord를 common/runtime이 책임지는 경계 확인

---

# 12. v3 → v4 Red Team / 변경 결정

## RT1. `web → case`라고 해놓고 web이 domain contract를 직접 읽던 모순

**v3 문제:** 계약 표에서 Observation/VisualEvidence/PlateReadout/TimeResolution의 consumer에 web이 직접 들어가 있었다.

**v4 결정:** web direct consumer는 CaseView 하나. case가 UI projection을 만든다.

## RT2. `VideoAsset = 원본 파일 1개`가 실제 블랙박스와 맞지 않음

**실측:** AVI 하나에 전방/후방 video + audio stream.

**v4 결정:** SourceAsset과 MediaStream을 개념적으로 분리. 구체 schema는 Data Contract.

## RT3. `purge_case()`가 사용자 원본까지 지울 수 있는 표현

**v4 결정:** ExternalSourceRef는 삭제 금지. Managed copy와 derived만 삭제.

## RT4. Metadata 우선 Timestamp 정책이 260831 회의와 충돌

**v4 결정:** Verified Overlay가 있으면 최우선. 없으면 Filename / File metadata / 제조사 metadata 후보를 비교하고, 충돌 시 MVP에서는 Filename을 기본값으로 선택한다. `CONFLICT` provenance를 보존하고 non-blocking warning만 표시하며, 별도 확인 단계 없이 최종 `USER_REVIEWED` 화면에서 수정 가능하게 한다.

## RT5. 사후 Timestamp를 OCR 근거에 섞을 위험

**v4 결정:** Incident Clip(readout용)과 Report Video(신고용)를 분리. 사후 Timestamp는 Evidence 확정 뒤 Report Video에만.

## RT6. Search가 사건 영상 생성까지 책임질 위험

**v4 결정:** Search는 span 반환, file boundary / clip 생성은 recording.

## RT7. `verify_candidate(candidate_ref)`가 Eval A-tier를 막음

**v4 결정:** Fine/Classification capability를 candidate-independent input으로 일반화. eval-only branch 금지.

## RT8. JobRecord 단독 소유권 충돌

**v3:** case가 JobRecord 전체를 소유.

**Ops 조사:** runtime이 queue row 상태/lease/heartbeat를 관리해야 함.

**v4 결정:** case는 Job Intent/rerun policy, common/runtime은 execution lifecycle.

**종결(2026-09-05).** Data Contract에서 확정됐다 — `JobRecord`는 Job Intent로 범위를 좁히고 실행 상태는 `JobExecution`으로 분리. `force_rerun` 기본값 `false`, **`SUCCEEDED` 결과만 캐시 재사용**(`FAILED`/`STALE`은 재실행), optional `scope_ref`로 `AnalysisScope` 연결. 원문은 `contracts/adr/adr-job-record-case-view.md` 부록-A.

## RT9. `READY` 하나로 Evidence/파일/UI 상태가 섞임

**v4 결정:** EVIDENCE_SUFFICIENT / PACKAGE_READY / USER_REVIEWED 분리.

## RT10. Eval의 모든 metric을 1분 clip으로 통일할 것인가

**판정: 일부만 수용.**

Eval suite 내부 비교는 clip 단위를 사용하되 제품 economics의 `source-video-hour`는 유지한다. raw duration을 남겨 환산한다.

## RT11. 특정 Gemini proxy를 Architecture에 고정할 것인가

**판정: 고정하지 않음.**

현재 baseline은 low/no-audio profile이 유력하지만, Architecture는 `provider-compatible AnalysisSource` capability만 요구한다.

## RT12. 신고용 Package에 원본을 같이 넣을 것인가

**회의 결정:** 기본 포함하지 않는다.

v4 Package는 Report Video + Plate Image(가능 시) + Report Fields + Report Text 중심이다.

---

# 13. Architecture Handoff 요약

## 13-1. 이제 확정된 것

```
상위 도메인 모듈 = 7개 유지
web → case only
case = 유일한 orchestration owner
common/runtime = execution infrastructure
search = 사건 span + visual observation
recording = source/stream/timeline/span/frame/derived asset
readout = plate + overlay observation
Evidence = confirmed value + policy + package semantics
Eval = offline sibling

Verified Overlay Timestamp 우선
Search는 영상 file 생성 안 함
Incident Clip ≠ Report Video
사용자 원본 ≠ Managed copy
원본은 Final Package 기본 포함 안 함
```

## 13-2. v4 작성 당시 Data Contract로 넘긴 것 — historical handoff

> 아래는 **당시 이관 목록**이다. 2026-09-19 현재 `docs/architecture/contracts/contract-*.md` 16건은 모두 `Final — Accepted` 상태이며, 현재 schema·enum·nullable·불변조건은 각 Final Contract가 소유한다. 이 목록을 현재 TODO로 사용하지 않는다.

```
필드명 / enum / nullable
File ↔ MediaStream schema
frame_ref / input_ref
Analysis profile tag
TimeResolution verification enum
EvidenceNeeds enum
Requirement PASS/WARN/BLOCK exact rules
CaseView exact JSON
JobRecord row fields / fingerprint
UsageRecord pricing fields
CorrectionRecord event-level fields
```

## 13-3. v4 작성 당시 Technical Spec로 넘긴 것 — historical handoff

> 아래 항목은 Architecture 밖으로 내린 구현 선택의 범위를 보여주는 기록이다. 일부는 이미 하위 Decision/Tech Spec에서 닫혔고(예: web stack), 일부는 Runtime/Ops 또는 모듈 실험의 현재 미결로 남아 있다. 현재 상태는 해당 하위 문서를 따른다.

```
Gemini Files API 구현
proxy resolution/FPS
RemoteCopy registry/cache 및 provider-side delete 방식
OCR/detector/tracker 조합
FFmpeg command
MySQL queue SQL
lease/heartbeat interval
frontend framework
polling interval
storage layout
```

## 13-4. Owner가 v4를 검토할 때 보는 기준

> **“내 구현 취향과 다른가?”가 아니라 아래 세 가지에만 답한다.**

1. 내 모듈이 **소유하면 안 되는 값을 소유하게 되었는가?**
2. 타 모듈의 내부 구현을 **알아야만 구현 가능한 경계가 생겼는가?**
3. 내 모듈의 정상적인 실패가 **비싼 상위 단계를 불필요하게 재실행시키는가?**

셋 다 아니면 Architecture는 통과시키고 세부 구현 논쟁은 Data Contract / Technical Spec으로 내린다.

---

# 부록 A. 기획안/회의 용어 ↔︎ v4 구조

| 용어 | v4 위치 |
| --- | --- |
| Main Agent / Orchestrator | `case` |
| Case State | `Case` + workflow stage + Selection |
| Coarse Candidate | `search.search_candidates` |
| Fine Verification | `search`의 candidate-independent verification capability |
| Candidate Top-K | `CandidateEvent[]` |
| Evidence Interval | Candidate span → recording Incident Clip |
| Plate Pipeline | `readout` |
| Best/Multi-frame | `PlateReadout` |
| Timestamp Resolver | recording/readout 수집 + evidence 판정 |
| Overlay Timestamp 우선 | evidence time policy — verified observation 기준 |
| Metadata 사후 각인 | Evidence 확정 → recording Report Video export |
| GPS parser | `recording` |
| Geocoder | thin adapter |
| Evidence State | `EvidenceRecord` |
| Visual Event | search observation |
| SafetyReport Report Type | evidence rule mapping |
| 신고문 | evidence deterministic template |
| 신고 Package | `ReportPackage` |
| Handoff | download/copy/open only |
| FFmpeg | recording 내부 tool |
| Job Queue | common/runtime infrastructure |
| Usage Ledger | `UsageRecord` |
| UI state | `CaseView` |
| Evaluation Harness | `eval` |

---

# 부록 B. v4에서 특히 금지하는 구조

```
web → evidence 직접 조회
web이 raw score로 "low confidence" 계산
case가 Timestamp source 우선순위 직접 구현
evidence가 readout/search 함수를 직접 호출
search가 신고용 mp4 생성
readout이 Report Video에 사후 삽입된 Timestamp를 최종 근거로 OCR
recording이 Visual Event나 신고유형을 조건문으로 사용
purge_case가 사용자 SD카드 원본 삭제
Fine evaluation을 위해 search에 if eval_mode 추가
runtime이 "왜 이 job이 필요한지" 판단
Eval batch cost와 제품 runtime cost를 같은 숫자로 보고
```

---

# 마지막 — v4의 성공 기준

- [ ]  7개 상위 모듈의 책임과 호출 방향이 한 문장으로 설명된다.
- [ ]  사용자 원본 / Managed copy / Incident Clip / Report Video가 구분된다.
- [ ]  한 파일 안의 복수 Media Stream을 Architecture가 막지 않는다.
- [ ]  Search는 사건 span을 찾고 Recording이 실제 clip을 만든다.
- [ ]  OCR은 Source-derived Incident Clip을 보고, 사후 Timestamp는 그 이후 Report Video에 들어간다.
- [ ]  Verified Overlay 우선 → Filename/Metadata 비교 → 충돌 시 Filename 기본값 + CONFLICT provenance + non-blocking warning 정책이 모순 없이 설명된다.
- [ ]  web은 CaseView 하나만 소비한다.
- [ ]  case와 common/runtime의 Job 책임이 분리된다.
- [ ]  Evidence sufficient / Package ready / User reviewed가 구분된다.
- [ ]  Eval이 candidate-less classification을 public capability로 실행할 수 있다.
- [ ]  아직 결정하지 않은 upload/profile/schema 세부가 미결 상태로 남아 있다.
- [ ]  각 Owner가 §11만 보고 자기 모듈의 후속 Data Contract 작업을 시작할 수 있다.
