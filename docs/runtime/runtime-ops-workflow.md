# Runtime/Ops 작업 워크플로우

**Status:** Working — work process guide  
**Owner:** common/runtime — 김준영  
**Date:** 2026-10-02  
**Runtime router:** [Runtime Documentation](./README.md)

> 이 문서는 Runtime/Ops 작업을 **어떤 순서로 진행할지**만 정한다. 결정·값·threshold를 담지 않으며, 결정은 [`runtime-tech-spec.md`](./runtime-tech-spec.md) · [`ops-spec.md`](./ops-spec.md) · [`deployment-runbook.md`](./deployment-runbook.md) 또는 상위 Contract/ADR에 기록한다.

## 0. 현재 상태 정합성 검수

가장 먼저 현재 문서·코드·CI·공지 사이의 불일치를 전수 확인한다.

- [Runtime README](./README.md)
- [Runtime Tech Spec](./runtime-tech-spec.md)
- [Ops Spec](./ops-spec.md)
- [Deployment Runbook](./deployment-runbook.md)
- Final Contract — [`docs/architecture/contracts/`](../architecture/contracts/README.md)
- 현재 develop 코드
- GitHub Actions — `.github/workflows/`
- 카테캠 공식 공지와 [Official Inputs](./official-inputs/README.md)

발견 항목은 다음처럼 분류한다.

```text
STALE DOC
→ 문서가 현재 구현보다 뒤처짐

CONTRACT / SPEC MISMATCH
→ 문서끼리 의미가 충돌

IMPLEMENTATION GAP
→ 설계는 확정됐지만 구현되지 않음

OPEN DECISION
→ 구현 전에 결정·baseline·실측 여부를 판단해야 함
```

단순 문서 위생 문제는 묶어서 처리하고, 구현 방향을 잘못 유도할 수 있는 정합성 문제는 즉시 별도 Issue로 만든다. 이 단계에서 나온 `OPEN DECISION`은 §2 Decision Register의 입력으로 넘긴다.

검수 결과는 Audited SHA와 함께 [`reviews/`](./reviews/README.md)에 evidence로 보존한다. review는 결정의 SoT가 아니다.

---

## 1. 공식정보·외부 제약 확인

설계 브레인스토밍 전에 **우리 프로젝트에 실제 적용되는 외부 사실과 환경 제약**을 먼저 확인한다. 이 단계는 결정을 내리는 단계가 아니라 결정 가능한 범위를 좁히는 단계다.

### 카테캠 / AWS

```text
EC2 제공 사양
자원 증설 가능 범위
EBS
RDS
S3
ECR
Elastic IP
ALB
GPU
CloudWatch
SSM
GitHub OIDC / IAM 정책
비용 및 사용 제한
```

### ML API / Provider

```text
지원 API
media 전달 방식
최대 입력 크기
timeout
rate limit / concurrency
지원 codec / container
비용
retention / logging / delete 정책
```

### 법령 / 공식 가이드

```text
사용자 영상 · 식별정보 보관 · 파기 제약
```

카테캠 AWS/ML API 공지처럼 프로젝트에 직접 적용되는 외부 입력은 [`official-inputs/`](./official-inputs/README.md)에 보존한다.

MySQL Queue, ffmpeg, Object Storage, Worker scaling 같은 **일반 외부 기술 사례는 이 단계에 섞지 않는다.** 그런 조사는 §2–§3에서 실제 Open Decision을 정리한 뒤 필요한 질문만 §4에서 조사한다.

---

## 2. Open Decision 전수 수집

Runtime Tech / Ops / Runbook, §0의 정합성 검수 결과, §1의 공식 제약에서 아직 닫히지 않은 항목을 하나의 Decision Register로 모은다.

각 항목에는 최소 다음을 기록한다.

```text
Decision
현재 상태
관련 문서
Owner
Consult
현재 근거
결정 시점
Issue 필요 여부
ADR 필요 여부
실험 필요 여부
```

이 단계에서는 답을 임의로 만들지 않는다. 이미 상위 Contract/Accepted Decision에서 닫힌 항목은 Open Decision으로 다시 올리지 않는다.

현재 Register: [`open-decision-register.md`](./open-decision-register.md).

---

## 3. Decision 유형·결정 시점 분류

모든 결정을 같은 방식으로 처리하지 않는다. 먼저 **누가 결정하는지**와 **언제 닫아야 하는지**를 함께 분류한다.

