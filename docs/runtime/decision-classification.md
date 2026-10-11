# Runtime/Ops Decision Classification

**Status:** Working — Decision 유형 · 결정 시점 분류\
**Owner:** common/runtime — 김준영\
**Classified at:** 2026-10-03 · `origin/develop` `10787d8` (PR #241 merge 직후)\
**Workflow step:** [`runtime-ops-workflow.md`](./runtime-ops-workflow.md) §3 Decision 유형 · 결정 시점 분류\
**Input:** [Open Decision Register](./open-decision-register.md) — 18 group · External Input EI-01~EI-08

> 이 문서는 Register의 각 Open Decision을 **누가 · 언제까지 · 어떤 절차로 닫는가**로 분류한다.
>
> **무엇을 고를지는 적지 않는다.** 답과 추천안은 workflow §4 조사 이후 단계다. Question · Evidence · Already fixed · Sub-decision 원문은 Register가 SoT이고 여기에는 복제하지 않는다. 각 RD는 Register 앵커로 링크한다.
>
> Register가 바뀌면(새 RD · `CLOSED` · `SUPERSEDED` · group 경계 변경) 이 문서의 해당 행도 같이 고친다.

## 1. 목적과 범위

```text
open-decision-register.md   → 무엇이 열려 있는가 (§2 SoT)
decision-classification.md  → 누가 · 언제 · 어떤 route로 닫는가 (§3 view)
§4 조사                      → 어떤 근거를 더 모으는가
§4 이후                      → 어떤 안을 추천하고 확정하는가
```

이 문서만 보고 RD마다 다음에 답할 수 있어야 한다.

- 어떤 종류의 결정인가 — [§3](#3-classification-matrix) Type
- 누가 최종적으로 닫는가 · Runtime 혼자 닫을 수 있는가 — Decider · Required Consult · Runtime alone
- 언제까지 닫아야 하고 어느 milestone을 막는가 — Timing · Gate
- 어떤 문서 · Issue · ADR · Contract로 닫는가 — Closure Route
- §4에서 외부 조사가 필요한가 · External Input 확인이 필요한가 · Experiment 뒤로 미루는가 — §4 Need, [§6](#6-4-external-research-queue)~[§8](#8-experiment-dependent-queue)
- 먼저 닫아야 할 상류 Decision은 무엇인가 — Upstream, [§9](#9-dependency--resolution-order)

이번 분류에서 하지 않은 것: 답 선택 · 추천안 · 외부 조사 · 실험 · 구현 · Contract 변경 · ADR 작성 · Issue 생성.

---

## 2. 분류 기준

### 2.1 Decision Type

workflow §3.1의 책임 유형 네 가지를 출발점으로 하되, 「실측 기반」은 **무엇에 관한 결정인가**와 **언제 닫는가**를 한 칸에 담고 있어 둘로 나눴다. 시점은 Timing 축(C)과 Research Need(`EXPERIMENT`)가 맡고, 유형 축에는 인프라 · 배포 topology 결정을 `ARCH_OPS`로 둔다.

| Type | 판정 기준 | workflow §3.1 대응 |
| --- | --- | --- |
| `LOCAL` | 다른 모듈 Contract · Owner 문서를 바꾸지 않고, Runtime Tech/Ops Spec이 소유한 범위 안에서 닫힌다 | Runtime 단독 결정 |
| `CROSS_MODULE` | 둘 이상의 모듈 경계 · Contract · Owner 결정 문서를 건드린다. 한 Owner가 독단으로 닫으면 안 된다 | 공동 결정 |
| `PRODUCT_POLICY` | 사용자에게 보이는 동작이나 사용자 데이터 정책이 결정의 중심이다. Runtime 구현 편의로 정할 수 없다 | 제품/정책 결정 |
| `ARCH_OPS` | 인프라 · 배포 · 장기 운영 topology 선택이다. 되돌리는 비용이 크고 Ops Spec · ADR에 반영될 가능성이 높다 | 실측 기반 결정의 「무엇」 부분 |

- 한 RD에 **Primary 1개**만 둔다. 두 번째 성격이 결정권이나 closure route를 실제로 바꿀 때만 Secondary를 붙인다.
- workflow §3.1 예시와 다르게 분류한 경우는 [§3.1](#31-rd별-분류-근거)에 이유를 적었다(RD-03 · RD-14 · RD-19).

### 2.2 결정권

| 칸 | 뜻 |
| --- | --- |
| **Decider** | 결정을 닫을 권한이 있는 Owner. 공동 결정이면 `Joint`로 쓰고 각자의 범위를 나눈다. `Joint`는 공동 소유가 아니라 **각 Owner가 자기 surface를 승인한다**는 뜻이다(모듈 Owner 1명 원칙 유지) |
| **Required Consult** | 결정 전에 반드시 확인을 받아야 하는 Owner. 그 Owner의 Contract · Owner 결정과 충돌하면 닫을 수 없다 |
| **Informed** | 결과를 알려야 하지만 확인 없이 닫을 수 있는 Owner. 매트릭스에는 적지 않고 [§3.1](#31-rd별-분류-근거)에만 적는다 |
| **Runtime alone?** | `YES` = Decider가 common/runtime뿐이고 Required Consult가 없다. 그 밖은 `NO` |

판정 근거:

- 모듈 Owner = 최종 결정권자 ([`ownership.md`](../management/ownership.md) 원칙 4).
- cross-module Contract는 **Producer Owner가 결정하고 Consumer가 확인**한다(각 Contract 머리말 Producer / Consumer 절).
- 코드를 구현하는 사람과 결정권자를 구분한다. 예: JobExecution 구현 담당 정철원은 RD-01의 Decider가 아니다(Tech Spec 머리말 · `ownership.md` recording 절).
- 운영진(카테캠) 자원 요청 · 공지 확인은 module Owner 결정이 아니라 외부 확인이다. Runtime alone 판정에 넣지 않는다.

Owner 표기 — 매트릭스에는 모듈 이름만 쓴다.

| 모듈 | Owner | 비고 |
| --- | --- | --- |
| common/runtime (`runtime`) · `api` composition root | 김준영 | PM(B-1 Product Spec 승인)을 겸한다 |
| `case` | 유소연 | |
| `search` | 서어진 | |
| `recording` | 정철원 | JobExecution 구현 담당을 겸한다 — 결정권은 아님 |
| `readout` · `web` | 신유민 | |
| `eval` | 김대원 | |

> **역할 겹침.** common/runtime Owner · `api` composition root Owner · PM이 같은 사람이다. Runtime이 당사자인 Joint 결정(특히 RD-05a의 Owner 확정)과 Product Spec 문구가 바뀌는 PRODUCT_POLICY 결정에서 이 겹침을 어떻게 처리할지는 이 문서가 정하지 않는다 — `[확인 필요]`. 참고 선례는 [`cross-cutting-decisions.md`](../management/cross-cutting-decisions.md) B-3이다.

### 2.3 Timing A/B/C/D

workflow §3.2를 따른다. 경계가 애매한 지점만 이렇게 읽는다.

| Timing | 뜻 | 판정 질문 |
| --- | --- | --- |
| **A** | 구현 전에 반드시 닫는다 | 답에 따라 구현 방향 · Contract · 모듈 경계가 달라지는가. 첫 비동기 Real E2E가 성립하지 않는가 |
| **B** | Provisional Baseline으로 구현할 수 있다 | 초기값 · reversible 구조로 먼저 구현하고, Implementation Plan에 Provisional 가정을 적으면 되는가 |
| **C** | 구현 후 실측해야 닫힌다 | 구현 전 선택보다 P2 · smoke · Real E2E 측정이 먼저인가 |
| **D** | 현재 구현 milestone을 막지 않는다 | 명시된 trigger나 Gate(M9 · M10) 전에만 닫으면 되는가 |

D는 「MVP 이후로 미룬다」가 아니다. Gate가 MVP 안에 있는 D도 있다(RD-10, Gate M9).

Group Timing과 Sub-decision Timing이 다를 때의 원칙은 Register 「읽는 법」을 따른다 — A group 안의 일부 세부가 B로 내려가는 것은 허용하고, B/C/D group 안에 A sub-decision은 두지 않는다. 확인 결과는 [§4.5](#45-sub-decision-timing-예외).

### 2.4 Decision Gate

Gate는 **늦어도 이 milestone 전에 닫혀 있어야 하는 지점**이다. 날짜가 아니다. M1~M4는 workflow §7 Implementation Plan 우선순위 순서이고, §7에서 순서가 바뀌면 Gate 이름은 그대로 두고 순서만 따라간다. M1~M5가 어느 Task 착수에 해당하는지는 [Runtime Implementation Plan](./runtime-implementation-plan.md) §3.1이다.

| Gate | Milestone | 근거 |
| --- | --- | --- |
| **M1** | Runtime persistence 구현 착수 — MySQL Queue · JobExecution · UsageRecord schema / migration · Final UsageRecord append | workflow §7 우선순위 1 |
| **M2** | Worker 구현 착수 — claim loop · handler · failure mapping · retry · lease / heartbeat · stale sweep | workflow §7 우선순위 2 |
| **M3** | API composition root · HTTP / Web 실연동 착수 | workflow §7 우선순위 3 |
| **M4** | Docker / Compose slice 착수 | workflow §7 우선순위 4 |
| **M5** | 첫 비동기 Real E2E | Register dependency graph의 마일스톤 |
| **M6** | 첫 EC2 배포 — P2 실행 환경 구성 | [P2 plan](./experiments/elice-runtime-capacity-smoke-plan.md) §5 (완료 판정은 baseline 동등 배포 환경) |
| **M7** | P2 Runtime Capacity Smoke 착수 | workflow §9 · P2 plan §8 |
| **M8** | P2 결과 확보 후 | workflow §9~§11 |
| **M9** | Pre-deploy review — 실제 사용자 데이터 · 외부 provider 운영 전 | Ops §21 · [`pre-deploy-security-review.md`](../management/pre-deploy-security-review.md) |
| **M10** | 외부 공개 demo 또는 OAuth 요구 발생 | Ops §2-2 trigger · Register RD-14 Trigger |

매트릭스의 Gate는 **실효 Gate**다. RD 자신이 직접 막는 milestone보다 그 RD가 선행하는 다른 A Decision의 Gate가 더 이르면 더 이른 쪽을 적고, 직접 Gate를 괄호에 둔다.

Timing과 Gate의 정합 규칙:

```text
A → 결정 확정 Gate가 M1~M5
B → Provisional 가정 Gate(M1~M7)와 최종 Gate(≤ M9)를 둘 다 적는다
C → M8
D → M9 또는 M10
```

### 2.5 Closure Route

| Route | 뜻 |
| --- | --- |
| `LOCAL_SPEC` | Runtime Tech Spec · Ops Spec · Runbook 갱신으로 충분하다 |
| `CONTRACT` | cross-module Contract 개정 · 신규 작성 · Finalization이 필요하다 |
| `OWNER_DECISION` | 다른 모듈의 Owner 결정 · 정책 문서에 확정을 남겨야 한다 |
| `ADR` | 장기 architecture · topology 선택이라 ADR이 필요하다 |
| `EXPERIMENT_BASELINE` | 측정 뒤 baseline · config에 반영해 닫는다 |
| `JOINT_ISSUE` | 여러 Owner가 Decision Card 형태 Issue에서 닫는다 |

매트릭스는 `Primary → Follow-up artifact`로 쓴다. Follow-up에 붙은 「조건부」는 Register가 그 artifact를 「가능」 · 「필요해지면」으로 적은 경우다. 이번 단계에서 Issue · ADR · Contract를 만들지 않았다(workflow §5 · §7에서 처리).

### 2.6 Research Need

| Tag | 뜻 |
| --- | --- |
| `NONE` | 현재 repository의 Contract · Spec · Owner evidence만으로 결정안을 만들 수 있다 |
| `EXTERNAL_RESEARCH` | 외부 공식 문서 · 기술 사례 조사가 결정안 작성에 필요하다 → [§6](#6-4-external-research-queue) |
| `EXTERNAL_INPUT` | EI-xx 확인이 입력이다 → [§7](#7-external-input-queue) |
| `EXPERIMENT` | 외부 조사보다 P2 · smoke · Real E2E 측정이 먼저다 → [§8](#8-experiment-dependent-queue) |
| `OWNER_ALIGNMENT` | 기술 조사보다 다른 모듈 Owner와의 정책 · 계약 합의가 핵심이다 |

복수 tag를 허용한다. `NONE`은 다른 tag와 함께 쓰지 않는다.

§4 조사 우선순위는 **조사 실행 순서**이지 Decision 중요도가 아니다.

```text
R1 — 실효 Gate가 M1~M5인 Decision(또는 그 sub-decision)의 결정안 작성에 필요한 조사
R2 — B baseline 또는 Gate M6~M7 sub-decision의 품질을 높이는 조사
R3 — C / D, 또는 trigger 뒤에 하는 조사
```

---

## 3. Classification Matrix

Upstream은 Register 각 group의 「선행」 Decision만 적는다(External Input 제외 · 「함께 본다」는 `~`). §4 Need 약어: `ER` = EXTERNAL_RESEARCH · `EI` = EXTERNAL_INPUT · `EXP` = EXPERIMENT · `OA` = OWNER_ALIGNMENT.

| RD | Type (Primary / Secondary) | Decider | Required Consult | Runtime alone? | Timing | Gate | Closure (Primary → Follow-up) | §4 Need | Upstream |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [RD-01](./open-decision-register.md#rd-01--runtime-persistence--queue-physical-design) | LOCAL / ARCH_OPS | runtime | — | **YES** | A | M1 | LOCAL_SPEC → ADR(조건부) | ER(R1 · R2) | RD-02 · RD-03 · RD-06 · RD-18 · RD-19 |
| [RD-02](./open-decision-register.md#rd-02--retry-attempt-생성-시점과-queued_at-의미) | CROSS_MODULE | runtime | case · eval (web: CaseView 문구 변경 시) | NO | A | M1 | JOINT_ISSUE → LOCAL_SPEC · CONTRACT(조건부) | OA | RD-03 |
| [RD-03](./open-decision-register.md#rd-03--retry-책임-층위--failure-lifecycle) | CROSS_MODULE | Joint: runtime + search | case · readout | NO | A | M1 (직접 M2) | JOINT_ISSUE → ADR · OWNER_DECISION | OA · EI | — |
| [RD-04](./open-decision-register.md#rd-04--execution-timing-provisional-baseline의-축과-제약) | LOCAL | runtime | case (RD-04b) | NO | B | M2 → 최종 M8 | LOCAL_SPEC → EXPERIMENT_BASELINE | EI · EXP | RD-01 · RD-03 |
| [RD-05](./open-decision-register.md#rd-05--http-api-contract와-transport-담당) | CROSS_MODULE | Joint: api ↔ web (RD-05a) → RD-05a가 정한 Contract Owner (RD-05b~f) | case · recording (RD-05e) | NO | A | M3 | JOINT_ISSUE → CONTRACT | OA · ER(R1) | RD-06 · RD-17 |
| [RD-06](./open-decision-register.md#rd-06--case--runtime-dispatch-port와-결과-반영-경로) | CROSS_MODULE | Joint: case + runtime | recording (RD-06g) | NO | A | M1 (직접 M3) | JOINT_ISSUE → ADR(조건부) | OA | — (~RD-17) |
| [RD-07](./open-decision-register.md#rd-07--runtime-configuration--secret-주입) | CROSS_MODULE / ARCH_OPS | runtime | search (RD-07a · d) · eval (RD-07e) | NO | A | M4 (RD-07c: M6) | JOINT_ISSUE → OWNER_DECISION · LOCAL_SPEC | OA · ER(R1 · R2) | — |
| [RD-08](./open-decision-register.md#rd-08--pricing--fx-artifact) | CROSS_MODULE | Joint: runtime + search | case | NO | B | M1(placeholder) → 최종 M9 | JOINT_ISSUE → LOCAL_SPEC · OWNER_DECISION | OA · EI | — |
| [RD-09](./open-decision-register.md#rd-09--worker-domain-service-수명--analysissource-process-local-reuse) | CROSS_MODULE | Joint: recording + runtime | — | NO | B | M2 → 최종 M8 | JOINT_ISSUE → EXPERIMENT_BASELINE | OA · EXP | RD-17 |
| [RD-10](./open-decision-register.md#rd-10--자산--원장-retention과-purge-범위-제품정책) | PRODUCT_POLICY / CROSS_MODULE | Joint: recording (RD-10a · b · e) + runtime (RD-10c · d) | case | NO | D | M9 | JOINT_ISSUE → CONTRACT · ADR(조건부) | OA · EI | RD-17 |
| [RD-11](./open-decision-register.md#rd-11--ops-retention--cleanup) | LOCAL | runtime | recording (RD-11b · c) | NO | B | M7 → 최종 M9 | LOCAL_SPEC | EI · EXP · ER(R2) | RD-10 · RD-13 |
| [RD-12](./open-decision-register.md#rd-12--deployment-pipeline-세부) | LOCAL / ARCH_OPS | runtime | — | **YES** | B | M4 (RD-12a · g) → 최종 M6 | LOCAL_SPEC → ADR(조건부) | ER(R2) | RD-01 · RD-05 · RD-07 · RD-17 |
| [RD-13](./open-decision-register.md#rd-13--운영-관측-수단) | LOCAL | runtime | — | **YES** | B | M7 → 최종 M8 (RD-13c) | LOCAL_SPEC → EXPERIMENT_BASELINE | ER(R2) · EXP | RD-01 · RD-12 |
| [RD-14](./open-decision-register.md#rd-14--public-endpoint--domain--tls) | ARCH_OPS / PRODUCT_POLICY | runtime | web | NO | D | M10 | LOCAL_SPEC | OA · ER(R3) | RD-12 |
| [RD-15](./open-decision-register.md#rd-15--capacity--scaling-선택) | ARCH_OPS / CROSS_MODULE | runtime | recording (RD-15c · d) · search (RD-15a) | NO | C | M8 | EXPERIMENT_BASELINE → ADR(조건부) | EXP · EI · ER(R3) | RD-09 |
| [RD-17](./open-decision-register.md#rd-17--api--worker-recording--source-persistence-boundary) | CROSS_MODULE / ARCH_OPS | Joint: recording + runtime | case · RD-05 Owner (upload) | NO | A | M3 (직접 M5) | JOINT_ISSUE → ADR | OA · ER(R1) | — (~RD-06) |
| [RD-18](./open-decision-register.md#rd-18--search--runtime-usage--pricing-handoff) | CROSS_MODULE | Joint: search + runtime | — (Contract 보강 시 UsageRecord Consumer) | NO | A | M1 | JOINT_ISSUE → LOCAL_SPEC · CONTRACT(조건부) | OA · EI | RD-03 |
| [RD-19](./open-decision-register.md#rd-19--사용자-중단cancellation-전달-경로와-실행-중단-semantics) | CROSS_MODULE / PRODUCT_POLICY | Joint: case (RD-19a) + runtime (RD-19b · c) | web (RD-19a) · search (RD-19c) | NO | A | M1 (직접 M2) | JOINT_ISSUE → CONTRACT · ADR(조건부) | OA · ER(R1) | RD-06 |

### 3.1 RD별 분류 근거

Register 원문을 반복하지 않고 **분류를 그렇게 한 이유**만 적는다.

- **RD-01** — Tech Spec §1이 DB Queue 물리 구조 · claim을 소유하고 JobExecution Contract §11 · ERD↔Runtime ADR §10이 물리 구현을 Runtime에 위임했다 → LOCAL. schema · migration은 되돌리는 비용이 크고 ADR Non-decision `runtime-db-schema` 후속과 연결된다 → Secondary ARCH_OPS · Follow-up ADR. case가 확인해야 하는 JobRecord 관계는 RD-06b에서 닫히므로 RD-01 자체에는 Required Consult가 없다 → YES. Informed: case · eval · search.
- **RD-02** — 결정 대상은 Runtime 동작이지만 제약이 case 소유 CaseView A§10-6과 eval의 `queued_at` 지표에서 온다 → CROSS_MODULE. Decider는 JobExecution Producer인 runtime이다. 해소 경로가 CaseView 문구 개정을 요구하면 그 부분은 CaseView Producer(case)가 닫고 web이 Consumer로 확인한다(Register Follow-up).
- **RD-03** — workflow §3.1은 「retry/backoff」를 Runtime 단독 예시로 들지만 그것은 값(RD-04)이다. 이 group의 쟁점인 in-call retry는 Search adapter 코드(`search/retry.py`)라 Search Owner 없이 바꿀 수 없다 → Joint. case는 timeout · 「이어서 찾기」 정책(RD-03c)과 Contract 머리말 2026-09-13 명확화의 작성 Owner, readout은 JobExecution Contract §9-9 공동 결정 당사자다. 실효 Gate M1은 RD-03 → RD-02 · RD-18 → RD-01 경로에서 온다.
- **RD-04** — Contract §11이 값을 Runtime config로 위임한 tuning이다 → LOCAL. RD-04b 한 축이 case 소유 timeout 값과의 관계라 case 확인이 필요하다 → NO. 축과 제약이 Provisional로 적히면 구현을 막지 않는다 → B, 최종값은 P2.
- **RD-05** — HTTP 경계는 web 소비 · case 진입점 · recording upload를 동시에 건드린다. RD-05a(Owner 확정) 자체가 `api` composition root Owner와 web 사이의 합의라 한쪽이 혼자 닫을 수 없다 → Joint. 그 뒤 RD-05b~f는 RD-05a가 정한 HTTP API Contract Owner가 Producer로 닫는다. workflow §5가 Baseline 전에 닫을 예시로 명시한다 → A.
- **RD-06** — Architecture 원칙 6(orchestrator / executor)의 기전이고, RD-06b의 Case schema는 case 소유다 → Joint. RD-06g의 export capability는 recording 소유라 recording 확인이 필요하다. Informed: web(재선택 가드 표시). 실효 Gate M1은 RD-06 → RD-01a에서 온다.
- **RD-07** — RD-07a가 Search 결정 [`gemini-3.8-proxy-baseline-2026-09-18.md`](../modules/search/decisions/gemini-3.8-proxy-baseline-2026-09-18.md) 5항과 맞물려 Search Owner 없이 닫을 수 없다 → Primary CROSS_MODULE. RD-07c(secret source)는 배포 topology 선택이다 → Secondary ARCH_OPS. 주입 경계 자체는 Ops §1 · Tech Spec §15.1이 Runtime 소유로 둔다 → Decider runtime. eval은 RD-07e(로컬 평가 실행 loader) 확인 대상이다.
- **RD-08** — artifact를 Search가 rate 주입에 쓰고 Runtime이 `pricing_id`로 가리킨다 → Joint. 종결 사실을 case 문서 [`budget-krw-normalization.md`](../modules/case/decisions/budget-krw-normalization.md) 「남은 것」에 반영해야 하므로 case 확인이 필요하다. Informed: eval. `pricing_id`를 opaque하게 보존하므로(UsageRecord Contract §5) placeholder로 진행할 수 있다 → B.
- **RD-09** — RecordingService 내부 cache는 recording, Worker 안 인스턴스 범위는 Worker composition root(runtime)다 → Joint. Informed: search. 최종 범위는 P2-B/D 결과다.
- **RD-10** — 사용자 자산 보관 · 삭제는 [Product Spec](../product/product-spec.md) §5 Must 「개인정보 처리·삭제 정책 설계」와 Ops §14 「개인정보/재현성/비용/사용자 flow」 축에 걸린다 → PRODUCT_POLICY. 보관기간 · 일괄 삭제는 recording 소유(`ownership.md`)이고, RD-10c · d는 UsageRecord Contract Owner(runtime)가 recording과 함께 닫는다(Contract §10 「정철원과 확인 필요」) → Joint. case는 cross-cutting C-4 Owner다. Product Spec 문구가 바뀌면 PM 승인(B-1)이 붙는다. 구현 milestone을 막지 않지만 Gate M9는 MVP 안에 있다(pre-deploy-security-review #8).
- **RD-11** — Ops §14가 log retention을 asset retention과 다른 축으로 둔다 → LOCAL. RD-11b(temp media)와 RD-11c(RemoteCopy cleanup)의 실행 코드가 recording(`recording/materialization.py` · RemoteCopy registry)에 있다 → NO. RD-11a만 단독이다.
- **RD-12** — topology(EC2 1대 + Compose)는 Ops §2에서 닫혔고 남은 것은 pipeline 세부다 → LOCAL. 그중 artifact 전달(RD-12b)과 backup(RD-12g)은 AWS 자원과 장기 운영에 걸린다 → Secondary ARCH_OPS. ECR · S3 같은 운영진 자원 요청은 외부 확인이다 → YES.
- **RD-13** — Ops §8 · §9 범위 안의 수단 선택이다 → LOCAL · YES. alert threshold(RD-13c)는 deployment 환경이 생긴 뒤 정한다(Ops §9).
- **RD-14** — workflow §3.1은 「외부 공개 endpoint」를 제품/정책 예시에 둔다. 그런데 공개 여부는 Register에서 Trigger로 분리됐고 남은 결정은 EIP · DNS · reverse proxy · TLS · Security Group 구성이다 → Primary ARCH_OPS, 공개 여부 trigger 때문에 Secondary PRODUCT_POLICY. web은 domain · callback 소비자라 확인이 필요하다. 공개 여부 trigger 자체는 PM 판단이다(위 [역할 겹침](#22-결정권)).
- **RD-15** — Ops §13 · §16~§18 확장 기준을 실측에 적용하는 선택이다 → ARCH_OPS · C. Object Storage는 recording storage adapter, concurrency는 provider 한도(search)를 건드린다 → Secondary CROSS_MODULE. EC2 상향 · RDS · GPU는 운영진 자원 요청이 별도로 붙는다.
- **RD-17** — recording repository 경계와 process topology가 한 결정이다 → Joint. persistent storage boundary이고 Register가 ADR 후보로 둔다 → Secondary ARCH_OPS · Follow-up ADR. case는 RD-06b와 같은 persistence 판단의 당사자다. 실효 Gate M3은 RD-17 → RD-05e에서 온다.
- **RD-18** — UsageRecord Producer는 runtime이지만 호출은 `search/providers` 경계 안에서 일어난다(Contract §2 · Architecture A4) → Joint. 전달 모양이 search-internal을 넘어 Contract 보강이 필요해지면 UsageRecord Consumer 확인이 붙는다. Informed: eval · case.
- **RD-19** — 사용자 동작(즉시 중단 · 보존 결과 유지 · 현재 범위에서 부분 후보 없음)은 [`core-user-flow.md`](../product/core-user-flow.md)에서 이미 닫혔다. 남은 것은 command 표면(case-command Draft — case) · 전달 port · 실행 semantics(runtime) · 진행 중 provider 호출(search adapter)이다 → Primary CROSS_MODULE. RD-19b의 「현재 탐색 범위 밖 kind에서 `produced`를 남기는지」는 사용자가 보는 부분 결과를 바꿀 수 있다 → Secondary PRODUCT_POLICY. core-user-flow 문구 반영이 필요해지면 PM 승인이 붙는다. web은 case-command Draft의 Consumer 확인 대상이다.

---

## 4. Timing별 Queue

### 4.1 A — 구현 전 필수 (9)

| RD | 실효 Gate | 직접 막는 것 |
| --- | --- | --- |
| RD-01 | M1 | MySQL persistence · migration · claim · Final UsageRecord append |
| RD-02 | M1 | RD-01a · b |
| RD-03 | M1 | RD-02 · RD-18 · Worker handler failure mapping(M2) |
| RD-06 | M1 | RD-01a · RD-19a · RD-05c · 202 경로(M3) |
| RD-18 | M1 | RD-01e · f · g |
| RD-19 | M1 | RD-01b · e · f · Worker handler 구조(M2) |
| RD-05 | M3 | API composition root · web 실연동 · RD-12 smoke endpoint |
| RD-17 | M3 | RD-05e · Compose volume(RD-12) · 첫 비동기 Real E2E(M5) |
| RD-07 | M4 | Compose 주입 경로 · RD-12 (RD-07c는 M6) |

**§5 진행:** 2026-10-03에 9개 모두 Decision Issue로 연결했고, **2026-10-04에 9/9 CLOSED**다 — #244 ~ #250 ACCEPTED, 승격된 SoT와 Issue 링크는 Register [§5 진행 상태](./open-decision-register.md#5-진행-상태--timing-a)가 추적한다(Umbrella [#251](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/251), PR #253). 이 분류의 Type · 결정권 · Timing · Gate는 바꾸지 않았다.

### 4.2 B — Provisional 가능 (6)

| RD | Provisional 가정이 필요한 시점 | 최종 Gate | 최종을 정하는 것 |
| --- | --- | --- | --- |
| RD-08 | M1 — placeholder `pricing_id` (RD-18 접합) | M9 — Ops §21 「UsageRecord와 실제 비용 발생이 정합하는가」 | EI-06 · Joint 합의 |
| RD-04 | M2 — Worker loop 기본값 | M8 | P2 |
| RD-09 | M2 — Worker composition root의 인스턴스 범위 | M8 | P2-B · P2-D |
| RD-12 | M4 — RD-12a · g (Compose · volume) | M6 — 나머지 | 배포 smoke |
| RD-11 | M7 — P2-C cleanup 관측 기준 | M9 — RD-11c (RD-10b · EI-07) | P2-C · pre-deploy review |
| RD-13 | M7 — P2 관측 수단 | M8 — RD-13c alert threshold | P2 |

### 4.3 C — 실측 후 (1)

| RD | Gate | 선행 |
| --- | --- | --- |
| RD-15 | M8 | P2 결과 · RD-09 · EI-02. P3는 RD-15 Trigger로 연다 |

### 4.4 D — 구현 milestone을 막지 않음 (2)

| RD | Gate | 조건 |
| --- | --- | --- |
| RD-10 | M9 | 실제 사용자 데이터를 받는 배포 전. Product Spec §5 Must · pre-deploy-security-review #8 |
| RD-14 | M10 | 외부 공개 demo · OAuth 요구 발생 시. 사용자 데이터가 오가는 공개 endpoint면 HTTPS가 pre-deploy 조건(Ops §2-2) → M9 |

**§2 Timing candidate와 변경 없음.** 18개 group 모두 Register candidate를 근거와 대조해 그대로 확정했다.

### 4.5 Sub-decision Timing 예외

| Group | 예외 sub-decision | 판정 |
| --- | --- | --- |
| RD-01 (A) | RD-01j 도구 세부 | B로 내려감 — A group 안 B 허용 |
| RD-07 (A) | RD-07b(config shape) · RD-07d(key ownership) | B — 코드 내부 구조 · 문서화 범위라 reversible |
| RD-07 (A) | RD-07c(배포 secret source) | Gate만 M6로 늦음 — A group 안 허용 |
| RD-12 (B) | RD-12b(artifact 전달) | Ops §23이 「실측 후 결정」으로 적음 — B group 안의 C 성격. A가 아니라 Register 경계 원칙과 충돌하지 않음 |
| RD-13 (B) | RD-13c(alert threshold) | C 성격 — Register 「B (일부 C)」와 같음 |
| RD-04 · RD-09 (B) | 최종값 · 최종 범위 | C(P2) — Register candidate에 이미 표기 |
| RD-11 (B) | RD-11c | 최종 Gate M9 — RD-10b(D)에 의존 |

B/C/D group 안에서 구현을 막는 A sub-decision은 새로 발견되지 않았다. **group 분할 없음.**

---

## 5. Cross-module / Joint Decision Queue

Runtime이 혼자 닫을 수 없는 15개 RD다. Decider가 Joint인 것과 단일 Decider + Required Consult인 것을 나눴다.

### 5.1 Joint Decision (9)

| RD | Decider 구성 | Required Consult | 닫히면 반영할 곳 | 같은 자리에서 볼 RD |
| --- | --- | --- | --- | --- |
| RD-06 | case + runtime | recording | ADR(조건부) · Tech Spec §12 · §13 · case persistence 결정 | RD-17 (Register 「함께 본다」 · RD-17 Issue needed) |
| RD-17 | recording + runtime | case · RD-05 Owner | ADR · Ops §2 · §10 | RD-06 |
| RD-03 | runtime + search | case · readout | ADR · Tech Spec §6 · Search retry 결정 · case `timeout-fallback.md` 정합 | RD-18 (search + runtime, RD-03a → RD-18d) |
| RD-18 | search + runtime | — (Contract 보강 시 UsageRecord Consumer) | Tech Spec §11 · UsageRecord Contract(조건부) | RD-03 · RD-08 |
| RD-19 | case + runtime | web · search | case-command Draft · Tech Spec · ADR(조건부) | RD-06 (선행) |
| RD-05 | api ↔ web → Contract Owner | case · recording | HTTP API Contract 신규 Draft → Final | RD-06 · RD-17 (선행) |
| RD-08 | runtime + search | case | Tech Spec §11.3 · `budget-krw-normalization.md` 「남은 것」 | RD-18 |
| RD-09 | recording + runtime | — | Ops §11 · recording 문서 → P2 뒤 baseline | RD-17 (선행) |
| RD-10 | recording + runtime | case | AnalysisSource/Derived Contract §5 · §11 · UsageRecord Contract §10 · ADR(조건부) | RD-11 (후행) |

RD-03 · RD-08 · RD-18은 모두 search + runtime 조합이고 Issue #153(OPEN)이 같은 경계를 다룬다. 기존 Issue에 붙일지 새 카드로 낼지는 workflow §5에서 정한다.

### 5.2 단일 Decider + Required Consult (6)

| RD | Decider | Required Consult | 확인 범위 |
| --- | --- | --- | --- |
| RD-02 | runtime | case · eval (web 조건부) | CaseView A§10-6 정합 · `queued_at` 지표 의미 |
| RD-04 | runtime | case | RD-04b — lease · STALE threshold와 case job wall의 관계 |
| RD-07 | runtime | search · eval | Search 결정 5항 범위 · 로컬 평가 loader |
| RD-11 | runtime | recording | temp media 회수 · RemoteCopy cleanup 실행 주체 |
| RD-14 | runtime | web | domain · callback. 공개 여부 trigger는 PM |
| RD-15 | runtime | recording · search | Object Storage · disk(storage adapter) · provider 동시성 |

### 5.3 Runtime 단독 (3)

RD-01 · RD-12 · RD-13. 단 RD-01은 상류 Joint Decision(RD-03 · RD-06 · RD-18 · RD-19)과 RD-02가 닫힌 뒤에야 확정할 수 있다.

---

## 6. §4 External Research Queue

**조사 질문만 적는다. 답은 §4에서 조사한다.** 외부 사례의 숫자를 baseline으로 복사하지 않는다(workflow §4).

| Priority | RD | 조사 질문 | 왜 필요한가 | 조사하지 않으면 무엇을 가정해야 하나 |
| --- | --- | --- | --- | --- |
| R1 | RD-01 (01b) | MySQL 8.4 InnoDB `SELECT … FOR UPDATE SKIP LOCKED`의 lock 범위(record · gap · next-key)와 isolation level 영향, ORDER BY / LIMIT · index 조합, claim과 `JobExecution(RUNNING)` INSERT를 한 transaction에 둘 때의 failure mode | Tech Spec §4.3 claim 요구사항 5개를 만족하는 transaction 경계를 고르려면 lock semantics가 필요하다. Tech Spec §4는 우선 후보로만 둔다 | claim 정합성을 integration test #1(동시 claim 중복 없음)만으로 판단해야 하고, test가 재현하지 못한 동시성 결함은 P2 전까지 드러나지 않는다 |
| R1 | RD-01 (01c · 01d · 01g) | MySQL 8.4에서 JSON column과 관계 테이블의 조회 · 제약 검증 · migration tradeoff — `produced` · `usage_refs` · `Money` · `pricing_context` 같은 구조 값 기준 | ERD↔Runtime ADR D5 · D6과 ERD §5.2가 물리 선택을 Runtime에 넘겼다 | Contract 소비 패턴만 보고 고르고, 조회 · 검증 비용은 구현 뒤에야 확인한다 |
| R1 | RD-17 (17a · 17b) | Docker Compose에서 두 container가 같은 파일을 공유할 때의 권한(uid / gid) · 정리 · 동시 접근 failure mode, process 재시작 뒤 file-backed metadata를 복원하는 일반 패턴 | RD-17이 첫 비동기 Real E2E를 막고 Register가 조사 질문으로 남겼다 | 공유 경계의 failure mode를 pre-implementation spike 한 번으로만 확인한다 |
| R1 | RD-05 (05e) · RD-17 (17a) | FastAPI / Starlette가 대용량 영상 upload를 받을 때 request body가 메모리 · 임시 파일 중 어디에 쌓이는지, 크기 한도를 거는 위치(app · reverse proxy), 단일 t3.medium에서의 메모리 · disk 영향 | upload 완료와 source 등록의 관계(RD-05e)와 파일 공유 경계(RD-17a)가 upload 수신 방식에 걸린다. Ops §11은 working set이 RSS에 먼저 쌓이는 상황을 이미 관찰했다(검수 A-07). repository에 upload 수신 근거가 없다 | upload 데이터가 어디에 쌓이는지 모른 채 endpoint 계약과 공유 경계를 정한다 |
| R1 | RD-07 (07a) | Docker Compose `environment` · `env_file` · project `.env` interpolation의 우선순위와 container 안 process에 실제 전달되는 범위, `.env` 파일 mount 방식과의 차이 | `common/env.py`가 process environment를 쓰지 않는 현행 규칙과 Compose 주입 경로의 관계를 정리하려면 Compose 쪽 semantics가 필요하다 | Compose 주입 semantics를 구현 중 시행착오로 확인한다 |
| R1 | RD-19 (19b · 19c) | Python Worker에서 진행 중인 외부 HTTP 호출과 ffmpeg subprocess를 중단하는 수단(취소 신호 확인 지점 · timeout · subprocess 종료)과 각 수단의 failure mode | RD-19가 A인 이유는 RUNNING 중단 방식이 Worker handler 구조를 바꾸기 때문이다. 중단할 수 있는 범위에 대한 repository 근거가 없다 | 중단 가능 범위를 모른 채 Owner 합의를 하고, 합의한 semantics가 구현 불가로 드러나면 다시 합의한다 |
| R2 | RD-01 (01j) | Python 3.12 + MySQL 8.4에서 DB 접근 계층(driver · ORM 사용 여부)과 migration tool 선택지의 운영 차이 — 동기 / 비동기 driver, migration 버전 관리, Compose 배포 시 migration 실행 방식 | `pyproject.toml`에 DB 계층이 없다. RD-12f migration 절차와 이어진다 | 구현자가 도구를 임의로 고른다 |
| R2 | RD-07 (07c) | 단일 EC2에서 SSM Parameter Store 값을 Compose container에 전달하는 패턴(배포 시 fetch → env / file · 권한 범위)과 host 파일 방식의 운영 차이 | Ops §4-1 · Runbook §8이 secret source를 미결로 둔다. [`aws-environment.md`](./official-inputs/aws-environment.md)에 Parameter Store 사용 사례가 있다 | secret source를 배포 workflow 구현 중에 처음 정한다 |
| R2 | RD-12 | 단일 EC2 + Compose에서 ECR pull과 host build의 운영 차이(revision 식별 · rollback · build 자원), SSM Run Command 배포 명령 패턴, MySQL container volume backup / restore 방식, Compose 배포에서 DB migration 실행 순서 | Runbook §8 미결 10개를 닫는 데 필요한 운영 사례다 | Runbook 미결을 구현 PR에서 처음 정한다 |
| R2 | RD-13 (13a) · RD-11 (11a) | EC2 단일 서버에서 CloudWatch Agent와 Docker `awslogs` logging driver의 운영 차이, Docker log rotation · 보관을 설정하는 위치 | Ops §8은 방향만 있고 CloudWatch Agent · Log Group이 아직 없다([`aws-environment.md`](./official-inputs/aws-environment.md)). log rotation은 RD-11a와 같은 설정면이다 | log transport와 rotation을 P2 직전에 정한다 |
| R3 | RD-14 | 단일 EC2 + Compose에서 reverse proxy(Caddy가 첫 후보)의 자동 TLS · 무료 서브도메인 · OAuth callback 구성 요구사항(EIP · 80 / 443 · DNS) | Ops §2-2 순서의 실행 근거. trigger(M10) 전에는 조사하지 않는다(Register 「그때」) | trigger 발생 뒤 조사한다 — 지금 가정할 것 없음 |
| R3 | RD-15 | CPU-bound(ffmpeg · OCR)와 I/O-bound(provider 대기) workload에서 Worker 수를 늘릴 때의 scaling 특성, MySQL DB Queue claim contention | Ops §16 · §17 trigger를 P2 결과에 적용하는 해석 근거 | P2 측정값만으로 해석하고 failure mode 후보는 사례 없이 정한다 |

### 6.1 검토했지만 Queue에 넣지 않은 질문

| 질문 | RD | 넣지 않은 이유 |
| --- | --- | --- |
| provider retry layering 관행 | RD-03 | 쟁점이 Search adapter와 Runtime의 책임 분담 합의와 Contract 머리말 해석이다. Search retry 코드 · case timeout 예산 · Tech Spec §6으로 대안을 쓸 수 있다 |
| HTTP 202 · async job polling 관행 | RD-05 (05b~d) | case-command Draft §3 · Tech Spec §9 · §13이 응답 범위를 이미 좁혔다. Owner 합의가 핵심이다 |
| transactional outbox · dual-write | RD-06 (06a) | 필요 여부가 RD-06b(case persistence 위치)에 먼저 걸린다. RD-06b가 Runtime과 같은 MySQL transaction에 들어가지 않는 쪽으로 닫힐 때만 추가한다 |
| KRW 환산 FX source 후보 | RD-08 (08b) | EI-06(크레딧 정산 기준) 결과에 따라 필요 여부가 갈린다. EI-06 확인 뒤 판단한다 |
| 개인정보 법령 · 공식 가이드상 보관 · 파기 제약 | RD-10 | 우리가 고르는 기술 사례가 아니라 RD-10의 선택 범위를 좁히는 외부 사실이다 → External Input **EI-08**(workflow §1). §4에서는 EI-08 확인 결과의 해석이 필요할 때만 보조 조사한다 |

---

## 7. External Input Queue

EI 원문 · 확인 경로 · 담당은 Register [External Inputs](./open-decision-register.md#external-inputs--decision이-아니라-확인할-사실)가 SoT다. 여기서는 Decision과의 연결과 확인 시점만 적는다.

| EI | 영향을 받는 RD | 늦어도 확인할 시점 | 확인 전 처리 | 성격 |
| --- | --- | --- | --- | --- |
| EI-01 | RD-03a · RD-04b | M7 (P2 baseline config 전) | Provisional — Search 내부 per-attempt 값은 provider 보장값이 아니라고 표기하고 진행 | 재검토 trigger |
| EI-02 | RD-03a · RD-03e · RD-15a | M8 (RD-15a 결정 전) | Provisional. RD-15a는 P2-E smoke 관측이 EI 확인 경로의 일부다 | 재검토 trigger |
| EI-03 | RD-03e | M7 | Provisional — 거절 응답의 retryable 분류를 가정으로 표기 | 재검토 trigger |
| EI-04 | RD-03a · RD-18d | M9 (Ops §21 비용 정합) | Provisional — RD-18d는 노출 모양을 정하고, 과금 여부는 cost 값에만 들어간다 | 재검토 trigger |
| EI-05 | RD-03f | M9 | Provisional — 계정 수준 실패 처리를 가정으로 표기 | 재검토 trigger |
| EI-06 | RD-08a · RD-08b | M9 | placeholder `pricing_id`로 진행 | **RD-08 최종 closure의 전제** — Tech Spec §11.3이 정산 기준을 artifact · FX source와 같은 미결 목록에 둔다 |
| EI-07 | RD-10b · RD-11c | M9 | Provisional — 현재 Elice 경로는 RemoteCopy를 쓰지 않는다 | **RD-10b · RD-11c 최종 closure의 전제** — pre-deploy-security-review #19가 provider 보관 · logging 확인을 요구한다 |
| EI-08 | RD-10a · RD-10b | M9 | RD-10은 D라 확인 전 Provisional 가정이 필요 없다 | **RD-10a · RD-10b 최종 closure의 전제** — Ops §14가 retention 값을 「개인정보」 축으로 정하라고 하고 그 근거가 repository에 없다 |

- **A Decision을 반드시 막는 EI는 없다.** A group 중 EI 입력이 있는 RD-03 · RD-18은 Register가 「확인 전에는 Provisional 가정을 명시하고 진행할 수 있다」고 적었다. EI-06 · EI-07 · EI-08은 B · D Decision의 최종 closure 전제이지 구현 선행 조건이 아니다.
- **확인 시점 주의.** EI-01~EI-07은 Search가 선택한 운영 모델 기준이다(Register EI 전제). 운영 모델 · 전송 방식 재선정 Issue #240이 OPEN이므로, 그 결정 전에 확인한 값은 모델이 바뀌면 다시 확인한다. 모델 선택은 Search 소유이고 Runtime Open Decision이 아니다.

---

## 8. Experiment-dependent Queue

| RD | 실험 | 실험 전 처리 | 실험 후 closure |
| --- | --- | --- | --- |
| RD-15 | P2 → P3(RD-15 Trigger) | 결정하지 않는다 (C) | EXPERIMENT_BASELINE · 도입 시 ADR |
| RD-04 | P2 | 축 · 제약과 Provisional Baseline v0.1(workflow §6) | 최종값 EXPERIMENT_BASELINE |
| RD-09 | P2-B · P2-D | Provisional 인스턴스 범위 · reuse 범위 | 범위 조정. Object Storage 도입 판단은 RD-15d로 넘긴다(RD-09 Trigger) |
| RD-11 | P2-C | Provisional cleanup | cleanup 동작 확인 · LOCAL_SPEC |
| RD-13 | P2 — 관측 수단 자체를 검증 | Provisional 수단 | RD-13c alert threshold |

**Experiment 뒤에 Decision 자체를 닫는 RD:** RD-15만이다. RD-04 · RD-09 · RD-11 · RD-13은 Provisional로 먼저 닫고 최종값 · 범위만 실험 뒤에 조정한다.

Experiment가 아닌 검증:

| 종류 | RD | 내용 |
| --- | --- | --- |
| Pre-implementation spike (workflow §4) | RD-01 (01b) | 동시 claim 중복 없음 |
| Pre-implementation spike | RD-17 | api · worker 두 process에서 같은 source를 등록 · 조회하는 최소 경로 |
| Pre-implementation spike | RD-12 | OIDC 인증 전용 workflow(`sts get-caller-identity`) — Ops §2-1 순서상 첫 단계 |
| 배포 검증 | RD-12 | 배포 smoke (Runbook §4) |

---

## 9. Dependency / Resolution Order

**답의 순서가 아니라 논의를 시작할 수 있는 순서다.** Register [Dependency graph](./open-decision-register.md#dependency-graph)의 실선 의존만 사용했고 새 의존을 만들지 않았다.

### 9.1 A Decision

```text
Wave 1 — 선행 Decision 없음
  RD-03 retry 층위 · failure lifecycle
  RD-06 dispatch port  ~ RD-17 recording persistence   (같은 자리에서 본다)
  RD-07 config / secret                                 (Gate M4 — 다른 A와 병렬, 서둘 필요 없음)

Wave 2 — Wave 1 결과가 입력
  RD-02 attempt 생성 시점     ← RD-03
  RD-18 usage handoff         ← RD-03
  RD-19 사용자 중단           ← RD-06
  RD-05 HTTP API Contract     ← RD-06 · RD-17

Wave 3
  RD-01 persistence / queue   ← RD-02 · RD-03 · RD-06 · RD-18 · RD-19
```

M1까지의 critical path:

```text
RD-03 ─┬→ RD-02 ─┐
       └→ RD-18 ─┼→ RD-01 → M1
RD-06 ──→ RD-19 ─┘
```

RD-01은 Gate가 가장 이르면서(M1) dependency상 가장 늦다. Wave 1 · 2가 늦어지면 M1이 바로 밀린다.

### 9.2 B / C / D Decision (참고)

| RD | 선행 | 비고 |
| --- | --- | --- |
| RD-08 | — | 다른 Decision과 독립. EI-06 |
| RD-09 | RD-17 | |
| RD-10 | RD-17 | |
| RD-04 | RD-03 · RD-01 | Wave 3 뒤 |
| RD-12 | RD-07 · RD-01 · RD-05 · RD-17 | |
| RD-13 | RD-12 · RD-01 | |
| RD-11 | RD-13 · RD-10 | |
| RD-14 | RD-12 · Architecture A2(인증) | trigger 대기 |
| RD-15 | RD-09 · P2 결과 | |

---

## 10. §3 결과 요약

| 항목 | 값 |
| --- | --- |
| 분류한 Open Decision Group | **18** — RD-01~RD-15 · RD-17~RD-19 |
| Primary Type | LOCAL 5 · CROSS_MODULE 10 · PRODUCT_POLICY 1 · ARCH_OPS 2 |
| Secondary tag | ARCH_OPS 4 (RD-01 · RD-07 · RD-12 · RD-17) · PRODUCT_POLICY 2 (RD-14 · RD-19) · CROSS_MODULE 2 (RD-10 · RD-15) |
| Timing | A 9 · B 6 · C 1 · D 2 — §2 candidate와 변경 없음 |
| Runtime alone | YES 3 (RD-01 · RD-12 · RD-13) · NO 15 |
| Joint Decider | 9 (RD-03 · RD-05 · RD-06 · RD-08 · RD-09 · RD-10 · RD-17 · RD-18 · RD-19) |
| Primary Closure Route | LOCAL_SPEC 6 · JOINT_ISSUE 11 · EXPERIMENT_BASELINE 1 · CONTRACT · OWNER_DECISION · ADR은 Primary 0 (Follow-up으로만) |
| §4 External Research | 10 RD — R1 6행 · R2 4행 · R3 2행 |
| External Input 연결 | EI-01~EI-08 전부. A를 막는 EI 없음 |
| Experiment 뒤 closure | RD-15 (최종값 조정: RD-04 · RD-09 · RD-11 · RD-13) |
| group 분할 · 새 RD | 없음 |

---

## Register 정합

분류 중 Register 본문의 Dependencies와 dependency graph를 대조해 단순 누락 2건을 Register에 바로 고쳤다. Timing · Owner · group 경계는 바꾸지 않았다.

- RD-01 → RD-13 edge가 graph에 없었다. 양쪽 본문(RD-01 「막는 것」 · RD-13 「선행」)에는 있었다.
- RD-12 「막는 것」에 RD-14가 없었다. RD-14 「선행」과 graph에는 있었다.

외부 사실 1건을 External Input으로 추가했다.

- **EI-08** — 개인정보 법령 · 공식 가이드상 영상 · 식별정보 보관 · 파기 제약 → RD-10a · RD-10b. 처음에는 §4 조사(R3)로 분류했으나, 법령상 제약은 일반 기술 사례가 아니라 결정 범위를 좁히는 외부 사실이라 workflow §1 경로로 옮겼다.

## Change log

| 날짜 | 변경 | 기준 |
| --- | --- | --- |
| 2026-10-03 | 최초 작성 — 18 group 분류. Timing 변경 없음 · group 분할 없음 · 답 선택 없음 | `origin/develop` `10787d8` |
| 2026-10-03 | 검토 반영 — §2.1 예외 목록에 RD-19 추가, RD-10 개인정보 법령 조사를 R3에서 EI-08로 이동, `Joint` 뜻(각 Owner가 자기 surface 승인) 명시 | `origin/develop` `10787d8` |
| 2026-10-03 | §4.1에 workflow §5 진행 포인터 추가(Register §5 진행 상태 · #251). 분류 변경 없음 | `origin/develop` `43dd8ec` |
| 2026-10-04 | §4.1 포인터를 Timing A 9/9 CLOSED로 갱신. 분류 변경 없음 | PR #253 |
| 2026-10-06 | §2.4에 M1~M5 ↔ Implementation Plan Task 대응 pointer 추가. 분류 변경 없음 | PR #304 |
