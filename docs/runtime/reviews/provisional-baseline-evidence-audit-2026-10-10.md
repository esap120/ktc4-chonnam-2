# Provisional Baseline v0.1 Evidence Audit — 2026-10-10

**Status:** Review evidence — Runtime/Ops Baseline 근거 재검토  
**Owner:** common/runtime — 김준영  
**Scope:** `provisional-baseline-v0.1.md`의 초기값 근거 · 후속 측정 계획 · Issue #291에서 드러난 metric semantics  
**SoT:** 이 문서는 review evidence이며 Baseline/Contract/Accepted Decision의 SoT가 아니다.

## 1. 목적

Issue #291 RT-04(b)에서 `runtime.retry.after_case_stopped_count`의 의미를 구현하려는 과정에서 기존 Baseline 문구가 다음 두 해석을 허용하는 문제가 드러났다.

1. attempt ≥ 2의 모든 `NOT_APPLIED`를 집계
2. retry가 Case timeout 뒤 늦게 도착해 `STOPPED_WAITING`으로 버려진 경우만 집계

이에 따라 Baseline v0.1을 만들 때 어떤 근거를 수집했고 무엇을 후속 실험으로 넘겼는지 다시 감사했다. 목적은 당시 값을 사후적으로 정당화하는 것이 아니라 다음을 구분하는 것이다.

- 당시 충분히 근거가 있었던 값
- 의도적으로 Provisional로 둔 값
- 구현 뒤 측정하기로 했지만 실험 설계가 약했던 부분
- 현재 구현에서 새로 드러난 semantics 공백

## 2. 당시 Baseline 작성 원칙

`runtime-ops-workflow.md` §6은 구현에 필요한 값이 TBD로 남아 구현자가 임의로 고르지 않도록 초기값을 정하는 단계다. 최종 운영 threshold를 만드는 단계가 아니다.

Baseline은 각 항목의 evidence를 다음처럼 분리했다.

- `MEASURED` — 대신고 직접 실측
- `DERIVED` — 기존 Contract/Decision 또는 다른 값에서 유도
- `EXTERNAL` — 공식 문서/외부 research
- `CONSERVATIVE_DEFAULT` — 직접 근거가 부족하지만 구현 시작을 위해 둔 안전한 초기값

LOW confidence 값도 구현 시작값은 두고, Runtime Integration · 첫 async Real E2E · EC2/P2에서 metric을 수집해 재조정하는 방식이었다.

RD-04의 retry/backoff/lease/heartbeat/sweep/polling은 Decision Classification에서 `B — Provisional Baseline으로 구현 가능`, 최종값은 `C — P2`로 분류됐다. 별도 외부 research나 pre-implementation performance spike로 숫자를 확정하는 대상이 아니었다.

## 3. 사전 근거로 실제 수집한 것

### 3.1 외부 기술 조사

2026-10-03 Runtime research 4종을 수행했다.

- `research/01-mysql-runtime-persistence-2026-10-03.md`
  - MySQL/InnoDB queue · lock · transaction · connection pool
- `research/02-api-worker-media-persistence-upload-2026-10-03.md`
  - API↔Worker shared media · upload · filesystem publish
- `research/03-runtime-config-secret-cancellation-2026-10-03.md`
  - config/secret · cancellation semantics
- `research/04-deployment-observability-operations-2026-10-03.md`
  - deployment · logging · observability · rotation

외부 숫자를 그대로 대신고 baseline으로 복사하지 않고 구조/failure mode/실험 후보를 좁히는 근거로 사용했다.

### 3.2 Pre-implementation spike

`experiments/pre-implementation-spike-2026-10-03.md`에서 기술 semantics가 불명확한 항목만 작은 spike로 확인했다.

- S1 — MySQL `SKIP LOCKED`의 RR/RC lock footprint
- S2 — cancel/completion/sweep conditional UPDATE race
- S3 — Compose secret/shared volume/same-mount rename

이 spike의 단회 시간·건수는 Baseline 수치로 사용하지 않는다고 문서에 명시했다.

반대로 capacity/성능 성격의 다음 항목은 의도적으로 구현 후 실험으로 넘겼다.

- upload 실제 413 timing · interrupted upload · disk peak
- long-lived DB connection/reconnect
- 실제 Runtime host의 capacity/working set
- Worker scaling

### 3.3 Search / Case 실제 지연 실측