### 3.1 책임 유형

#### Runtime 단독 결정

Runtime 구현 내부에서 닫을 수 있는 항목.

```text
queue physical schema
claim transaction
polling interval
retry/backoff
lease/heartbeat
stale sweep
Docker service command
```

#### 공동 결정

다른 모듈과 계약이 맞물리는 항목.

```text
HTTP API Contract
pricing/FX artifact 위치 · FX source
AnalysisSource storage/reuse
retention
```

pricing 정책(Search rate 주입 유지 · `pricing_id` 추가 · KRW 정규화)과 provider config/key naming은 이미 닫혔다([Tech Spec](./runtime-tech-spec.md) §11.3 · §15.1). 여기서 다시 결정 후보로 올리지 않는다.

필요한 Owner만 호출해서 Issue에서 빠르게 결정한다.

#### 제품/정책 결정

```text
사용자 자산 보관기간
삭제 정책
외부 공개 endpoint
사용자 flow와 연관된 retention
```

#### 실측 기반 결정

현재 숫자나 인프라 선택을 확정하면 안 되는 항목.

```text
Worker 수
EC2 증설
disk guardrail
Object Storage
RDS
전용 Queue
GPU
capacity threshold
```

### 3.2 결정 시점

```text
A. 구현 전에 반드시 닫아야 함
→ 계약/구조가 정해지지 않으면 구현 자체가 달라짐

B. Provisional Baseline이면 구현 가능
→ 초기값으로 구현한 뒤 실험으로 조정 가능

C. 구현 후 실측해야 닫을 수 있음
→ capacity / scaling / 운영 threshold

D. 현재 MVP에서 보류 가능
→ 관측된 필요가 생길 때 다시 연다
```

모든 Open Decision을 미리 완결하려 하지 않는다. 구현을 막는 Decision과 실측 뒤 닫을 Decision을 분리한다.

현재 분류: [`decision-classification.md`](./decision-classification.md). §3.1 책임 유형과 그 문서 Decision Type의 대응은 그 문서 §2.1에 있다.

---

## 4. Decision-driven 외부 기술 조사

외부 기술 사례는 §2–§3에서 **실제로 남은 Decision을 닫는 데 필요한 질문만** 조사한다.

예:

```text
Decision: DB Queue exact claim transaction
→ MySQL 8.4 / InnoDB
→ SELECT ... FOR UPDATE SKIP LOCKED
→ lock 범위 / ORDER BY / LIMIT
→ transaction boundary / commit 시점
→ concurrent worker failure mode

Decision: Runtime working set
→ 영상 처리 서버 resource 특성
→ ffmpeg CPU/RAM/temp disk
→ base64/JSON request construction
→ process RSS / copy overhead

Decision: local-only storage 유지 여부
→ Object Storage 사용 패턴
→ restart / multi-worker reuse
→ lifecycle / retention

Decision: Worker 1 → N
→ CPU-bound vs I/O-bound scaling
→ queue wait / backpressure
→ DB contention / resource isolation
```

자료 우선순위는 대략 다음과 같다.

```text
1. 기술 자체 공식 문서
2. 신뢰할 수 있는 engineering / architecture 사례
3. 오픈소스 구현·issue·benchmark
4. 커뮤니티 자료는 보조 근거
```

외부 사례의 숫자를 그대로 대신고 baseline으로 복사하지 않는다. 외부 자료는 **후보·failure mode·실험 항목을 현실화하는 근거**로 사용한다.

구현 가능성 자체가 불명확하면 작은 **pre-implementation spike**를 수행할 수 있다. 이 spike는 P2 capacity 같은 운영 실험과 구분한다.

---

## 5. 구현 전 필수 Decision 처리

§3에서 **A. 구현 전에 반드시 닫아야 함**으로 분류한 항목을 먼저 처리한다.

```text
공동 계약 필요
→ Decision Issue 생성
→ 필요한 Owner / Consult만 호출
→ Accepted Decision 반영

Runtime 단독 + reversible
→ 근거를 남기고 Runtime Spec에서 결정 가능

기술 semantics 불확실
→ §4의 작은 spike 결과로 닫음

실측 후 결정
→ 지금 최종값을 만들지 않음
```

예를 들어 HTTP API Contract처럼 다른 모듈과 맞물린 계약은 Baseline을 만들기 전에 닫는다. 반대로 Worker 수나 Object Storage처럼 실측이 필요한 선택은 이 단계에서 확정하지 않는다.

