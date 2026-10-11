# Elice Runtime Capacity Smoke Plan

**Status:** Planned — 구현/실행 전 설계  
**Owner:** common/runtime — 김준영  
**Design input:** Issue #95 P0/P1/R3  
**Ops baseline:** [Runtime Ops Spec](../ops-spec.md)  
**Experiment router:** [Runtime Experiments](./README.md)

> 이 문서는 #95의 Search/Recording 실험을 다시 수행하거나 canonical media profile을 확정하는 문서가 아니다. 이미 확인된 module 사실을 실제 Runtime baseline에서 조합했을 때 **capacity, working set, cleanup, concurrency 가정이 유지되는지** 검증하기 위한 P2 계획이다. 또한 Provisional Baseline v0.1의 heartbeat · lease · STALE · retry 값은 사전 성능 실측이 아니라 구현 시작값이므로, RT-05/06 구현 뒤에는 §8 P2-F의 Runtime timing/failure validation으로 RD-04 최종 튜닝 근거를 수집한다.

## 1. 왜 필요한가

Issue #95 P0/P1/R3에서 다음 흐름은 실제 호출/로컬 실험으로 확인됐다. 범위는 2026-09 시점 운영 경로(`gemini-3.8-flash` · OpenAI-compatible `/v1/chat/completions` · base64 inline video)이며, 모델이나 전송 방식이 바뀌면 working set 가정을 다시 확인한다([`mlapi.md`](../official-inputs/mlapi.md) §7.1).

```text
Recording AnalysisSource materialization
→ open_analysis_source()
→ Search가 binary media 획득
→ base64 data URL
→ JSON request
→ Elice ML API
```

또한 다음 운영 영향이 확인됐다.

- inline media 전송은 binary보다 더 큰 request body와 추가 process memory working set을 만들 수 있다.
- ffmpeg materialization은 CPU/RAM/time/temp disk를 사용한다.
- 동일 `source + span + profile`의 process-local reuse는 materialization 비용을 크게 줄일 가능성이 있다.
- Elice 경로는 provider-side reusable object를 기본 가정으로 둘 수 없다.

하지만 아직 baseline 배포 환경에서 아래 조합을 함께 실행하지 않았다.

```text
api
+ worker
+ mysql
+ ffmpeg
+ AnalysisSource bytes
+ base64 encode
+ JSON serialization
+ provider HTTP request
```

따라서 module benchmark만으로 `t3.medium / 4GB / 50GB / Worker 1` baseline이 충분하다고 결론 내리지 않는다.

또한 Runtime Provisional Baseline v0.1의 heartbeat 10 s · lease 60 s · stale sweep 15 s · STALE retry 1회/5 s backoff는 `CONSERVATIVE_DEFAULT`/`DERIVED` 시작값이다. 구조의 정확성은 Runtime Integration test가 검증하지만, 이 숫자가 실제 t3.medium 부하에서 적절한지는 별도 timing/failure 관측이 필요하다.

## 2. 이 실험이 닫아야 하는 질문

P2가 끝나면 최소 다음을 설명할 수 있어야 한다.