`modules/search/experiments/latency-baseline-2026-09-28.md`는 현재 Elice 제품 경로에서 다음을 실측했다.

- Coarse 20 s / 1 min / 2 min / 5 min
- Fine 총 29회
- Coarse concurrency 1 / 4 / 8
- provider latency와 전체 wall time 분리
- ffmpeg 전처리 시간
- media bytes / token / 실패

주요 관측:

- 5분 Coarse wall p50 47.6 s
- Fine 전체 wall p50 8.5 s · p95 15.5 s · max 33.4 s
- concurrency 1→4→8에서 클립당 wall 약 59→203→341 s, batch 전체 이득은 약 1.3배
- 병목은 provider보다 로컬 ffmpeg/CPU 쪽

이 결과로 Case는 `timeout-fallback.md`에서 잠정적으로 Coarse 150 s · Fine 70 s · case 내부 clip concurrency 1을 사용했다. 단, 로컬 4코어 측정이므로 Runtime 머신에서 다시 재야 확정한다고 명시했다.

### 3.4 Baseline PR의 Owner review

PR #276에서 구현 담당은 Worker/polling/retry/DB 시작값이 구현 가능한 범위임을 확인했다. 다만 heartbeat DB I/O timeout을 합산해 `attempt <= 7 s`, `cancel <= 17 s` 같은 hard bound를 만든 부분은 근거가 부족하다고 지적했고, 해당 보장은 제거됐다.

수정 뒤:

- heartbeat 10 s · lease 60 s · sweep 15 s는 v0.1 시작값 유지
- heartbeat 시도 겹침 금지 · 늦으면 tick skip
- STALE은 실패 횟수가 아니라 마지막 성공 heartbeat 뒤 lease 만료로 판정
- cancel은 hard bound가 아니라 DB 정상 구간 p95 ≤ 20 s 측정 목표

Case Owner도 retry 시간과 Case timeout 관계를 검토했다.

- attempt 2 시작은 최대 약 82 s까지 갈 수 있음
- Coarse 150 s 안에는 대체로 들어감
- Fine 70 s에서는 Case가 기다리기를 멈춘 뒤 attempt 2가 시작/종료될 수 있음
- Case는 timeout 때 진행 중 Job을 강제 취소하지 않고 기다리기만 멈춤
- 늦은 결과를 반영할지는 Case context가 판단

이 관계를 관찰하기 위해 `runtime.retry.after_case_stopped_count`를 둔다는 데 동의했다.

## 4. Baseline 묶음별 재평가

| 묶음 | 당시 주요 근거 | Evidence 성격 | 감사 결과 | 추가 확인 |
| --- | --- | --- | --- | --- |
| B-W* Worker 수/concurrency | Architecture + Search ffmpeg concurrency 실측 | DERIVED + MEASURED | 충분 | 실제 EC2 api+mysql+worker P2 |
| B-Q* polling | 실행시간 대비 2 s queue delay 계산 · 장애 시 5 s 보수값 | CONSERVATIVE/DERIVED | 시작값으로 적절 | 실제 queue wait/claim latency |
| B-L* heartbeat/lease/STALE | 구조 관계 + false STALE 비용 추론 | CONSERVATIVE/DERIVED | **후속 실측 핵심** | heartbeat lag/skipped tick/false STALE |
| B-R* retry/backoff | failure-mode 추론 + Case timeout 비교 | CONSERVATIVE | 시작값으로 적절, empirical 근거 약함 | STALE 원인·복구시간·성공률·추가비용·Case outcome |
| B-D* DB | 공식 research + MySQL spike | EXTERNAL/DERIVED | 강함 | 실제 구현 장애주입으로 추가 강화됨 |
| B-U* upload | 실측 블랙박스 bitrate 1종 + research | MEASURED + CONSERVATIVE, LOW | LOW 표기 적절 | 실제 EC2 upload/disk/abort/413 |
| B-P1 view | 팀/MVP 규모 가정 | CONSERVATIVE, LOW | 가정값으로 적절 | 실제 Web polling/rps |
| B-F* frame | ffmpeg CPU 경합의 간접 근거 | CONSERVATIVE, LOW/MED | B-F2 직접 측정 약함 | frame concurrency 1/2/4 |
| B-C* cleanup | upload/tool timeout에서 유도 | DERIVED/CONSERVATIVE | 대체로 충분 | crash 후 실제 잔여물 |
| B-H* readiness | local DB/EBS metadata는 ms 단위라는 시작 가정 | CONSERVATIVE | 구현 시작값으로 충분 | 실제 Compose/EC2 정상·장애 latency |
| B-X1 cancel | heartbeat 10 s에서 유도한 측정 목표 | DERIVED/CONSERVATIVE | hard bound가 아니라 목표라 적절 | 실제 observe latency |
| B-G1 usage recovery | state machine/event 기반 derivation | DERIVED | 충분 | false STALE 뒤 late usage |
| B-O* logging | Docker 공식 동작 + 보수 local cap | EXTERNAL/CONSERVATIVE | 충분 | 실제 log 발생량/rotation |