Decision Issue는 이후 §7의 Implementation Issue와 구분한다.

---

## 6. Provisional Baseline v0.1 확정

구현에 필요한 값이 TBD로 남아 구현자가 임의 결정하지 않도록 초기값을 정한다.

단, 최종값이 아님을 다음 라벨로 명시한다.

```text
Provisional Baseline
Initial Default
```

예:

```text
worker concurrency
retry max
backoff
polling interval
lease duration
heartbeat interval
STALE threshold
stale sweep interval
```

각 값에는 반드시 다음을 붙인다.

```text
값
근거
왜 지금 이 값을 쓰는가
어떤 실험으로 검증하는가
변경 가능 조건
```

### 구분

```text
Implementation Baseline
→ 시스템을 실행하기 위해 지금 필요한 숫자
→ 구현 전 provisional 값으로 결정 가능

Operational Threshold
→ 실제 성능/운영 데이터를 보고 정할 숫자
→ 구현·실험 후 결정
```

임의의 CPU 70%, Disk 80% 같은 운영 threshold는 만들지 않는다.

현재 산출물: [Provisional Baseline v0.1](./provisional-baseline-v0.1.md).

---

## 7. Runtime Implementation Plan 작성 및 Task 분해

§5의 필수 Decision과 §6의 Baseline을 기준으로 실제 구현 담당자에게 넘길 Implementation Plan을 먼저 만든다.

우선순위는 대략:

```text
1. MySQL Runtime persistence
   - DB Queue
   - JobExecution
   - UsageRecord

2. Worker
   - claim
   - retry
   - lease
   - heartbeat
   - stale recovery

3. API composition root
   - HTTP API Contract
   - Case command
   - Runtime dispatch
   - 202 Accepted

4. Docker / Compose
   - api
   - worker
   - mysql
   - volume
   - config

5. Runtime configuration / secret injection

6. Structured logging
   - trace_id
   - case_id
   - job_id
   - execution_id

7. /health/live
   /health/ready

8. Runtime integration tests
```

Implementation Plan에는 dependency, acceptance criteria, 필요한 test/observability/experiment를 함께 적는다. 그 뒤 구현 slice를 Issue로 분해한다.

Issue 종류는 구분한다.

```text
Decision Issue
→ §5에서 결정 자체를 닫기 위해 사용

Implementation Issue
→ §7에서 확정된 Plan을 구현하기 위해 사용

Experiment Issue
→ 구현 후 실측이 필요한 경우

Documentation Issue
→ 결과를 SoT에 반영해야 하는 경우
```

Deployment automation은 실행 단위가 만들어진 뒤 별도 slice로 붙인다.

현재 산출물: [Runtime Implementation Plan](./runtime-implementation-plan.md).

---

## 8. Baseline 기반 구현 + Test / CI / Observability

이미 확정된 Architecture/Contract와 Provisional Baseline을 기준으로 구현한다.

현재 실행 모델(구현 책임 · merge authority · Owner 확인 조건)은 [Runtime Implementation Plan](./runtime-implementation-plan.md) §12, 실제 구현 기록은 [Runtime Implementation Log](./runtime-implementation-log.md)다.

```text
확정된 것
→ 바로 구현

공동 Decision 결과
→ 그대로 반영

실측이 필요한 것
→ Baseline으로 먼저 구현
```

각 구현 Task는 기능 코드만으로 끝내지 않고 가능하면 다음을 한 묶음으로 정의한다.

```text
Implementation
Acceptance Test
Integration Test
Observability
필요한 CI gate
Experiment
Evidence location
Decision affected
```

예:

```text
Worker claim 구현
→ duplicate claim integration test
→ queue wait / claim latency 기록 가능
→ deterministic Runtime Integration을 CI에서 실행
→ P2에서 Worker resource 측정
→ Worker scaling 판단 근거로 사용
```

### CI 원칙

기존 CI를 먼저 확인하고 **없는 gate만 추가**한다. `.github/workflows/python-tests.yml`은 이미 repo-wide pytest regression을 실행하므로 이를 새 작업으로 중복 기재하지 않는다.

pytest와 CI는 성격을 구분한다.

```text
Unit
Contract
Integration
Runtime Integration
External / Real E2E
```

일반 PR gate에는 결정론적으로 재현 가능한 항목만 둔다.

```text
기존 repo-wide pytest regression
Unit / Contract
deterministic Integration
필요 시 MySQL Runtime Integration
추가로 필요성이 확인된 lint / type / secret gate
```

