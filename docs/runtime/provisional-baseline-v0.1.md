# Runtime/Ops Provisional Baseline v0.1

**Status:** Provisional — implementation baseline (workflow §6 산출물). 최종값이 아니다\
**Owner:** common/runtime — 김준영 · 구현 담당 정철원\
**Date:** 2026-10-05 · 기준 `origin/develop` `a6027f6` (PR #265 merge 직후)\
**Workflow step:** [`runtime-ops-workflow.md`](./runtime-ops-workflow.md) §6 → 다음은 §7 Runtime Implementation Plan\
**Closes (Provisional):** [RD-04](./open-decision-register.md#rd-04--execution-timing-provisional-baseline의-축과-제약) 04a · 04c · 04d · 04e · 04b(lease ↔ case job wall 관계 — case 확인 완료, §8.1) · [RD-11](./open-decision-register.md#rd-11--ops-retention--cleanup) 11a(local rotation만) · 11b · Register 「[§5 → §6 Baseline 입력](./open-decision-register.md#5--6-baseline-입력)」 · HTTP API Contract §4가 이 단계로 넘긴 숫자

> 이 문서는 **이미 닫힌 구조를 구현할 수 있게 하는 초기 숫자**만 정한다. Final Contract · Accepted Decision의 의미를 바꾸지 않고, 새 정책을 만들지 않는다. 값은 구현 → Runtime Integration · P2 · Real E2E 측정 → 조정의 출발점이다(workflow §6 · §9 · §11).
>
> **이 문서가 아래 값의 canonical source다.** Tech Spec · Ops Spec · Runbook · Register는 이 문서의 ID(`B-xx`)를 가리키기만 하고 숫자를 복제하지 않는다. 코드의 config 기본값도 이 문서를 따른다.

## 0. 읽는 법

### 0.1 각 값에 붙는 것

| 칸 | 뜻 |
| --- | --- |
| **v0.1** | 구현 시작값. 단위를 함께 쓴다 |
| **Scope / Config** | 어느 process · 층에 적용되는가와 config key **후보**. 접두어 `DAESINGO_RUNTIME_`만 확정이고(Tech Spec §15.2) 나머지 이름은 첫 구현에서 고정한다. 「config 아님」은 코드 구조 · query · Compose로 고정되는 값이다 |
| **근거** | 왜 이 값으로 시작하는가 |
| **Evidence** | `MEASURED`(대신고 실측) · `DERIVED`(기존 Decision · 다른 값에서 계산) · `EXTERNAL`(공식 문서 · 외부 research) · `CONSERVATIVE_DEFAULT`(직접 근거 부족 — 안전한 MVP 초기값) + Confidence `HIGH` / `MEDIUM` / `LOW` |
| **검증 지표** | §6의 metric 이름 |
| **재조정 Trigger** | 이 조건이면 값을 다시 본다 |

LOW라도 값은 정한다. 구현자가 숫자를 고르지 않게 하는 것이 목적이고, 검증은 Trigger가 맡는다.

### 0.2 권한

- 우선순위는 `Final Contract > Accepted Decision > Runtime/Ops SoT > 실험 > 외부 research > 관행`이다. 이 문서는 Runtime/Ops SoT 층이다.
- [JobExecution Contract](../architecture/contracts/contract-job-execution.md) §11은 retry 상한 · backoff · lease · heartbeat · STALE 판정 임계값을 「Runtime 구현 세부 — 구현 담당(정철원)이 정한다」로 둔다. §2.1 ~ §2.5의 값은 그 구현의 **시작값**이며 구현 담당 확인을 받는다(§8). 값을 바꿔도 Contract는 바뀌지 않는다.
- Register RD-04b(lease · STALE threshold와 case job wall의 관계)는 case 확인 대상이다(RD-04 「Issue needed」). §3.2의 결론은 case 확인을 받았다(§8.1).
- 다른 Owner가 소유한 숫자(case timeout · Search in-call retry · recording 도구 timeout · Web polling interval)는 **읽기만** 하고 덮어쓰지 않는다(§4).

### 0.3 이미 닫혀 있어 이 문서가 다시 정하지 않는 것

| 닫힌 것 | SoT |
| --- | --- |
| FastAPI 1 + Worker 1 + MySQL 8.4 DB Queue | Architecture A3 |
| `job_execution` 단일 table = 실행 원장 + queue · READ COMMITTED · `(status, available_at, execution_id)` · `LIMIT 1 FOR UPDATE SKIP LOCKED` · INSERT 없는 짧은 claim · 조건부 전이 | Tech Spec §4.2 · §4.3 (RD-01) |
| PyMySQL + SQLAlchemy Core 2.x · ORM 없음 · Alembic forward-only · startup migration 금지 | Tech Spec §4.4 |
| Runtime 자동 retry = `STALE`만 · `FAILED` terminal · 일시 장애는 Search in-call retry | Tech Spec §6.2 (RD-03) |
| 다음 attempt는 이전 attempt terminal과 같은 transaction에서 `QUEUED` 생성 · Worker는 backoff 동안 sleep하지 않음 | Tech Spec §6.3 (RD-02) |
| RUNNING row lease + 별도 heartbeat thread · 조건부 갱신 0 rows = 소유 상실 → 결과 commit 안 함 | Tech Spec §7.2 |
| Worker startup sweep 1회 + loop 주기 sweep · 별도 reaper 없음 | Tech Spec §7.3 |
| 협력적 중단 · QUEUED 즉시 `CANCELLED` · capability 사이 checkpoint · first commit wins | Tech Spec §12.5 (RD-19) |
| usage begin durable → HTTP → finish durable → Run 확정 → Final 1건 · usage identity UNIQUE | Tech Spec §11.1 (RD-18) |
| 1 request = 1 file · 같은 mount staging → `fsync` → publish → commit · `413` · frame `Cache-Control: private` · `ready`는 외부 provider를 부르지 않음 | HTTP API Contract §5.2 · §5.5 · §5.7 · Ops §4-2 (RD-05 · RD-17) |
| 값은 파일에서만 · startup fail-fast · Runtime key 접두어 `DAESINGO_RUNTIME_` | Tech Spec §15.2 (RD-07) |

---

## 1. 요약

| ID | Parameter | v0.1 | Evidence | Confidence |
| --- | --- | --- | --- | --- |
| B-W1 | Worker process(replica) 수 | 1 | DERIVED | HIGH |
| B-W2 | Worker 당 execution concurrency | 1 (config로 열지 않음) | DERIVED · MEASURED | HIGH |
| B-W3 | claim 1회당 execution 수 | 1 (`LIMIT 1`) | DERIVED | HIGH |
| B-W4 | API(uvicorn) process 수 | 1 | DERIVED | HIGH |
| B-Q1 | idle poll interval (빈 queue) | 2 s | CONSERVATIVE_DEFAULT | MEDIUM |
| B-Q2 | claim 성공 · 실행 종료 직후 다음 claim | 즉시 (0 s) | DERIVED | HIGH |
| B-Q3 | Worker DB 오류 시 대기 | 5 s 고정 · process 유지 | CONSERVATIVE_DEFAULT | MEDIUM |
| B-L1 | heartbeat interval | 10 s · fixed-rate cadence · 동시 시도 최대 1개(이전 시도가 안 끝났으면 그 tick 건너뜀) · 재시도 없음 | CONSERVATIVE_DEFAULT · DERIVED | MEDIUM |
| B-L2 | lease duration | 60 s | CONSERVATIVE_DEFAULT · DERIVED | MEDIUM |
| B-L3 | STALE threshold | = lease 만료 (별도 grace 없음) | DERIVED | HIGH |
| B-L4 | 주기 stale sweep interval | 15 s · handler 실행 시간에 묶이지 않음 | CONSERVATIVE_DEFAULT | MEDIUM |
| B-L5 | startup stale sweep | 함 — 첫 claim 전 1회, 주기 sweep과 같은 조건 | DERIVED | HIGH |
| B-L6 | lease 시각 기준 | DB server `NOW(6)` | CONSERVATIVE_DEFAULT | HIGH |
| B-R1 | 자동 retry 상한 | 1회 (job당 execution 최대 2개) | CONSERVATIVE_DEFAULT | MEDIUM |
| B-R2 | backoff | `5 s × 2^(attempt−2)`, 상한 60 s → v0.1에서는 attempt 2 = 5 s | CONSERVATIVE_DEFAULT | MEDIUM |
| B-R3 | jitter | 없음 | DERIVED | HIGH |
| B-D1 | `innodb_lock_wait_timeout` (api · worker session) | 5 s | DERIVED | MEDIUM |
| B-D2 | Worker pool (heartbeat 제외) | `pool_size=2` · `max_overflow=2` | DERIVED | MEDIUM |
| B-D3 | API pool | `pool_size=5` · `max_overflow=5` | CONSERVATIVE_DEFAULT | MEDIUM |
| B-D4 | `pool_timeout` | 5 s | CONSERVATIVE_DEFAULT | MEDIUM |
| B-D5 | `pool_recycle` | 1800 s | EXTERNAL(제약) · CONSERVATIVE_DEFAULT(값) | MEDIUM |
| B-D6 | `pool_pre_ping` | true | EXTERNAL | HIGH |
| B-D7 | PyMySQL `connect_timeout` · `read_timeout` · `write_timeout` | 5 s · 30 s · 30 s | CONSERVATIVE_DEFAULT | MEDIUM |
| B-D8 | transaction retry | API 없음(COMMIT 전 실패 → `503` · 결과 불명 → `500`) · Worker 최대 3회 · 1 s 간격(heartbeat 제외) | DERIVED | MEDIUM |
| B-D9 | heartbeat 전용 connection | 1개 · I/O 단계별 timeout `connect_timeout=2 s` · `read_timeout=5 s` · `write_timeout=5 s`(시도 전체 상한 아님) · lock wait 2 s | DERIVED | MEDIUM |
| B-U1 | upload body 최대 (`POST /sources`) | 1 GiB (1,073,741,824 bytes) | MEASURED · CONSERVATIVE_DEFAULT | LOW |
| B-U2 | JSON body 최대 (`POST /commands`) | 1 MiB | CONSERVATIVE_DEFAULT | MEDIUM |
| B-U3 | upload 수신 idle timeout | 60 s | CONSERVATIVE_DEFAULT | LOW |
| B-U4 | upload 수신 전체 상한 | 30 min | CONSERVATIVE_DEFAULT | LOW |
| B-U5 | JSON request HTTP timeout | 별도 없음 — DB timeout이 상한 | DERIVED | HIGH |
| B-P1 | `GET /view` 용량 가정 | 탭당 ≤ 0.5 rps · 동시 탭 ≤ 10 → ≤ 5 rps | CONSERVATIVE_DEFAULT | LOW |
| B-F1 | frame `Cache-Control` | `private, max-age=3600` | CONSERVATIVE_DEFAULT | MEDIUM |
| B-F2 | API 동시 frame 생성 | 2 | CONSERVATIVE_DEFAULT | LOW |
| B-C1 | 버려진 upload staging 정리 나이 | 1 h (mtime 기준) | DERIVED | MEDIUM |
| B-C2 | orphan publish 파일 정리 나이 | 24 h | CONSERVATIVE_DEFAULT | LOW |
| B-C3 | temp media 잔여 정리 나이 | 1 h | DERIVED | MEDIUM |
| B-C4 | cleanup scan 주기 | process startup 1회 + 1 h마다 | CONSERVATIVE_DEFAULT | MEDIUM |
| B-H1 | ready DB probe 제한 | 2 s — pool을 쓰지 않는 전용 연결 | CONSERVATIVE_DEFAULT | MEDIUM |
| B-H2 | ready 공유 저장소 probe 제한 | 1 s | CONSERVATIVE_DEFAULT | MEDIUM |
| B-H3 | ready 전체 budget | 3 s | DERIVED | MEDIUM |
| B-X1 | cancel 요청 → handler 관찰 목표 | DB 정상 응답 시 p95 ≤ 20 s — 측정 목표, 상한 보장 아님 | DERIVED · CONSERVATIVE_DEFAULT | MEDIUM |
| B-G1 | usage in-flight 복구 시점 | event 기반 — execution terminal 뒤, sweep 주기에 함께 | DERIVED | MEDIUM |
| B-O1 | container local log rotation | `max-size=20m` · `max-file=5` (container당 ~100 MB) | EXTERNAL · CONSERVATIVE_DEFAULT | MEDIUM |
| B-O2 | application log level | `INFO` | CONSERVATIVE_DEFAULT | HIGH |

NOT_BASELINED 항목은 §5.

---

## 2. Baseline

### 2.1 Worker execution concurrency — A

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-W1 | Worker process(replica) 수 | 1 | Compose service 1개 — config 아님 | Architecture A3 「FastAPI 1 + Worker 1」. 2 이상은 RD-15a(Timing C)의 선택이다 | DERIVED · HIGH | `runtime.queue.wait_ms` · host CPU/RAM | RD-15a 결정(P2-E 이후) |
| B-W2 | Worker 당 execution concurrency | 1 | worker — **config로 열지 않는다** | Ops §17 · P2 plan이 concurrency=1을 먼저 측정한다. case 로컬 실측에서 같은 머신 ffmpeg가 병목이라 동시성 1 · 4 · 8 → 클립당 59 → 203 → 341 s, 전체는 1.3배만 빨라졌다([`timeout-fallback.md`](../modules/case/decisions/timeout-fallback.md)). 값을 knob으로 열면 검증 안 된 병렬 실행이 생긴다 | DERIVED · MEASURED · HIGH | 동상 + `runtime.execution.duration_ms` | RD-15a. 2 이상으로 바꿀 때는 concurrent claim · lease integration test(Tech Spec §16 #1 · #10)를 먼저 통과한다 |
| B-W3 | claim 1회당 execution 수 | 1 | claim query `LIMIT 1` — config 아님 | Tech Spec §4.3에서 닫힌 query 모양 | DERIVED · HIGH | `runtime.db.claim_latency_ms` | claim query 자체가 바뀔 때만(RD-01b 재오픈) |
| B-W4 | API(uvicorn) process 수 | 1 (`--workers 1`) | api command — config 아님 | A3 「FastAPI 1」. pool 계산(§3.3)의 전제 | DERIVED · HIGH | `api.view.latency_ms` · API CPU | API 수평 확장 요구(Ops §18 ALB 조건) |

### 2.2 Worker queue polling — B

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-Q1 | idle poll interval | 2 s | worker · `DAESINGO_RUNTIME_WORKER_IDLE_POLL_SEC` | claim이 빈 결과를 내면 2 s 쉰다. Worker가 놀고 있을 때 queue 시작 지연은 ≤ 2 s + claim 시간이다 — 5분 클립 Coarse p50 47.6 s([latency baseline](../modules/search/experiments/latency-baseline-2026-09-28.md)) 대비 5% 미만. DB 부하는 covering index `LIMIT 1` 0.5 qps로 무시할 수준이다 | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.queue.wait_ms`(attempt 1, Worker idle) · `runtime.db.claim_latency_ms` | Worker idle 상태의 attempt 1 queue wait p95 > 3 s → 줄인다 · claim p95 > 50 ms 또는 DB CPU에서 claim이 보이면 → 늘린다 |
| B-Q2 | claim 성공 · 실행 종료 직후 | 즉시 다음 claim (0 s) | worker — config 아님 | 일이 남아 있을 수 있는 시점에 쉴 이유가 없다. 빈 결과일 때만 B-Q1 | DERIVED · HIGH | 동상 | — |
| B-Q3 | Worker DB 오류(연결 실패 · pool timeout · B-D8 소진) 시 대기 | 5 s 고정, process는 종료하지 않는다 | worker · `DAESINGO_RUNTIME_WORKER_ERROR_BACKOFF_SEC` | DB 일시 장애마다 process를 죽이면 restart 정책(NOT_BASELINED, §5)에 회복을 맡기게 된다. 5 s는 B-Q1보다 길어 장애 중 DB를 두드리지 않고 lease(B-L2)보다 충분히 짧다. config 오류는 이 경로가 아니라 startup fail-fast다(Tech Spec §15.2) | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.db.error_count` | DB 장애가 반복되는데 회복이 늦거나 로그가 과다하면 |

idle polling에 jitter를 두지 않는다 — Worker가 1개다(B-W1). Worker가 2개 이상이 되면 다시 본다.

### 2.3 Lease / heartbeat / STALE — C

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-L1 | heartbeat interval | 10 s — **fixed-rate cadence**(`T0 + k × 10 s` tick) · **동시에 진행 중인 heartbeat 시도는 최대 1개** — tick이 왔을 때 이전 시도가 끝나지 않았으면 새 시도를 겹쳐 시작하지 않고 그 tick을 건너뛴다(밀린 tick을 몰아서 하지 않음). fixed-rate는 「10 s마다 무조건 새 DB 호출을 시작한다」는 뜻이 아니다 · 시도 안에서 B-D8 재시도 없음 — 다음 tick이 재시도다 · 시도 1회 전체의 시간 상한은 두지 않는다(B-D9) | worker heartbeat thread · `DAESINGO_RUNTIME_HEARTBEAT_INTERVAL_SEC`. 스케줄 수단(thread · event loop 등)은 §7 | lease(60 s) 안에 갱신 기회가 여러 번 오도록 lease의 1/6로 둔다 — 일시 실패 · 지연 몇 번으로 lease가 만료되지 않는다. 다만 실패 **횟수**는 STALE 조건이 아니다(아래 「STALE 조건」). 겹침 금지는 느린 DB 앞에 heartbeat가 쌓여 connection · DB 부하를 키우지 않게 하고, 전용 connection 1개(B-D9)로 충분하게 한다. heartbeat 간격은 cancel 관찰 지연(B-X1)의 기본 단위다. 쓰기 ≤ 0.1 qps(PK 1 row) | CONSERVATIVE_DEFAULT · DERIVED · MEDIUM | `runtime.heartbeat.lag_ms` · `runtime.heartbeat.attempt_ms` · `runtime.heartbeat.skipped_tick_count` | heartbeat lag p99 > 20 s 또는 false STALE ≥ 1(§6) |
| B-L2 | lease duration | 60 s | worker · `DAESINGO_RUNTIME_LEASE_DURATION_SEC` | claim과 성공한 heartbeat가 `lease_expires_at = NOW(6) + 60 s`로 갱신한다. heartbeat가 handler와 **별개 thread**라(Tech Spec §7.2) lease는 capability 길이(case · Search · recording이 소유하는 timeout)보다 길 필요가 없고 **heartbeat 공백**보다 길면 된다. 공백 원인 후보 — t3.medium CPU credit 소진 · ffmpeg와의 CPU 경합 · GIL을 잡는 base64/JSON 구성 · DB stall — 을 실측하기 전이라 짧게 잡지 않는다. false STALE는 정상 실행 결과를 통째로 버리므로(Tech Spec §7.2) 느린 복구보다 비싸다 | CONSERVATIVE_DEFAULT · DERIVED · MEDIUM | `runtime.heartbeat.lag_ms` · `runtime.stale.detect_latency_s` · `runtime.stale.false_count` | false STALE ≥ 1 → 늘리거나 원인 제거 · P2에서 heartbeat lag p99 ≤ 10 s가 확인되고 복구 지연이 UX 문제면 → 줄이기 검토 |
| B-L3 | STALE threshold | lease 만료와 같다 — `status=RUNNING ∧ lease_expires_at < NOW(6)` | sweep predicate — **별도 config 아님** | lease와 STALE 판정을 두 축으로 두면 둘의 관계가 또 하나의 불변조건이 된다. RD-04a(어느 축을 config로 둘지)의 답으로 한 축만 둔다 | DERIVED · HIGH | `runtime.stale.count` | 「만료 직후 판정」이 false STALE의 원인으로 확인되면 grace 축 추가 검토 |
| B-L4 | 주기 stale sweep interval | 15 s | worker · `DAESINGO_RUNTIME_STALE_SWEEP_INTERVAL_SEC` | lease 만료 뒤 판정까지 지연 ≤ 15 s. sweep은 index 조건 UPDATE 1회로 가볍다(0.07 qps). **값의 전제:** sweep 주기가 handler 실행 시간에 묶이지 않아야 15 s가 의미를 가진다 — claim 사이에만 돌면 분 단위 실행 동안 sweep이 멈춘다. Tech Spec §7.3의 「Worker loop의 periodic sweep · 별도 reaper process 없음」 안에서 수단(Worker process 안의 별도 주기 thread 등)은 §7이 정한다 | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.stale.detect_latency_s` | detect latency p95 > lease + 20 s |
| B-L5 | startup stale sweep | 한다 — 첫 claim 전 1회, B-L3와 **같은 조건** | worker — config 아님 | Tech Spec §7.3. 「이전 owner의 RUNNING은 즉시 STALE」 같은 지름길을 두지 않는다 — Worker가 2개 이상이 되거나 배포 중 두 Worker가 겹치면 살아 있는 실행을 빼앗는다. 아직 lease가 남은 row는 B-L4가 처리한다 | DERIVED · HIGH | 동상 | Worker ≥ 2 |
| B-L6 | lease 시각 기준 | DB server `NOW(6)` | claim · heartbeat · sweep SQL — config 아님 | lease를 쓰는 쪽과 판정하는 쪽이 같은 시계를 본다. container 시계 차이를 lease 계산에 넣지 않는다 | CONSERVATIVE_DEFAULT · HIGH | — | — |

**STALE 조건 — 마지막 성공 heartbeat 기준.** 성공한 heartbeat(와 claim)는 `lease_expires_at = NOW(6) + 60 s`로 lease를 갱신한다. 마지막으로 성공한 갱신의 DB 시각을 `T`라 하면, `T+60 s`까지 heartbeat 갱신이 한 번도 성공하지 못할 때 lease가 만료되고, sweeper가 그 뒤 다음 sweep(주기대로 돌면 ≤ `T+75 s`)에서 만료된 RUNNING row를 STALE로 처리한다. 그 60 s 동안 실패한 시도의 **횟수는 조건이 아니다** — 빠른 오류면 tick마다 다시 시도하지만, 시도가 timeout · DB stall로 길어지면 건너뛴 tick만큼 시도 수가 줄어든다. 「N회 연속 실패해야 STALE」로 읽지 않는다.

heartbeat가 공용 pool(B-D4 · B-D7)이나 B-D8 재시도에 묶이면 handler · sweep의 DB 사용과 서로 기다려 갱신 공백이 불필요하게 커진다. 그래서 heartbeat는 전용 connection(B-D9)을 쓰고 재시도를 다음 tick에 맡긴다. 이 분리는 공백을 줄이는 장치이며 시도 하나의 시간 상한을 보장하지 않는다.

### 2.4 Runtime automatic retry — D

자동 retry는 `STALE`에만 적용된다(Tech Spec §6.2 — 이 문서가 바꾸지 않는다). 아래 「retry 횟수」는 **attempt 1 뒤에 추가로 만드는 execution 수**다.

```text
attempt 1 RUNNING → STALE
→ (같은 transaction) attempt 2 QUEUED, available_at = NOW(6) + 5 s
→ attempt 2 RUNNING → STALE
→ 상한 도달 — attempt 3을 만들지 않는다 · job은 CaseView에서 FAILED (STALE→FAILED 매핑)
```

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-R1 | 자동 retry 상한 | **1회** — 같은 `job_id`의 execution은 최대 2개(attempt 1 · 2) | worker · `DAESINGO_RUNTIME_STALE_RETRY_MAX` | ① STALE의 흔한 원인(배포 · 재시작)은 한 번의 재시도로 넘는다. ② 같은 입력에서 두 번 연속 Worker가 죽으면 입력이 원인(OOM 등)일 가능성이 커서 더 돌리면 crash loop가 된다. ③ attempt 2 시작까지 이미 최대 ~82 s가 걸려(§3.2) case 대기 안에서 attempt 3이 쓸모 있을 여지가 거의 없다. ④ 재시도마다 provider 비용이 다시 든다. Mock fixture `scenario_infra_failure_001`도 attempt 1 `STALE` → attempt 2가 마지막이다 | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.retry.auto_count` · `runtime.retry.exhausted_count` | 상한 소진이 입력과 무관하게(배포 등) 반복되면 → 2로 · 소진 뒤 같은 입력으로 사용자 재시도도 실패하면 → 원인(OOM 등) 조사 |
| B-R2 | backoff · `available_at` | `available_at = NOW(6) + min(5 s × 2^(attempt−2), 60 s)`. v0.1에서는 attempt 2만 생기므로 **5 s** | worker · `DAESINGO_RUNTIME_STALE_RETRY_BACKOFF_BASE_SEC` · `…_BACKOFF_MAX_SEC` | STALE 판정 시점에 이미 ≥ 60 s가 지났다 — 원인(재시작)은 대개 끝났다. backoff는 crash loop에서 즉시 재claim을 막는 정도면 된다. 곡선을 지금 정해 두면 B-R1을 올릴 때 다시 설계하지 않는다. `NOW(6)`은 terminal 기록 + 다음 attempt INSERT transaction의 DB 시각(Tech Spec §6.3) | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.queue.wait_ms`(attempt ≥ 2) | B-R1 변경 시 곡선 재확인 |
| B-R3 | jitter | 없음 | — | concurrency 1 · Worker 1이라 동시에 RUNNING인 execution이 1개다 → 한 번에 STALE이 되는 것도 사실상 1개라 thundering herd가 없다 | DERIVED · HIGH | `runtime.stale.count`(sweep 1회당) | Worker ≥ 2 또는 concurrency ≥ 2 → full jitter 추가 |

- 중단 요청이 있는 job이 STALE이 되면 상한과 무관하게 다음 attempt를 만들지 않는다(Tech Spec §6.3 · §12.5).
- Search in-call retry(`max_retries` · `retry_base_sec`)는 Search 소유 값이다(`src/daesingo/search/config.py`). 이 문서가 바꾸거나 복제하지 않는다(§4).

### 2.5 MySQL claim / transaction — E

isolation · claim query는 닫혀 있다(§0.3). 여기서는 connection과 대기 상한만 정한다.

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-D1 | `innodb_lock_wait_timeout` | 5 s (server 기본 50 s) | api · worker engine의 session — connection 생성 때 `SET SESSION` · `DAESINGO_RUNTIME_DB_LOCK_WAIT_TIMEOUT_SEC` | claim은 `SKIP LOCKED`라 기다리지 않는다. 나머지 Runtime 쓰기는 PK 1 row 조건부 UPDATE이고 lock을 ms 단위로 쥔다. 기본 50 s면 막힌 쓰기 하나가 lease 60 s를 거의 다 쓴다 → **heartbeat interval(10 s)보다 짧게** 둔다(heartbeat 자신은 더 짧은 B-D9). spike S1은 관찰용으로 2 s를 썼다 | DERIVED · MEDIUM | `runtime.db.lock_wait_timeout_count`(1205) | 1205가 정상 경로에서 1건이라도 나오면 원인(긴 transaction) 조사 — 값을 늘리는 것이 첫 대응이 아니다 |
| B-D2 | Worker pool (heartbeat 제외) | `pool_size=2` · `max_overflow=2` (최대 4) | worker · `DAESINGO_RUNTIME_DB_POOL_SIZE` · `…_DB_MAX_OVERFLOW` | 공용 pool을 쓰는 thread = main/handler 1(claim · terminal · usage tracker는 순차) + sweep 1 = 2. heartbeat는 B-D9 전용 connection이라 이 pool을 기다리지 않는다. overflow는 짧은 겹침(T2 반영 · reconciliation)용 | DERIVED · MEDIUM | `runtime.db.pool_timeout_count` · checked-out 수 | pool timeout ≥ 1 |
| B-D3 | API pool | `pool_size=5` · `max_overflow=5` (최대 10) | api · 같은 key(api env 파일) | B-P1 가정(≤ 5 rps × 수십 ms)에서 동시 사용은 1 미만이다. upload · frame 처리 중 connection을 쥐지 않으므로(§2.6 · §2.8) 긴 요청이 pool을 잡지 않는다. anyio threadpool(기본 40)보다 작으므로 초과 요청은 B-D4 뒤 `503`이다 | CONSERVATIVE_DEFAULT · MEDIUM | 동상 · `api.request.latency_ms` | pool timeout ≥ 1 · view p95 상승 |
| B-D4 | `pool_timeout` | 5 s | api · worker · `…_DB_POOL_TIMEOUT_SEC` | API는 넘으면 `503 http.dependency_unavailable`(HTTP Contract §3.4 — 반영 안 됨, 다시 보내도 됨). Worker는 B-Q3 | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.db.pool_timeout_count` | 동상 |
| B-D5 | `pool_recycle` | 1800 s | api · worker · `…_DB_POOL_RECYCLE_SEC` | MySQL `wait_timeout`(기본 28,800 s)보다 짧아야 한다는 제약은 공식 문서 근거다([Research 01](./research/01-mysql-runtime-persistence-2026-10-03.md) §4.10). 1800 s라는 값 자체는 그 안의 관행적 선택이다. server `wait_timeout`은 바꾸지 않는다. api · worker · mysql이 같은 Docker network라 중간 NAT idle timeout이 없다 | EXTERNAL(제약) · CONSERVATIVE_DEFAULT(값) · MEDIUM | stale connection error 수 | server `wait_timeout`을 바꾸거나 RDS · proxy가 생기면 |
| B-D6 | `pool_pre_ping` | true | api · worker — config 아님 | checkout 시 끊긴 connection을 교체한다. transaction **도중** 끊김은 복구하지 않는다 → B-D8 | EXTERNAL · HIGH | 동상 | — |
| B-D7 | PyMySQL `connect_timeout` · `read_timeout` · `write_timeout` | 5 s · 30 s · 30 s | api · worker engine만. **migration runner는 제외**(긴 DDL) · `…_DB_CONNECT_TIMEOUT_SEC` · `…_DB_READ_TIMEOUT_SEC` · `…_DB_WRITE_TIMEOUT_SEC` | PyMySQL read/write 기본은 무제한이다. 무제한이면 DB stall 하나가 Worker main thread · sweep · API 요청 thread를 영원히 붙잡는다. 30 s는 B-D1(5 s)보다 길어 정상 lock 대기를 끊지 않는다. heartbeat는 이 값이 아니라 B-D9를 쓴다 | CONSERVATIVE_DEFAULT · MEDIUM | `runtime.db.error_count`(timeout 종류별) | 정상 query가 read timeout에 걸리면(긴 query 발견) |
| B-D8 | transaction retry | **API:** 자동 재시도 없음. COMMIT **전** 실패(1205 · 1213 · 연결 끊김 · pool timeout) → rollback → `503`. COMMIT을 보낸 뒤 응답을 못 받은 경우(연결 끊김 · read timeout) → 반영 여부를 모르므로 `500`. **Worker:** 1213 · 1205 · 연결 끊김 → transaction **전체** rollback 후 처음(read)부터 다시, 최대 3회 · 1 s 간격. **heartbeat에는 적용하지 않는다**(B-L1) | api · worker — config 아님 | API 쪽은 HTTP Contract가 이미 「`503` = 반영 안 됨, 다시 보내도 됨 · `500` = 반영 여부를 모름」으로 정했다(§3.4) — 서버가 case command를 다시 돌리지 않는다. Worker 재실행이 안전한 근거: 상태 전이는 현재 status 조건부 UPDATE(spike S2), 다음 attempt INSERT는 `(job_id, attempt)` UNIQUE(Tech Spec §12.1), usage는 usage identity UNIQUE(§11.1), T2 case 반영은 `execution_id` idempotent(§12.2). 1205 뒤에는 transaction을 이어 가지 않는다(Research 01 §5 「lock wait timeout 뒤 transaction 계속 살아 있음」). COMMIT 결과를 모르면 row 상태를 다시 읽은 뒤 판단한다 | DERIVED · MEDIUM | `runtime.db.tx_retry_count` · `…_exhausted_count` | 소진이 반복되면 |
| B-D9 | heartbeat 전용 connection | Worker당 1개(pool 공유 안 함) · PyMySQL **I/O 단계별** timeout `connect_timeout=2 s` · `read_timeout=5 s` · `write_timeout=5 s` · session `innodb_lock_wait_timeout=2 s` | worker heartbeat thread · `…_HEARTBEAT_DB_CONNECT_TIMEOUT_SEC` · `…_HEARTBEAT_DB_READ_TIMEOUT_SEC` · `…_HEARTBEAT_DB_WRITE_TIMEOUT_SEC` | 공용 pool(B-D4 · B-D7 30 s)과 B-D8 재시도에 heartbeat가 묶이지 않게 분리한다(§2.3 아래). PyMySQL은 `connect_timeout`을 연결 수립에, `write_timeout` · `read_timeout`을 각 socket 쓰기 · 읽기 대기에 따로 적용한다. 한 시도에는 (끊긴 뒤라면) 재연결과 statement · COMMIT 왕복의 쓰기 · 읽기가 차례로 들어가므로 이 값들은 **시도 전체의 wall-clock 상한이 아니고, 서로 더해 상한을 만들지도 않는다**. 시도 전체 deadline은 v0.1에 두지 않는다 — 시도가 길어지면 B-L1대로 tick을 건너뛰고 안전성은 lease(B-L2)가 맡는다. 단계별 timeout은 무한 대기만 막는다. lock 대기(2 s)를 read timeout(5 s)보다 짧게 둬 lock 경합이면 1205가 read timeout보다 먼저 온다. 끊기면 다음 시도에서 다시 연결한다 | DERIVED · MEDIUM | `runtime.heartbeat.attempt_ms` · `…skipped_tick_count` | DB 정상 구간에서 heartbeat가 I/O timeout에 걸림 · 건너뛴 tick이 반복됨 |

**Worker 재시도 소진 뒤.** claim · sweep은 그 주기를 건너뛰고(heartbeat는 애초에 재시도 없이 다음 tick에 다시 시도한다) 다음 주기에 다시 한다. terminal 기록은 **lease를 쥐고 있는 동안** B-Q3 간격(5 s)으로 계속 시도한다 — heartbeat가 0 rows(소유 상실)를 보면 멈추고 결과를 commit하지 않는다(Tech Spec §7.2). 새 「결과 폐기」 규칙을 만들지 않고 기존 fencing에 맡긴다. T2(case 반영) 실패는 Tech Spec §12.2의 재전달로 넘어간다 — 재전달 scan은 startup + B-L4 주기다(§9).

### 2.6 API request / upload — F

`1 request = 1 file`과 응답 전 publish · commit 순서는 바꾸지 않는다(HTTP API Contract §5.2).

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-U1 | upload body 최대 | **1 GiB** (1,073,741,824 bytes, multipart overhead 포함 전체 raw body) | api `POST /cases/{id}/sources` — Starlette ≥ 1.6 `RequestBodyLimitMiddleware` · `DAESINGO_RUNTIME_API_UPLOAD_MAX_BYTES` | 실측 기종은 AVI 약 60 s · 113.25 MB/파일(약 15 Mbps, 6.79 GB/h — [recording memo](../modules/recording/research/architecture-input-memo.md))이다. 1 GiB는 그 파일의 ~9배, 같은 bitrate로 ~9분 · 25 Mbps(4K급)로 ~5분을 덮는다. 정상 파일을 `413`으로 거부하는 쪽이 UX 손해가 커서 넉넉히 둔다. disk 영향은 upload 1건당 일시 ~2 GiB(§3.4 — 50 GiB의 4%). 한도는 **서버 안전 상한**이며 upload 전략(Architecture A6)이 더 작은 제품 한도를 두면 그쪽이 먼저다 | MEASURED · CONSERVATIVE_DEFAULT · LOW | `api.upload.bytes` 분포 · `api.upload.rejected_413_count` | 정상 사용자 파일이 `413` ≥ 1 · disk pressure(§7) · A6 결정 |
| B-U2 | JSON body 최대 | 1 MiB | api `POST /cases/{id}/commands`만 · `…_API_JSON_MAX_BYTES` | case-command 요청은 수 KB다. Contract가 `413`을 두는 endpoint는 sources · commands뿐이다(HTTP Contract §3.4). `POST /cases`는 body를 읽지 않아 한도를 걸지 않는다(그 Errors는 `503` · `500`뿐, §5.1). 비정상 body가 메모리를 쓰지 않게 한다 | CONSERVATIVE_DEFAULT · MEDIUM | `api.request.rejected_413_count` | 정상 command가 `413` |
| B-U3 | upload 수신 idle timeout | 60 s — body byte가 60 s 동안 오지 않으면 수신 중단 | api — ASGI receive 경계 · `…_API_UPLOAD_IDLE_TIMEOUT_SEC` | Uvicorn에는 request body 수신 timeout이 없다(Research 02 §4.7). 멈춘 연결이 spool · staging을 무기한 쥐지 않게 한다 | CONSERVATIVE_DEFAULT · LOW | `api.upload.aborted_count{reason=idle}` | 정상 사용자 upload가 idle abort |
| B-U4 | upload 수신 전체 상한 | 30 min | api — 같은 경계 · `…_API_UPLOAD_MAX_DURATION_SEC` | 진행 중 upload의 최대 수명을 정해야 staging 정리 나이(B-C1)가 진행 중 파일을 지우지 않는다고 말할 수 있다. 1 GiB를 30분에 받으려면 ≥ 4.8 Mbps가 필요하다 — 실측 파일(113 MB)은 그 속도로 ~3분 | CONSERVATIVE_DEFAULT · LOW | `api.upload.duration_ms` · `…aborted_count{reason=duration}` | 정상 upload가 duration abort · B-U1 변경 |
| B-U5 | JSON request HTTP timeout | 별도 timeout 없음 | — | sync route는 thread를 강제로 끊을 수 없다. 대신 요청이 쓰는 DB 대기가 B-D4(pool 5 s) · B-D7(connect 5 s · statement 응답 30 s) 안에서 B-D1(lock 5 s)로 묶인다 — 정상 경로는 lock 대기 5 s, 최악은 statement당 ~40 s(§3.3). 외부 provider는 request 안에서 부르지 않는다(Tech Spec §13) | DERIVED · HIGH | `api.request.latency_ms` | p99 > 5 s |

- B-U3 · B-U4로 수신을 중단하면 **새 status를 만들지 않고 연결을 닫는다.** client는 HTTP Contract §5.2 「응답을 받지 못했을 때 — `file_count`로 확인」 경로를 탄다. 공유 mount에 남은 staging은 B-C1이 정리한다. Starlette spool은 이름 없는 임시 파일이라 request 종료와 함께 사라지고 B-C1 대상이 아니다(Research 02 §4.5 · §5).
- upload bytes를 받는 동안 DB connection · transaction을 쥐지 않는다 — case 확인 · 등록 commit은 각각 짧은 transaction이다(Tech Spec §4.3 짧은 transaction 원칙).
- Starlette spool(`/tmp`)을 `tmpfs`에 두지 않는다 — 1 GiB 한도에서 spool이 RAM(usable ~3.7 GiB)을 쓰게 된다(Research 02 §4.5).

### 2.7 HTTP polling 가정 — G

Web polling interval과 재시도 간격은 **Web 구현값**이다(HTTP API Contract §4 · §5.4). 이 절은 Web에 의무를 주지 않고 Runtime 용량 계산의 **가정**만 적는다.

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-P1 | `GET /view` 용량 가정 | 열린 case 탭당 ≤ 0.5 rps(2 s 이상 간격) · 동시 탭 ≤ 10 → API 합계 ≤ 5 rps | 가정 — config 아님 | MVP 사용 규모(팀 · 시연). Runtime 상태가 바뀌는 단위(idle poll 2 s · heartbeat 10 s · 실행 수십 초)보다 촘촘한 polling은 새 정보를 거의 주지 않는다. `running_jobs=[]`이면 polling을 멈춰도 된다는 의미는 그대로다 | CONSERVATIVE_DEFAULT · LOW | `api.view.request_rate` · `api.view.latency_ms` | 합계 > 5 rps 지속 · view p95 > 300 ms · Web이 2 s 미만 interval을 택함(→ 용량 재계산, Web 값을 바꾸라는 뜻이 아니다) |

### 2.8 Frame serving — H

FrameRef를 bytes로 저장할지 원본 + 위치로 다시 만들지는 recording 구현 선택이다(Ops §4-2 · #246 S-4). 아래 값은 그 선택과 무관하게 api가 정하는 것만 다룬다.

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-F1 | frame 응답 `Cache-Control` | `private, max-age=3600` | api `GET /frames/{frame_ref}` · `DAESINGO_RUNTIME_API_FRAME_MAX_AGE_SEC` | 같은 `frame_ref`는 다른 frame을 가리키지 않으므로(SourceAsset Contract §5.2) 재사용은 안전하다. 1 h는 한 사용 세션 동안 polling으로 다시 그리는 썸네일 요청을 없앤다. 더 길게 두지 않는 이유 — retention · purge(RD-10)가 아직 열려 있어, 서버에서 지운 뒤 브라우저에 남는 시간을 짧게 둔다 | CONSERVATIVE_DEFAULT · MEDIUM | `api.frame.request_rate` · `api.frame.latency_ms` | RD-10 closure · frame 요청 반복이 부하로 보이면 |
| B-F2 | api 동시 frame 생성 | 2 — 초과 요청은 기다린다(새 error 없음, 대기 상한은 두지 않고 `api.frame.wait_ms`로 본다) | api · `DAESINGO_RUNTIME_API_FRAME_CONCURRENCY` | frame이 재생성 방식이면 요청마다 ffmpeg가 api process에서 돈다. 2 vCPU에서 Worker ffmpeg와 경합한다(B-W2 근거와 같은 실측). 저장 방식이면 이 제한은 영향이 거의 없다. frame 생성 동안 DB connection을 쥐지 않는다(소유 확인 → 반환 → `read_frame`) | CONSERVATIVE_DEFAULT · LOW | `api.frame.latency_ms` · `api.frame.wait_ms` · host CPU | 썸네일 목록 로딩 p95 > 10 s · CPU 경합이 Worker 실행을 늦춤 |

신고용 asset 다운로드(`GET /assets/…`)는 `Cache-Control: private, no-store`로 Contract가 고정했다. 이 문서에 추가 숫자는 없다.

### 2.9 운영 temp · orphan cleanup — I

**Product retention(사용자 원본 · managed asset · ReportPackage · UsageRecord 보관 기간)은 정하지 않는다** — RD-10(Timing D)이다. 여기서는 어떤 ref에도 연결되지 않은 운영 잔여물만 다룬다.

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-C1 | 버려진 upload staging 정리 나이 | 1 h — 마지막 수정(mtime) 기준 | 공유 mount의 staging 경계(Ops §4-2) · `DAESINGO_RUNTIME_CLEANUP_STAGING_AGE_SEC` | 진행 중 upload는 최대 30분(B-U4)이고 수신 중에는 mtime이 계속 바뀐다. 1 h = B-U4의 2배라 진행 중 파일을 지우지 않는다(Register §5 → §6 입력 제약) | DERIVED · MEDIUM | `storage.staging.count` · `…bytes` · `…oldest_age_s` | B-U4 변경 · staging 누적 |
| B-C2 | orphan publish 파일 정리 나이 | 24 h | 공유 mount의 source 경계 — recording 등록이 **없는** 파일만 · `…_CLEANUP_ORPHAN_AGE_SEC` | publish → 등록 commit 사이는 초 단위다(Ops §4-2 「파일 먼저, row 나중」). 24 h는 그 창을 크게 넘고, 운영자가 원인을 볼 시간을 준다. 지우기 전 판정은 recording 등록 조회로 한다(§9 — 판정 수단은 §7). 로그에는 건수 · bytes만 남기고 경로를 남기지 않는다(Ops §7) | CONSERVATIVE_DEFAULT · LOW | `storage.orphan.count` · `…bytes` | orphan이 정상 운영에서 하루 1건 이상 생김(publish 경로 버그 의심) · disk pressure |
| B-C3 | temp media 잔여 정리 나이 | 1 h | api · worker 각자의 temp root — composition root가 recording에 `temp_root`를 주입(`recording/materialization.py` · `incidents.py`) · `…_CLEANUP_TEMP_AGE_SEC` | 현재 temp는 ffmpeg encode 동안의 `TemporaryDirectory`라 정상 종료면 남지 않는다. 남는 것은 강제 종료 잔여뿐이다(RD-11b). recording 도구 timeout(recording 코드 소유 — 현재 모두 분 단위 이하)보다 1 h가 충분히 커서 살아 있는 작업의 temp가 아니다. service별 temp root를 나눠 한 service가 다른 service의 temp를 지우지 않게 한다 | DERIVED · MEDIUM | `storage.temp.count` · `…bytes` | recording 도구 timeout 변경 · temp 누적 |
| B-C4 | cleanup scan 주기 | process startup 1회 + 1 h마다 | api · worker · `…_CLEANUP_INTERVAL_SEC` | 잔여물은 crash · 실패 경로에서만 생겨 증가 속도가 느리다. startup scan이 crash 직후 잔여물을 회수한다. 실제 삭제는 위 나이 조건을 넘은 것만이다 — startup이라도 나이 조건을 건너뛰지 않는다 | CONSERVATIVE_DEFAULT · MEDIUM | 위 지표 | disk pressure |

### 2.10 Health / readiness — J

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-H1 | ready DB probe 제한 | 2 s — **공용 pool을 쓰지 않는** 전용 연결(`connect_timeout=1 s` · `read_timeout=1 s`)로 `SELECT 1` | api `/health/ready` · `DAESINGO_RUNTIME_READY_DB_TIMEOUT_SEC` | 같은 host의 MySQL `SELECT 1`은 ms 단위다. 공용 pool로 재면 B-D4(5 s) · B-D7(30 s)에 묶여 2 s를 지킬 수 없다 — 그래서 probe 연결의 timeout 자체를 2 s 안(connect 1 + 응답 1)으로 둔다 | CONSERVATIVE_DEFAULT · MEDIUM | `api.ready.duration_ms` · `api.ready.unavailable_count` | 정상인데 ready `503` |
| B-H2 | ready 공유 저장소 probe 제한 | 1 s — mount 경로 존재 · 디렉터리 · 쓰기 가능(`access(W_OK)` · `statvfs`), **파일을 쓰지 않는다** · 1 s 안에 끝나지 않으면 실패로 본다(호출을 별도 thread에서 돌리고 1 s만 기다림) | api · `…_READY_STORAGE_TIMEOUT_SEC` | local EBS의 metadata 호출은 ms 단위다. 매 호출 파일 쓰기는 I/O만 늘린다. 읽기 전용 remount는 `W_OK`로 잡힌다 | CONSERVATIVE_DEFAULT · MEDIUM | 동상 | 동상 |
| B-H3 | ready 전체 budget | 3 s — 넘으면 `503 {status: unavailable}` | api · 별도 key 없음(B-H1 + B-H2) | 두 probe를 순서대로 돌린 합이다. ready를 부르는 쪽(Compose healthcheck · 배포 smoke — §5)은 timeout을 **3 s보다 길게** 잡아야 한다 | DERIVED · MEDIUM | 동상 | 동상 |

- `/health/live`는 dependency를 보지 않으므로 숫자가 없다.
- ready는 외부 provider · Worker 생존 · queue 적체를 보지 않는다(HTTP Contract §5.7). Worker 상태는 heartbeat lag(§6)로 본다.

### 2.11 Cancellation observation — L

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-X1 | RUNNING 중단 요청 → handler가 관찰하기까지 목표 | **Provisional 측정 목표** — DB가 정상 응답하는 동안 `runtime.cancel.observe_latency_ms` p95 ≤ 20 s. 상한 보장이 아니다 | B-L1에서 유도 — 별도 config 아님 | 중단이 전달되는지는 구조가 보장한다 — heartbeat가 중단 표식을 읽으면 handler에 알린다(Tech Spec §7.2 · §12.5). 얼마나 빨리 전달되는지는 측정 · 조정 대상이다. DB가 정상이면 heartbeat 시도는 ms 단위라 관찰은 대개 다음 tick까지(≤ 10 s)다. 20 s는 tick 하나를 놓치거나 실패해도(t3 CPU 경합 등) 목표 안에 들도록 둔 여유다. heartbeat 시도가 실패 · timeout · DB stall로 길어지거나 tick을 건너뛰면 그만큼 더 늦어질 수 있고, 그 경우의 시간 상한은 없다 | DERIVED · CONSERVATIVE_DEFAULT · MEDIUM | `runtime.cancel.observe_latency_ms` · `runtime.cancel.terminal_latency_ms` | DB 정상 구간 observe p95 > 20 s |

- 실제로 멈추는 시각은 **관찰 + 지금 실행 중인 capability가 반환할 때까지**다. capability 길이는 각 모듈 · case가 소유한다(§4) — 이 문서는 terminal latency 목표를 만들지 않고 측정만 한다.
- QUEUED 중단은 중단 command와 같은 transaction에서 `CANCELLED`라 지연이 없다(Tech Spec §12.5).
- 화면 즉시성은 case가 준다(`running_jobs`에서 바로 뺌). 이 값은 Runtime 실행 정지 · 추가 비용에만 영향이 있다.

### 2.12 Usage in-flight recovery — M

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-G1 | in-flight 복구 시점 | **event 기반** — in-flight가 속한 execution이 terminal(STALE 포함)이면 복구 대상이다. scan은 Worker startup + B-L4 sweep 주기에 함께 돈다 | worker — 별도 config 없음 | Tech Spec §11.1은 복구를 「stale recovery · reconciliation」에 묶는다. in-flight를 만든 Worker가 살아 있는 동안에는 그 execution이 RUNNING이고 lease로 소유가 보인다 — 「몇 분 지나면 버려진 것」이라는 **시간 판정이 필요 없다** | DERIVED · MEDIUM | `runtime.usage.recovered_count` · `runtime.usage.inflight_count` · `…inflight_oldest_age_s` | terminal execution에 묶인 in-flight가 한 sweep 주기 넘게 남음 |

「abandoned in-flight 판단 시간」은 NOT_BASELINED다(§5) — 의미가 Tech Spec · Contract에 없고 event 기반 판정으로 충분하다.

**알려진 한계 — false STALE.** 원래 Worker가 살아 있는데 STALE로 판정되면(§6 `runtime.stale.false_count`), 그 Worker의 provider HTTP가 아직 진행 중인 in-flight를 복구 경로가 먼저 finalize할 수 있다. usage identity UNIQUE 때문에 Final row가 두 개 생기지는 않지만, 늦게 도착한 관측값(token · cost)이 Final에 반영되지 못할 수 있다. 이 경우를 다루는 방식은 §7 구현에서 정하고(새 정책 아님 — Tech Spec §11.1 「관측된 값은 버리지 않는다」를 지키는 구현), false STALE 1건이 곧 재조정 trigger다(§7 표).

### 2.13 Logging — N

| ID | Parameter | v0.1 | Scope / Config | 근거 | Evidence | 검증 지표 | 재조정 Trigger |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-O1 | container local log rotation | container당 `max-size=20m` · `max-file=5` (~100 MB) | Compose `logging:` — app config 아님 | Docker 기본 `json-file`은 rotation이 없어 50 GiB disk에 무제한 증가 경로를 남긴다([Research 04](./research/04-deployment-observability-operations-2026-10-03.md) B-4). 값은 Docker `local` driver 기본(`20m × 5`)과 같다. api · worker · mysql 합계 ~300 MB(disk의 < 1%). **어떤 driver를 고르든(RD-13a) host 쪽 local file 상한으로 이 값을 쓴다** — `json-file`이면 명시하고, `local` · remote driver의 dual logging cache면 같은 값으로 맞춘다 | EXTERNAL · CONSERVATIVE_DEFAULT · MEDIUM | host disk 중 log 크기 · rotate 빈도 | 장애 분석에 필요한 log가 rotate로 사라짐 · RD-13a 결정 |
| B-O2 | application log level | `INFO` (P2 · 배포 기본) | api · worker · `DAESINGO_RUNTIME_LOG_LEVEL` | 실제 사용자 데이터가 들어가는 단계에서 `DEBUG`는 payload · 경로를 남길 위험이 있다(Ops §7). 로컬 개발은 바꿔도 된다 | CONSERVATIVE_DEFAULT · HIGH | — | pre-deploy review(M9) |

log transport와 CloudWatch retention은 정하지 않는다 — §5.

---

## 3. 결합 검증

단독으로 그럴듯한 값이 조합에서 모순이 없는지 본다. 아래 계산은 모두 위 값으로 다시 계산할 수 있다.

### 3.1 heartbeat · lease · STALE · sweep

```text
heartbeat cadence 10 s  <  lease 60 s     → lease 안에 갱신 기회가 여러 번 온다 (필수 불변조건, startup 검증)
stale sweep 15 s  <  lease 60 s           → 만료 뒤 판정 지연 ≤ 15 s (설계 관계 — 정확성 조건은 아님)
heartbeat 동시 시도 ≤ 1                    → 이전 시도가 안 끝난 tick은 건너뜀 · 겹침 없음 (B-L1)
STALE threshold = lease 만료              → 같은 축 (B-L3)
lease 갱신 · 판정 시각 = DB server NOW(6)   → container 시계 차이 무관 (B-L6)
heartbeat lock wait 2 s  <  heartbeat read_timeout 5 s → lock 경합이면 1205가 read timeout보다 먼저 온다 (단계별 timeout 사이 관계)
STALE 가능 조건 = 마지막 성공 heartbeat 갱신(T) 뒤 T+60 s까지 성공한 갱신 없음
Worker 생존 시 판정 지연 ≤ lease 60 s + sweep 15 s = 75 s (T 기준, sweep이 주기대로 돌 때)
```

- **heartbeat 시도 1회의 시간 상한은 없다.** B-D9의 connect · read · write timeout은 I/O 단계별 상한이라 더해서 시도 전체 상한을 만들지 않는다. 그래서 「시도가 다음 tick 전에 끝난다」나 「N회 연속 실패해야 STALE」을 셈의 전제로 두지 않는다. 판정은 실패 횟수가 아니라 마지막 성공 갱신 뒤 지난 시간(lease)으로만 한다(§2.3 아래).
- **heartbeat와 sweep의 대소는 필수 불변조건이 아니다.** lease 갱신은 heartbeat가, 만료 뒤 판정은 sweep이 하고 둘은 서로 기다리지 않는다. sweep 주기는 판정 지연만 정한다. v0.1에서 sweep(15 s) > heartbeat(10 s)인 것은 각자 정한 값의 결과다. sweep < lease도 판정 지연을 lease 안쪽으로 두려는 설계 관계로 지키지만, 어겨도 정확성은 깨지지 않으므로 startup 검증은 `sweep > 0`만 한다(§9).
- Worker가 1개라 **Worker 자신이 죽으면 sweep할 주체도 없다.** 복구는 Worker가 다시 떠야 시작된다: `재시작 시각 + max(0, lease 남은 시간) + ≤ 15 s`. 재시작 정책은 RD-13c(§5)다.
- 정상 실행이 STALE로 바뀌는 경로는 「마지막 성공 heartbeat 뒤 lease 60 s 동안 heartbeat 갱신이 한 번도 성공하지 못함」뿐이다. capability 길이와는 무관하다(heartbeat가 별개 thread). 이것이 lease를 다른 Owner의 capability timeout에 맞추지 않는 이유다(§4).

### 3.2 STALE retry · case 대기

```text
Worker 사망(Worker는 곧 재시작된다고 가정)
→ 판정 ≤ 75 s → backoff 5 s → idle poll ≤ 2 s
→ attempt 2 시작 ≤ ~82 s (마지막 heartbeat 기준)
```

- case 대기 잠정값(Coarse 클립당 · Fine 후보당 — 수치는 case 소유 [`timeout-fallback.md`](../modules/case/decisions/timeout-fallback.md))은 이 ~82 s와 같은 자릿수다. attempt 2는 case가 기다리기를 멈춘 뒤 끝날 수 있고, 그러면 case가 결과를 반영하지 않을 수 있다(Tech Spec §12.2). Runtime은 이것을 판단하지 않는다. **이 관계(RD-04b)는 case 확인을 받았다(§8.1).**
- 그래서 B-R1을 1로 둔다 — STALE 1건당 추가 비용은 execution 최대 1개다. case timeout 수치나 「timeout 때 중단 요청을 보낼지」는 case 정책이고 이 문서가 바꾸지 않는다(관찰만 §6 `runtime.retry.after_case_stopped_count`).
- 모순 없음: backoff(5 s)는 판정 지연(≥ 60 s)보다 작고, 상한 1이라 곡선 상한(60 s)에 닿지 않는다.

### 3.3 DB

```text
connection 최대 = api 10 + ready probe 1 + worker 4 + heartbeat 1 + migration 1 + 운영자 2 ≈ 19  ≪  MySQL max_connections 기본 151 (바꾸지 않음)
Runtime 고정 부하 ≈ claim 0.5 qps + heartbeat 0.1 qps + sweep 0.07 qps  < 1 qps
API 가정 부하   ≈ view ≤ 5 rps (+ command · upload 등록은 짧은 transaction)
API statement 하나의 DB 대기:
  정상 경로(lock 경합)  ≤ lock wait 5 s
  최악(장애)            ≤ pool 5 s + connect 5 s + 응답 30 s ≈ 40 s
  → COMMIT 전 실패는 503, COMMIT 결과 불명은 500 (B-D8)
```

- concurrency 1 · Worker 1에서 claim 경합은 없다. 경합 관측은 RD-15a 전에 integration test로 한다.

### 3.4 upload · disk · cleanup · timeout

```text
upload 1건 일시 disk ≈ Starlette spool(≤ 1 GiB, container /tmp) + staging→final(≤ 1 GiB) ≈ ≤ 2 GiB
Web 기본 흐름은 파일을 한 번에 하나씩 보낸다(HTTP Contract §5.2) → 보통 동시 1건
staging 정리 1 h  ≥  2 × upload 상한 30 min
idle 60 s  <  전체 30 min
1 GiB / 30 min ⇒ ≥ 4.8 Mbps 필요
```

- 한도가 지키는 것은 「파일 1개」의 상한이다. 성공한 upload가 쌓이는 양(~6.79 GB/영상 시간)은 working set · retention(RD-15c · RD-10)이고 한도로 막지 않는다.
- 동시 upload가 여럿이면 일시 disk가 건수만큼 늘어난다(5건 ≈ 10 GiB). 동시 upload 제한 · disk free guard는 운영 threshold라 정하지 않는다(§5) — disk 지표(§6)로 관찰한다.

### 3.5 Web · API · DB read

```text
view ≤ 5 rps × (case load + JobExecution read port 수 row) → DB read 수십 qps 이하
frame: max-age 1 h → 같은 썸네일은 세션 동안 1회 · 생성은 동시 2
```

모순 없음. B-P1을 넘는 사용은 §7 trigger다.

### 3.6 cancel

```text
전달 = heartbeat가 중단 표식을 읽으면 handler에 알린다 (정확성 — 구조가 보장, Tech Spec §7.2 · §12.5)
관찰 지연 (DB 정상) ≈ 다음 heartbeat tick까지 ≤ 10 s + 시도 소요(보통 ms)
목표 B-X1        = DB 정상 구간 observe p95 ≤ 20 s (측정 목표 — 상한 보장 아님)
시도 실패 · timeout · DB stall · 건너뛴 tick → 그만큼 늦어진다 (시간 상한 없음)
정지 = 관찰 + 실행 중 capability 반환 (상한은 case가 넘기는 `max_latency_sec` 등 다른 Owner 값)
```

- 관찰이 늦어져도 정확성은 바뀌지 않는다 — 중단 요청된 job은 STALE이 되어도 다음 attempt를 만들지 않고(§2.4), 경합은 first commit wins다(Tech Spec §12.5). 지연은 Runtime 실행 정지 · 추가 비용에만 영향이 있다(§2.11).

---

## 4. 다른 Owner 값과의 접합 — 읽기만 한다

수치는 각 SoT에만 있다. 이 표는 위치와 접합 조건만 적는다(Tech Spec §7.4 「Runtime 문서에 그 값을 복제하지 않는다」).

| 값 | Owner · SoT | Runtime 쪽 접합 조건 | 충돌 |
| --- | --- | --- | --- |
| Coarse 클립당 · Fine 후보당 timeout | case — [`timeout-fallback.md`](../modules/case/decisions/timeout-fallback.md)(잠정) | lease는 capability 길이와 무관(별개 heartbeat thread, §3.1). retry 시간 비교에만 쓴다(§3.2 — RD-04b case 확인) | 없음 |
| Search run deadline · in-call retry · per-attempt timeout | search — `src/daesingo/search/config.py` · `provider.py` · `execution.py` | Runtime 자동 retry와 곱해지지 않는다 — Search in-call retry로 못 넘기면 `FAILED` terminal(Tech Spec §6.2) | 없음 |
| recording ffmpeg · ffprobe timeout | recording — `recording/materialization.py` · `incidents.py` · `frames.py` · `probe.py` | B-C3 정리 나이(1 h)가 이 값들보다 충분히 크다(현재 모두 분 단위 이하). lease와 무관(§3.1) | 없음 |
| Web polling interval · 재시도 간격 | web — HTTP Contract §4 | B-P1은 가정일 뿐 의무가 아니다 | 없음 |
| FrameRef 저장 방식 · 서버 쪽 frame cache | recording — Ops §4-2 · #246 S-4 | B-F1 · B-F2는 방식과 무관 | 없음 |

**결과: 다른 Owner의 값을 바꾸거나 새 의무를 만든 항목은 없다.** B-C3의 `temp_root` 주입은 recording이 이미 가진 생성자 인자를 composition root가 채우는 것이다.

---

## 5. NOT_BASELINED

| 항목 | 이유 | Owner / Decision | 언제 정하나 |
| --- | --- | --- | --- |
| Worker concurrency ≥ 2 · Worker ≥ 2 | C — 실측 뒤 선택 | runtime · RD-15a | M8 (P2-E 뒤) |
| container restart policy · health 기반 restart/alert | A — 열린 B Decision 정책 자체 | runtime · RD-13c · Ops §9 | M7 Provisional · M8 최종 |
| Compose healthcheck interval/timeout · `stop_grace_period` · Worker graceful shutdown 동작 | A — Compose 모양이 열린 Decision | runtime · RD-12a · RD-12h | M4 (Compose slice). 조건만: ready 호출 timeout > B-H3 |
| log transport(driver · CloudWatch Agent) · CloudWatch Log Group retention | A — 열린 Decision · 비용 정책 | runtime · RD-13a · RD-11a | M7 (P2 직전, Research 04 R2) |
| disk free-space guard · 동시 upload 수 제한 · capacity threshold | A/C — 운영 threshold는 실측 뒤(workflow §6 「임의 threshold 금지」) | runtime · RD-15c | M8 |
| Product retention — 원본 · managed asset · ReportPackage · UsageRecord · `purge_case` 범위 | A — Timing D Product 정책 | recording · RD-10 | M9 전 |
| 서버 쪽 frame cache 수명 · 보관 수 · FrameRef bytes vs 재생성 | B — 다른 Owner 구현 | recording · #246 S-4 · RD-09 | recording 구현 |
| Runtime 소유 외부 HTTP timeout | C — Runtime이 직접 부르는 외부 HTTP가 없다(provider 호출은 Search adapter) | — | Runtime이 외부 HTTP를 갖게 되면(예: FX 조회, RD-08) |
| Search in-call retry · per-attempt timeout | B — Search 소유 | search · `search/config.py` | Search 결정 |
| case 대기 timeout | B — case 소유 | case · `timeout-fallback.md` | runtime 머신 재측정 |
| Web polling interval | B — Web 구현값 | web · HTTP Contract §4 | Web 구현 |
| abandoned usage in-flight 판단 시간 | C — 필요 없음. 복구는 event 기반(B-G1) | runtime · Tech Spec §11.1 | event 기반으로 못 다루는 경우가 관측되면 |
| `DECIMAL` precision/scale | B — §6 값이 아니라 RD-01g 구현 세부 | runtime · Tech Spec §4.5 | 첫 migration |
| pricing/FX artifact · FX source | A — 열린 B Decision | runtime + search · RD-08 | M9 |

---

## 6. Validation — 측정할 지표

계측 구현은 §7 · §8이다. 여기서는 이름과 뜻만 정한다. 1차 출처는 Ops §8대로 **Runtime DB query + structured log**다. 이름은 후보이며 첫 구현에서 고정한다.

| Metric | 뜻 · 계산 | 출처 | 보는 값 |
| --- | --- | --- | --- |
| `runtime.queue.wait_ms` | `started_at − queued_at`. attempt 1과 ≥ 2를 나눈다(≥ 2는 backoff 포함, JobExecution Contract §5) | DB | p50 · p95 |
| `runtime.queue.oldest_queued_age_s` | 지금 `available_at ≤ NOW()`인 QUEUED 중 가장 오래된 것 | DB | max |
| `runtime.execution.duration_ms` | `ended_at − started_at`, kind · status별 | DB | p50 · p95 · max |
| `runtime.heartbeat.lag_ms` | heartbeat 성공 시 직전 성공과의 간격 − interval | log | p99 · max |
| `runtime.heartbeat.attempt_ms` | heartbeat 시도 1회의 소요(성공 · 실패 모두). 보장 상한은 없다 — interval(10 s)을 넘으면 다음 tick을 건너뛴다(B-L1) | log | p99 · max |
| `runtime.heartbeat.skipped_tick_count` | 이전 시도가 끝나지 않아 건너뛴 tick 수(B-L1) | log | 합계 |
| `runtime.heartbeat.consecutive_failures` | execution별 최대 연속 실패 수 — 관찰용. STALE 조건이 아니다(§2.3) | log | max |
| `runtime.stale.count` | `RUNNING→STALE` 전이 수 | DB | 합계 |
| `runtime.stale.detect_latency_s` | STALE 기록 시각 − 마지막 heartbeat | DB · log | p95 |
| `runtime.stale.false_count` | STALE 뒤 **원래 Worker가 terminal 기록을 시도해 0 rows를 받은** 수 = Worker가 살아 있었는데 STALE | log | 합계 — **1건이면 trigger** |
| `runtime.retry.auto_count` · `…exhausted_count` | 자동 attempt 생성 수 · 상한 소진 수 | DB | 합계 |
| `runtime.retry.after_case_stopped_count` | attempt ≥ 2의 T2 결과가 `NOT_APPLIED(STOPPED_WAITING)`인 수(§3.2). `APPLIED` · `ALREADY_APPLIED` · `NOT_APPLIED(CANCELLED)` · `NOT_APPLIED(SUPERSEDED)`는 제외하고 reflector 예외/rollback은 집계하지 않고 재전달 대상으로 남긴다 | log | 합계 |
| `runtime.cancel.observe_latency_ms` | 중단 요청 기록 → handler 관찰. B-X1 목표와 비교할 때는 DB 정상 구간만 본다 | log | p95 · max |
| `runtime.cancel.terminal_latency_ms` | 중단 요청 기록 → `CANCELLED` 기록 | DB | p95 · max |
| `runtime.db.claim_latency_ms` | claim transaction 시작 → commit | log | p95 |
| `runtime.db.lock_wait_timeout_count` · `…deadlock_count` · `…pool_timeout_count` · `…error_count` · `…tx_retry_count` | 1205 · 1213 · pool timeout · 기타 DB 오류 · B-D8 재시도 | log | 합계 |
| `runtime.usage.recovered_count` · `…inflight_count` · `…inflight_oldest_age_s` | 복구 경로로 append된 Final row · 남은 in-flight | DB | 합계 · max |
| `runtime.reflect.redelivery_count` | T2 재전달 수(Tech Spec §12.2) | log | 합계 |
| `api.view.request_rate` · `api.view.latency_ms` | `GET /view` | log | rps · p95 |
| `api.request.latency_ms` · `api.request.rejected_413_count` | 전체 route | log | p99 · 합계 |
| `api.upload.bytes` · `…duration_ms` · `…throughput_bps` · `…aborted_count{reason}` · `…rejected_413_count` · status별 실패 | `POST /sources` | log | 분포 · 합계 |
| `api.frame.latency_ms` · `…wait_ms` · `…request_rate` | `GET /frames` · B-F2 대기 | log | p95 |
| `api.asset.download_latency_ms` · `…bytes` | `GET /assets` | log | p95 |
| `api.ready.duration_ms` · `…unavailable_count` | `/health/ready` | log | max · 합계 |
| `storage.root.free_bytes` · `storage.staging.*` · `storage.orphan.*` · `storage.temp.*` | 건수 · bytes · 최고 나이 | cleanup scan · host | 추세 |
| host CPU(credit 포함) · RAM · Worker RSS · disk I/O | EC2 기본 지표 · P2 plan | host | peak |

---

## 7. 공통 재검토 Trigger

아래 중 하나가 생기면 해당 값 묶음을 다시 본다. 단발 관측을 곧바로 운영 보장값으로 올리지 않는다(workflow §11).

| Trigger | 다시 볼 값 |
| --- | --- |
| 첫 MySQL Runtime integration test(M2) | B-D* · B-L* · B-R* 동작 확인 |
| 첫 비동기 Real E2E(M5) | B-Q1 · B-L* · B-U* · B-F* |
| 첫 EC2 배포 · P2 착수(M6 · M7) — **t3.medium CPU credit 소진 상태 포함** | B-L1 · B-L2(heartbeat lag) · B-F2 · B-W2 |
| P2 결과(M8) | 전체 — RD-04 최종값 |
| 30분 ~ 1시간 실제 영상(P3) | B-U1 · B-U4 · B-C* · disk 지표 |
| 동시 case ≥ 2 · Worker 또는 concurrency ≥ 2(RD-15a) | B-R3 jitter · B-Q1 jitter · B-D2 · B-L5 |
| provider latency p95 확보 · case timeout 확정 | §3.2 retry 계산 · B-R1 |
| false STALE ≥ 1 | B-L1 · B-L2 즉시 |
| 같은 입력의 STALE 상한 소진 반복 | B-R1 · 원인(OOM 등) |
| DB 정상 구간 cancel observe p95 > 20 s | B-L1 · B-D9 · B-X1 |
| DB 정상 구간 heartbeat 건너뛴 tick 반복 · I/O timeout | B-L1 · B-D9 |
| DB 1205 · 1213 발생 | B-D1 · B-D8 · 긴 transaction 조사 |
| disk pressure · ENOSPC · orphan/staging 누적 | B-U1 · B-C* · RD-15c |
| Web interval < 2 s 또는 view rps > 5 지속 | B-P1 · B-D3 |
| 정상 파일 `413` | B-U1 |
| RD-10 retention closure | B-F1 · B-C2 |
| pre-deploy review(M9) | B-O* · B-C2 로그 내용 |

---

## 8. Owner 확인 · 변경 절차

### 8.1 merge 전 확인 대상

대부분은 Runtime/Ops Owner의 초기값이라 별도 review를 열지 않는다. 다만 아래 두 곳은 상위 문서가 다른 사람에게 결정 또는 확인을 맡겼으므로 **확인 전에는 merge하지 않는다.**

| 대상 | 확인자 | 근거 | 확인할 것 |
| --- | --- | --- | --- |
| §2.1 ~ §2.5 (Worker · polling · lease/heartbeat/STALE · retry · DB) | 정철원 — `JobExecution` 구현 담당 | JobExecution Contract §11 「retry 상한 · backoff · lease · heartbeat · STALE 판정 임계값은 구현 담당이 정한다」 · [`ownership.md`](../management/ownership.md) | 이 값으로 구현을 시작하는 데 이의가 있는가 |
| §3.2 · §4 첫 행 (RD-04b — lease · STALE threshold와 case job wall의 관계) | 유소연 — case | Register RD-04 「case timeout과의 제약(RD-04b)만 case 확인」 | lease를 case timeout에 맞추지 않는다는 결론 · STALE 재시도 attempt 2가 case 대기 뒤 끝날 수 있다는 관계에 이의가 있는가. case 값 · 정책은 바꾸지 않는다 |

recording 쪽(B-C3 `temp_root` 주입 · B-F2)은 recording의 기존 인자 · 계약 안이고 새 의무가 없다(§4). 정철원 확인에 함께 묶는다.

**확인 결과 (2026-10-06, PR #276).** 정철원 — §2.1 ~ §2.5 · B-C3 · B-F2 구현 시작에 이의 없음. heartbeat 시도 상한 계산 지적 1건은 반영했다(Change log). 유소연 — RD-04b는 case 값 · 정책과 충돌 없음, B-R1 = 1 적절. case 후속(case가 기다리기를 멈춘 뒤 attempt 2가 도는 동안의 CaseView 표시)은 case 소유이고 이 문서의 blocker가 아니다.

### 8.2 변경 절차

- 값을 바꾸면 **이 문서의 해당 행과 [Change log](#change-log)를 고친다**(근거 evidence 링크 포함). 다른 문서는 ID만 가리키므로 따라 고치지 않는다.
- tuning 값 변경은 ADR을 만들지 않는다(workflow §11). 구조가 바뀌면(예: STALE threshold를 lease와 다른 축으로 분리, Worker ≥ 2) 해당 Decision을 다시 연다.
- JobExecution Contract §11에 따라 §2.1 ~ §2.5(Worker · polling · lease/heartbeat/STALE · retry · DB) 값은 구현 담당(정철원)이 같은 절차로 바꿀 수 있다. Contract는 바뀌지 않는다.
- 최종값은 P2(M8) 뒤 이 문서의 v0.2(또는 Tech/Ops Spec 승격)로 정한다 — RD-04 최종 Gate.

---

## 9. §7 Implementation Inputs

§7에서 바로 slice로 나눌 수 있게 묶었다. **Task · Issue · 순서 · 담당은 정하지 않는다.**

| 묶음 | 확정 baseline | 필요한 implementation surface | 필요한 integration test |
| --- | --- | --- | --- |
| **Persistence / Queue** | B-W3 · B-L6 · B-D1 ~ B-D9 | api · worker 공용 engine factory(RC · `SET SESSION innodb_lock_wait_timeout` · pool · PyMySQL timeout · pre-ping · recycle) · heartbeat 전용 connection(B-D9) · ready probe 전용 연결(B-H1) · migration runner는 별도 timeout · Worker transaction 재시도 helper(1205 · 1213 · disconnect, 전체 재실행) | lock wait 1205 → transaction 전체 rollback · 재시도 뒤 중복 전이 없음 · pool 고갈 → API `503` · idle 연결 recycle · `wait_timeout` 초과 뒤 checkout 정상(Research 01 Spike F) |
| **Worker lifecycle** | B-W1 · B-W2 · B-Q1 ~ B-Q3 · B-L1 · B-L2 · B-L4 · B-L5 | claim loop(빈 결과 2 s · 성공 즉시 · 오류 5 s) · heartbeat thread(fixed-rate 10 s cadence · 동시 시도 최대 1개 — 이전 시도가 안 끝났으면 그 tick 건너뜀 · 시도 안 재시도 없음 · lease 60 s · 중단 표식 전달) · heartbeat 전용 connection(B-D9) · handler 실행에 묶이지 않는 sweep 주기 15 s · startup sweep → 첫 claim. 스케줄 수단(thread · event loop)과 시간 기반 test 방식(fake · injected clock · test 전용 짧은 interval)은 §7이 정한다 | 빈 queue에서 claim 주기 · `available_at` 전 claim 없음 · heartbeat 시도가 tick보다 오래 걸려도 다음 tick에서 두 번째 heartbeat DB 호출이 겹쳐 시작되지 않음(건너뛴 tick 기록) · heartbeat 성공 시 `lease_expires_at` 갱신 · lease duration 동안 heartbeat 성공 없음 → 만료 뒤 sweep에서 STALE · heartbeat가 계속 성공하면 lease보다 긴 handler 실행도 STALE 아님 · heartbeat DB 오류 · timeout이 handler 실행을 죽이지 않고 handler 쪽 오류가 heartbeat thread를 죽이지 않음 · startup sweep이 lease 남은 row를 건드리지 않음 |
| **Retry / Recovery** | B-L3 · B-R1 ~ B-R3 · B-D8 소진 규칙 | sweep transaction(STALE + attempt+1 QUEUED, `available_at = NOW(6)+5 s`) · 상한 1 · 중단 요청 시 생성 안 함 · terminal 기록 재시도(lease 보유 중) · T2 재전달 scan(startup + 15 s) | attempt 2만 생기고 attempt 3 없음 · backoff 5 s 동안 claim 없음 · 다중 sweeper attempt 중복 없음(Tech Spec §16 #10) · 소유 상실 뒤 결과 commit 없음(#13) · T1–T2 사이 kill 뒤 반영 1회(#15) |
| **Cancellation** | B-X1 | heartbeat가 읽은 중단 표식 → handler in-process 신호 · capability 사이 checkpoint | heartbeat가 읽은 중단 표식이 handler에 전달됨 · `runtime.cancel.observe_latency_ms` 기록 · checkpoint 뒤 `CANCELLED` · 중단 + STALE → 다음 attempt 없음(Tech Spec §16 #12) |
| **Usage ledger** | B-G1 | in-flight reconciliation을 startup · sweep 주기에 결합 · terminal execution에 묶인 in-flight만 대상 | finish 뒤 Run 확정 전 kill → 다음 sweep에서 Final 1건(Tech Spec §16 #11) · 살아 있는 RUNNING의 in-flight는 건드리지 않음 |
| **API / Upload** | B-W4 · B-U1 ~ B-U5 · B-D3 · B-D4 | `POST /sources` body limit middleware(1 GiB) · `POST /commands` 1 MiB(`POST /cases`는 한도 없음) · COMMIT 전 실패 `503` / COMMIT 결과 불명 `500` 분기 · ASGI receive idle 60 s · 전체 30 min · 중단 시 연결 종료 · upload 중 DB connection 미보유 · Starlette ≥ 1.6 pin · spool `/tmp` non-tmpfs | 1 GiB + 1 byte → `413` · COMMIT 응답 유실 주입 → `500`(`503` 아님) · `Content-Length` 없는 초과 body도 `413` · idle 60 s → 연결 종료 · staging 잔여는 B-C1 대상 · 응답 없음 뒤 `file_count` 경로 |
| **Media serving** | B-F1 · B-F2 | frame 응답 `Cache-Control: private, max-age=3600` · api 동시 `read_frame` 2 · 소유 확인 뒤 DB connection 반환 | frame header · 동시 요청 3건 중 1건 대기 · asset `private, no-store` 유지 |
| **Config / Secret** | 모든 `DAESINGO_RUNTIME_*` 후보 | 불변 `RuntimeConfig`에 이 문서의 기본값 · key 이름 고정 · 값 범위 검증(fail-fast, key 이름만 로그) · 불변조건 검증: `heartbeat_interval > 0` · `lease_duration > heartbeat_interval` · `stale_sweep_interval > 0` · heartbeat `connect` · `read` · `write` timeout > 0 · `heartbeat_lock_wait < heartbeat_read_timeout` · `lock_wait < heartbeat_interval`. heartbeat I/O timeout의 합을 heartbeat interval과 비교하지 않는다 — 시도 전체 상한이 아니다(B-D9) · `staging_age ≥ 2 × upload_max_duration` · `ready_db + ready_storage ≤ ready budget` | 불변조건 위반 config → startup non-zero 종료 · 값이 로그에 없음 |
| **Health** | B-H1 ~ B-H3 | `/health/ready` probe(공용 pool을 쓰지 않는 DB 전용 연결 2 s · 저장소 1 s thread 대기 · 합 3 s, 파일 쓰기 없음) · 실패 dependency는 서버 로그에만 | DB 중지 · API pool 고갈 상태에서도 → 3 s 안 응답 · mount 읽기 전용 → `503` · provider 미호출 |
| **Observability** | §6 metric · B-O2 | structured log event(heartbeat 성공 간격 · 시도 소요 · 건너뛴 tick · 0 rows terminal 시도 · 1205/1213 · upload abort 이유 · cleanup 건수/bytes) · DB 집계 query(queue wait · oldest · stale · retry) | false STALE 식별 event가 남음 · 민감 원문 · 경로 미기록(Ops §7) |
| **Cleanup** | B-C1 ~ B-C4 · B-O1 | api: staging(1 h) · orphan(24 h, recording 등록 조회 뒤) · api temp root(1 h). worker: worker temp root(1 h) · composition root의 `temp_root` 주입 · startup + 1 h scan · Compose `logging:` rotation(Compose slice) | 진행 중 upload staging 미삭제 · 등록된 파일 미삭제 · 나이 미달 파일 미삭제 · 건수/bytes만 로그 |

---

## Change log

| 날짜 | 변경 | 기준 |
| --- | --- | --- |
| 2026-10-05 | v0.1 최초 작성 — workflow §6. RD-04 축 · 제약 · 초기값, RD-11a(local rotation) · 11b, Register 「§5 → §6 Baseline 입력」, HTTP API Contract §4가 넘긴 숫자를 Provisional로 정함. 새 Decision · Contract 변경 없음 | `origin/develop` `a6027f6` |
| 2026-10-06 | PR #276 Runtime 구현 담당 리뷰 반영 — 기술적 정합성 보정, 새 Architecture Decision 아님. PyMySQL의 I/O 단계별 timeout(B-D9)을 heartbeat 시도 전체의 wall-clock 상한으로 해석한 오류를 고쳤다. 시도 ≤ 7 s · 「5회 연속 실패해야 STALE」 · cancel 관찰 ≤ 17 s hard bound를 제거하고, B-L1을 heartbeat 겹침 금지(이전 시도가 안 끝난 tick은 건너뜀)로, STALE 설명을 마지막 성공 heartbeat + lease 기준으로, B-X1을 DB 정상 구간 p95 ≤ 20 s 측정 목표로 정합화. §3.1 · §3.6 · §6 · §7 · §9(config 불변조건 · integration test) 함께 수정. 10 s · 60 s · 15 s 값과 B-R1 · RD-04b 결론은 그대로. Owner 확인 결과 기록(§8.1) | PR #276 리뷰 |
| 2026-10-10 | Issue #291 RT-04(b) T2 결과 taxonomy 합의에 맞춰 `runtime.retry.after_case_stopped_count`의 집계 의미를 §3.2의 원래 관찰 목적에 맞게 명확화. `attempt ≥ 2 ∧ NOT_APPLIED(STOPPED_WAITING)`만 집계하고 `CANCELLED` · `SUPERSEDED` · `ALREADY_APPLIED` 및 reflector 예외/rollback은 제외한다. retry/timeout 숫자와 정책 변경 없음 | Issue #291 · PR #337 |
