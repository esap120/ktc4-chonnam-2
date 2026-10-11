# Runtime Documentation

대신고의 `common/runtime` 실행 인프라 문서 진입점이다.

> `common/runtime`은 여덟 번째 도메인 모듈이 아니다. `case`가 작업의 이유와 발주 의도를 소유하고, Runtime은 그 Intent를 실제 실행으로 옮긴다.

## Source of Truth 우선순위

```text
Product Policy
→ docs/architecture/module-architecture.md
→ Final Data Contract / Accepted Owner Decision · ADR
→ docs/architecture/erd-draft.md (Logical ERD)
→ docs/runtime/*
→ implementation
```

Runtime 문서는 Architecture나 Final Contract schema를 다시 정의하지 않는다. Logical ERD는 cross-domain 관계와 저장 후보를 통합하는 입력이며, Final Contract/Accepted Owner Decision과 충돌하면 상위 결정을 따른다. Research/experiment는 결정의 근거이지 단독 SoT가 아니다.

## 문서 구조

| 문서 | 역할 |
| --- | --- |
| [`runtime-tech-spec.md`](./runtime-tech-spec.md) | DB Queue, claim, JobExecution persistence, retry, lease/heartbeat, STALE recovery, Usage persistence, Worker dispatch |
| [`ops-spec.md`](./ops-spec.md) | EC2/Docker Compose, logging, monitoring, health 운영, storage/cleanup/retention, capacity, CI/CD, rollback 원칙 |
| [`deployment-runbook.md`](./deployment-runbook.md) | 배포 전 확인, revision 식별, health/smoke 검증, rollback, 장애 원인 축소 실행 체크리스트 |
| [`runtime-ops-workflow.md`](./runtime-ops-workflow.md) | Runtime/Ops 작업 순서 — 정합성 검수 → 공식 제약 → Open Decision → 필요한 외부 조사 → 필수 결정 → Baseline → 구현·관측 → 실험 → 갱신. 결정은 담지 않음 |
| [`provisional-baseline-v0.1.md`](./provisional-baseline-v0.1.md) | workflow §6 산출물 — Worker · polling · lease/heartbeat/STALE · retry · DB · upload · frame · cleanup · health · logging의 **Provisional 시작값의 canonical source**. 다른 문서는 ID(`B-xx`)만 가리킨다 |
| [`runtime-implementation-plan.md`](./runtime-implementation-plan.md) | workflow §7 산출물 — 현재 구현 gap · critical path · Task/Issue 분해 · Decision Gate 위치 · integration test 배치 · 구현 책임 구조(§12 Single Implementer + Deferred Owner Review). 결정 · 값을 새로 만들지 않는다 |
| [`runtime-implementation-log.md`](./runtime-implementation-log.md) | workflow §8 기록 — 실제로 구현된 것 · Plan 대비 변경과 이유 · 새 implementation detail · Owner 확인 포인트 · Milestone audit. Plan을 다시 쓰지 않고 차이를 여기에 남긴다 |
| [`open-decision-register.md`](./open-decision-register.md) | 아직 닫히지 않은 Runtime/Ops 결정의 통합 추적표(workflow §2 산출물). 답을 정하지 않으며, 닫히면 Spec/Contract/ADR로 승격하고 CLOSED 처리 |
| [`decision-classification.md`](./decision-classification.md) | Register의 각 결정을 유형 · 결정권 · Timing · Gate · Closure route · §4 조사 필요로 분류(workflow §3 산출물). 답을 정하지 않으며 Register 내용을 복제하지 않음 |
| `research/` | workflow §4 외부 기술 조사. `prompts/NN-<topic>.md` = 실행용 self-contained prompt(decision-classification §6 R1 · R2 Queue), `NN-<topic>-<조사 기준일>.md` = 그 결과. 결과는 Decision 근거이며 결정이 아님 — Owner 검토 뒤 Spec · Contract · ADR로 옮긴다 |
| [`official-inputs/README.md`](./official-inputs/README.md) | 카테캠 운영진 공지(AWS 환경 · ML API 등) 사본. 외부 입력이며 결정이 아님 |
| [`experiments/README.md`](./experiments/README.md) | Runtime cross-cutting 실험의 plan/result 라우터. 실험은 근거이며 결과가 반복 가능할 때 Tech/Ops 결정으로 승격 |
| [`reviews/README.md`](./reviews/README.md) | 특정 시점의 Runtime/Ops 정합성 검수·review evidence. Audited SHA 기준으로만 읽으며 결정의 SoT가 아님 |
| `decisions/` | 장기 영향을 주는 실제 Runtime 결정이 생겼을 때만 ADR 추가 |