실제 ML API 호출, 긴 영상, P2 Capacity Smoke는 일반 PR gate와 분리한다.

완벽한 연구가 끝날 때까지 구현을 멈추지 않되, 관측 불가능한 상태로 구현만 끝내지도 않는다.

---

## 9. Runtime Integration / Capacity / Real E2E

구현된 Baseline을 기준으로 실제 동작과 운영 가정을 검증한다.

우선 다음 조건에서 확인한다. P2 계획은 [`experiments/elice-runtime-capacity-smoke-plan.md`](./experiments/elice-runtime-capacity-smoke-plan.md)에 있다.

```text
P2 Runtime Capacity Smoke
Worker concurrency = 1
```

확인 항목:

```text
CPU
RAM
Worker RSS
MySQL contention
disk working set
ffmpeg temp
base64/JSON construction
provider latency
cleanup
failure recovery
restart/reuse
```

그 뒤 근거가 있을 때만 다음으로 확장한다.

```text
concurrency >= 2
30분~1시간 P3
Object Storage
EC2 증설
RDS
전용 Queue
GPU
```

Pre-implementation spike는 기술 semantics 확인용이고, 이 단계의 Runtime experiment는 **실제 capacity / performance / recovery / operation 검증**용이다.

---

## 10. Evidence 기록

실험은 실행만 하고 끝내지 않는다.

최소한 다음을 남긴다.

```text
executed_at
commit SHA
환경
입력
Baseline config
측정값
결과
known limitation
```

Raw 결과와 반복 가능한 결론을 분리한다.

```text
실험 결과 / raw evidence
→ docs/runtime/experiments/

반복 가능한 운영 결론
→ Runtime Tech / Ops Spec
```

다른 모듈이 소유한 실험은 원문을 복제하지 않고 Runtime에 영향을 주는 결론만 링크한다.

---

## 11. Baseline 및 설계 갱신

Evidence를 바탕으로 다음 중 하나를 결정한다.

```text
Baseline 유지
Baseline 수정
Architecture 변경 검토
Infrastructure 확장
Decision 종료 / 재오픈
```

장기적으로 여러 구현에 영향을 주는 구조 결정이면 ADR로 승격한다. 단순 tuning 값 변경까지 ADR을 만들지는 않는다.

실험 한 번의 raw 수치를 곧바로 운영 보장값으로 승격하지 않는다.

---

## 12. 다음 iteration

남은 Open Decision과 새로 관측된 failure mode를 Decision Register에 반영하고 다시 필요한 단계로 돌아간다.

```text
새로운 정합성 문제
→ §0

새 외부 제약
→ §1

새 Open Decision
→ §2–§5

Baseline 조정
→ §6

구현 후 capacity 문제
→ §9–§11
```

모든 iteration을 처음부터 반복할 필요는 없다. 변경된 근거가 영향을 주는 단계부터 다시 진행한다.

---

## 전체 흐름

```text
0. 현재 상태 정합성 검수
      ↓
1. 공식정보 / 외부 제약 확인
      ↓
2. Open Decision 전수 수집
      ↓
3. 책임 유형 + 결정 시점 분류
      ↓
4. 필요한 외부 기술 사례 / 기술 검증 조사
      ↓
5. 구현 전 필수 Decision 처리
      ↓
6. Provisional Baseline v0.1
      ↓
7. Runtime Implementation Plan + Task/Issue 분해
      ↓
8. 구현 + Test / CI / Observability
      ↓
9. Runtime Integration / Capacity / Real E2E
      ↓
10. Evidence 기록
      ↓
11. Tech / Ops / ADR / Baseline 갱신
      ↓
12. 다음 iteration
```

## 핵심 원칙

**추측으로 인프라를 늘리지 않고, 그렇다고 모든 값을 TBD로 남겨 구현자가 임의 결정하게 두지도 않는다.**

```text
현재 상태를 먼저 검수한다.

↓

실제 적용되는 외부 제약을 확인한다.

↓

Open Decision을 모으고
필요한 조사만 수행한다.

↓

구현을 막는 결정은 닫고
나머지는 Provisional Baseline으로 실행 가능하게 만든다.

↓

Test / CI / Observability와 함께 구현한다.

↓

실제 환경에서 측정한다.

↓

Evidence를 기록하고
필요한 부분만 설계와 인프라를 확장한다.
```
