# Runtime Tech Spec

**Status:** Working — implementation spec  
**Owner:** common/runtime — 김준영 · 구현 담당 정철원  
**Scope:** 대신고 modular monolith의 실행 인프라  
**Architecture SoT:** [`docs/architecture/module-architecture.md`](../architecture/module-architecture.md)  
**Logical Data Model:** [`docs/architecture/erd-draft.md`](../architecture/erd-draft.md)  
**Alignment ADR:** [ERD ↔ Runtime 정합화](../architecture/contracts/adr/adr-erd-runtime-alignment-2026-09-19.md)

> 이 문서는 Final Data Contract를 재정의하지 않는다. `JobRecord`, `JobExecution`, `UsageRecord`, `CaseView`의 필드·enum·불변조건은 각 Contract가 authoritative하다. Logical ERD는 cross-domain 관계·cardinality·저장 후보의 입력이다. 이 문서는 그 상위 논리 의미를 유지하면서 **DB Queue·Worker·실행 lifecycle의 물리 구현**을 정한다.

## 1. 문서 경계

### 이 문서가 소유한다

- DB Queue의 물리 구조와 claim 방식
- `JobExecution` persistence
- retry scheduling
- lease / heartbeat / STALE recovery
- Worker polling / dispatch
- `UsageRecord` persistence 접합
- Runtime configuration
- API/Worker composition root의 실행 경계
- Runtime health endpoint의 기술 의미
- Runtime integration test acceptance criteria

### 이 문서가 소유하지 않는다

- 작업이 필요한 이유와 부분 재실행 정책 — `case`
- cache/reuse 정책 결정 — `case`
- Search/Readout/Recording 내부 알고리즘
- Final Contract schema
- Logical ERD에 이미 확정된 cross-domain 의미·cardinality
- 배포·모니터링·disk/retention 운영 정책 — [`ops-spec.md`](./ops-spec.md)
- Recording/Search benchmark 원본

### 설계 입력 우선순위

Runtime 관련 저장/실행 설계가 충돌할 때는 다음 순서로 판정한다.

```text
Product / Module Architecture
→ Final Data Contract / Accepted Owner Decision · ADR
→ Logical ERD
→ Runtime Tech Spec
→ code / migration
```

Final Contract에서 이미 닫힌 의미를 ERD나 Runtime이 다시 결정하지 않는다. 반대로 `produced`의 JSON/관계 테이블 선택처럼 상위 문서가 물리 저장을 열어둔 경우에는 Runtime 구현에서 결정할 수 있다. 양쪽 모두 미결이면 임의 확정하지 않는다.

## 2. 상위 경계

```text
HTTP request
→ API composition root
→ case가 JobRecord(Intent) 발주
→ common/runtime 실행 경계
→ 202 Accepted + 조회 가능한 식별자

이후

Worker composition root
→ Runtime queue claim
→ JobExecution 생성/전이
→ 대상 domain public capability 호출
→ produced refs / UsageRecord 연결
→ case가 현재 context에 유효한 결과인지 판단해 반영 (§12.2)
```

`common/runtime`은 여덟 번째 도메인 모듈이 아니다. `case`가 **왜 실행하는지**를 소유하고 Runtime은 **어떻게 실행됐는지**만 소유한다.

API와 Worker는 별도 프로세스일 수 있지만 같은 repository와 Final Contract를 사용하는 modular monolith의 composition root다.

## 3. Contract 접합

### 3.1 JobRecord = Intent

Authoritative source: [`contract-job-record-case-view.md`](../architecture/contracts/contract-job-record-case-view.md)

Runtime은 JobRecord를 Queue row와 동일시하지 않는다.

Runtime이 필요로 하는 Intent 정보는 예를 들면 다음과 같다.

```text
job_id
case_id / case_rev
kind
scope_ref
input_fingerprint
force_rerun
requested_at
```

`status`, `attempt`, lease, heartbeat, retry timing, produced result, failure, cost를 JobRecord에 다시 추가하지 않는다.

### 3.2 JobExecution = 실행 1회분

Authoritative source: [`contract-job-execution.md`](../architecture/contracts/contract-job-execution.md)

닫힌 status는 다음 여섯 값이다.

```text
QUEUED
RUNNING
SUCCEEDED
FAILED
STALE
CANCELLED
```

같은 `job_id`의 자동 인프라 retry는 **새 `execution_id`와 증가한 `attempt`**를 만든다.

사용자가 “이어서 찾기”, 재검색, 재판독을 요청하는 것은 retry가 아니라 새 Intent이므로 **새 JobRecord / 새 job_id**다.

### 3.3 UsageRecord = 호출 단위 원장

Authoritative source: [`contract-usage-record.md`](../architecture/contracts/contract-usage-record.md)

실제 capability/provider invocation이 시작된 호출만 UsageRecord를 남긴다. queue에서 기다리다 dispatch 전에 취소·실패한 execution에는 UsageRecord를 만들지 않는다.

금액의 authoritative source는 UsageRecord이며 JobRecord/JobExecution에 비용 필드를 복제하지 않는다.

## 4. DB Queue

### 4.1 Baseline

Architecture baseline은 **MySQL 8.4 LTS / InnoDB 기반 DB Queue**다.

Redis, Celery, RabbitMQ, SQS는 baseline에 넣지 않는다.

### 4.2 Logical ERD와 Queue row의 분리

Logical ERD는 `JobRecord 1 → N JobExecution`, `JobExecution → UsageRecord.execution_ref` 같은 **논리 관계**를 제공한다. 하지만 queue scheduling 자체의 `available_at`, claim owner, lease 같은 Runtime metadata까지 독립 domain record로 확정하지 않는다.

