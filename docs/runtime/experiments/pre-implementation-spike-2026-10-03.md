# Pre-implementation Spike — §5 Required Decision 근거 (2026-10-03)

**Status:** Result — pre-implementation spike (workflow §4 · §5). P2 capacity 실험이 아니다\
**Owner:** common/runtime — 김준영\
**Executed at:** 2026-10-03 · `origin/develop` `43dd8ec` 기준 브랜치 `docs/runtime-required-decisions-261003`\
**Decisions affected:** [RD-01](../open-decision-register.md#rd-01--runtime-persistence--queue-physical-design) (01b) · [RD-19](../open-decision-register.md#rd-19--사용자-중단cancellation-전달-경로와-실행-중단-semantics) (19b) · [RD-02](../open-decision-register.md#rd-02--retry-attempt-생성-시점과-queued_at-의미) (02a) · [RD-17](../open-decision-register.md#rd-17--api--worker-recording--source-persistence-boundary) (17a) · [RD-07](../open-decision-register.md#rd-07--runtime-configuration--secret-주입) (07a · 07c)

> 이 문서는 **기술 semantics 확인**만 한다. 측정 시간 · 건수는 로컬 단회 관찰이며 baseline 값이 아니다(workflow §4 · §6). schema · query는 spike용 후보이고 최종 migration이 아니다. spike 코드는 production source와 분리해 repository 밖(작업자 scratch)에서 실행했고, 재현에 필요한 SQL · 설정만 아래에 남긴다.

## 실행한 spike와 실행하지 않은 spike

| Spike | 근거 문서의 제안 | 실행 | 이유 |
| --- | --- | --- | --- |
| S1 Claim lock matrix (RR / RC) | Research 01 Spike A | **실행** | RD-01b isolation 선택이 「`SKIP LOCKED`가 gap lock을 남기는가」에 걸려 있고 공식 문서에 명시가 없다(Research 01 Review notes High) |
| S2 Writer contention · cancel/completion race · sweep race | Research 01 Spike C · Research 03 Part B 9 | **실행** | RD-19b 경합 규칙 · RD-02a 「terminal + 다음 attempt 같은 transaction」이 conditional UPDATE semantics에 걸려 있다. S1과 같은 환경에서 비용이 작다 |
| S3 Compose secret file · shared volume · rename | Research 02 Spike A · B · Research 03 Part A 3 · 4 · 5 | **실행** | RD-07 추천(파일 기반 secret)과 RD-17 추천(같은 mount 안 publish)의 전제를 한 번에 확인 |
| Crash boundary (Research 01 Spike B) | — | 안 함 | 추천안의 claim transaction은 INSERT 없이 한 row의 conditional UPDATE이고, commit 뒤 crash는 lease/STALE 경로라 결과가 추천안을 바꾸지 않는다. 구현 integration test(Tech Spec §16 #3)로 검증 |
| JSON vs relational · Money round trip · long-lived connection (Spike D · E · F) | — | 안 함 | RD-01c · 01d · 01g 추천은 조회 패턴과 Contract 불변조건으로 정했다. round trip · reconnect는 구현 test 대상 |
| Migration failure · concurrent migration (Spike G · H) | — | 안 함 | 추천안이 app startup migration을 금지하고 단일 실행 지점을 둔다 → 동시 실행 경합 자체를 만들지 않는다. partial DDL은 도구와 무관한 MySQL 사실(atomic DDL ≠ transactional DDL) |
| Sync HTTP in-flight cancel · ffmpeg signal matrix (Research 03 Part B 2 · 5) | — | 안 함 | RD-19 추천안이 MVP에서 진행 중 provider 호출 · ffmpeg를 선점 중단하지 않는다(경계에서만 중단). 선점을 도입할 때(Reopen trigger) 다시 연다 |
| Upload resource trace · interrupted upload · body limit (Research 02 Spike E · F · G) | — | 안 함 | RD-05e 추천은 구조(같은 mount staging → rename → 등록)만 정하고 크기 한도는 §6이다. 413 timing · disk peak는 구현 · P2 대상 |

---

## S1 — Claim lock footprint (RD-01b)

**Question.** MySQL 8.4에서 `SELECT … FOR UPDATE SKIP LOCKED` claim이 RR과 RC에서 각각 어떤 lock을 남기는가. 그 lock이 enqueue · heartbeat · 다른 row의 terminal 전이를 막는가.

**Environment.** Docker Desktop 29.4.0 (Windows host, Linux VM) · `mysql:8.4` image → `8.4.11` · `innodb_autoinc_lock_mode=2` · PyMySQL 1.2.3 · Python 3.12.3 · `innodb_lock_wait_timeout=2`(관찰용 session 값).

**Input.**

```sql
CREATE TABLE job_execution (
  execution_id VARCHAR(64) PRIMARY KEY,
  job_id VARCHAR(64) NOT NULL, attempt INT NOT NULL, status VARCHAR(16) NOT NULL,
  queued_at DATETIME(6) NOT NULL, available_at DATETIME(6) NOT NULL,
  started_at DATETIME(6) NULL, ended_at DATETIME(6) NULL,
  lease_owner VARCHAR(64) NULL, lease_expires_at DATETIME(6) NULL, cancel_requested_at DATETIME(6) NULL,
  UNIQUE KEY uq_job_attempt (job_id, attempt),
  KEY ix_claim (status, available_at, execution_id)
) ENGINE=InnoDB;

-- claim (한 transaction, INSERT 없음)
SELECT execution_id FROM job_execution
 WHERE status='QUEUED' AND available_at <= NOW(6)
 ORDER BY available_at, execution_id LIMIT 1 FOR UPDATE SKIP LOCKED;
UPDATE job_execution SET status='RUNNING', started_at=NOW(6), lease_owner=?, lease_expires_at=...
 WHERE execution_id=? AND status='QUEUED';
COMMIT;
```

seed: 실행 가능 QUEUED 5 · 미래 `available_at` QUEUED 2 · RUNNING 3. session A가 claim 후 commit하지 않은 상태에서 다른 session으로 관찰.

**Observed.**

| 관찰 | REPEATABLE READ | READ COMMITTED |
| --- | --- | --- |
| `EXPLAIN` | `range` · `ix_claim` · `Using where; Using index` (filesort 없음) | 같음 |
| A의 `data_locks` (`ix_claim`) | `X` — **next-key(record + gap)** on `('QUEUED', t0, 'ex_q0')` | `X,REC_NOT_GAP` — record만 |
| A의 `data_locks` (PRIMARY) | `X,REC_NOT_GAP` | `X,REC_NOT_GAP` |
| B의 동시 claim | 대기 없이 다음 row(`ex_q1`) | 같음 |
| enqueue, `available_at = NOW()` | 통과 | 통과 |
| enqueue, `available_at`이 claim한 row보다 이른 값 | **1205 lock wait timeout** | 통과 |
| enqueue, 미래 `available_at` | 통과 | 통과 |
| 다른 RUNNING row heartbeat UPDATE | 통과 | 통과 |
| 다른 row RUNNING→FAILED | **1205** | 통과 |
| 다른 row RUNNING→CANCELLED | **1205** | 통과 |
| 다른 row QUEUED→CANCELLED | **1205** | 통과 |
| 다른 row RUNNING→STALE · →SUCCEEDED | 통과 | 통과 |
| 4 worker + 동시 enqueue, 600 claim | 중복 0 · deadlock 0 | 중복 0 · deadlock 0 |

**해석.** 이 schema에서 RR의 `SKIP LOCKED` claim은 첫 QUEUED index entry 앞의 gap을 잠근다. `ix_claim`이 `status`로 시작하므로 새 entry가 그 gap에 들어가는 쓰기 — 알파벳상 `QUEUED`보다 앞인 `CANCELLED` · `FAILED`로의 전이, 더 이른 `available_at` enqueue — 가 claim transaction이 끝날 때까지 막힌다. RC에서는 gap lock이 없어 같은 쓰기가 모두 통과한다. Research 01 §1 「`SKIP LOCKED`와 gap lock의 관계는 공식 문서에 명시 없음」에 대해, **이 schema · query에서는 RR에서 gap lock이 남는다**는 관찰이다.

**Decision affected.** RD-01b — Runtime DB session isolation을 READ COMMITTED로 두고, claim transaction은 INSERT 없이 짧게 끝낸다(Tech Spec §4.3에 반영).

**Limitation.** 단일 host · 단회 관찰. 막힌 gap의 범위는 index 이웃 entry에 따라 달라지므로 RR에서 어떤 쓰기가 막히는지의 목록은 data에 의존한다(RC 선택의 근거는 「막힐 수 있음」이지 이 목록이 아니다). 최종 schema가 정해지면 같은 관찰을 그 index로 integration test에서 반복한다.

---

## S2 — Conditional UPDATE 경합 (RD-19b · RD-02a)

**Question.** (a) RUNNING execution에 cancel과 completion이 동시에 오면 무엇이 남는가. (b) QUEUED cancel과 claim이 겹치면 claim되는가. (c) Worker 둘이 동시에 stale sweep을 돌 때 「RUNNING→STALE + 다음 attempt INSERT」를 한 transaction에 두면 attempt가 중복 생성되는가.

**Environment · Input.** S1과 같다. 모든 terminal 전이는 `WHERE execution_id=? AND status='RUNNING'`(또는 `'QUEUED'`) 조건부 UPDATE. sweep은 `UPDATE … SET status='STALE' WHERE … AND status='RUNNING' AND lease_expires_at < NOW(6)`가 1 row를 바꾼 경우에만 `INSERT (job_id, attempt+1, 'QUEUED', available_at = NOW()+Δ)`.

**Observed (RR · RC 동일).**

| 경우 | 결과 |
| --- | --- |
| cancel 먼저(미commit) → completion | completion이 lock 대기 후 **0 rows** · 최종 `CANCELLED` |
| completion 먼저(미commit) → cancel | cancel이 lock 대기 후 **0 rows** · 최종 `SUCCEEDED` |
| QUEUED cancel(미commit) 중 claim | `SKIP LOCKED`로 건너뜀(결과 없음) · commit 뒤에도 claim 대상 아님 |
| sweeper 2개 barrier 동시 시작 | 한쪽만 1 row 갱신 · attempt 2 **정확히 1개** · deadlock 0 |

**Decision affected.** RD-19b — 「먼저 commit한 terminal 전이가 이긴다」를 별도 lock 없이 conditional UPDATE로 구현할 수 있다. RD-02a — 이전 attempt terminal 기록과 다음 attempt QUEUED 생성을 한 transaction에 두는 안이 다중 sweeper에서도 중복 없이 동작한다.

**Limitation.** cancel 요청을 RUNNING handler가 **관찰하는 시점**(heartbeat · checkpoint)은 이 spike가 다루지 않는다 — 그것은 Worker 구조 설계(RD-19 · RD-01h)다.

---

## S3 — Compose secret file · shared volume (RD-07 · RD-17)

**Question.** (a) Compose `secrets:`(file source)로 mount한 KEY=VALUE 파일을 현재 `common/env.py` `load_env_file(path)`가 그대로 읽는가, 그 값이 process environment · `docker inspect`에 나타나는가. (b) API · Worker가 같은 volume을 같은 numeric UID로 쓸 때 쓰기 · 읽기 · read-only가 의도대로인가. (c) 같은 mount 안 rename과 다른 mount 사이 rename의 결과.

**Environment.** Docker Compose v5.1.1 · `python:3.12-slim`(3.12.15) · 두 service 모두 `user: "10001:10001"` · `common/env.py` 원본 사본.

**Input.** api: `media` named volume RW + `other` volume, worker: `media` RO. 두 service에 `secrets: [runtime_env]`(file source) + `environment: DAESINGO_ENV_FILE=/run/secrets/runtime_env`(경로만). 초기화 one-off가 volume root를 `10001:10001`로 chown.

**Observed.**

| 관찰 | 결과 |
| --- | --- |
| `load_env_file("/run/secrets/runtime_env")` | 두 service 모두 key 2개 읽음 |
| secret 값이 `os.environ`에 있는가 | 없음 |
| secret 값이 `docker inspect … .Config.Env`에 있는가 | 없음 (경로 변수만) |
| `/run/secrets/runtime_env` 소유 · mode | `0:0`, mode는 host 파일을 따름(Windows host라 `0777` — Linux host 값은 아래 Limitation) |
| api: `staging/` 쓰기 → `fsync` → 같은 volume `sources/`로 rename | ok |
| api: 다른 volume → `media` rename | **`EXDEV`** |
| api: container `/tmp` → `media` rename | **`EXDEV`** |
| worker: api가 publish한 파일 읽기 | ok |
| worker: RO mount에 쓰기 | `EROFS` |
| **named volume을 image에 이미 있는 경로(`/media`)에 mount** | 비어 있는 동안 mount할 때마다 image 디렉터리 소유(root `0755`)로 다시 맞춰져 non-root UID가 **`EACCES`**. image에 없는 경로(`/srv/media`)로 바꾸자 chown이 유지됐다 |

**Decision affected.** RD-07 — secret을 process environment가 아니라 파일로 넘기고 loader가 그 경로를 읽는 안이 현재 loader 그대로 동작하며 ffmpeg 자식 process 상속 · `docker inspect` 노출면을 만들지 않는다. RD-17 — staging과 final은 **같은 mount 안**이어야 하고 `/tmp` · 다른 volume을 staging으로 쓸 수 없다. shared mount 경로와 소유는 image가 소유를 고정하는 방식(이미지에 없는 경로 + 초기화 또는 Dockerfile에서 디렉터리 생성 · 소유 지정)으로 다뤄야 한다.

**Limitation.** Windows host의 Docker Desktop이라 bind된 secret 파일의 mode · 소유는 Linux EC2 host와 다르다. Compose는 file source secret의 `uid`/`gid`/`mode`를 무시하고 host 파일 권한을 따르므로(Research 03 Review notes Low), EC2에서는 host 파일 소유 · mode를 container UID가 읽을 수 있게 둬야 한다 — 배포 smoke(RD-12)에서 확인한다. bind mount 변형 · host reboot · user namespace는 실행하지 않았다.