## 5. 구현 후 새로 강화된 DB 근거

RT-02(a) PR #319에서는 실제 MySQL 8.4에서 다음 장애를 주입해 검증했다.

- lock wait timeout 1205
- deadlock 1213
- connection kill
- COMMIT 성공 후 응답 유실
- COMMIT 결과 불명 뒤 독립 connection 반영 확인

따라서 B-D*의 transaction/retry semantics는 Baseline 작성 시점보다 현재 근거가 강해졌다. 단, 이 검증은 DB 정확성/복구 semantics에 대한 것이며 heartbeat/lease 숫자의 적절성을 대신 측정하지 않는다.

## 6. 발견된 핵심 공백 1 — `after_case_stopped_count` semantics

Baseline §3.2의 원래 문제의식은 다음이었다.

```text
STALE retry가 늦게 시작/종료
→ Case가 이미 timeout으로 기다리기를 멈춤
→ 늦은 retry 결과가 Case에 반영되지 않을 수 있음
→ 그 현상을 관찰
```

그러나 Baseline §6의 metric 정의는 이를 넓게 다음처럼 적었다.

```text
attempt >= 2가 끝났을 때 case가 반영하지 않은 수
```

RT-04(b)에서 T2 port가 구체화되며 Case 미반영 사유가 다음처럼 분리됐다.

- `STOPPED_WAITING`
- `CANCELLED`
- `SUPERSEDED`

이제 broad `NOT_APPLIED`를 모두 세면 timeout/retry timing 문제와 사용자 취소·orchestration 교체가 한 metric에 섞인다.

### Owner clarification — Issue #291

2026-10-10 Runtime/Ops Owner 확인으로 다음 의미를 사용한다.

```text
runtime.retry.after_case_stopped_count
= count(attempt >= 2 AND T2 outcome == NOT_APPLIED(STOPPED_WAITING))
```

집계하지 않는 경우:

- `APPLIED`
- `ALREADY_APPLIED`
- `NOT_APPLIED(CANCELLED)`
- `NOT_APPLIED(SUPERSEDED)`
- reflector exception / T2 rollback — 이는 redelivery 경로

이는 retry 상한이나 Case timeout 정책을 새로 바꾸는 결정이 아니라 Baseline §3.2의 원래 관찰 목적에 맞춘 metric semantics 명확화다.

### Canonical Baseline 반영 문구

다음 Baseline 편집 시 §6 metric 행을 아래 의미로 정합한다.

```md
| `runtime.retry.after_case_stopped_count` | attempt ≥ 2의 T2 결과가 `NOT_APPLIED(STOPPED_WAITING)`인 수 — retry가 Case 대기 timeout 뒤 도착해 반영되지 않은 경우만 센다. `CANCELLED` · `SUPERSEDED` · `ALREADY_APPLIED`는 제외 | log | 합계 |
```

§3.2의 관찰 설명에는 아래를 명시한다.

```md
`after_case_stopped_count`는 Case의 모든 미반영을 세는 지표가 아니다. attempt ≥ 2가 Case의 대기 종료 뒤 도착해 `STOPPED_WAITING`으로 반영되지 않은 경우만 센다. 사용자 중단(`CANCELLED`)과 새 context/job으로의 교체(`SUPERSEDED`)는 원인이 달라 별도 경로로 관찰한다.
```

## 7. 발견된 핵심 공백 2 — P2 capacity와 RD-04 tuning의 간극

기존 `elice-runtime-capacity-smoke-plan.md`는 다음 질문에는 강하다.

- Worker concurrency=1의 CPU/RAM/disk working set
- ffmpeg와 request construction peak
- cold/warm reuse
- restart/reuse boundary
- concurrency 증가 가능성