1. Worker concurrency=1에서 대표 Real media path가 OOM/crash 없이 완료되는가.
2. ffmpeg materialization과 request construction 시 EC2/Worker peak CPU·RAM이 어느 정도인가.
3. api/mysql과 Worker가 같은 host에서 자원을 경쟁할 때 눈에 띄는 contention이 있는가.
4. temp media와 request working set이 정상·실패 후 회수되는가.
5. cold materialization 대비 warm local reuse의 이득과 steady-state disk 비용은 무엇인가.
6. Worker/process restart 후 재생성 비용은 어느 정도인가.
7. Worker concurrency 증가를 검토할 자원 여유가 있는가, 아니면 먼저 host/storage 구조를 바꿔야 하는가.
8. 정상 Real media 부하에서 heartbeat lag/attempt time/skipped tick이 어느 정도이며 false STALE이 발생하지 않는가.
9. Worker kill · DB stall 같은 장애에서 `last heartbeat → STALE → retry queued → retry started → terminal` timeline이 Baseline 계산과 실제로 얼마나 다른가.
10. retry attempt가 Case 대기 종료 뒤 도착할 때 T2 결과 사유를 분리해 관찰할 수 있는가. `runtime.retry.after_case_stopped_count`는 attempt ≥ 2의 `NOT_APPLIED(STOPPED_WAITING)`만 센다(#291 Owner clarification).
11. DB 정상 구간에서 cancel 요청이 handler에 관찰되는 시간이 B-X1 p95 ≤ 20 s 목표를 만족하는가.

## 3. 이번 단계에서 결정하지 않는 것

P2 계획만으로 다음을 확정하지 않는다.

- canonical AnalysisSource profile
- 최종 clip length / overlap
- coarse/fine 최종 media quality
- Worker count > 1
- EC2 spec 상향
- Object Storage / shared cache 도입
- cache TTL / retention
- pricing/FX artifact 위치 · schema
- 30분~1시간 P3의 exact 입력과 threshold

provider/usage/pricing/config ownership은 Issue #153 합의(2026-09-26)로 닫혔다 — [Runtime Tech Spec](../runtime-tech-spec.md) §11.3 · §15.1. P2는 이 경계를 다시 정하지 않는다.

## 4. 첫 시험 입력 후보

첫 smoke candidate:

```text
duration    20s
resolution  480p
codec       H.264
container   MP4
audio       off
```

이 값은 #95 P1에서 실제 Elice 호출과 비교적 작은 transport size가 확인되어 **첫 capacity fixture 후보**로 사용하는 것이다.

다음 의미는 아니다.

```text
20s / 480p
≠ canonical Search profile
≠ Runtime contract
≠ 운영 상수
```

Search/Recording이 이후 profile을 바꾸면 P2 입력도 그 결정에 맞춰 다시 실행할 수 있다.

## 5. 실행 환경

현재 baseline:

```text
EC2          t3.medium
CPU          2 vCPU
RAM          4GB
Disk         50GB SSD
OS           Ubuntu 24.04 LTS
Deployment   Docker Compose

services
- api
- worker
- mysql
```

실제 Compose/API/Worker가 아직 구현되지 않은 시점의 로컬 preflight는 측정 도구·경로 검증에만 사용할 수 있다.

**P2 완료 판정은 실제 baseline과 동등한 배포 환경에서 api/worker/mysql 조합을 포함해 실행한 결과**를 기준으로 한다.

P2-F는 RT-05(lease/heartbeat/cancel)와 RT-06(STALE/retry/redelivery)의 대상 동작이 구현된 뒤 실행한다. 그 전의 fake/timer 결과는 실험 완료 증거로 쓰지 않는다.

## 6. 기준 실행 경로

목표 경로:

```text
JobRecord
→ Runtime dispatch / DB Queue
→ Worker claim
→ Recording AnalysisSource
→ Search capability
→ binary read
→ base64 encode
→ JSON serialize
→ Elice call
→ provider response normalize
→ Usage observation
→ domain result
→ cleanup
→ JobExecution terminal
→ T2 ResultReflector / Case reflection
```

Queue/Worker가 아직 구현 전이라면 preflight에서는 capability 경로만 검증할 수 있지만, 그 결과를 P2 완료로 취급하지 않는다.

## 7. 관측 항목

### Host

- EC2 CPU utilization
- available/used RAM
- swap 사용 여부
- disk 사용량 / temp working set
- disk I/O가 가능하면 함께 기록
- t3 CPU credit balance / throttling 징후

### Process

가능한 범위에서:

- api RSS
- worker RSS
- mysql RSS
- ffmpeg process peak RSS / CPU
- Worker request construction 전후 RSS

### Media / Transport

- source bytes
- materialized AnalysisSource bytes
- base64 bytes
- serialized request body bytes
- materialization elapsed time
- provider round-trip latency
- end-to-end execution latency

### Runtime

실제 Queue가 구현된 뒤:

- `runtime.queue.wait_ms`
- `runtime.execution.duration_ms`
- `runtime.heartbeat.lag_ms`
- `runtime.heartbeat.attempt_ms`
- `runtime.heartbeat.skipped_tick_count`
- `runtime.stale.count`
- `runtime.stale.detect_latency_s`
- `runtime.stale.false_count`
- `runtime.retry.auto_count` · `runtime.retry.exhausted_count`
- `runtime.retry.after_case_stopped_count`
- `runtime.cancel.observe_latency_ms` · `runtime.cancel.terminal_latency_ms`
- T2 reflection outcome/reason: `APPLIED` · `ALREADY_APPLIED` · `NOT_APPLIED(STOPPED_WAITING|CANCELLED|SUPERSEDED)`
- JobExecution terminal status
- cleanup success/failure

Usage/cost는 관측하되 pricing/FX artifact 구조는 P2가 정하지 않는다(Tech Spec §11.3). Retry 실험에서는 attempt별 provider invocation/usage가 관찰 가능한 경우 추가 비용도 함께 기록한다.

## 8. 실험 순서

### P2-A — concurrency=1 cold path

대표 입력을 새로 materialize해서 전체 경로를 한 번 관통한다.

목적:

- baseline working set 파악
- ffmpeg와 request construction peak 분리
- 정상 cleanup 확인

### P2-B — concurrency=1 warm reuse

동일 `source + span + profile`을 다시 요청한다.

비교:

- materialization 시간
- total latency
- disk steady state
- Worker RSS
- 재사용된 ref/asset의 일관성

### P2-C — failure / cleanup

안전한 실패 조건을 만들어 확인한다.

예:

- provider timeout
- materialization 실패
- 실행 중 취소/Worker 종료는 Runtime lifecycle 구현 뒤 P2-F에서 실행

관측:

- partial temp media 잔존
- request payload/raw media가 로그에 남는지
- terminal execution 상태
- retry 대상 여부
- disk/RAM 회수

### P2-D — restart / reuse boundary

Worker/process restart 전후 동일 입력을 비교한다.

목적:

- 현재 reuse가 process-local이라는 가정을 실제로 확인
- restart 후 duplicate materialization 비용 측정
- persistent/shared cache가 필요한지 판단할 근거 확보

### P2-E — concurrency 증가 탐색

**P2-A~D가 설명된 뒤에만** 검토한다.

concurrency=2 이상은 목표값이 아니라 탐색 조건이다. concurrency=1에서도 OOM/swap/지속 CPU saturation 또는 api/mysql contention이 보이면 먼저 원인을 줄이고 Worker 수를 늘리지 않는다.

### P2-F — Runtime timing / failure validation

**RT-05 · RT-06 구현 및 관련 Runtime Integration test 통과 뒤에만** 실행한다. 목적은 구조의 정확성을 다시 테스트하는 것이 아니라 B-L* · B-R* · B-X1의 v0.1 숫자를 실제 배포 환경에서 조정할 근거를 수집하는 것이다.

#### P2-F1 정상 Real media 부하

대표 Real media path를 concurrency=1로 반복 실행한다. 가능하면 CPU credit이 충분한 구간과 낮아진 구간을 나눠 기록한다.

관측:

- heartbeat lag p50/p95/p99/max
- heartbeat attempt p50/p95/p99/max
- skipped tick 합계
- false STALE 합계
- execution duration과 ffmpeg/provider 구간
- host CPU/RAM/credit

`runtime.stale.false_count >= 1`이면 현재 lease/heartbeat 조합은 즉시 재검토한다.

#### P2-F2 Worker kill timeline

같은 대표 입력에서 가능한 범위로 Worker를 서로 다른 지점에 종료한다.

```text
A. claim 직후 / handler 초반
B. materialization 또는 provider 호출 중
C. handler 결과 뒤 T1 전후
D. T1 뒤 T2 전후
```

각 실행에서 다음 시각을 같은 `execution_id`/`job_id` lineage로 기록한다.

```text
last_heartbeat_at
worker_killed_at
stale_recorded_at
retry_queued_at
retry_started_at
retry_ended_at
case_reflection_at
```

목적은 실제 `STALE detect + backoff + poll` 지연과 retry 성공률을 확인하고 B-R1/B-R2를 조정할 근거를 얻는 것이다. D는 retry 자체보다 T2 redelivery/idempotency 검증용이다.

#### P2-F3 DB stall / heartbeat gap

안전한 실험 환경에서 heartbeat DB 경로를 5 s / 15 s / 30 s / 60 s 수준으로 일시 방해하거나 동등한 fault injection을 사용한다. 운영 데이터가 있는 환경에서 임의 network 차단을 하지 않는다.

관측:

- heartbeat attempt duration/error
- skipped tick
- 마지막 성공 heartbeat 이후 gap
- STALE 발생 여부와 detect latency
- handler 생존 여부
- DB 복구 뒤 lease 갱신/재시도 동작

이 실험은 “N회 실패하면 STALE”을 검증하는 것이 아니다. STALE 조건은 마지막 성공 갱신 뒤 lease 만료라는 현재 규칙 그대로다.

#### P2-F4 Case reflection reason / late retry

attempt ≥ 2가 실제로 존재하는 시나리오에서 T2 outcome을 사유별로 기록한다.

| Case outcome | `after_case_stopped_count` |
| --- | --- |
| `APPLIED` | 증가하지 않음 |
| `ALREADY_APPLIED` | 증가하지 않음 |
| `NOT_APPLIED(STOPPED_WAITING)` | **증가** |
| `NOT_APPLIED(CANCELLED)` | 증가하지 않음 |
| `NOT_APPLIED(SUPERSEDED)` | 증가하지 않음 |
| reflector exception / T2 rollback | 증가하지 않음 — redelivery 대상 |

이는 #291에서 확정한 지표 의미를 측정으로 보존하기 위한 표다. Case 8-9 timeout 기록이 구현되기 전에는 `STOPPED_WAITING` 표본이 0이어도 정상이다.

#### P2-F5 cancellation observation

RUNNING 중 cancel 요청을 넣고 `cancel_requested_at → handler observed → terminal`을 기록한다.

- DB 정상 구간 `runtime.cancel.observe_latency_ms` p95를 B-X1(20 s)와 비교
- capability 내부 선점 중단은 범위 밖이므로 terminal latency와 observe latency를 분리
- cancel이 STALE과 겹쳐도 다음 automatic retry가 생기지 않는지 확인

## 9. 완료 기준

현재 단계에서 RAM/CPU percentage 같은 임의의 PASS 숫자를 만들지 않는다.

P2 1차 완료는 다음 질문에 측정 근거로 답할 수 있는 상태다.

- 현재 baseline을 유지할 수 있는가
- Worker concurrency=1을 유지해야 하는가
- EC2 spec 상향이 필요한가
- local disk guardrail을 더 좁혀야 하는가
- process-local reuse로 충분한가
- persistent/shared storage 실험이 필요한가
- P3 long-duration Runtime E2E를 어떤 조건으로 설계해야 하는가
- heartbeat/lease/sweep 조합에서 정상 부하의 false STALE이 없는가
- STALE retry의 실제 복구시간·성공률·추가비용을 설명할 수 있는가
- late retry의 Case 미반영을 `STOPPED_WAITING`과 다른 사유로 분리해 설명할 수 있는가
- B-X1 cancel observe 목표를 유지/조정할 근거가 있는가

RD-04의 최종값을 P2로 닫으려면 최소 P2-F1/F2 결과가 있어야 한다. `runtime.stale.false_count >= 1`이면 값 확정보다 원인 조사와 Baseline 재검토가 먼저다. Case timeout과 B-R1 관계를 최종 판단하려면 Case timeout 재측정과 P2-F4 표본을 함께 본다.

결론이 “추가 측정 필요”여도 어떤 미확인 변수가 남았는지 특정할 수 있으면 결과 문서에 그대로 남긴다.

## 10. 결과가 바꿀 수 있는 결정

```text
P2 result
├─ baseline 여유 충분
│  └─ t3.medium + Worker 1 유지
│
├─ CPU/RAM contention
│  ├─ media path/profile 영향 재확인
│  └─ 필요 시 EC2 spec 상향 검토
│
├─ disk/reuse 문제가 병목
│  └─ persistent/shared storage 또는 Object Storage 실험 검토
│
├─ heartbeat lag / false STALE
│  └─ B-L1/B-L2/B-L4와 원인(CPU/GIL/DB stall) 재검토
│
├─ STALE retry 복구시간/성공률 문제
│  └─ B-R1/B-R2와 Case timeout 관계 재검토
│
├─ provider-bound + host 여유
│  └─ DB claim/lease concurrent-safe 확인 후 Worker pool 탐색
│
└─ 장시간 입력에서만 불확실성 큼
   └─ P3 30분~1시간 Runtime E2E plan 작성
```

P2 결과가 여러 구현과 향후 migration에 장기 영향을 주는 구조 결정을 만들면 `docs/runtime/decisions/` ADR로 승격한다.

예:

- baseline topology 변경
- persistent/shared AnalysisSource storage 도입
- Worker scaling model 변경
- STALE threshold를 lease와 별도 축으로 분리하는 구조 변경

단순 tuning 값 변경은 Provisional Baseline change log와 evidence link로 처리하고 새 ADR을 만들지 않는다.

## 11. Evidence 기록 규칙

실제 실행 시 최소 다음을 결과에 남긴다.

```text
executed_at
commit_sha
environment / EC2 type
docker image/revision (해당 시)
input fixture identity
AnalysisSource profile identity
worker concurrency
host CPU/RAM/disk observations
process peak observations
materialized bytes
request body bytes
latency
queue/execution observations
heartbeat lag / attempt / skipped tick
STALE / retry timeline
cancel observation timeline
T2 reflection outcome/reason
attempt별 usage/cost (관찰 가능한 범위)
cleanup result
known limitations
```

P2-F의 장애 시나리오는 가능하면 아래 lineage를 한 행/한 묶음으로 연결한다.

```text
trace_id → case_id → job_id → execution_id(attempt) → T1 → T2 outcome
```

secret, raw media bytes, base64 payload 전문, 번호판 문자열, 정확한 위치 원문은 결과 문서에 남기지 않는다.

## 12. 다음 단계

P2 결과를 먼저 Runtime Ops/Tech 가정과 [Provisional Baseline v0.1](../provisional-baseline-v0.1.md)의 B-ID에 대조한다.

- capacity/working-set 근거는 P2-A~E를 본다.
- heartbeat/STALE/retry/cancel 최종 tuning 근거는 P2-F를 본다.
- Baseline 값 변경 시 해당 행과 Change log에 결과 evidence를 연결한다.

그 뒤 장시간 workload가 여전히 중요한 미확인 변수라면 별도의 P3 30분~1시간 Runtime E2E plan을 작성한다.

```text
#95 P0/P1
→ P2 Runtime Capacity + Timing/Failure Validation
→ Provisional Baseline 재검토 / Tech·Ops 결정 갱신
→ 필요 시 ADR
→ 필요 시 P3 Long-duration Runtime E2E
```

## References

- [Issue #95 — Elice ML API migration tracker](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/95)
- [Issue #153 — provider usage · pricing · runtime config boundary review](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153)
- [Issue #291 — RT-04 Worker loop · T1/T2](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/291)
- [Issue #292 — RT-05 Lease · heartbeat · fencing · cancellation](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/292)
- [Issue #293 — RT-06 STALE sweep · retry · redelivery](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/293)
- [Provisional Baseline v0.1](../provisional-baseline-v0.1.md)
- [Runtime Ops Spec](../ops-spec.md)
- [Runtime Tech Spec](../runtime-tech-spec.md)
- [AnalysisSource / RemoteCopy Contract](../../architecture/contracts/contract-analysis-source-derived.md)
- [UsageRecord Contract](../../architecture/contracts/contract-usage-record.md)