빈 ADR 폴더를 미리 만들지는 않는다.

## 핵심 경계

```text
Browser
  ↓
API composition root
  ↓
case
  └─ JobRecord = Job Intent
       ↓
common/runtime
  ├─ DB Queue / claim
  ├─ JobExecution
  ├─ retry / lease / heartbeat
  └─ UsageRecord
       ↓
Worker composition root
  └─ recording / search / readout / evidence public capability
```

- `case = orchestrator`
- `common/runtime = executor`
- JobRecord와 Queue row는 같은 개념이 아니다.
- 사용자 재실행은 새 JobRecord / 새 `job_id`.
- 자동 인프라 retry는 같은 `job_id` + 새 `execution_id` + `attempt+1`.
- STALE은 Worker 소멸 실행 상태이며 old `case_rev`와 다른 개념이다.
- 비용/사용량의 authoritative ledger는 UsageRecord다.

## Upstream Design Inputs

Runtime 구현 시 다음 문서를 직접 참조한다.

- [Logical ERD](../architecture/erd-draft.md) — cross-domain 관계·cardinality·저장 후보
- [JobRecord / CaseView](../architecture/contracts/contract-job-record-case-view.md)
- [JobExecution](../architecture/contracts/contract-job-execution.md)
- [UsageRecord](../architecture/contracts/contract-usage-record.md)
- [AnalysisSource / RemoteCopy / DerivedAsset](../architecture/contracts/contract-analysis-source-derived.md)
- [ERD ↔ Runtime 정합화 ADR](../architecture/contracts/adr/adr-erd-runtime-alignment-2026-09-19.md)

schema, enum, 불변조건을 Runtime 문서로 복사해 별도 SoT를 만들지 않는다. Logical ERD에서 JSON/관계 테이블처럼 물리 저장 선택이 열려 있으면 Runtime Tech Spec이 구현 근거를 가지고 닫는다.

## 현재 구현 상태 — 2026-10-02 (`develop` `9c204ee` 기준)

### 확인된 구현

- 여러 domain module Python 구현과 pytest
- Python 3.12 정렬 — root `pyproject.toml` · `uv.lock` · `.python-version` · CI workflow
- CI: repo-wide pytest(offline fixture) · Recording 합성 media smoke · boundary / contract fixture 검사 (상세 [Ops Spec](./ops-spec.md) §19)
- `JobExecution v1.1` in-memory lifecycle (`InMemoryJobExecutionStore`)
- recording 실제 ffmpeg AnalysisSource materialization · 다중 원본 Timeline · `purge_case`
- search 실제 Elice ML API 호출 경로
- case 동기 real 경로 — case adapter가 Search·Fine·Readout을 **같은 프로세스에서 동기로 직접 호출**한다. Runtime queue와 JobExecution을 거치지 않고, case가 남기는 JobRecord는 in-memory case store에만 있다
- Mock Pack / contract validator / boundary checker

### 아직 구현되지 않은 Runtime

- MySQL Runtime persistence (JobExecution · UsageRecord · migration)
- MySQL DB Queue / claim
- lease / heartbeat / stale sweep
- API composition root (`src/daesingo/api/`는 README만 있음)
- Worker composition root (`src/daesingo/worker/`는 README만 있음)
- Final `UsageRecord` persistence — Search 내부 ledger는 있으나 Final Contract 원장이 아니다
- live / ready health endpoint
- Runtime Docker / Compose deployment
- deployment workflow

따라서 Runtime Tech/Ops 문서의 일부는 **현재 동작 설명이 아니라 구현 acceptance criteria**다. 검수 근거는 [`reviews/runtime-ops-consistency-audit-2026-10-02.md`](./reviews/runtime-ops-consistency-audit-2026-10-02.md) §4 A-01 · §6.

## Recording / Search Benchmark와의 관계

Runtime 문서가 실측 원본을 소유하지 않는다.

```text
recording
→ media/profile/ffmpeg/storage 사실

search
→ provider compatibility / recall / cost / latency

runtime
→ 위 결과가 실행/저장/배포에 미치는 영향만 반영
```