반면 Baseline은 B-L*/B-R*의 최종값을 P2에서 조정한다고 적었지만, 기존 P2에는 아래 failure timing matrix가 명시적이지 않았다.

- 정상 Real media 부하의 heartbeat lag/attempt/skipped tick
- CPU credit 저하/ffmpeg 경합 시 heartbeat gap
- Worker kill 뒤 STALE detect → retry timeline
- DB stall과 false STALE
- retry attempt의 Case reflection reason
- cancellation observe latency

그래서 같은 브랜치에서 P2 계획에 `P2-F — Runtime timing / failure validation`을 추가한다.

## 8. P2-F 최소 수집 데이터

### 정상 부하

- heartbeat lag p50/p95/p99/max
- heartbeat attempt p50/p95/p99/max
- skipped tick
- false STALE
- execution duration
- host CPU/RAM/t3 credit

### Worker kill

동일 lineage에 다음을 기록한다.

```text
last_heartbeat_at
worker_killed_at
stale_recorded_at
retry_queued_at
retry_started_at
retry_ended_at
case_reflection_at
```

### DB stall

안전한 fault injection으로 5/15/30/60 s 수준의 heartbeat gap을 만들고 다음을 본다.

- heartbeat attempt/error
- skipped tick
- STALE 여부
- detect latency
- DB 복구 뒤 lease/retry 동작

### T2 outcome

attempt ≥ 2에 대해 최소 다음을 구분한다.

| outcome | after_case_stopped |
| --- | --- |
| APPLIED | no |
| ALREADY_APPLIED | no |
| NOT_APPLIED(STOPPED_WAITING) | yes |
| NOT_APPLIED(CANCELLED) | no |
| NOT_APPLIED(SUPERSEDED) | no |
| exception/rollback | no — redelivery |

### Cancel

- cancel_requested_at
- handler_observed_at
- terminal_at
- DB 정상 구간 observe latency p95

## 9. 이번 감사로 새로 하지 않는 것

- B-L1/B-L2/B-L4/B-R1/B-R2 숫자를 지금 변경하지 않는다.
- Case timeout을 Runtime 문서에서 재정의하지 않는다.
- Worker count/concurrency를 지금 올리지 않는다.
- false STALE이 관측되기 전 grace axis를 새로 만들지 않는다.
- 외부 시스템의 heartbeat/retry 숫자를 대신고 Baseline으로 복사하지 않는다.

현재 단계의 올바른 순서는 다음이다.

```text
RT-04 T2 semantics 명확화
→ RT-05 heartbeat/lease/cancel 구현 + 정확성 test
→ RT-06 STALE/retry/redelivery 구현 + kill/integration test
→ 첫 async Real E2E
→ 실제 baseline 환경 P2-F 측정
→ workflow §10/§11 Baseline 재검토
```

## 10. 결론

초기 Baseline의 전체 프로세스는 의도대로 동작했다.

- 기술 semantics는 research/spike
- 제품 경로 성능은 기존 Search/Case 실측 재사용
- 구현 전 숫자는 Provisional로 명시
- 최종값은 Runtime Integration/Real E2E/P2로 넘김

이번에 발견된 문제는 “Baseline을 실측 없이 임의로 정했다”기보다 다음 두 가지다.

1. T2가 구체화되기 전 작성한 metric 문구가 Case 미반영 reason을 충분히 구분하지 못함
2. P2 capacity plan이 RD-04 최종 튜닝에 필요한 failure timing 측정을 충분히 구체화하지 못함

Issue #291 Owner clarification과 P2-F 보강으로 두 공백을 닫고, 실제 숫자 변경은 측정 결과가 생긴 뒤 evidence와 함께 처리한다.

## References

- [Provisional Baseline v0.1](../provisional-baseline-v0.1.md)
- [Runtime/Ops Workflow](../runtime-ops-workflow.md)
- [Open Decision Register](../open-decision-register.md)
- [Decision Classification](../decision-classification.md)
- [Pre-implementation Spike](../experiments/pre-implementation-spike-2026-10-03.md)
- [P2 Runtime Capacity Smoke Plan](../experiments/elice-runtime-capacity-smoke-plan.md)
- [Search latency baseline](../../modules/search/experiments/latency-baseline-2026-09-28.md)
- [Case timeout fallback](../../modules/case/decisions/timeout-fallback.md)
- [Issue #291](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/291)
- [Issue #292](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/292)
- [Issue #293](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/293)
- [PR #276](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/276)
- [PR #319](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/319)