물리 모델은 확정이다(RD-01a, [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-04).

```text
case-owned JobRecord            (case table — case 소유 schema)
    │  job_id (FK 없음)
    └── job_execution row(s)    (Runtime table — 실행 원장 = queue)
            │  execution_id
            └── usage in-flight → usage_record (append-only)
```

- **별도 queue table을 두지 않는다.** `job_execution` table 하나가 실행 원장과 queue를 함께 맡는다. queue 항목은 `status=QUEUED`인 row다.
- row는 JobExecution Contract 필드에 Runtime 내부 column을 더한다 — `available_at` · lease owner / expiry · heartbeat · 중단 요청 · case 반영 완료 표식 · `trace_id` 등. 내부 column은 **Final JobExecution Contract 필드로 승격하지 않고** Contract projection에 내보내지 않는다.
- case table과 Runtime table 사이에 FK를 두지 않는다. 연결은 `job_id` 유일성으로 지키고, 각 모듈은 자기 schema · migration만 소유한다(§12.1).
- column 이름은 첫 migration에서 고정한다.

### 4.3 Claim 요구사항

claim은 다음을 만족해야 한다.

1. 동시에 둘 이상의 Worker가 같은 queue item을 정상 claim하지 않는다.
2. claim과 `JobExecution(RUNNING)` 시작 사이의 불일치를 transaction 경계에서 최소화한다.
3. 다음 실행 가능 시각 이전의 item을 잡지 않는다.
4. lease가 유효한 다른 Worker의 실행을 빼앗지 않는다.
5. 여러 Worker로 확장되더라도 claim 알고리즘 자체를 바꾸지 않고 concurrency만 늘릴 수 있어야 한다.

MySQL에서는 `SELECT ... FOR UPDATE SKIP LOCKED`를 사용한다. 다음 규칙은 확정이다(RD-01b 핵심 규칙, [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-03).

- Runtime DB session isolation은 **`READ COMMITTED`**다. 기본값 `REPEATABLE READ`에서는 `SKIP LOCKED` claim이 첫 실행 가능 index entry 앞의 gap을 잠가, claim transaction이 끝날 때까지 다른 row의 `FAILED` · `CANCELLED` 전이와 이른 `available_at` enqueue를 막는 것이 관찰됐다([spike S1](./experiments/pre-implementation-spike-2026-10-03.md#s1--claim-lock-footprint-rd-01b)).
- claim transaction은 `ORDER BY`를 그대로 만족하는 covering index 위의 `LIMIT 1 FOR UPDATE SKIP LOCKED` + 조건부 UPDATE로 끝내고 **INSERT를 넣지 않는다.** commit한 뒤에 실제 작업을 시작하며, provider 호출 · ffmpeg 같은 작업 동안 DB transaction을 열어 두지 않는다.
- 모든 terminal 전이는 현재 status를 조건으로 한 UPDATE다. 같은 execution에 두 전이가 겹치면 먼저 commit한 쪽이 남고 다른 쪽은 0 rows다([spike S2](./experiments/pre-implementation-spike-2026-10-03.md#s2--conditional-update-경합-rd-19b--rd-02a)).
- claim 순서는 다음 실행 가능 시각 → 고유 tiebreaker의 best-effort다. `SKIP LOCKED`는 잠긴 앞 row를 건너뛰므로 strict FIFO를 보장하지 않는다.

물리 모양도 확정이다(RD-01b 모양, [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-04). claim은 `job_execution`의 `(status, available_at, execution_id)` index를 타는 `LIMIT 1 FOR UPDATE SKIP LOCKED`로 `QUEUED` row 하나를 잡고, 같은 transaction에서 그 row를 조건부 UPDATE로 `RUNNING`(lease 포함)으로 바꾼 뒤 commit한다. 다음 attempt는 claim이 아니라 이전 attempt의 terminal 기록과 같은 transaction에서 만든다(§6.3). 최종 query는 integration test로 검증한다.

### 4.4 DB 접근 계층 · Migration

확정(RD-01j, [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-03):

- driver는 **PyMySQL**(sync, pure Python), 접근 계층은 **SQLAlchemy Core 2.x**(connection pool · transaction)이고 ORM은 쓰지 않는다. API와 Worker는 같은 **sync DB access stack**을 쓴다. claim처럼 lock · transaction 경계가 정합성의 일부인 query는 명시적 textual SQL로 둘 수 있다.
- idle connection 끊김은 pool pre-ping · recycle로 다룬다(값은 [Provisional Baseline v0.1](./provisional-baseline-v0.1.md) B-D5 · B-D6, pool · timeout · transaction 재시도는 같은 문서 §2.5).
- 이 결정은 DB access stack만 정한다. **FastAPI route를 `def`로 둘지 `async def`로 둘지는 정하지 않는다** — HTTP/API 구현에서 I/O 경계(예: upload의 `UploadFile` 수신)를 보고 정한다. `async def` route가 sync DB service를 부르면 event loop를 막지 않도록 threadpool 등의 adapter 경계를 구현 단계에서 둔다.
- migration 도구는 **Alembic**이다. 운영 계약은 forward-only이며 schema 변경은 expand → contract 순서로 나눈다. downgrade script를 운영 rollback 경로로 쓰지 않는다 — MySQL DDL은 statement 단위로만 atomic하다.
- migration은 api · worker 시작 전 **단일 실행 단계**로만 돌린다. application startup에서 migration을 실행하지 않는다. 실행 명령과 위치는 Ops/Runbook(RD-12f)이 정한다.

근거: [Research 01](./research/01-mysql-runtime-persistence-2026-10-03.md) §4.8 ~ §4.13 · Review notes.

### 4.5 결과 · 원장 물리 표현

확정(RD-01c · 01d, RD-01g는 물리 표현까지 — [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-03). 필드 의미는 각 Contract가 authoritative하다.

- **`JobExecution.produced`** — execution row의 JSON column에 `ContractRef[]` 그대로 저장한다. 별도 child table을 두지 않는다. produced ref로 execution을 찾는 요구가 생기면 다시 연다.
- **`JobExecution.usage_refs`** — 저장하지 않는다. `UsageRecord.execution_ref`(index)로 projection한다. 두 방향을 독립 원장으로 두지 않는다(ERD↔Runtime ADR D6).
- **UsageRecord** — Contract 필드를 typed column으로 둔다. `token_usage` 세 값은 nullable 정수이고 「전부 null 또는 전부 존재」 · 「total = input + output」을 DB 제약으로 건다(Contract §8-3 · §8-4). `pricing_context`는 `pricing_id` · `unit` column. `cost`는 nullable `DECIMAL` 계열 exact numeric amount + 별도 typed currency column이다. 애플리케이션은 금액을 `Decimal` ↔ 문자열 경계로만 다루고 float를 쓰지 않으며, 저장 scale보다 자릿수가 많은 값은 DB에 넣을 때 조용히 반올림하지 않고 거부한다. Contract에 없는 opaque 확장 column은 두지 않는다.
  - **아직 고정하지 않은 것:** `DECIMAL` precision · scale 값. 새 Open Decision이 아니라 RD-01g 안의 구현 세부로, **첫 migration에서** cost 생산자 출력 범위([#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244) U-2)와 Contract 예시를 기준으로 고정한다.

UsageRecord의 append 시점 · in-flight 추적 · 중복 방지(RD-01e · 01f)는 §11.1이 정한다.

## 5. Idempotency / Cache Reuse 접합

cache/reuse 여부의 Owner는 `case`다.

현재 Final Contract 기준 재사용의 핵심 조건은 다음 의미다.

```text
same case_id
+ same kind
+ same input_fingerprint
+ force_rerun = false
+ reusable prior SUCCEEDED result
→ case may reuse
```

Runtime은:

- fingerprint를 임의로 다시 계산하지 않는다.
- domain module의 model/prompt/version 내부를 해석하지 않는다.
- FAILED/STALE execution을 성공 cache처럼 취급하지 않는다.
- `force_rerun=true`의 의미를 무시하지 않는다.

`input_fingerprint`의 canonical serialization/hash algorithm은 case 접합 구현이 고정한다. Runtime Contract로 SHA-256 같은 algorithm을 선결하지 않는다.

## 6. Retry

### 6.1 사용자 재실행과 자동 retry

```text
사용자 Intent
→ new JobRecord
→ new job_id

자동 인프라 retry
→ same job_id
→ new execution_id
→ attempt + 1
```

기존 execution row를 되살리거나 attempt를 in-place 수정하지 않는다.

### 6.2 Retry 책임 층위

확정(RD-03, [#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244), 2026-10-04). 실패마다 재시도하는 층이 하나다 — 두 층이 곱해지지 않는다.

| 실패 | 맡는 층 | Runtime 처리 |
| --- | --- | --- |
| provider 일시 장애(429 · 5xx 등) | Search adapter의 **in-call retry**(run deadline 안, 값은 Search 소유) | in-call retry로 못 넘기면 `FAILED` terminal |
| Search run deadline 초과 | — (재시도 없음) | `FAILED` terminal. case의 대기 timeout과는 별개다 |
| 계정 수준 provider 실패(401 · 403 · Key 삭제 등) | — (재시도 없음). Search taxonomy가 일반 INFRA와 구분되는 `failure_kind`로 남긴다 | `FAILED` terminal. 전역 정지 · Circuit Breaker는 baseline이 아니다(Ops §15) — 운영자 수동 대응 |
| Worker 소멸 | **Runtime 자동 execution retry** | `STALE` → 같은 `job_id` · 새 `execution_id` · `attempt+1`(§6.3) |

- Runtime 자동 retry 대상은 **`STALE`만**이다. `FAILED`는 terminal이고, 다음 시도는 case가 사용자 action으로 **새 `job_id`**를 발주한다(§6.1).
- MVP Runtime에는 retryable failure mapping 표와 Runtime override를 두지 않는다. Runtime 정책은 「`status=STALE` ∧ attempt 상한 미만 ∧ 중단 요청 없음 → 다음 attempt」 하나다.
- `failure_kind`는 각 모듈 taxonomy가 채우고 Runtime은 해석하지 않는다. handler 밖에서 난 예외는 `RUNTIME_` 접두어 `failure_kind`로 `FAILED`다.
- readout 경로에는 in-call retry가 없다. readout은 `STALE` 자동 재시도 때만 새 execution = 새 `ReadoutRun`을 만든다(JobExecution Contract §9-9).

in-call retry로 못 넘긴 일시 장애가 P2 · Real E2E에서 반복되면 retryable 목록 추가를 다시 연다([#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244) Reopen Trigger).

### 6.3 Scheduling

Worker가 backoff 동안 `sleep()`으로 실행 슬롯을 붙잡지 않는다.

확정(RD-02, [#248](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/248), 2026-10-04):

```text
retry 필요 (§6.2 — STALE)
→ 한 transaction 안에서
   ├─ 이전 attempt terminal 기록 (RUNNING→STALE)
   └─ 다음 attempt INSERT (QUEUED, attempt+1, available_at = 지금 + backoff)
→ commit
→ available_at 전에는 claim되지 않음
```

- retry 상한에 닿았거나 중단 요청이 있으면 다음 attempt를 만들지 않는다.
- 다음 attempt가 terminal 기록과 같은 commit에 생기므로 CaseView 대표 execution(attempt 최댓값, CaseView Contract A§10-6)은 backoff 동안 `QUEUED`(→ `PENDING`)이고 `FAILED`로 깜빡이지 않는다.
- `queued_at`은 그 execution row가 queue에 들어간 시각 = 생성 시각이다. 따라서 attempt ≥ 2의 `queued_at → started_at`은 계획된 backoff와 실제 queue 대기를 함께 포함한다(JobExecution Contract §5). `available_at`은 Runtime 내부 scheduling metadata이고 Contract 필드가 아니다.

### 6.4 Runtime 값

다음 값은 Final Contract가 의도적으로 정하지 않았다(JobExecution Contract §11). 시작값은 [Provisional Baseline v0.1](./provisional-baseline-v0.1.md) §2.4(B-R1 retry 상한 · B-R2 backoff · `available_at` · B-R3 jitter)가 정하고, 최종값은 P2 뒤다. 이 문서에 숫자를 복제하지 않는다.

기존 working 문서에 있던 “최대 3회”, “2s→4s→8s” 같은 값은 확정값으로 사용하지 않는다.

## 7. Lease / Heartbeat / STALE Recovery

### 7.1 상태 의미

`JobExecution.STALE`은 **실행 중 Worker가 더 이상 살아 있지 않다고 Runtime이 판정한 terminal execution 상태**다.

case가 반영하지 않는 늦은 결과와 STALE을 혼동하지 않는다.

```text
SUCCEEDED인데 case가 현재 context에 유효하지 않다고 판단 (중단된 job_id · 현재 선택과 맞지 않음 등, §12.2)
→ execution은 SUCCEEDED 유지
→ case가 produced 적용을 거부
```

### 7.2 Lease · Heartbeat · Recovery

lease 구조는 확정이다(RD-01h, [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-04).

- lease는 RUNNING `job_execution` row의 Runtime 내부 column(lease owner · expiry · heartbeat · 중단 요청)에 둔다.
- handler와 **별개인 heartbeat thread**가 `status=RUNNING` ∧ `lease_owner=자기` 조건부 UPDATE로 lease를 갱신하고, 같은 갱신에서 중단 요청을 읽어 handler에 알린다(§12.5). sync provider 호출 · ffmpeg 중에도 lease가 유지된다.
- 조건부 갱신이 0 rows면 소유를 잃은 것이다(STALE로 처리됨). 그 Worker는 이후 결과를 commit하지 않는다 — stale recovery 뒤 이전 Worker가 늦게 돌아와 결과를 덮어쓰지 못한다.

lease 만료된 RUNNING execution을 같은 execution의 QUEUED로 되돌리지 않는다.

```text
attempt 1 RUNNING
→ heartbeat/lease 만료
→ 한 transaction: attempt 1 STALE + attempt 2 QUEUED (§6.3)
→ attempt 2 RUNNING ...
```

### 7.3 Sweep

현재 Worker 1 baseline의 recovery 주체는 별도 reaper process가 아니다.

```text
Worker startup
→ stale RUNNING sweep 1회

Worker loop
→ periodic stale sweep
```

다중 Worker로 확장할 때 sweep의 중복 실행이 안전하도록 DB transaction/idempotency를 보장해야 한다.

### 7.4 Runtime 값

lease duration · heartbeat interval · STALE threshold · periodic sweep interval의 시작값과 서로의 관계는 [Provisional Baseline v0.1](./provisional-baseline-v0.1.md) §2.3(B-L1 ~ B-L6) · §3.1이 정한다. STALE threshold는 별도 축이 아니라 lease 만료다(B-L3). heartbeat persistence 구조는 §7.2로 닫혔고, 값은 첫 실제 DB Queue/Worker integration에서 테스트 근거를 남긴 뒤 P2에서 조정한다.

값을 정할 때의 입력: Job timeout과 「진행 중 Job은 강제 취소하지 않는다」는 정책은 `case`가 소유한다([`timeout-fallback.md`](../modules/case/decisions/timeout-fallback.md), 잠정값). Runtime 문서에 그 값을 복제하지 않는다.

## 8. 실패 이력과 DLQ

MVP에서는 별도 DLQ infrastructure를 두지 않는다.

```text
JobRecord       → Intent history
JobExecution    → FAILED / STALE / CANCELLED execution history
UsageRecord     → 실제 invocation 사용량/비용 history
```

운영자가 terminal execution을 조회하고 재현할 수 있으면 현재 규모에서 충분하다.

향후 전용 message queue를 도입하고 redrive 운영 요구가 생기면 DLQ를 함께 재검토한다.

## 9. 진행 상태와 CaseView

Web은 JobExecution을 직접 소비하지 않고 CaseView projection을 본다.

현재 Contract mapping:

```text
QUEUED     → PENDING
RUNNING    → RUNNING
SUCCEEDED  → DONE
FAILED     → FAILED
STALE      → FAILED
CANCELLED  → PARTIAL
```

같은 `job_id`에 여러 attempt가 있으면 가장 큰 `attempt`가 그 job의 대표 execution 상태다. 같은 kind의 JobRecord가 여러 개라면 Final JobRecord/CaseView Contract A절 §10-7에 따라 **`requested_at`이 가장 늦은 JobRecord**가 그 kind의 대표 job이다. `case_rev`는 발주 순서 정렬 키로 쓰지 않는다. 이 선택 규칙은 Runtime이 새로 판단하는 정책이 아니라 case projection Contract를 따르는 것이다.

모든 가능한 stage를 미리 채우거나 근거 없는 percentage를 만들지 않는다.

`CaseView.running_jobs[]`는 Runtime의 물리 `RUNNING` 목록이 아니라 **case가 아직 결과를 기다리는 job**이다([#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247) H-4 — 정의는 CaseView Contract 소유). terminal commit과 case 반영(§12.2) 사이, retry backoff(§6.3) 동안에도 그 job은 빠지지 않고, 사용자 중단 · case timeout처럼 case가 기다리기를 멈춘 job은 Runtime에서 아직 RUNNING이어도 빠진다.

MVP UI의 polling은 baseline이지만 polling interval은 Runtime Contract가 아니다. baseline Web polling 정지 조건은 `running_jobs`가 빈 것이다.

## 10. 부분 실패

Runtime은 domain dependency graph를 스스로 추론하지 않는다.

원칙은:

> 이미 성공한 domain artifact를 하위 단계 실패 때문에 불필요하게 무효화하지 않는다.

예:

```text
CandidateEvent 확보
→ IncidentClip 생성
→ Plate Readout 실패

CandidateEvent 유지
유효한 IncidentClip 유지
case가 필요한 readout Job만 새로 발주
```

재실행 범위는 `case`가 결정하고 Runtime은 발주된 Job만 실행한다.

## 11. UsageRecord Persistence

### 11.1 기록 대상과 persistence 시점

Final UsageRecord Contract가 확정하는 것은 **기록 대상 조건**이다.

```text
실제 capability/provider invocation 시작
→ 해당 호출은 UsageRecord 기록 대상

dispatch 전 CANCELLED/FAILED
→ UsageRecord 없음
```

호출 시작 순간에는 token/cost/latency/실패 정보가 완성되지 않을 수 있다. 따라서 Runtime은 관측 가능한 사용량·결과·실패 정보를 Contract 규칙에 맞게 채울 수 있는 시점에 호출 1건당 append-only UsageRecord 1건을 남긴다.

전달 경계와 persistence 시점은 확정이다(RD-18 · RD-01e · 01f, [#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244) · [#250](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/250), 2026-10-04).

```text
Search provider adapter — provider HTTP 시도 1회마다
→ begin  : Runtime usage tracker가 durable in-flight 기록 생성 · usage identity 발급
           기록 실패 → HTTP를 보내지 않음
→ provider HTTP (in-call retry의 각 시도도 각각 begin/finish)
→ finish : 성공/실패 + 실제 관측한 token usage · latency · cost를 같은 usage identity에 durable 보존
           (이 시점에 Final UsageRecord를 만들지 않을 수 있다)
→ logical Run 관계 확정
→ Runtime이 Final UsageRecord를 정확히 1건 append · in-flight 정리
```

- **interface.** Search adapter는 Worker composition root가 execution context와 묶어 주입한 Runtime usage tracker(port)를 provider HTTP 시도마다 부른다. Search는 persistence를 모른다. 정확한 port 이름 · signature는 구현에서 정한다.
- **대상.** 실제 provider HTTP invocation이 시작됐다면 성공/실패와 무관하게 호출 1회당 Final row 1건이다 — in-call retry의 실패 시도와 응답 parsing · validation 실패도 포함한다. 관측되지 않은 token은 `token_usage=null`(객체 전체), 관측되지 않은 cost는 `amount=null`이다.
- **연결 context.** usage identity(`usage_id`)는 Runtime이 begin에서 발급하고 Search가 Run의 `usage_refs[]`에 담는다(파생값, UsageRecord Contract §8-12). `execution_ref` · `case_id`는 Runtime이 execution context에서 채운다. `run_ref` · `run_ref_reason`은 run identity를 소유한 Search가 준다. 실제 Run이 생성됐다면 `FAILED` Run이라도 그 Run에 연결한다.
- **복구.** HTTP 완료 뒤 Run 확정 전에 Worker가 죽어도 이미 관측된 값은 버리지 않는다. stale recovery · reconciliation은 durable한 Run 관계가 있으면 그 `run_ref`로 finalize하고, **실제 logical Run이 생성되지 않은 경우에만** `run_ref=null` + `RUN_NOT_PRODUCED`로 finalize한다. 관측되지 않은 필드만 null이다.
- **중복 방지.** usage identity 1개당 Final row 1개를 PK/UNIQUE로 강제해 정상 경로와 recovery 경로가 둘 다 append하지 못하게 한다.
- **재호출 금지.** usage persistence · finalization 실패 때문에 이미 수행한 provider HTTP를 다시 부르지 않는다. 이 실패는 provider retry(§6.2)와 분리된 Runtime/persistence failure다.
- **범위.** 별도 Redis · Kafka · usage service를 두지 않는다. MySQL Runtime persistence 안의 작은 in-flight 구조 + append-only `usage_record`다(§4.2). in-flight 구조는 UsageRecord Contract 밖의 Runtime 내부 구조이며 새 Final Data Contract가 아니다.

### 11.2 집계

- execution 단위: `execution_ref`
- logical run 단위: `run_ref`
- 사건 단위: `case_id`

Run contract의 `usage_refs[]`와 ledger가 어긋나면 `UsageRecord.run_ref`가 authoritative하다.

### 11.3 Pricing

실행 시점 cost를 이후 가격표로 덮어쓰지 않는다.

Runtime이 확정적으로 소유하는 것은 **Final `UsageRecord`에 실행 시 사용한 `pricing_id`, usage, 실행 시점 cost snapshot을 보존하는 책임**이다.

가격표 숫자 자체의 SSOT를 Runtime config가 독점하지 않는다. Issue #153에서 Search·Runtime Owner가 합의한 현재 경계(2026-09-26)는 다음과 같다.

- 현재 MVP에서는 Search가 rate를 주입받아 cost를 계산한다.
- 공용 versioned pricing catalog는 지금 만들지 않는다. Search/Eval/Runtime이 가격표를 직접 소비해야 하는 요구가 실제로 생기면 다시 검토한다.
- `pricing_id`는 지금 추가하는 방향이다. 의미는 「실행 시 cost 계산에 실제로 사용된 가격표의 opaque stable identifier」이고, Runtime은 내부 구조를 파싱하지 않고 전달받은 값을 그대로 보존한다. Search → Runtime 접합에는 `pricing_context.unit`과 cost도 함께 전달한다.
- provider invocation → Search가 usage/cost/pricing context 확정 → Runtime이 Final UsageRecord append.

통화는 별도 결정이다. budget 대상 `UsageRecord.cost`는 저장 전에 KRW로 정규화하고 `currency="KRW"`로 기록하며, provider-native 통화와 환율 provenance는 `pricing_id`가 가리키는 versioned artifact가 보존한다([`budget-krw-normalization.md`](../modules/case/decisions/budget-krw-normalization.md), 2026-09-09, #19).

정규화가 일어나는 층은 확정이다(RD-18b, [#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244) U-2, 2026-10-04). **cost 계산과 KRW 정규화는 Search**가 한다. Runtime은 `cost.currency == "KRW"`를 검증하고 snapshot을 보존할 뿐 환산하지 않는다(환산하려면 `pricing_id`를 해석해야 한다). 요율 · FX가 확정되지 않았으면 `amount=null`이며 **0원으로 쓰지 않는다.** FX source가 정해질 때까지(RD-08) `pricing_id`는 placeholder다.

아직 닫히지 않은 것은 정책이 아니라 구현 세부다.

- `pricing_id`가 가리킬 versioned pricing/FX artifact의 위치와 schema
- KRW 환산에 쓰는 FX source
- provider/model 가격 변경 이력 보존 방식
- provider별 실제 정산 기준(원화 크레딧과 표시 가격의 관계, [`mlapi.md`](./official-inputs/mlapi.md))

공용 catalog가 나중에 채택되더라도 Search의 실행 중 cost estimate와 Runtime의 authoritative ledger는 서로 다른 목적의 소비자일 수 있다. **SSOT는 가격표 데이터에 하나만 두고, 사용 주체를 하나로 제한하지 않는다.**

### 11.4 아직 열려 있는 값

- UsageRecord · in-flight table의 column 이름과 `DECIMAL` precision/scale — 첫 migration (§4.5). in-flight 추적 · 복구 · 중복 방지 규칙은 §11.1로 닫혔다
- `pricing_id`가 가리킬 pricing/FX artifact 형식·위치와 history 보관 (§11.3)
- UsageRecord retention
- `purge_case()`와 ledger 삭제 관계

마지막 두 항목은 Ops/정책과 함께 닫는다.

## 12. Worker Dispatch

Worker composition root가 Runtime과 domain public capability를 연결한다.

금지:

- `case`가 Worker 구현을 직접 import
- Worker가 orchestration 결정을 새로 만듦
- Runtime이 domain 내부 private service를 호출
- module별 provider detail을 common/runtime에 흡수

Worker handler는 Job kind를 **등록된 public capability invocation**으로만 매핑한다.

Readout 계열은 Final JobExecution Contract의 “1 execution : public readout 1회” 불변조건을 지켜야 한다.

§12.1 ~ §12.5는 확정이다(RD-06 · RD-19, [#245](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/245), 2026-10-04). case ↔ Runtime의 application-level 접합 의미는 여기서 닫고 별도 Contract를 두지 않는다. Case table schema · `CaseStore` MySQL 구현 · 결과 반영 함수는 case 소유이고, Runtime은 dispatch · cancel · read port와 transaction 참여 방식을 제공한다.

### 12.1 Dispatch transaction

- Case aggregate · JobRecord와 Runtime table은 api · worker가 함께 쓰는 **같은 MySQL**에 있다. Case schema는 case, Runtime schema는 runtime이 소유하며 모듈 간 FK는 두지 않는다.
- **transaction 경계는 composition root가 소유한다.** API composition root가 한 DB transaction 안에서 ① case command 처리 · 저장 ② case가 돌려준 「이번 command로 append된 JobRecord 목록」마다 Runtime enqueue(`attempt=1` `QUEUED`) ③ commit을 한다.
- case repository와 Runtime dispatch · persistence는 호출자가 준 같은 transaction에 참여하고 **각자 독자적으로 commit하지 않는다.** 정확한 transaction · UoW API 모양(SQLAlchemy Connection 등)은 구현 플래닝에서 정한다.
- case 저장이나 enqueue 중 하나라도 실패하면 전체 rollback이다 — command는 반영되지 않는다. case-command 응답 의미와 `error.code`는 바꾸지 않는다(HTTP 매핑은 §13).
- 같은 `job_id`의 같은 attempt 중복 enqueue는 DB unique 제약이 거부한다. command 수준 중복 제출(`idempotency_key`)은 case-command의 결정이다.

### 12.2 결과 반영 (push)

```text
T1  Worker: execution terminal · produced commit
T2  Worker composition root → case 공개 반영 함수
      case 반영 + 후속 JobRecord append + 후속 enqueue + Runtime 「반영 완료」 표식
    (한 transaction)
```

- T2가 실패하거나 T1 · T2 사이에 Worker가 죽으면 Worker가 표식 없는 terminal execution을 다시 넘긴다. 그래서 case 반영 함수는 **`execution_id` 기준 idempotent**여야 하고 처리한 `execution_id`를 case persistence에 남긴다(case 요구사항).
- **반영 여부는 case가 판단한다 — case가 현재 context에 유효하다고 판단한 결과만 반영한다.** 기준은 case가 들고 있는 「중단된 `job_id` 집합」과 현재 선택 context다. `case_rev` 일치를 늦은 결과 배제 기준으로 쓰지 않는다 — 같은 `case_rev`에서 병렬 Job이 돌고 `case_rev`는 중단 외 command에서도 오르므로, 지정하지 않은 병렬 Job의 유효한 결과는 계속 반영돼야 한다(JobExecution Contract §9-8).

### 12.3 Kind registry

kind → handler 등록은 Worker composition root의 단일 registry다. 등록되지 않은 kind는 enqueue는 받고, Worker가 claim 즉시 invocation 없이 `FAILED`(`RUNTIME_` 접두어)로 끝낸다 — UsageRecord는 없다. recording export 2종은 public capability가 구현된 뒤 등록한다.

### 12.4 JobExecution read port

Runtime은 CaseView projection에 필요한 JobExecution read port(`job_id` 목록 → JobExecution Contract 모양)를 제공하고 composition root가 case에 주입한다. 대표 execution 선택(attempt 최댓값)은 CaseView Contract A§10-6대로 case가 한다. 구체 API shape는 구현에서 정한다.

### 12.5 사용자 중단

```text
case 중단 command 성공
→ 같은 transaction에서 case가 넘긴 job_id 목록마다 Runtime cancel 요청 (JobRecord 발주 아님)
   ├─ QUEUED  → 즉시 CANCELLED (Worker 개입 없음 · UsageRecord 없음)
   └─ RUNNING → Runtime 내부 「중단 요청」 표식만 기록, 상태는 RUNNING 유지
                → heartbeat가 표식을 읽어 handler에 알림 (§7.2)
                → handler가 public capability 사이 checkpoint에서 멈춤
                → 실제로 멈춘 뒤 RUNNING→CANCELLED 기록
```

- **협력적 중단이다.** 이미 진입한 public capability는 반환될 때까지 계속된다. Search capability 안의 in-call retry · backoff도 그 capability가 반환할 때까지 계속될 수 있으므로 「현재 HTTP 1회가 끝나면 즉시 중단」을 보장하지 않는다. 실제 정지 지연과 추가 비용은 그 capability가 반환할 때까지다. capability 내부에 cancel checkpoint를 넣는 것은 baseline이 아니다.
- 시작된 provider HTTP 시도는 중단과 무관하게 §11.1대로 usage 기록 대상이다.
- **경합.** 먼저 commit된 terminal 전이가 이긴다(조건부 UPDATE, §4.3). 중단 요청 뒤 `SUCCEEDED`로 끝나면 `SUCCEEDED`가 남고(사실 기록), case는 중단된 `job_id` 집합에 있으므로 그 결과를 반영하지 않는다. 중단 요청된 job이 STALE이 되면 다음 automatic attempt를 만들지 않는다.
- MVP에서 `CANCELLED` execution의 `produced`는 모든 kind에서 `[]`다. 이미 case에 반영된 결과는 유지한다.
- 화면의 즉시성은 case가 준다 — 중단 command가 성공하면 case는 그 job을 `running_jobs`에서 바로 빼고 해당 step을 `PARTIAL`로 투영한다. Runtime의 실제 RUNNING과 Web의 「더 기다리지 않음」은 별개다.

## 13. API Boundary

FastAPI `BackgroundTasks`를 긴 영상 처리 queue로 사용하지 않는다.

API request의 책임:

1. 요청 validation
2. case command 호출
3. JobRecord 발주
4. Runtime dispatch 요청 (§12.1)
5. 202 Accepted와 조회 정보 반환

실제 media transform/search/readout은 request lifecycle 밖에서 Worker가 실행한다.

HTTP 경계의 방향은 확정이다(RD-05, [#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247), 2026-10-04). **request · response · schema · status · error의 세부는 [HTTP API Contract](../architecture/contracts/contract-http-api.md)(`http-api/v1`, `Final — Accepted`)가 정한다.** 여기에는 결정된 surface와 원칙만 두고 schema를 복제하지 않는다.

- **Owner.** HTTP API Contract Producer = `api` composition root, Web = Consumer. route 구현자는 Contract Owner와 같은 사람일 필요가 없고 Contract를 따른다.
- **필수 surface.** 정확한 경로 표기는 Contract §2다.

  ```text
  POST /cases
  POST /cases/{case_id}/sources
  POST /cases/{case_id}/commands
  GET  /cases/{case_id}/view
  GET  /cases/{case_id}/frames/{frame_ref}
  GET  /cases/{case_id}/assets/{asset_ref}
  GET  /health/live
  GET  /health/ready
  ```

  frames · assets는 「또는 동등한 경로」로 결정됐고 Contract가 위 경로로 고정했다. frames는 CaseView의 FrameRef(`thumb_ref` · `preview_ref` · `plate_preview_ref`)를, assets는 최종 신고용 artifact 다운로드를 지원한다.
- **domain action은 command `kind`다.** 분석 시작 · 중단 · 선택 등은 route를 늘리지 않고 `POST /cases/{case_id}/commands`의 kind로 둔다. job 상태 endpoint는 두지 않는다 — Web은 JobExecution을 직접 읽지 않는다.
- **202 / 200.** command가 JobRecord를 1건 이상 발주하면 `202`, 없으면 `200`이다. 판단은 composition root가 §12.1의 「append된 JobRecord 목록」으로 하고 transport가 domain 의미를 추론하지 않는다. body는 case-command 응답 그대로이며 `error.code`를 재해석하지 않는다. transport 자체 오류는 `http.*` 계열로 분리한다.
- **polling.** `GET /cases/{case_id}/view` 반복. baseline 정지 조건은 `running_jobs`가 빈 것이다(§9).
- **upload.** 1 request = 1 file. 응답 전에 같은 mount의 staging → `fsync` → same-mount publish → recording 등록 · metadata commit을 끝낸다(Ops §4-2). 여러 파일은 파일별 요청이다.

## 14. Runtime Health

구현 시 최소 두 endpoint를 둔다.

```text
/health/live
→ API process가 요청을 받을 수 있는가

/health/ready
→ 현재 요청 처리에 필수인 Runtime dependency(DB 등)를 사용할 수 있는가
```

외부 AI provider 전체의 실시간 성공 여부를 `ready`에 묶어 provider 장애가 곧 API process down으로 해석되게 하지 않는다.

Worker는 public health endpoint 대신 Runtime DB의 heartbeat/lease 관측으로 상태를 볼 수 있다.

운영에서 health를 어떻게 alert에 사용할지는 Ops Spec이 소유한다.

## 15. Runtime Configuration

환경별 변경 가능성이 있는 Runtime 값은 코드 상수보다 config로 둔다. 각 값의 시작값 · key 후보 · config로 열지 않는 값은 [Provisional Baseline v0.1](./provisional-baseline-v0.1.md)가 정한다.

후보:

```text
DB connection
worker polling interval
retry max/backoff/jitter
lease duration
heartbeat interval
STALE threshold
stale sweep interval
pricing catalog/reference (채택 시)
log level
```

### 15.1 Module / Provider configuration 주입 경계

Worker composition root는 domain module이 실행에 필요한 config와 secret을 **주입**할 수 있어야 하지만, common/runtime이 provider-specific 의미를 해석하지 않는다.

```text
deployment / Worker composition root
→ module config · secret 주입
→ search public capability / provider adapter

common/runtime
→ 전달 경계와 secret 비노출 책임

search
→ Elice base_url, model, reasoning_effort,
   OpenAI-compatible schema, media transport 등 provider 의미 해석
```

따라서 Runtime이 Elice request schema나 `reasoning_effort` 같은 provider semantics를 별도 설정 모델로 복제하지 않는다.

provider label · provider config 의미와 validation은 Search가 소유한다(Issue #153 합의, 2026-09-26). key naming은 `GEMINI_API_KEY → ELICE_ML_API_KEY` rename 방향으로 합의됐고, 기존 `.env` 호환 alias는 `common/env.py`가 아니라 **Search config 내부**에 둔다. alias 제거는 팀 `.env`와 deployment secret migration이 끝난 뒤다. rename 자체는 Search 작업이며 develop에 아직 반영되지 않았다. Runtime은 구현 편의를 이유로 Search보다 먼저 rename하거나 별도 가격표를 복제하지 않는다. pricing 경계는 §11.3을 따른다.

secret은 repository config에 저장하지 않는다.

Python/dependency의 executable SoT는 root `pyproject.toml`, `uv.lock`, CI workflow다.

### 15.2 Config · secret 로딩

확정(RD-07, [#249](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/249), 2026-10-04). 배포 환경의 secret source · 전달 · rotation은 [Ops Spec](./ops-spec.md) §4-1이 소유한다.

- **값은 파일에서만 읽는다.** `os.environ`을 config 값 출처로 쓰지 않고, Compose `environment:` · `env_file:`로 config 값을 넣지 않는다. 출처가 하나라 우선순위 충돌이 없다.
- **`DAESINGO_ENV_FILE`(파일 경로, secret 아님)은 api · worker composition root만 해석한다.** composition root가 고른 경로를 `load_env_file(path)`에 명시적으로 넘긴다. `load_env_file(path=None)`의 기본 동작은 지금처럼 `cwd/.env`다 — Search CLI · eval 등 인자 없이 부르는 쪽은 shell에 남은 `DAESINGO_ENV_FILE`의 영향을 받지 않는다.
- **shape.** composition root가 파일을 한 번 읽어 mapping을 만들고, Runtime 값은 불변 `RuntimeConfig`로, 각 모듈 값은 그 모듈의 factory · validator에 mapping으로 넘긴다. key 이름 · alias 의미는 각 모듈이 소유한다(Search key alias는 Search 경로, §15.1). Runtime 소유 key는 `DAESINGO_RUNTIME_` 접두어를 쓴다.
- **fail-fast.** api · worker composition root는 startup에서 Runtime config와 각 모듈 config를 모두 만들어 검증하고, 필수 key 누락 · 잘못된 값이면 non-zero로 종료한다. 첫 호출 때 늦게 실패하지 않는다. 로그에는 **key 이름만** 남기고, 값이나 입력값이 들어갈 수 있는 exception 원문은 출력하지 않는다. 미결인 pricing/FX(RD-08)를 startup 필수값으로 새로 강제하지 않는다(§11.3 `amount=null`).
- 앱은 startup에 한 번 읽는다. 값 변경은 container 재생성으로 반영한다(Ops §4-1).
- 로컬 · eval은 기존대로 인자 없는 `load_env_file()` = `cwd/.env`다.

## 16. Test Acceptance Criteria

### Unit

- JobExecution state transition
- attempt 증가
- invalid transition rejection
- retry scheduling pure logic
- stale detection pure logic

### Contract / Boundary

- Final Contract fixture validation
- module import boundary
- Job kind → public capability dispatch registration
- CaseView projection 정합

### Runtime Integration

실제 MySQL을 사용해 최소 다음을 검증한다.

1. concurrent claim에서 동일 job 중복 claim 없음
2. `available_at` 이전 claim 없음
3. RUNNING worker 소멸 → STALE
4. retry 시 same job_id + new execution_id + attempt+1
5. startup/periodic stale sweep idempotent
6. 실제 invocation이 시작된 호출은 UsageRecord 기록 대상이 되며, 호출 1건당 최종 원장 row가 정확히 1건 남음
7. dispatch 전 cancel에는 UsageRecord 없음
8. case가 반영하지 않는 늦은 SUCCEEDED execution(중단된 job 등)이 STALE로 바뀌지 않음
9. command 하나 = JobRecord + attempt 1 `QUEUED`가 한 commit, DB 실패 시 둘 다 없음 (§12.1)
10. STALE 판정과 attempt+1 `QUEUED`가 한 transaction, 다중 sweeper에서 attempt 중복 없음, backoff 동안 claim 없음 (§6.3)
11. usage begin 기록 실패 → provider HTTP 없음 · finish 뒤 Run 확정 전 Worker kill → 관측값 보존, Final row 정확히 1건 · persistence 실패로 provider 재호출 없음 (§11.1)
12. QUEUED 중단 → 즉시 CANCELLED · UsageRecord 0 / RUNNING 중단 → checkpoint 뒤 CANCELLED / 중단과 완료 경합 → 하나만 terminal (§12.5)
13. heartbeat 조건부 갱신 0 rows → 이전 Worker가 결과를 commit하지 않음 (§7.2)
14. 미등록 kind → `FAILED`(`RUNTIME_`) · UsageRecord 0 (§12.3)
15. Worker kill이 T1과 T2 사이 → 재시작 뒤 case 반영 정확히 1회 (§12.2)

실제 외부 AI provider 호출은 일반 PR CI의 결정론적 gate에서 분리한다.

## 17. 현재 구현 상태 — 2026-10-02 (`develop` `9c204ee` 기준)

현재 `develop`에서 확인된 것:

- `src/daesingo/common/job_execution.py`
  - JobExecution v1.1 model
  - 허용 상태 전이
  - in-memory attempt 연속성 (`InMemoryJobExecutionStore`)
  - STALE/CANCELLED
- 여러 domain module pytest / Mock Pack / contract validator
- CI: repo-wide pytest · Recording media smoke · boundary / contract fixture 검사 (Python 3.12, [Ops Spec](./ops-spec.md) §5 · §19)
- 동기 real 경로: case adapter가 Search·Fine·Readout public capability를 같은 프로세스에서 직접 호출한다. Runtime queue와 JobExecution을 거치지 않으며, case가 남기는 JobRecord는 in-memory case store에만 있다
- Search 내부 usage ledger (Final `UsageRecord` Contract 원장이 아니다)
- API/Worker 책임 README

아직 구현되지 않은 것:

- MySQL Runtime persistence · migration
- 실제 MySQL DB Queue / claim
- lease / heartbeat
- stale sweep
- API composition root
- Worker composition root
- case → Runtime 발주 경로
- Final UsageRecord persistence
- Runtime health endpoint

따라서 이 문서는 **구현 완료 설명서가 아니라 다음 Runtime 구현의 acceptance 기준**이다.

## 18. Open Runtime Decisions

첫 DB Queue/Worker 구현에서 닫아야 한다.

workflow §5 Timing A 9개는 2026-10-04에 모두 닫혔다(Register [§5 진행 상태](./open-decision-register.md#5-진행-상태--timing-a)). workflow §6 값은 2026-10-05 [Provisional Baseline v0.1](./provisional-baseline-v0.1.md)로 Provisional이 정해졌다(최종값 P2). 남은 항목은 B · C · D Decision이다.

- [x] queue table / execution table의 물리 schema — `job_execution` 단일 table = 실행 원장 + queue로 닫힘 (§4.2). column 이름은 첫 migration
- [x] `JobExecution.produced` 물리 저장 — JSON column으로 닫힘 (§4.5)
- [x] `JobExecution.usage_refs` materialization — `UsageRecord.execution_ref` projection으로 닫힘 (§4.5)
- [x] UsageRecord final append timing / in-flight recovery / duplicate prevention — durable in-flight + run 연결 확정 뒤 Final append로 닫힘 (§11.1)
- [x] claim transaction / locking query — RC · `(status, available_at, execution_id)` index · `LIMIT 1 FOR UPDATE SKIP LOCKED`로 닫힘 (§4.3)
- [x] DB 접근 계층 · migration 도구 — sync DB access stack · Alembic으로 닫힘 (§4.4). FastAPI route `def`/`async def`는 이 항목이 정하지 않음
- [x] retry 책임 층위 — STALE만 Runtime 자동 retry로 닫힘 (§6.2)
- [x] retry backoff 동안 다음 attempt 생성 시점 ↔ CaseView 대표 상태 계약 정합 — 같은 transaction에서 QUEUED 생성으로 닫힘 (§6.3)
- [x] heartbeat persistence 구조 — RUNNING row lease + 별도 heartbeat thread로 닫힘 (§7.2)
- [x] case ↔ Runtime dispatch · 결과 반영 · 사용자 중단 — 닫힘 (§12.1 ~ §12.5)
- [x] HTTP 경계 방향 — 닫힘 (§13). [HTTP API Contract](../architecture/contracts/contract-http-api.md) `http-api/v1` Final — Accepted(2026-10-05). 구현 선행 조건은 Contract §9.1
- [x] retry max — Provisional v0.1 B-R1 (최종값 P2)
- [x] backoff + jitter — Provisional v0.1 B-R2 · B-R3 (최종값 P2)
- [x] lease duration — Provisional v0.1 B-L2 (최종값 P2)
- [x] heartbeat interval — Provisional v0.1 B-L1 (최종값 P2)
- [x] STALE threshold — Provisional v0.1 B-L3 (최종값 P2)
- [x] stale sweep interval — Provisional v0.1 B-L4 · B-L5 (최종값 P2)
- [x] worker polling interval — Provisional v0.1 B-Q1 ~ B-Q3 (최종값 P2)
- [x] Runtime configuration shape · secret 주입 — 닫힘 (§15.2 · Ops §4-1)
- [x] UsageRecord persistence shape — 물리 표현(typed column · exact numeric · float 금지)으로 닫힘 (§4.5). `DECIMAL` precision/scale은 첫 migration에서 고정
- [ ] `pricing_id`가 가리킬 versioned pricing/FX artifact 위치·schema · FX source — 정책은 §11.3에서 닫힘 (Search rate 주입 유지 · KRW 정규화)
- [x] provider config/key naming boundary — Issue #153 합의로 닫힘 (§15.1). rename 구현은 Search 작업으로 남음

결정이 여러 구현에 장기 영향을 주면 `docs/runtime/decisions/`에 ADR을 추가한다. 단순 config 튜닝값마다 ADR을 만들지는 않는다.

## References

- [Architecture v4](../architecture/module-architecture.md)
- [Logical ERD](../architecture/erd-draft.md)
- [ERD ↔ Runtime 정합화 ADR](../architecture/contracts/adr/adr-erd-runtime-alignment-2026-09-19.md)
- [JobRecord / CaseView Contract](../architecture/contracts/contract-job-record-case-view.md)
- [JobExecution Contract](../architecture/contracts/contract-job-execution.md)
- [UsageRecord Contract](../architecture/contracts/contract-usage-record.md)
- [AnalysisSource / Derived Asset Contract](../architecture/contracts/contract-analysis-source-derived.md)
- [Runtime Ops Spec](./ops-spec.md)
- [Runtime experiments router](./experiments/README.md)
- [Issue #95 — Elice ML API migration tracker](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/95)
- [Issue #153 — provider usage · pricing · runtime config boundary review](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153)
- [common runtime README](../../src/daesingo/common/README.md)