Issue #41에서 이미 합의된 경계:

- recording은 측정 가능한 media 속성을 보장
- search는 recall/provider 적합성을 검증
- H.265 direct/copy 확인 → AnalysisSource 조건 고정 → A~D 분할 비교

참조:

- [Recording architecture input](../modules/recording/research/architecture-input-memo.md)
- [Search architecture input](../modules/search/research/architecture-input-memo.md)

### Issue #95 이후 Runtime 라우팅

Issue #95의 Elice 전환 P0/P1 결과는 Recording/Search가 소유한 실험 사실이며, Runtime은 그 결과에서 **실행 환경에 영향을 주는 질문만** 가져온다.

```text
#95 P0/P1
→ provider inline media 경로 / materialization / local reuse 사실
→ Runtime cross-cutting 질문 추출
→ experiments/에서 capacity · working set · recovery 검증
→ 반복 가능한 결과만 runtime-tech-spec / ops-spec에 승격
→ 장기 구조 결정이면 decisions/ ADR
```

provider/usage/pricing/config 경계는 후속 Issue #153에서 Search 전수조사 후 Search·Runtime Owner가 합의했다(2026-09-26). 통화 정규화는 그보다 앞서 #19 답변으로 결정됐다([`budget-krw-normalization.md`](../modules/case/decisions/budget-krw-normalization.md), 2026-09-09). Runtime 쪽 반영은 [Tech Spec](./runtime-tech-spec.md) §11.3(pricing · 통화)과 §15.1(config · key naming)이 담는다.

Runtime 쪽에서 확정된 책임은 Final `UsageRecord` persistence와 실행 시점 pricing context · cost snapshot 보존, Worker/composition root의 config·secret 주입 경계, queue/retry/lease/heartbeat/observability다. 합의 항목(`pricing_id` · key rename · KRW 정규화)은 아직 develop에 구현되지 않았다.

P2 Runtime Capacity Smoke의 계획과 결과는 [`experiments/`](./experiments/README.md)에서 관리한다.

## 현재 열린 Runtime/Ops 결정

열린 결정의 통합 목록은 [`open-decision-register.md`](./open-decision-register.md)가 추적한다 — group별 Owner · Consult · 이미 닫힌 범위 · 의존 관계 · Timing 후보를 담고, 이미 결정된 항목 · Implementation Gap · 실험값은 그 문서 하단에서 제외 근거와 함께 구분한다. 이 README에는 목록을 복제하지 않는다.

각 Spec의 미결 체크리스트는 해당 문서 범위의 원문으로 남는다 — [Tech Spec](./runtime-tech-spec.md) §18 · [Ops Spec](./ops-spec.md) §23 · [Runbook](./deployment-runbook.md) §8.

정확한 수치는 실제 Runtime integration과 Recording/Search benchmark 결과 없이 임의 확정하지 않는다.

## Baseline Non-goals

현재 기본 구조에는 다음을 넣지 않는다.

```text
Redis / Celery / RabbitMQ / SQS / Kafka
Kubernetes / Microservices / Service Mesh
별도 DLQ
Auto Scaling
복잡한 Circuit Breaker
WebSocket/SSE progress
Prometheus/Grafana/OpenTelemetry full stack
```

관측된 failure mode가 필요성을 증명할 때 확장한다.

## Update Rule

Runtime 관련 변경 시:

1. Architecture/Final Contract 변경인지 먼저 확인한다.
2. Contract 변경이 아니라 구현 선택이면 Runtime Tech Spec에 기록한다.
3. 배포·운영 선택이면 Ops Spec에 기록한다.
4. recording/search 실험값은 Owner 문서에 남기고 Runtime에는 결정 영향만 링크한다.
5. Runtime cross-cutting 실험은 `experiments/`에 plan/result를 남기고, 반복 가능한 결과만 Tech/Ops 결정으로 승격한다.
6. 같은 설정값을 두 문서가 동시에 소유하지 않게 한다.

## Related

- [Architecture v4](../architecture/module-architecture.md)
- [Logical ERD](../architecture/erd-draft.md)
- [ERD ↔ Runtime 정합화 ADR](../architecture/contracts/adr/adr-erd-runtime-alignment-2026-09-19.md)
- [common runtime code README](../../src/daesingo/common/README.md)
- [Pre-deploy security review](../management/pre-deploy-security-review.md)
