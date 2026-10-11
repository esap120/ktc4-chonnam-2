# Runtime Implementation Plan

**Status:** Implementation Plan — workflow §7 CLOSED (PR #304) · §8 실행 모델 보정 2026-10-06(§12 — §7 reopen 아님)\
**Owner:** common/runtime — Runtime/Ops Owner · HTTP API Contract Owner · Deferred Acceptance 김준영(@flosure23) · **Primary Implementer RT-01 ~ RT-15 정철원(@cheol1203)** (§12)\
**Date:** 2026-10-06 · 기준 `origin/develop` `4052ada` (PR #276 merge 직후)\
**Workflow step:** [`runtime-ops-workflow.md`](./runtime-ops-workflow.md) §7 → 다음은 §8 Implementation / Test / CI / Observability\
**Inputs:** [Provisional Baseline v0.1](./provisional-baseline-v0.1.md) §9 · [Tech Spec](./runtime-tech-spec.md) · [Ops Spec](./ops-spec.md) · [HTTP API Contract](../architecture/contracts/contract-http-api.md) `http-api/v1` · JobExecution · UsageRecord · JobRecord/CaseView Contract · Decision #244 ~ #250\
**실제 구현 기록:** [Runtime Implementation Log](./runtime-implementation-log.md) — 이 Plan 대비 무엇이 달라졌는지는 Log에 남기고 이 문서를 구현에 맞춰 다시 쓰지 않는다(§12.5)

> 이 문서는 **무엇을 · 어떤 순서로 · 어떤 Issue/PR 단위로** 만들지만 정한다. Architecture · Contract · Accepted Decision · Baseline 값의 의미를 바꾸지 않는다. 숫자는 Baseline ID(`B-xx`)로만 가리키고 복제하지 않는다(Baseline 머리말 규칙). Task 본문의 「Scope」는 구현 범위이지 새 규칙이 아니다 — 충돌하면 위 Inputs가 맞다.

## 0. Scope / authority

```text
Final Contract > Accepted Decision > Provisional Baseline v0.1 > Runtime/Ops Spec > 이 Plan
```

- **이 Plan이 정하는 것:** Task · Issue 분해, dependency, 순서, Owner · Implementer(§12), PR 경계, acceptance test 배치, Decision Gate 위치. 그리고 상위 문서가 「구현 플래닝 · §7」로 **명시적으로 넘긴** 구현 선택(§0.1).
- **정하지 않는 것:** 새 Decision · 새 정책 · Baseline 값 재조정 · 다른 Owner의 capability 모양. 열린 Decision(Timing B · C · D)은 답을 만들지 않고 Gate로만 표시한다(§7).
- 구현 Task가 SoT와 모순을 발견하면 Task 안에서 고치지 않고 해당 SoT Owner에게 올린다.

### 0.1 상위 문서가 §7로 넘긴 구현 선택

아래만 이 Plan이 고정한다. 각 행은 위임한 원문이 있고, 새 policy가 아니라 구현 모양이다.

| # | 항목 | 위임 원문 | 이 Plan의 선택 | 적용 Task |
| --- | --- | --- | --- | --- |
| P-1 | Alembic 배치 | Tech Spec §4.2 「각 모듈은 자기 schema · migration만」 · [case-store-mysql](../modules/case/decisions/case-store-mysql.md) §9 「정확한 배치는 Runtime Implementation Plan」 | **모듈별 Alembic env** — `migrations/<module>/` · version table `<module>_alembic_version`. #282의 잠정 배치(`migrations/case/` · `case_alembic_version`)를 공용 규칙으로 채택한다. Runtime은 `migrations/runtime/`. 모듈 간 FK가 없으므로 실행 순서는 결정성을 위한 고정 순서일 뿐이다. 배포에서 **언제 · 어디서** 돌리는지는 RD-12f(§7) | RT-02 |
| P-2 | MySQL integration CI | case-store-mysql §9 「CI MySQL — 세부 구성은 Runtime Implementation Plan」 · Ops §19 「없는 gate만 추가」 | 기존 `python-tests.yml`에 MySQL 8.4 service를 붙이고 MySQL 테스트가 **skip되지 않았음을 확인하는 step**을 둔다(media smoke와 같은 방식). 새 pytest workflow를 중복으로 만들지 않는다. 운영진 소유 workflow 3개 · CODEOWNERS는 건드리지 않는다 | RT-02 |
| P-3 | heartbeat · sweep 스케줄 수단 | Baseline B-L1 · B-L4 「수단은 §7」 · Tech Spec §7.2 「별개 heartbeat thread」 | **thread** — main thread = claim + handler, heartbeat thread, 주기 sweep thread. event loop를 쓰지 않는다. 공용 pool 사용 thread 수는 B-D2 근거와 같다 | RT-05 · RT-06 |
| P-4 | 시간 기반 test 방식 | Baseline §9 Worker lifecycle 행 「§7이 정한다」 | tick · skip · backoff 계산은 **주입 clock/scheduler unit test**. lease · STALE · 실제 DB 시각(B-L6)이 걸리는 것은 **test 전용 짧은 interval config**로 MySQL integration(불변조건 검증은 그대로 통과해야 함). 엄격한 wall-clock 상한 assert 대신 순서 · 결과 · 여유 있는 상한을 본다 | RT-04 ~ RT-07 |
| P-5 | transaction 참여 모양 | Tech Spec §12.1 「UoW API 모양은 구현 플래닝」 · #267 리뷰 합의 | 호출자가 SQLAlchemy `Connection`을 넘기고 case · recording · Runtime repository는 commit/rollback하지 않는다. 별도 UoW 객체는 두지 않는다. case 행과 Runtime 행을 함께 잠그는 경로는 **case 행을 먼저** 잠근다(#267 합의) | RT-03 · RT-04 · RT-08 |
| P-6 | orphan publish 판정 수단 | Baseline B-C2 「판정 수단은 §7」 | recording 공개 조회(「이 locator가 등록돼 있는가」)를 **후보**로 둔다. Runtime이 recording schema를 직접 읽지 않는다. 이 조회는 recording에 아직 없고 기존 결정에 없던 **새 요청**이라 이 Plan은 의무로 만들지 않는다 — RT-12 orphan 부분 착수 전 recording Owner 확인 Gate(§7). 확인 전 RT-12는 staging · temp만 정리 | RT-12 |
| P-7 | false STALE 뒤 늦은 usage 관측 | Baseline §2.12 「§7 구현에서 정하고」 · Tech Spec §11.1 「관측값을 버리지 않는다」 | recovery가 Final을 만든 뒤 원래 Worker의 `finish`가 오면 Final은 그대로 두고(usage identity UNIQUE), 그 늦은 관측값을 해당 in-flight 기록에 durable하게 남기고 event를 기록한다. 이를 위해 Tech Spec §11.1의 「in-flight 정리」를 **삭제가 아니라 finalize 상태 표시**로 구현한다. 정리된 in-flight 기록의 보관 기간은 retention(RD-10) 범위다 | RT-07 |
| P-8 | config key 이름 | Baseline §0.1 「접두어만 확정, 나머지 이름은 첫 구현에서 고정」 | Baseline §2 표의 **후보 이름을 그대로** 확정 이름으로 쓴다(`…`는 `DAESINGO_RUNTIME_`). Baseline에 없는 key(DB 접속 · 공유 mount root · service별 temp root)는 RT-01 PR이 이름을 정하고 Baseline에 행을 더하지 않는다(값이 아니다) | RT-01 |
| P-9 | FastAPI route `def` / `async def` | Tech Spec §4.4 · HTTP Contract §4 「구현」 | JSON route는 sync `def`(sync DB stack). upload route의 수신 경계(B-U3 · B-U4)는 RT-11에서 정한다 | RT-08 · RT-11 |
| P-10 | `DECIMAL` precision/scale | Tech Spec §4.5 · Register RD-01g 「첫 migration」 | **값은 RT-07 migration PR이 고정한다.** 기준 — Search cost 계산 출력 자릿수(#244 U-2) · Contract 예시 · 초과 자릿수는 거부(무음 반올림 금지). 새 Decision을 만들지 않는다 | RT-07 |

Task PR로 넘기는 구현 선택(이 Plan이 값을 정하지 않음): Baseline 밖 config key 이름(P-8) · `DECIMAL` 값(P-10) · type checker 도구 · secret scan 배치(RT-15) · Compose smoke의 CI 편입(RT-13). 각 PR이 근거를 남긴다.

---

## 1. Current implementation gap

**Audit 기준:** `origin/develop` `4052ada` (2026-10-06) + open PR #282 · #284 · #286 · #277. 코드를 직접 읽어 분류했다. Tech Spec §17 · README의 「현재 구현 상태」(2026-10-02)보다 이 표가 최신이다.

| 영역 | 상태 | 근거 (path · symbol) |
| --- | --- | --- |
| RuntimeConfig · `DAESINGO_RUNTIME_*` · composition bootstrap | **MISSING** | `common/env.py: load_env_file()`(cwd `.env`, `os.environ` 미사용)만 있다. RuntimeConfig · key 없음 |
| DB engine · session factory | **MISSING** (develop) · **PARTIAL** (#282) | develop은 전부 in-memory. #282가 `sqlalchemy` · `pymysql` · `alembic` 의존성과 `case/store_mysql.py: MySQLCaseRepository`(호출자 `Connection` 참여 · 자체 commit 없음 · RC 요구)를 추가. 공용 engine factory 없음 |
| Migration (Alembic) | **MISSING** (develop) · **PARTIAL** (#282) | #282 `migrations/case/{alembic.ini,env.py,versions/0001_case_tables.py}` · `case_alembic_version`(잠정 배치). Runtime · recording · usage DDL 없음 |
| Queue — enqueue · claim · `SKIP LOCKED` · 조건부 전이 | **MISSING** | 해당 코드 없음. enqueue 입력은 있다 — `case/command.py: CommandResult.appended_job_records`(#268) |
| JobExecution model · 전이표 | **DONE** (in-memory) | `common/job_execution.py` — v1.1 model · `_TRANSITIONS` · `InMemoryJobExecutionStore`. 재사용한다 |
| Worker loop · dispatch · heartbeat · lease · sweep | **MISSING** | `worker/README.md`뿐 |
| Retry · recovery · fencing | **PARTIAL** (model만) | in-memory attempt 증가 · 전이 검증만. backoff · fencing · STALE 판정 없음 |
| Cancellation | **PARTIAL** | Contract 상태 `CANCELLED` · `case/view.py` CANCELLED→PARTIAL 투영 있음. case 중단 command(8-9) 없음 · #284 `settle_job()`. Runtime 쪽 없음 |
| Usage ledger | **MISSING** · **STALE** 1건 | Final UsageRecord · in-flight · sink port 없음. `search/ledger.py: UsageRecord`/`SearchLedger`는 이름만 같은 Search 내부 원장(Tech Spec §17 · #153) — Final 원장이 아니다 |
| HTTP API 8 route | **MISSING** | FastAPI 없음. 감쌀 case 함수는 있다 — `create_case` · `record_source_registered` · `execute_command` · `get_view`(#284에서 `job_executions=` 인자로 바뀜) |
| Upload · staging · publish | **MISSING** | `RecordingService.register_local_source(path)`(신뢰된 local 파일, 원본 파일명 인자 없음) |
| Frame · asset serving | **PARTIAL** (domain만) | `RecordingService.read_frame()` 있음. 소유 조회 · DerivedAsset bytes 공개 read 없음 · header 처리 없음 |
| Health | **MISSING** | — |
| Cleanup | **PARTIAL** (domain만) | `RecordingService.purge_case()`(product purge — 이 Plan 범위 밖). staging · orphan · temp 정리 없음 |
| Observability | **PARTIAL** (모듈 국소) | `recording/observability.py` trace sink만. structured log 설정 · metric 없음 |
| Docker · Compose | **MISSING** | Dockerfile · compose 없음 |
| Deployment (EC2 · ECR · SSM) | **MISSING** | 문서뿐 |
| Recording persistence | **MISSING** | `InMemoryRecordingRepository` · `_local_clips`. RD-17 후속(recording MySQL) 미착수 |
| Search → usage sink | **MISSING** | provider 호출(`coarse.py` · `fine.py` · `diagnostic_call.py` · #277 `intent.py`)은 `SearchLedger`에만 기록 |
| Case ↔ Runtime port | **PARTIAL** | append 목록(#268) ✅ · CaseStore MySQL 1단계(#282) · `running_jobs` 계산(#284) open. **T2 진입(`execution_id`를 받는 반영 함수, 8-8) MISSING** — develop에는 `receive_search_candidates` · `receive_hint_extraction`(execution 개념 없음)뿐. 중단(8-9) · read port 연결(8-10) · 모듈 결과 영속(8-6 2단계) 미착수 |
| CI 품질 gate (Ruff · type checker · secret scan) · Runtime import 경계 검사 | **MISSING** | Ops §19 「없음」 · `check_boundaries.py`에 `common` · `api` · `worker` 규칙 없음(Register Implementation Gap C-10) |
| Test infra | **PARTIAL** | unit · contract fixture · boundary CI 있음. MySQL은 #282의 opt-in(`DAESINGO_MYSQL_URL` 없으면 skip)뿐, CI에 MySQL 없음. API contract test 없음 |

**STALE 항목 (재구현 · 오용 방지):**

- `search/ledger.py: UsageRecord` — Final Contract 원장으로 쓰지 않는다. 이름 정리는 #153(search) 범위이고 이 Plan이 고치지 않는다.
- #282 `migrations/case/env.py`의 `os.environ["DAESINGO_MYSQL_URL"]` — dev/test 편의 경로다. 배포 migration의 DB 접속 출처는 RD-12f(§7)에서 닫는다. 그 전까지 app config(RD-07 「값은 파일에서만」)와 섞지 않는다.

---

## 2. Target runtime path

```text
[API process]                                   [Worker process]
POST /commands                                  startup sweep (B-L5) ─┐
 └ tx (composition root 소유)                     claim loop (B-Q*) ◀─┘
    ├ case.execute_command(conn)                   └ claim tx: SKIP LOCKED → RUNNING + lease → commit
    ├ appended JobRecord마다 runtime.enqueue(conn)   handler(kind registry) ── heartbeat thread (lease · cancel)
    └ commit → 202 / 200                           T1 terminal (조건부 · lease owner)
GET /view                                         T2 tx: case 반영(execution_id idempotent) + 후속 enqueue + 반영 표식
 └ case.get_view(read port: job_id → JobExecution) sweep thread: STALE → attempt+1 · T2 재전달 · usage reconciliation
```

---

## 3. Dependency graph

```text
Foundation     RT-01 config·log  ┊  RT-02 DB·Alembic·harness·CI
                        └──────────┬───────────┘
Persistence              RT-03 job_execution·queue ──────────────┐
                              │                                   │
Runtime core   RT-04 worker core (E2E-0)              API  RT-08 cases·commands·view·health
                              │                                   │      ◀ case #282 · #284 · 8-10
               RT-05 lease·heartbeat·cancel                       │
                              │                                   │
               RT-06 sweep·retry·T2 재전달                          │
                                                                  ▼
first E2E                      RT-09 첫 비동기 E2E ◀── RT-04 · RT-08 · case 8-8
                                     │
Usage          RT-07 usage ledger ◀── RT-02 · RT-03 · RT-06(hook)   ──▶ SRCH-1 (search)
Media          REC-1 (recording) ◀── RT-02      RT-11 upload·frames·assets ◀── RT-08 · REC-1
Real handler   RT-10 ◀── RT-09 · RT-05 · RT-07 · SRCH-1 · REC-1 · [case 8-6 2단계] · [RD-09]
Ops            RT-12 cleanup·관측 ◀── RT-11 · RT-06 · RT-07 · [orphan: P-6 확인]
Compose        RT-13 ◀── RT-09 · RT-02 · RT-06 · RT-11 · [RD-12a · 12g · NOT_BASELINED Compose 값]
EC2            RT-14 ◀── RT-13 · [RD-12b~f · 12h · RD-13a · 13c · 13d · RD-11a · RD-07c]
CI gate        RT-15 ◀── RT-01 · RT-02(a)
```

| Task | 착수 전 merge 필요 | 병렬 착수 가능 (interface만) | Gate |
| --- | --- | --- | --- |
| RT-01 | — | RT-02 | — |
| RT-02 | — (#282와 의존성 순서만) | RT-01 `DbSettings` | — |
| RT-03 | RT-02 | — | — |
| RT-04 | RT-03 · RT-01 | — | — |
| RT-05 | RT-04 | — | — |
| RT-06 | RT-05 | — | — |
| RT-07 | (a) RT-02 · (b) RT-03 · (c) RT-06(a) | — | — |
| RT-08 | (a) RT-01 · RT-02(a) · (b) case #282 · 8-10 · (c) RT-03 · case #284 · (d) RT-05(b) · case 8-9 | — | — |
| RT-09 | RT-04 · RT-08(c) · case 8-8 | — | — |
| RT-10 | RT-09 · RT-05 · RT-07 · SRCH-1 · REC-1 | — | case 8-6 2단계 · RD-09 |
| RT-11 | RT-08(a)(b) · case #282 · REC-1(해당 capability) | — | — |
| RT-12 | RT-11(a) · RT-06 · RT-07 | — | orphan 부분: P-6 recording 확인 |
| RT-13 | RT-09 · RT-02(b) · RT-06 · RT-11(a) | — | RD-12a · 12g · NOT_BASELINED Compose 값 |
| RT-14 | RT-13 | — | RD-12b~f · 12h · RD-13a · 13c · 13d · RD-11a · RD-07c |
| RT-15 | RT-01 · RT-02(a) | — | — |
| REC-1 | RT-02 | — | — |
| SRCH-1 | RT-07(b) | — | — |

- `[ ]`는 Decision Gate(§7) 또는 다른 Owner의 선행 작업이다.
- **순환 없음.** 모든 선행은 위 표에서 아래쪽 Task로만 향한다(RT-07 → SRCH-1 → RT-10 순). RT-07은 RT-06의 sweep hook에 reconciliation을 **등록**만 한다 — RT-06이 RT-07을 import하지 않는다.

### 3.1 Gate milestone 대응

[decision-classification.md](./decision-classification.md) §2.4의 M1 ~ M5는 workflow §7 우선순위 순서다. 이 Plan에서의 대응:

| Gate | 이 Plan에서 착수 시점 |
| --- | --- |
| M1 Runtime persistence | RT-02 · RT-03 · RT-07 착수 |
| M2 Worker | RT-04 착수 (RD-09a Provisional 가정 기록 — §7) |
| M3 API composition root · Web 실연동 | RT-08 착수 |
| M4 Docker / Compose | RT-13 착수 (RD-12a · 12g Provisional) |
| M5 첫 비동기 Real E2E | RT-10 · RT-11 · RT-13 완료 뒤 workflow §9 — M6 Decision(RD-12f · 12h 등)을 기다리지 않는다 |

순서가 workflow §7 목록과 다른 점: API(M3)를 Worker 완료(M2) 뒤로 미루지 않고 RT-03 직후 병렬로 시작한다 — 첫 비동기 E2E를 앞당기기 위해서다(§4). Gate 이름 · 의미는 바꾸지 않는다.

---

## 4. Critical Path to first async E2E

**목표:** 아래 경로가 실제 MySQL 위에서 자동 테스트로 한 번 통과한다.

```text
HTTP command → case JobRecord append → JobExecution enqueue (같은 commit)
→ Worker claim → handler → T1 terminal → T2 case 반영 → GET /view (running_jobs = [])
```

**순서:**

```text
1. RT-01 config · log            ∥ 2. RT-02 DB 기반 · harness · CI
3. RT-03 job_execution · queue repository
4. RT-04 worker core — E2E-0 (fake 반영 port · dummy handler, Runtime 단독)
5. RT-08 API — /cases · /commands · /view (RT-03 뒤 RT-04와 병렬)
   + case 선행: #282 (CaseStore MySQL) · #284 (running_jobs) · 8-8 (반영 idempotent) · 8-10 (read port 연결)
6. RT-09 첫 비동기 E2E
```

- **RT-05 · RT-06(heartbeat · STALE · retry)은 happy path에 필요 없어서 critical path에서 뺐다.** RT-08 · RT-09는 RT-05 · RT-06을 기다리지 않는다 — Implementer가 한 명(§12)이라 실제 순서는 case 선행 작업(§6.1) 상황에 맞춰 고른다. Runtime 코어 위험(claim · transaction)은 RT-03 · RT-04에서 먼저 검증된다.
- **RT-09는 single process다.** API(TestClient)와 Worker loop(thread · 별도 engine)를 한 process에서 돌린다. case의 모듈 adapter가 8-6 2단계 전까지 process 메모리에 있어서다(case-store-mysql §1 「1단계가 주지 않는 것」). api · worker **별도 process** 증명은 RT-10(case 2단계 뒤) · RT-13(Compose)이 맡는다.
- **E2E 진입 command.** case 분석 시작 command(8-1)가 develop에 있으면 그것을 쓰고, 없으면 JobRecord를 append하는 기존 command kind + fixture case를 쓴다. HTTP 층은 kind를 해석하지 않으므로(Contract §5.3) 어느 쪽이든 경로 검증은 같다.
- **critical path를 막지 않는 것:** CloudWatch · log transport(RD-13a) · cleanup 전체 · capacity tuning · Compose · 배포 자동화 · 실제 provider · upload · frame/asset.

**그 다음 (M5 Real E2E 경로, workflow §9 입력):** REC-1 → RT-11(upload) · SRCH-1 → RT-07 → RT-10(실제 handler, case 8-6 2단계 · RD-09 Gate) → RT-13(Compose) → §9 Real E2E.

---

## 5. Implementation slices

| Slice | 목표 | Task |
| --- | --- | --- |
| A Config / bootstrap | 불변 RuntimeConfig · fail-fast · composition bootstrap · structured log 기반 | RT-01 |
| B Persistence / migration | DB access stack · Alembic 배치 · MySQL harness · `job_execution` · usage table | RT-02 · RT-03 · RT-07 |
| C Queue / repository / transaction | enqueue(호출자 tx) · claim · 조건부 전이 · read port · tx 재시도 | RT-02 · RT-03 |
| D Worker lifecycle | claim loop · registry · dispatch · T1/T2 · heartbeat · sweep | RT-04 · RT-05 · RT-06 |
| E Retry / recovery / fencing | STALE · attempt+1 · 상한 · 소유 상실 · T2 재전달 | RT-05 · RT-06 |
| F Cancellation | QUEUED 즉시 · RUNNING 표식 → heartbeat → checkpoint | RT-05 (+ case 8-9 · RT-08 배선) |
| G Usage ledger | begin/finish/finalize · reconciliation · Search 접합 | RT-07 · SRCH-1 |
| H HTTP composition root | `/cases` · `/commands` · `/view` · `/health/*` · envelope · status | RT-08 |
| I Upload / shared media | `POST /sources` · staging → `fsync` → publish → commit | RT-11 (+ REC-1) |
| J Frame / asset serving | 소유 확인 · `read_frame` · DerivedAsset 다운로드 | RT-11 (+ REC-1) |
| K Health | live · ready probe | RT-08 |
| L Cleanup | staging · orphan · temp | RT-12 |
| M Observability | log event · DB 집계 query · event catalog | RT-01(기반) · 각 Task(자기 event) · RT-12(집계 · 검증) |
| N Compose / local runtime | api · worker · mysql · 공유 volume · migration step | RT-13 |
| O Deployment / operations | EC2 · OIDC · SSM · log transport · backup | RT-14 |
| — 실제 handler | kind → public capability 등록 · cross-process E2E | RT-10 |
| — 첫 비동기 E2E | critical path 통합 acceptance | RT-09 |
| — CI 품질 gate | Ruff · type · secret scan · Runtime import 경계 | RT-15 |

---

## 6. Task breakdown

공통 DoD(각 Task): **code · test(아래 표) · observability(아래 event) · docs pointer**. Final Contract · SoT를 바꾸지 않는 구현은 docs 수정 없이 implementation PR이면 된다 — 단 `src/daesingo/{api,worker,common}/README.md`의 「아직 코드가 없다」 같은 상태 문구는 해당 Task가 고친다.

책임 표기(§12): **Implementer**(실제 구현 · implementation detail 선택 · PR merge) · **Owner / Acceptance**(Contract · Decision · Baseline authority, 구현 뒤 deferred acceptance — merge 전 승인 gate 아님, §12.2) · **Consult**(해당 Owner surface의 모양을 맞출 때 확인) · **Consumer 통지**. RT-01 ~ RT-15는 모두 Implementer 정철원 · Owner / Acceptance 김준영이다. REC-1 · SRCH-1은 각 모듈 Owner 표기를 유지한다. GitHub — 김준영 @flosure23 · 정철원 @cheol1203 · 유소연 @yuusoyeon · 서어진 @kong2488-star · 신유민 @uminshin · 김대원 @kim1034.

### RT-01 — Runtime config · composition bootstrap · structured log 기반

- **Goal:** api · worker가 startup에 한 파일에서 Runtime 값을 읽어 불변 config로 만들고, 잘못되면 뜨지 않는다. 모든 후속 Task가 쓰는 log 기반을 둔다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영
- **Dependencies:** 없음
- **Inputs / SoT:** Tech Spec §15.2(RD-07) · Baseline §9 「Config / Secret」 행 · Baseline §2 각 표의 Config 칸 · B-O2 · Ops §6 · §6-1 · §7 · §0.1 P-8
- **Implementation scope:**
  - 불변 `RuntimeConfig` — Baseline 기본값 · key 이름(P-8) · 값 범위 검증 · Baseline §9의 config 불변조건 검증. `DbSettings`(B-D*) · health(B-H*) · upload(B-U*) · frame(B-F*) · cleanup(B-C*) · worker(B-Q* · B-L* · B-R*) 묶음
  - `DAESINGO_ENV_FILE`은 api · worker composition root bootstrap만 해석해 `load_env_file(path)`에 넘긴다. `load_env_file()` 기본 동작(cwd `.env`)은 바꾸지 않는다
  - **service별 schema** — api · worker가 읽는 key 묶음과 기본값을 나눈다(같은 key 이름이라도 B-D2 / B-D3처럼 service마다 기본값이 다름 · heartbeat key와 `lock_wait < heartbeat_interval` 불변조건은 worker만)
  - fail-fast — 누락 · 잘못된 값이면 non-zero 종료, 로그에는 key 이름만. 알 수 없는 `DAESINGO_RUNTIME_*` key는 경고 로그만(종료 조건을 새로 만들지 않는다)
  - **모듈 config 검증(RD-07)** — bootstrap이 그 service가 쓰는 모듈의 factory · validator에 mapping을 넘겨 startup에서 검증하고 실패하면 fail-fast(Tech Spec §15.2 「Runtime config와 각 모듈 config를 모두 만들어 검증」). key 해석 · alias는 각 모듈(§15.1). pricing/FX는 필수로 강제하지 않는다
  - structured log — JSON line stdout · correlation 필드(Ops §6) · `contextvars` 전파 helper · `trace_id` 생성 · 민감 원문 미기록 원칙(Ops §7)을 따르는 event helper
- **Expected files/modules:** `src/daesingo/common/config/` · `src/daesingo/common/logging/` · `src/daesingo/{api,worker}/bootstrap.py` · `tests/common/config/` · `tests/common/logging/`
- **Out of scope:** engine 생성(RT-02) · SSM · 배포 파일 배치(RT-14) · Search key rename(search · #153)
- **Acceptance criteria:** Baseline 기본값과 config 기본값 일치(service별 표 대조 test) · 불변조건 위반마다 non-zero · 모듈 config 검증 실패 → non-zero · 로그에 값 없음 · `load_env_file()` 무인자 호출이 shell의 `DAESINGO_ENV_FILE` 영향을 받지 않음
- **Integration tests:** 없음(unit). §8 매트릭스 「config fail-fast」
- **Observability:** `runtime.config.invalid`(key 이름만) · `process.started`(service · revision 식별 가능한 값)
- **Decision gate:** 없음
- **PR boundary:** 1 ~ 2 PR (config · log). 독립 merge 가능

### RT-02 — DB access 기반 · Alembic 배치 · MySQL integration harness · CI

- **Goal:** 모든 Runtime · case · recording MySQL 코드가 같은 sync DB stack · 같은 session 설정 · 같은 test harness 위에 선다. MySQL 테스트가 CI에서 실제로 돈다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영 · Consult 유소연(#282 Alembic · harness 공용화)
- **Dependencies:** RT-01의 `DbSettings`(interface만 — 병렬 착수 가능, §11) · #282와 의존성 추가 순서(먼저 merge되는 쪽이 `pyproject.toml`에 넣고 다른 쪽이 맞춤 — #267 합의)
- **Inputs / SoT:** Tech Spec §4.3(RC) · §4.4 · Baseline B-D1 ~ B-D9 · B-H1 · Baseline §9 「Persistence / Queue」 행 · Research 01 Spike F · §0.1 P-1 · P-2
- **Implementation scope:**
  - engine factory: api(B-D3) · worker(B-D2) — RC · `SET SESSION innodb_lock_wait_timeout`(B-D1) · pool(B-D4 ~ B-D6) · PyMySQL timeout(B-D7). heartbeat 전용 connection(B-D9) · ready probe 전용 connection(B-H1) · migration runner 용(B-D7 제외)
  - transaction helper — Worker: 1205 · 1213 · 연결 끊김 → 전체 rollback 후 재실행(B-D8). API: 실패를 「COMMIT 전」(→ `503`) / 「COMMIT 결과 불명」(→ `500`)으로 분류만(B-D8 — HTTP 매핑은 RT-08)
  - Alembic 공용 배치(P-1) + `migrations/runtime/` env(table은 RT-03 · RT-07) + 모든 모듈 env를 고정 순서로 올리는 migration runner 명령. 앱 startup에서 migration을 돌리지 않는다(Tech Spec §4.4). runner의 DB 접속은 **명시적 인자**로 받는다 — local · CI는 test 전용 URL을 넘기고, 배포에서 어디서 읽는지는 RD-12f(RT-14)다. RD-07 app config 경로와 섞지 않는다
  - pytest harness — 공용 `mysql_engine` · 빈 schema + migration fixture · `mysql` marker · `DAESINGO_MYSQL_URL`(test 전용, #282 관례) · `DAESINGO_REQUIRE_MYSQL=1`이면 skip 대신 실패
  - CI(P-2) — `python-tests.yml`에 MySQL 8.4 service · URL · require flag · MySQL 테스트 no-skip 확인 step
- **Expected files/modules:** `src/daesingo/common/db/` · `migrations/runtime/` · migration runner(`src/daesingo/common/db/migrate.py` 등) · `tests/conftest.py` 또는 `tests/common/db/conftest.py` · `.github/workflows/python-tests.yml` · `pyproject.toml` · `uv.lock`
- **Out of scope:** Runtime table(RT-03 · RT-07) · 배포 migration 실행 위치(RD-12f · RT-14) · case 테스트 파일 수정(case가 원하면 공용 fixture로 옮김 — 선택)
- **Acceptance criteria:** api · worker session isolation = READ-COMMITTED · lock wait = B-D1 · heartbeat 연결 = B-D9 값 · CI에서 MySQL 테스트 0 skip · (#282가 먼저 merge됐다면) case MySQL 테스트가 CI에서 실행됨
- **Integration tests:** 1205 주입 → 전체 rollback · 재시도 뒤 중복 전이 없음 · 1213 주입 → 재시도 · pool 고갈 → 「COMMIT 전」 분류 · COMMIT 응답 유실 주입 → 「결과 불명」 분류 · idle 연결 recycle · `wait_timeout` 초과 뒤 checkout 정상(Spike F) · 빈 DB에서 전 모듈 migration upgrade
- **Observability:** `runtime.db.lock_wait_timeout_count` · `…deadlock_count` · `…pool_timeout_count` · `…error_count` · `…tx_retry_count` · `…tx_retry_exhausted_count`
- **Decision gate:** 없음(RD-12f는 배포 실행 위치만 — RT-14)
- **PR boundary:** 2 PR — (a) 의존성 · engine · tx helper · harness · CI (b) Alembic 배치 · runtime env · runner

### RT-03 — `job_execution` schema · queue repository

- **Goal:** 실행 원장 = queue 단일 table과, 호출자 transaction에 참여하는 enqueue · 짧은 claim · 조건부 전이 · read port.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영
- **Dependencies:** RT-02(a)(b)
- **Inputs / SoT:** Tech Spec §4.2 · §4.3 · §4.5 · §6.3 · §12.1 · §12.4 · Ops §6-1(`trace_id` column) · JobExecution Contract §4 ~ §6 · §9 · Baseline B-W3 · B-L2(claim 시 lease) · B-L6 · Spike S1 · S2
- **Implementation scope:**
  - runtime migration — `job_execution`: Contract 필드 + 내부 column(`available_at` · lease owner/expiry · 마지막 heartbeat · 중단 요청 · case 반영 표식 · `trace_id` · dispatch용 `kind` · `case_id`). index `(status, available_at, execution_id)` · UNIQUE `(job_id, attempt)` · `job_id` index. **column 이름을 여기서 고정**(Tech Spec §4.2)
  - `enqueue(conn, job_records, trace_id)` — attempt 1 `QUEUED`, 호출자 tx 참여, commit 없음
  - `claim_one(engine, worker_id)` — 자기 짧은 tx: `LIMIT 1 FOR UPDATE SKIP LOCKED` → 조건부 UPDATE `RUNNING` + lease → commit. INSERT 없음
  - `finish(conn, execution_id, owner, …)` — `status=RUNNING ∧ lease owner=자기` 조건부, 영향 rows 반환
  - read port `read_executions(conn, job_ids)` — Contract 모양(내부 column 제외). `usage_refs`는 RT-07 전까지 `[]`
  - 전이 검증은 `common/job_execution.py` 전이표 재사용
- **Expected files/modules:** `src/daesingo/common/jobs/{schema,repository,read_port}.py` · `migrations/runtime/versions/0001_job_execution.py` · `tests/common/jobs/`
- **Out of scope:** worker loop(RT-04) · heartbeat · cancel(RT-05) · 다음 attempt 생성(RT-06) · usage projection(RT-07)
- **Acceptance criteria:** claim tx 안에 INSERT 없음 · claim 반환 시 tx commit 완료 · read port 출력이 JobExecution fixture validator 통과 · 내부 column 비노출
- **Integration tests:** 동시 claim(N connection × M row) 중복 0(Tech Spec §16 #1) · `available_at` 이전 claim 없음(#2) · 빈 queue → 오류 없이 없음 · 호출자 rollback → execution row 없음(#9의 Runtime 절반) · 같은 `(job_id, attempt)` 중복 거부 · 다른 owner · 비-RUNNING `finish` → 0 rows · RC에서 claim 중인 row가 다른 row의 terminal 전이를 막지 않음(Spike S1 재현)
- **Observability:** `runtime.db.claim_latency_ms`. `runtime.queue.wait_ms` · `runtime.execution.duration_ms`는 DB column으로 계산 가능해야 한다(RT-12 query)
- **Decision gate:** 없음
- **PR boundary:** 1 ~ 2 PR (schema · enqueue · read port / claim · finish)

### RT-04 — Worker core: claim loop · kind registry · dispatch · T1/T2 (E2E-0)

- **Goal:** Worker process가 queue를 돌려 handler를 실행하고 결과를 기록 · case에 넘긴다. Runtime만으로 닫히는 E2E-0을 통과한다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영 · Consult 유소연(T2 `ResultReflector` 모양)
- **Dependencies:** RT-03 · RT-01
- **Inputs / SoT:** Tech Spec §2 · §6.2(handler 밖 예외 = `RUNTIME_`) · §12 · §12.2 · §12.3 · Baseline B-W1 · B-W2 · B-Q1 ~ B-Q3 · B-D8(소진 규칙) · §0.1 P-3 · P-5
- **Implementation scope:**
  - `python -m daesingo.worker` entrypoint — RT-01 bootstrap → RT-02 engine. concurrency knob 없음(B-W2)
  - claim loop — 빈 결과 B-Q1 · 성공 직후 B-Q2 · DB 오류 B-Q3(process 유지)
  - 단일 kind registry(worker composition root) · 미등록 kind → claim 즉시 `FAILED`(`RUNTIME_` 접두어) · UsageRecord 없음
  - `ExecutionContext`(`execution_id` · `job_id` · `case_id` · `kind` · `attempt` · `trace_id` · cancel signal 자리 · usage sink 자리)
  - T1 — `SUCCEEDED`+`produced` / handler가 낸 모듈 taxonomy `FAILED` / handler 밖 예외 `RUNTIME_` `FAILED`. 기록 재시도는 B-D8, 소진 뒤 B-Q3 간격(lease 보유 확인은 RT-05가 붙임)
  - T2 — `ResultReflector` port(case 공개 반영 함수를 composition root가 주입) 호출 + 후속 enqueue + 반영 표식을 한 tx. **case 행 먼저 잠금**(P-5). case 쪽 T2 진입 함수(`execution_id`를 받는 반영 — 8-8)는 아직 없으므로 port 모양은 유소연과 맞추고 test는 fake로 한다
  - `runtime.retry.after_case_stopped_count`(Baseline §6) — attempt ≥ 2의 T2에서 case가 반영하지 않았을 때 emit. 반영 여부를 port 반환값으로 받을지 case 쪽 event로 대신할지는 8-8 설계 때 유소연과 정한다(case에 새 의무를 강제하지 않음)
  - 종료 신호 — 다음 idle 지점(claim 사이)에서 멈춘다. 실행 중 종료 처리는 두지 않는다 — Worker graceful shutdown은 Baseline NOT_BASELINED(RT-13 Gate)
  - kind → capability **dispatch registration test**(Tech Spec §16 Contract/Boundary) 틀 — registry에 등록된 kind만 dispatch되고 미등록은 `RUNTIME_`
- **Expected files/modules:** `src/daesingo/common/jobs/worker_loop.py` · `src/daesingo/worker/{__main__,registry,composition}.py` · `tests/common/jobs/` · `tests/worker/`
- **Out of scope:** heartbeat · lease 갱신 · cancel(RT-05) · sweep · retry · T2 재전달(RT-06) · usage(RT-07) · 실제 handler(RT-10)
- **Acceptance criteria:** **E2E-0** — enqueue → claim → dummy handler → `SUCCEEDED` → fake reflector 1회 → read port `SUCCEEDED`. handler 실행 중 DB tx가 열려 있지 않음
- **Integration tests:** 빈 queue에서 B-Q1 간격 claim(주입 sleep) · 성공 직후 즉시 claim · DB 중단 → loop 생존 · B-Q3 뒤 회복 · 미등록 kind → `FAILED`(`RUNTIME_`) · usage 0(Tech Spec §16 #14) · reflector 실패 → `SUCCEEDED` 유지 · 반영 표식 없음
- **Observability:** `runtime.execution.started` · `…completed`(correlation 필드 · `duration_ms` · `status`) · `runtime.reflect.failed` · `runtime.db.error_count`
- **Decision gate:** RD-09a — Classification §4.2가 Provisional 가정 시점을 M2(= RT-04 착수)로 둔다. RT-04는 domain service를 만들지 않지만(dummy handler) Gate를 옮기지 않는다 — **RT-04 착수 전 RD-09a Provisional 가정을 Register 절차(recording + runtime Joint, 「Issue needed: YES」)로 기록한다.** 가정 내용은 이 Plan이 정하지 않는다
- **PR boundary:** 2 PR (loop · registry · T1 / T2 port · E2E-0)

### RT-05 — Lease · heartbeat · fencing · 협력적 중단

- **Goal:** 실행 중 lease를 유지하고, 소유를 잃은 Worker는 결과를 commit하지 않으며, 사용자 중단이 checkpoint에서 실행을 멈춘다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영 · Consult 유소연(case 중단 command가 부르는 cancel port 모양)
- **Dependencies:** RT-04
- **Inputs / SoT:** Tech Spec §7.2 · §12.5 · JobExecution Contract §6 · §9 · Baseline B-L1 · B-L2 · B-L6 · B-D9 · B-X1 · §3.1 · §3.6 · Baseline §9 「Worker lifecycle」 · 「Cancellation」 행 · §0.1 P-3 · P-4
- **Implementation scope:**
  - heartbeat thread — B-L1 fixed-rate cadence · 동시 시도 최대 1(이전 시도 미완이면 그 tick 건너뜀 · 기록) · 시도 안 재시도 없음 · B-D9 전용 connection(끊기면 다음 시도에 재연결) · 조건부 UPDATE로 lease 갱신(B-L2 · DB 시각 B-L6) + 같은 갱신에서 중단 표식 읽기 · 0 rows → 소유 상실
  - fencing — T1이 lease owner 조건 · 소유 상실이면 결과 commit 안 함 · T1 재시도는 lease 보유 중에만(B-D8 소진 규칙)
  - Runtime cancel port `request_cancel(conn, job_ids)` — 호출자 tx 참여. `QUEUED` → 즉시 `CANCELLED` · `RUNNING` → 중단 표식만
  - in-process `CancelSignal` · handler용 `ctx.checkpoint()`(capability 사이에서만) · 멈춘 뒤 `RUNNING → CANCELLED` 조건부 · `CANCELLED` `produced=[]`(Tech Spec §12.5)
- **Expected files/modules:** `src/daesingo/common/jobs/{heartbeat,cancel}.py` · `tests/common/jobs/`
- **Out of scope:** sweep · STALE 판정(RT-06) · case 중단 command(case 8-9) · HTTP 배선(RT-08) · capability 내부 checkpoint(baseline 아님) · 강제 thread kill · provider 요청 강제 중단
- **Acceptance criteria:** heartbeat 오류 · timeout이 handler를 죽이지 않음 · handler 예외가 heartbeat thread를 남기지 않음 · 중단 관찰 지연이 기록됨
- **Integration tests:** heartbeat 시도가 tick보다 길 때 두 번째 DB 호출이 겹쳐 시작되지 않고 건너뛴 tick 기록 · 성공 heartbeat → `lease_expires_at` 연장 · lease를 다른 owner로 넘긴 뒤 heartbeat 0 rows → 결과 commit 없음(Tech Spec §16 #13) · `QUEUED` 중단 → 즉시 `CANCELLED` · usage 0(#7 · #12) · `RUNNING` 중단 → heartbeat 관찰 → checkpoint → `CANCELLED`(#12) · 중단과 완료 경합 → terminal 1개 · 중단 뒤 `SUCCEEDED`는 `SUCCEEDED` 유지(#8 · #12)
- **Observability:** `runtime.heartbeat.lag_ms` · `…attempt_ms` · `…skipped_tick_count` · `…consecutive_failures` · `runtime.cancel.observe_latency_ms` · `runtime.cancel.terminal_latency_ms`(DB) · 소유 상실 terminal 시도 event(= `runtime.stale.false_count` 원천)
- **Decision gate:** 없음
- **PR boundary:** 2 PR (heartbeat · lease · fencing / cancel)

### RT-06 — STALE sweep · 자동 retry · T2 재전달

- **Goal:** 죽은 Worker의 실행을 STALE로 정리하고 상한 안에서 다음 attempt를 같은 tx에 만들며, 반영되지 않은 terminal을 case에 다시 넘긴다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영
- **Dependencies:** RT-05
- **Inputs / SoT:** Tech Spec §6.2 · §6.3 · §7.2 · §7.3 · §12.2 · JobExecution Contract §5(`queued_at`) · Baseline B-L3 ~ B-L5 · B-R1 ~ B-R3 · §2.4 · §3.2 · Baseline §9 「Retry / Recovery」 행
- **Implementation scope:**
  - sweep — B-L3 조건 · 조건부 `RUNNING → STALE` + (상한 B-R1 미만 ∧ 중단 표식 없음이면) attempt+1 `QUEUED` · `available_at`(B-R2 · B-R3)을 **같은 tx**에서. UNIQUE `(job_id, attempt)`가 다중 sweeper 중복을 막음
  - sweep thread(B-L4, handler에 묶이지 않음) · startup sweep 1회 → 첫 claim(B-L5)
  - T2 재전달 scan — 반영 표식 없는 terminal을 startup + sweep 주기에 다시 reflector로(case 반영 함수가 `execution_id` idempotent — case 8-8)
  - sweep 주기 hook 등록 지점(RT-07 reconciliation이 등록)
  - pure logic unit — retry 판정 · backoff 계산 · stale 판정
- **Expected files/modules:** `src/daesingo/common/jobs/{sweep,retry_policy}.py` · `tests/common/jobs/`
- **Out of scope:** usage reconciliation 로직(RT-07)
- **Acceptance criteria:** STALE 판정은 lease 만료만 본다(실패 횟수 아님 — Baseline §2.3)
- **Integration tests:** heartbeat 없음 → lease 만료 뒤 sweep에서 STALE(#3) · STALE → 같은 `job_id` · 새 `execution_id` · attempt 2 `QUEUED` 한 tx(#4 · #10) · 마지막 허용 attempt(B-R1) STALE → 다음 attempt 없음 · 소진 기록 · backoff 동안 claim 없음(#10) · 중단 표식 + STALE → 다음 attempt 없음 · sweeper 2개 동시 → attempt 중복 없음(#5 · #10) · startup sweep이 lease 남은 row를 건드리지 않음 · heartbeat가 계속 성공하면 lease보다 긴 handler도 STALE 아님 · T1–T2 사이 Worker kill → 재시작 뒤 반영 정확히 1회(#15) · 실행 중 Worker kill → 재시작 → STALE → 다음 attempt 완료(subprocess kill)
- **선택:** 같은 subprocess 설정으로 fake kind의 api · worker 별도 process smoke를 RT-10보다 먼저 둘 수 있다 — fake handler 결과를 case가 process 밖에서 읽을 수 있는지(#284 정산 기록 등) 유소연과 확인한 뒤에만
- **Observability:** `runtime.stale.count` · `…detect_latency_s` · `runtime.retry.auto_count` · `…exhausted_count` · `runtime.reflect.redelivery_count` · `runtime.retry.after_case_stopped_count`(재전달 T2에서도 RT-04(b)와 같은 방식으로 emit) · `runtime.queue.wait_ms`(attempt ≥ 2 구분)
- **Decision gate:** 없음
- **PR boundary:** 2 PR (sweep · retry / T2 재전달 · kill 테스트)

### RT-07 — Usage ledger: in-flight · Final UsageRecord · reconciliation

- **Goal:** provider HTTP 시도 1회 = Final UsageRecord 1건을, Worker가 죽어도 관측값을 잃지 않고 정확히 한 번 남긴다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영 · Consult 서어진(sink 사용 모양 — SRCH-1 소비자). Runtime 쪽 `UsageSink` port까지가 이 Task다 — Search adapter 안의 배선은 SRCH-1(search Owner)
- **Dependencies:** RT-03(execution context · read port) · RT-06(sweep hook — reconciliation PR만). schema · Final append PR은 RT-02 뒤 병렬 가능
- **Inputs / SoT:** Tech Spec §3.3 · §4.5 · §11.1 ~ §11.4 · UsageRecord Contract §4 ~ §8 · #244 U-1 ~ U-4 · Baseline B-G1 · §2.12 · §0.1 P-7 · P-10
- **Implementation scope:**
  - runtime migration — `usage_inflight`(usage identity · execution · 관측값 · run 관계 · 상태) · `usage_record`(Contract 필드 typed column · usage identity PK/UNIQUE · `execution_ref` index · `token_usage` 「전부 null 또는 전부」 · total = input + output CHECK · `DECIMAL` amount + currency column). **`DECIMAL` precision/scale 고정**(P-10)
  - `UsageSink` port(#244 U-1 이름) — execution context에 묶여 worker composition root가 주입. `begin` = durable in-flight(실패 → 예외, 호출자는 HTTP를 보내지 않음) · `finish` = 관측값 durable · Run 관계 확정 뒤 Final 1건 append. `Decimal` ↔ 문자열만 · float 금지 · 초과 자릿수 거부 · `amount=null` 보존 · currency KRW 검증(Tech Spec §11.3)
  - reconciliation — terminal execution에 묶인 in-flight만(B-G1) · durable Run 관계가 있으면 그 `run_ref`, 실제 Run 미생성일 때만 `RUN_NOT_PRODUCED` · startup + sweep 주기(RT-06 hook에 등록)
  - P-7 늦은 관측 처리
  - read port `usage_refs` = `usage_record.execution_ref` projection(RT-03 read port 확장)
- **Expected files/modules:** `src/daesingo/common/usage/` · `migrations/runtime/versions/0002_usage.py` · `tests/common/usage/`
- **Out of scope:** Search adapter 배선(SRCH-1) · pricing/FX artifact(RD-08) · retention · `purge_case` 관계(RD-10c · d) · budget guard(case) · `SearchLedger` 정리(#153)
- **Acceptance criteria:** 정상 · 복구 경로가 같은 usage identity로 Final을 두 번 만들지 못함(DB 제약) · persistence 실패로 provider 재호출 없음
- **Integration tests:** begin 기록 실패 → fake provider 호출 0(#11) · 시작된 호출 N(in-call retry 실패 시도 · parsing 실패 포함) → Final N(#6) · finish 뒤 Run 확정 전 kill → 다음 sweep에서 관측값 보존 Final 1(#11) · dispatch 전 중단 → usage 0(#7) · 살아 있는 RUNNING의 in-flight는 reconciliation 대상 아님 · 초과 자릿수 거부 · `amount=null`이 0으로 저장되지 않음 · KRW 아닌 currency 거부 · token CHECK 위반 거부 · read port `usage_refs` projection · recovery finalize 뒤 늦은 `finish` → Final 불변 · 관측값 보존 · event 기록(P-7)
- **Observability:** `runtime.usage.recovered_count` · `…inflight_count` · `…inflight_oldest_age_s`(DB) · 늦은 관측 event
- **Decision gate:** RD-08 — **blocker 아님**(`pricing_id` placeholder · `amount=null`). RD-10c · d — blocker 아님
- **PR boundary:** 2 ~ 3 PR (schema · `DECIMAL` · Final append / sink · finalize / reconciliation · sweep hook)

### RT-08 — API composition root: `/cases` · `/commands` · `/view` · `/health/*`

- **Goal:** HTTP API Contract의 JSON · health surface를 Contract 표 그대로 구현하고 command + enqueue를 한 commit으로 묶는다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance · HTTP Contract Owner 김준영 · Consult 유소연(case 함수 호출 · 잠금 순서) · Consumer 통지 신유민
- **Dependencies:** RT-01 · RT-02 · RT-03 · case #282 · #284 · 8-10(read port 주입 지점). 중단 command 경로(PR d)만 RT-05(b) cancel port + case 8-9 뒤 — RT-09는 (d)를 기다리지 않는다
- **Inputs / SoT:** HTTP API Contract §2 · §3 · §5.1 · §5.3 · §5.4 · §5.7 · §6 · §7 · Tech Spec §12.1 · §12.4 · §12.5 · §13 · §14 · Baseline B-W4 · B-U2 · B-U5 · B-D3 · B-D4 · B-D8 · B-H1 ~ B-H3 · §0.1 P-5 · P-9
- **Implementation scope:**
  - FastAPI app factory · uvicorn process 수 B-W4 · Contract §3.3 envelope · §3.4 status 표 · 프레임워크 기본 오류 body 차단(404 · 405 · 검증 오류 → envelope)
  - `POST /cases` — tx → `create_case` → commit → `get_view` → `201` + `Location`
  - `POST /commands` — `415` · B-U2 `413` · JSON 파싱 `400` · path/body `case_id` 불일치 `400` → tx: `execute_command(conn)` → `appended_job_records`마다 `enqueue(conn)` → commit → 표 조회로 status → body 그대로
  - 중단 command 배선(PR d) — 같은 tx에서 case가 돌려준 job 목록으로 `request_cancel(conn)`
  - `GET /view` — read port 주입한 `get_view` → body 그대로 · `404`
  - `/health/live` · `/health/ready`(B-H1 · B-H2 · B-H3, provider · Worker 미검사, 실패 dependency는 로그에만)
  - DB 실패 매핑 — RT-02 분류를 `503` / `500`으로(B-D8)
  - 요청마다 `trace_id` → enqueue에 전달(Ops §6-1)
- **Expected files/modules:** `src/daesingo/api/{app,errors,routes_cases,routes_commands,routes_view,health,composition}.py` · `tests/api/`
- **Out of scope:** `/sources` · `/frames` · `/assets`(RT-11) · 인증(A2) · CORS · TLS(RD-14) · OpenAPI를 authority로 두기(Contract §8)
- **Acceptance criteria:** status는 append 목록 · case 응답 표만으로 결정(kind 미참조) · Contract §7 불변조건 1 ~ 5 · 10 · 11 · 12
- **Integration tests (API contract test, MySQL):** append ≥ 1 → `202` + `Location` · 0 → `200` · `202`의 `case_view.running_jobs` 비어 있지 않음(§7-2, case #284) · `200`/`202`/`404`/`409`/`422` body = case-command 응답과 필드 동일 · enqueue 실패 주입 → `503` · JobRecord · execution 둘 다 없음(Tech Spec §16 #9) · pool 고갈 → `503` · COMMIT 결과 불명 주입 → `500`(`503` 아님) · `400` · `413` · `415` envelope(`case_view=null`) · 미정의 경로 `404 http.not_found` · `405` · 없는 case view → `404` · ready: DB 중지 → B-H3 안 `503` · API pool 고갈 중에도 ready 응답 · mount 읽기 전용 → `503` · provider 호출 0 · 응답에 `execution_id` · `attempt` · lease 없음 · 중단 command → `200` + `QUEUED` job이 같은 commit에서 `CANCELLED`(PR d)
- **Observability:** `api.request.latency_ms` · `api.view.latency_ms` · `api.view.request_rate` · `api.request.rejected_413_count` · `api.ready.duration_ms` · `api.ready.unavailable_count` · access event(`trace_id` · `case_id` · status)
- **Decision gate:** 없음
- **PR boundary:** 4 PR — (a) app skeleton · envelope · health(case 의존 없음) (b) `/cases` · `/view` (c) `/commands` · enqueue (d) 중단 command 배선

### RT-09 — 첫 비동기 E2E (integration acceptance)

- **Goal:** §4 critical path를 실제 MySQL 위 자동 테스트로 통과한다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance · HTTP Contract Owner 김준영 · Consult 유소연(case T2 반영 경로)
- **Dependencies:** RT-04 · RT-08(b)(c) · case #282 · #284 · **case T2 진입 함수(8-8)** · 8-10. RT-08(d) · RT-05 · RT-06은 기다리지 않는다
- **Inputs / SoT:** Tech Spec §2 · §12.1 · §12.2 · HTTP Contract §5.3 · §5.4 · §6 · §7 · CaseView Contract B절 §10 불변조건 5 · Ops §6-1
- **Implementation scope:** `POST /cases` → JobRecord를 append하는 command(§4) → `202` → Worker loop(thread · 별도 engine) claim → test 등록 fake capability handler → T1 `SUCCEEDED` → T2 case 반영 → `GET /view` polling → `running_jobs=[]` · 해당 progress 반영. single process 이유는 §4
- **Expected files/modules:** `tests/e2e_runtime/test_async_e2e.py`(MySQL marker) · test 전용 composition helper
- **Out of scope:** 실제 provider · upload · 별도 process(RT-10 · RT-13) · recovery 시나리오(RT-06에서 Runtime 수준으로 검증)
- **Acceptance criteria:** CI(MySQL)에서 통과 · API 요청의 `trace_id`가 Worker execution event에 이어짐 · read port에서 attempt 1 `SUCCEEDED` · 응답에 Runtime 내부 필드 없음
- **Integration tests:** 위 경로 1건 + `202` 직후 `running_jobs`가 비지 않아 polling이 이어짐
- **Observability:** 위 경로 event 전부가 한 `trace_id`로 조회됨
- **Decision gate:** 없음
- **PR boundary:** 1 PR

### RT-10 — Worker composition root: 실제 kind handler 등록 · cross-process E2E

- **Goal:** case가 발주하는 kind를 각 모듈 public capability 호출로 연결하고, api · worker를 별도 process로 띄운 비동기 E2E(fake provider)를 통과한다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영 · Consult 서어진(search capability · sink) · 신유민(readout 1 execution = public 호출 1회) · 유소연(handler가 읽는 case 입력). recording export는 Implementer가 recording Owner를 겸한다
- **Dependencies:** RT-09 · RT-05(checkpoint) · RT-07 · SRCH-1 · REC-1 · case 8-13(source를 recording 공개 함수로 조회) · 8-16(`HINT_EXTRACT` 반영 배선) · **Gate: case 8-6 2단계**(§7) · RD-09a Provisional 가정(RT-04 착수 전 기록 — 실제 handler가 그 가정을 따른다)
- **Inputs / SoT:** Tech Spec §12 · §12.3 · §15.1 · JobExecution Contract §9-9 · case JobRecord kind 목록(`case/jobs.py: JOB_KINDS`, #286 `HINT_EXTRACT`)
- **Implementation scope:** kind별 handler — 입력 조회(공개 함수) → capability 호출 → capability 사이 `checkpoint()` → `produced`. readout 계열은 public 호출 정확히 1회. 모듈 config · secret은 env mapping을 각 모듈 factory에 주입(해석은 모듈). execution마다 `UsageSink` 주입. recording export 2종은 public capability가 생긴 뒤 등록(그 전에는 미등록 → `RUNTIME_` `FAILED`, Tech Spec §12.3)
- **Expected files/modules:** `src/daesingo/worker/handlers/` · `tests/worker/`
- **Out of scope:** capability 내부 변경 · capability 내부 cancel checkpoint · 모듈 결과 저장 위치 설계(case 8-6 2단계 · 각 모듈)
- **Acceptance criteria:** kind별 handler offline test(fake provider) · readout handler public 호출 정확히 1회 · case `JOB_KINDS`와 registry 대응 test(Tech Spec §16 dispatch registration) · api · worker 별도 process 비동기 E2E 통과
- **Integration tests:** cross-process E2E(fake provider) · 실제 handler의 중단 checkpoint
- **Observability:** handler 시작/끝 event(kind · `execution_id`) · capability 소요
- **Decision gate:** case 8-6 2단계(모듈 결과가 process 밖 어디에 남고 무엇으로 읽히는지 — case 주도 설계) · RD-09a(RT-04에서 기록한 Provisional 가정을 따름)
- **PR boundary:** kind 묶음별 2 ~ 3 PR

### RT-11 — Media HTTP: `POST /sources` · frames · assets

- **Goal:** 원본 upload를 응답 전에 durable하게 등록하고, CaseView ref의 이미지 · 신고용 파일을 case 격리를 지켜 내보낸다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance · HTTP Contract Owner 김준영 · Consumer 통지 신유민. recording 경계는 REC-1 공개 surface만 소비한다(Implementer가 recording Owner를 겸해도 recording 내부를 route에서 읽지 않는다)
- **Dependencies:** RT-08(a)(b) · case #282(upload의 case 확인 · 연결이 같은 tx) · REC-1(upload PR: 영속 등록 · 원본 파일명 · 실패 taxonomy · case 연결 / frames · assets PR: 소유 조회 · DerivedAsset read · 이미지 형식)
- **Inputs / SoT:** HTTP Contract §3.5 · §5.2 · §5.5 · §5.6 · §7-6 ~ §7-9 · Ops §4-2(RD-17) · Tech Spec §13 · Baseline B-U1 · B-U3 · B-U4 · §2.6 아래 주석 · B-F1 · B-F2 · §2.8 · §0.1 P-9
- **Implementation scope:**
  - upload — multipart `file` part 1개 + `filename` 필수(아니면 `400`) · `415` · `INTAKE` 아님 → `409`(등록 rollback) · body limit middleware(B-U1, `Content-Length` 없어도 `413`, Starlette 버전 pin) · 수신 idle B-U3 · 전체 B-U4 → 연결 종료 · 공유 mount staging → `fsync` → same-mount publish → 짧은 tx(case 확인 · recording 등록 · `record_source_registered`) → commit → `201`. 수신 중 DB connection 미보유
  - 실패 매핑 — recording `UNSUPPORTED_MEDIA` → `422` · `TEMPORARY_FAILURE` → `503` · 그 밖 → `500`(메시지 · 내용으로 추론 금지)
  - frames — 소유 확인(짧게, connection 반환) → 동시 생성 제한 B-F2 → `read_frame` → 실제 `Content-Type` · `Content-Length` · B-F1 `Cache-Control` · §5.5 오류표
  - assets — 소유 · DerivedAsset 확인 → bytes → `Content-Type` · `Content-Length` · `Content-Disposition`(서버 ASCII 이름, 개인정보 없음) · `private, no-store` · §5.6 오류표
- **Expected files/modules:** `src/daesingo/api/{routes_sources,routes_media,upload}.py` · `src/daesingo/common/storage/` · `tests/api/`
- **Out of scope:** FrameRef 저장 방식(recording) · Range(`206`) · retention(RD-10) · 동시 upload 제한 · disk guard(RD-15c)
- **Acceptance criteria:** Contract §7-6 ~ §7-9 · 로그에 경로 · 파일명 없음
- **Integration tests:** B-U1 + 1 byte → `413`(`Content-Length` 유무 둘 다) · idle 초과(test interval) → 연결 종료 · 등록 없음 · staging 잔여 · staging과 final의 `st_dev` 동일 · `fsync` 호출 · publish 뒤 commit 전 crash → row 없는 파일만 남음 · `201`은 commit 뒤 · 응답 유실 뒤 `file_count` = N+1 · `409` 뒤 등록 없음 · `422`/`503`/`500`이 recording 실패 종류로만 갈림 · upload · frame 처리 중 pool checkout 0 · frame header · B-F2 초과 동시 요청은 대기 · 다른 case의 `frame_ref` · `asset_ref` → `404 http.not_found`(존재 비노출) · ref unavailable → `404 http.ref_unavailable` · asset header
- **Observability:** `api.upload.bytes` · `…duration_ms` · `…throughput_bps` · `…aborted_count{reason}` · `…rejected_413_count` · status별 실패 · `api.frame.latency_ms` · `…wait_ms` · `…request_rate` · `api.asset.download_latency_ms` · `…bytes`
- **Decision gate:** 없음
- **PR boundary:** 3 PR (upload / frames / assets)

### RT-12 — 운영 위생: cleanup · 관측 집계

- **Goal:** ref에 연결되지 않은 운영 잔여물만 안전하게 지우고, Baseline §6 지표를 local · integration에서 DB query + structured log로 볼 수 있게 한다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영. P-6(orphan 판정 조회)은 recording Owner 판단이다 — Implementer와 같은 사람이어도 Gate는 유지하고 판단을 recording 문서에 남긴다
- **Dependencies:** RT-11(upload staging/publish 배치) · RT-06 · RT-07(지표 원천) · (orphan 부분만) P-6 확인
- **Inputs / SoT:** Baseline B-C1 ~ B-C4 · §2.9 · §6 · §9 「Cleanup」 · 「Observability」 행 · Ops §6 · §7 · §8 · §14 · RD-11b · §0.1 P-6
- **Implementation scope:**
  - cleanup — api: staging(B-C1) · orphan publish(B-C2 — P-6 Gate 통과 뒤에만) · api temp root(B-C3). worker: worker temp root(B-C3). service별 temp root를 recording `temp_root`에 주입. startup + 주기 scan(B-C4) · startup에도 나이 조건 유지 · 로그는 건수 · bytes만
  - 관측 — DB 집계 query module(queue wait p50/p95 attempt 구분 · oldest queued · execution duration · stale · retry · cancel terminal latency · usage in-flight) · Baseline §6의 log 출처 지표마다 emit event가 있는지 확인하는 catalog test · 로그 privacy test(경로 · payload · 원문 key 없음)
- **Expected files/modules:** `src/daesingo/common/storage/cleanup.py` · `src/daesingo/common/jobs/metrics.py`(또는 `scripts/runtime_metrics.py`) · `tests/common/`
- **Out of scope:** Product retention · purge(RD-10) · disk free guard(RD-15c) · CloudWatch transport(RD-13a) · 지표 정기 기록 방식(RD-13b)
- **Acceptance criteria:** 진행 중 upload staging(mtime 최신) · 등록된 파일 · 나이 미달 파일은 지우지 않음 · 집계 query가 seed DB에서 값 반환 · catalog test 통과
- **Integration tests:** 위 cleanup 안전성 3종 · orphan 판정이 recording 조회를 거침 · 집계 query
- **Observability:** `storage.staging.*` · `storage.orphan.*` · `storage.temp.*` · `storage.root.free_bytes`
- **Decision gate:** orphan 정리 부분 — recording Owner의 등록 조회 capability 확인(P-6, 새 요청). RD-13b(정기 기록을 할 때만 — 이 Task 범위 밖) · RD-10(제외됨)
- **PR boundary:** 2 PR (cleanup / 관측 집계 · catalog)

### RT-13 — Docker / Compose local runtime

- **Goal:** api · worker · mysql을 Compose로 띄워 별도 container 사이에서 Runtime 경로가 동작한다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영
- **Dependencies:** RT-09 · RT-02(b) · RT-06(재시작 복구 acceptance) · RT-11(upload) · **Gate: RD-12a · RD-12g · Baseline NOT_BASELINED Compose 값**(§7)
- **Inputs / SoT:** Ops §4 · §4-1 · §4-2 · §5 · Tech Spec §4.4 · §15.2 · Baseline B-W1 · B-W4 · B-O1 · B-H3(healthcheck timeout 조건) · §2.6 주석(spool non-tmpfs)
- **Implementation scope:** Dockerfile(Python 3.12 · `uv sync --locked` · ffmpeg) · compose(api · worker · mysql 8.4 named volume · 공유 media volume을 api · worker 같은 경로 · 같은 numeric UID · env 파일 secret mount + `DAESINGO_ENV_FILE`, `environment:`로 값 주입 안 함 · api/worker 전 migration 단계 · ready healthcheck · B-O1 `logging:`)
- **Expected files/modules:** `Dockerfile` · `compose.yaml` · `deploy/` 또는 `docker/`(배치는 RD-12a) · `.env.example` key 이름
- **Out of scope:** EC2 · registry · SSM(RT-14) · production restart policy(RD-13c)
- **Acceptance criteria:** clean 상태 `compose up` → migration(one-shot, RT-02 runner) → api ready → command · view smoke · api upload 파일을 worker가 읽음 · worker 재시작 → STALE → 다음 attempt 관찰 · `docker inspect` env에 secret 없음 · Starlette spool 위치가 tmpfs가 아님(Baseline §2.6) · healthcheck timeout > B-H3
- **Integration tests:** Compose smoke(로컬 · 수동 또는 CI 별도 job — 일반 PR gate 편입은 이 Task에서 정함)
- **Observability:** container log rotation 확인
- **Decision gate:** RD-12a(image · service · entrypoint 구조 — local migration one-shot service 포함) · RD-12g(MySQL volume baseline) — Classification §4.2의 M4 Provisional 대상 · Baseline §5 NOT_BASELINED Compose 값(healthcheck interval · `stop_grace_period` · Worker graceful shutdown — Baseline이 M4 Compose slice로 둠). RD-12f(배포 migration 시점 · 순서 · restore) · RD-12h(post-deploy smoke)는 M6 — RT-14
- **PR boundary:** 2 PR (Dockerfile · compose / migration 단계 · smoke)

### RT-14 — EC2 배포 · 운영 (Issue는 RT-13 착수 때 생성)

- **Goal:** 카테캠 EC2 1대에 Compose stack을 OIDC → SSM으로 배포하고 revision · health · smoke · rollback을 식별 가능하게 한다(M6 → P2).
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영
- **Dependencies:** RT-13 · **Gate: RD-12b ~ e · RD-12h · RD-13a · RD-13c · RD-13d · RD-11a · RD-07c 확인 · RD-14(외부 공개 시)**
- **Inputs / SoT:** Ops §2 · §2-1 · §4-1 · §8 · §9 · §19 · Runbook 전체 · Baseline B-O1
- **Implementation scope:** OIDC 인증 전용 workflow → 배포 workflow(새 파일) · EC2 배포 script(Parameter Store → 보호 파일 → migration → compose up) · revision 식별 · post-deploy health/smoke · rollback · backup/restore · log transport · restart policy
- **Out of scope:** capacity 확장(RD-15)
- **Decision gate:** 위 Gate가 모두 닫히거나 Provisional이 정해진 뒤 착수. **local Runtime core를 막지 않는다**
- **PR boundary:** Gate 결정 뒤 이 Plan을 갱신해 정한다
- **Issue:** 지금 만들지 않는다 — 막는 Decision이 5개 이상 열린 채 Issue를 만들면 범위가 고정되지 않은 Task가 생긴다. RT-13 착수 시점에 RD-12 Gate와 함께 연다. 만들 때 Implementer 정철원 · Owner / Acceptance 김준영(§12)

### RT-15 — CI 품질 gate · Runtime import 경계

- **Goal:** Register 「Implementation Gap」의 CI 묶음(검수 C-10 · Ops §19 목표 순서 6 ~ 8)을 Runtime 코드부터 닫는다.
- **Responsibility:** Implementer 정철원 · Owner / Acceptance 김준영
- **Dependencies:** RT-01 · RT-02(a) — 대상 package가 생긴 뒤. critical path 아님
- **Inputs / SoT:** Ops §19 「목표 확장 순서」 · Register 「Implementation Gap」(C-10 · Ruff · type checker · secret scan) · Architecture 「package import cycle을 만들지 않는다」 · Tech Spec §12 금지 목록 · Tech Spec §16 Contract/Boundary
- **Implementation scope:**
  - Ruff · type checker — **Runtime 소유 경로(`common/` · `api/` · `worker/` · `migrations/runtime/`)에만** 먼저 건다. repo 전체 확대는 다른 Owner 코드에 새 의무를 만들므로 이 Task가 하지 않는다(팀 합의 뒤 별도). type checker 도구 선택은 이 Task의 PR이 근거와 함께 정한다(Register가 「Implementation Plan의 CI 묶음 안에서」로 넘김)
  - Runtime import 경계 검사 — 이미 있는 Architecture 규칙만 기계화: `common/{jobs,usage,db,config,logging,storage}`는 domain 모듈을 import하지 않는다 · domain 모듈은 `api` · `worker`를 import하지 않는다. 금지 문자열 목록의 원문은 [`ownership.md`](../management/ownership.md) §6이므로 그 표와 `scripts/check_boundaries.py`를 함께 갱신한다(새 규칙이 아니라 기존 원칙의 검사 추가). domain 폴더에 검사가 추가되므로 PR에서 각 모듈 Owner에게 통지한다
  - Ops §19 목표(root Ruff · repo-wide type checker)의 repo 전체 확대는 이 Task 뒤 후속(Owner 김준영, 팀 합의 필요)으로 남긴다
  - secret scan — pre-deploy gate(M9) 전에 둔다. 일반 PR gate에 넣을지는 오탐률을 보고 이 Task에서 정한다
- **Expected files/modules:** `pyproject.toml`(tool 설정) · `.github/workflows/`(새 step 또는 새 파일 — 운영진 소유 3개 제외) · `scripts/check_boundaries.py` · `docs/management/ownership.md` §6
- **Out of scope:** 다른 모듈 경로의 lint · type 정리
- **Acceptance criteria:** Runtime 경로 lint · type 0 error로 CI 통과 · 경계 위반 fixture가 검사에 걸림 · 기존 boundary/contract 검사 PASS 유지
- **Integration tests:** 없음(정적 검사)
- **Observability:** 해당 없음
- **Decision gate:** 없음
- **PR boundary:** 2 ~ 3 PR (Ruff · type / import 경계 / secret scan)

### REC-1 — recording 영속화 · HTTP/Worker용 capability (recording Owner)

- **Goal:** api · worker 두 process가 같은 recording 상태를 보고, HTTP route와 cleanup이 필요한 공개 capability를 recording이 제공한다.
- **Responsibility:** Owner · Implementer 정철원(recording — 변경 없음) · Consumer 김준영(api 소비자 — deferred review, merge gate 아님) · Consult 유소연(case ↔ asset 연결 의미)
- **Dependencies:** RT-02(DB 기반 · Alembic 배치)
- **Inputs / SoT (모두 기존 의무):** Ops §4-2 · #246(RD-17 후속 — recording MySQL repository · FrameRef durability · persistent 목록) · HTTP Contract §9.1(원본 파일명 인자 · 등록 실패 taxonomy 세분화 · ref → case 소유 조회 · DerivedAsset bytes · 형식 read · FrameRef 이미지 형식) · Baseline B-C3(`temp_root` 주입 — 기존 인자). orphan 판정용 등록 조회(P-6)는 **여기 포함하지 않는다** — 새 요청이라 RT-12 Gate에서 따로 확인한다
- **Implementation scope (모양은 recording이 정한다):** recording MySQL repository(호출자 `Connection` 참여 · 자체 commit 없음) · persistent ref 복원 · 원본 파일명을 받는 등록 · `UNSUPPORTED_MEDIA` / `TEMPORARY_FAILURE` 구분 · `frame_ref` / `asset_ref` → case 소유 조회 · DerivedAsset bytes · `Content-Type` · FrameRef bytes vs 재생성(recording 선택)
- **Expected files/modules:** `src/daesingo/recording/` · `migrations/recording/`
- **Out of scope:** retention · purge 정책(RD-10) · Object Storage(RD-15d)
- **Acceptance criteria:** 새 `RecordingService` 인스턴스(같은 DB)가 SourceAsset · CaseView FrameRef · DerivedAsset을 다시 등록 없이 역참조 · 호출자 rollback → 등록 없음 · 다른 case ref → 소유 아님
- **Decision gate:** 없음(RD-09는 RT-10 Gate)
- **PR boundary:** recording이 정한다. 소비자 순서로 나누기를 권장 — ① MySQL repository · persistent 복원 ② 등록 입력(원본 파일명 · taxonomy · case 연결 — RT-11(a)) ③ 소유 조회 · DerivedAsset read · 이미지 형식(RT-11(b)(c)). 범위가 커서 한 PR로 묶지 않는다

### SRCH-1 — Search provider 호출을 Runtime `UsageSink`에 연결 (search Owner)

- **Goal:** Search adapter가 provider HTTP 시도마다 begin/finish를 남겨 RT-07이 Final UsageRecord를 만들 수 있게 한다.
- **Owner:** Primary 서어진(search) · Review 김준영
- **Dependencies:** RT-07(sink port PR)
- **Inputs / SoT (모두 기존 의무):** #244 U-1 ~ U-4(Search surface 결정 — 시도마다 `UsageSink` begin/finish · KRW 정규화는 Search · 요율 미확정 = `amount=null`) · Tech Spec §11.1 · §11.3 · UsageRecord Contract
- **Implementation scope (모양은 search가 정한다):** coarse · fine · diagnostic · intent(#277) 경로의 provider HTTP 시도마다 begin(실패 → HTTP 없음) · finish(성공/실패 · 관측값) · Run 관계 · `usage_id` → Run `usage_refs` · 요율 기본값 0.0과 미확정 구분 · `SearchLedger`는 Search 내부로 유지(#153). Runtime 밖(eval · CLI)에서 Search를 부를 때 쓸 기본 sink는 search가 정한다(eval 김대원 Consult — #244 informed)
- **Out of scope:** pricing/FX artifact(RD-08) · ledger 이름 정리(#153)
- **Acceptance criteria:** fake sink에서 HTTP 시도 N → begin/finish N · begin 실패 → provider 미호출 · 요율 미설정 → `amount=None`
- **PR boundary:** search가 정한다

### 6.1 다른 Owner의 기존 작업 — 이 Plan의 dependency (Issue를 새로 만들지 않음)

case는 자기 작업을 [`design-refinement-w7-baseline.md`](../modules/case/design-refinement-w7-baseline.md) 8순위로 이미 추적한다. 이 Plan은 번호만 가리킨다.

| case 항목 | 막는 Task | 상태 (2026-10-06) |
| --- | --- | --- |
| 8-6 1단계 CaseStore MySQL | RT-08(b) · RT-09 | PR #282 open |
| 8-11 `running_jobs` case 계산 | RT-08(c) `202` 불변조건 · RT-09 | PR #284 open (#282 커밋 포함) |
| 8-8 반영 함수 `execution_id` idempotent(= case T2 진입) | RT-04(b) port 모양 Consult · RT-06 실제 배선 · RT-09 | 미착수 |
| 8-10 JobExecution read port 연결 | RT-08(b) · RT-09 | 선택 규칙 선반영 · 연결 미착수 |
| 8-9 중단 command · 중단 job 집합 guard | RT-08(d) 중단 경로 | 미착수 |
| 8-1 분석 시작 command | RT-09 진입 command(없으면 대체 — §4) | Draft §11 초안 |
| 8-6 2단계 모듈 결과 영속 · adapter 제거 | RT-10 · M5 | 설계 전 |
| 8-13 source를 recording 공개 함수로 조회 | RT-10 | 미착수 |
| 8-16 `HINT_EXTRACT` 결과 반영 배선 | RT-10 | 반영 함수만 선반영 |

web(신유민)은 RT-08 · RT-11 merge 뒤 HTTP API Contract §6 흐름으로 실연동한다 — 이미 Contract Consumer로 정해진 역할이며 새 Task가 아니다.

---

## 7. Decision gates

열린 Decision이 **실제로** 막는 지점만 적는다. Timing · State는 바꾸지 않는다(Register · Classification 소유).

| Decision | 필요 시점 | 막는 Task | 현재 blocker? |
| --- | --- | --- | --- |
| RD-12a — image · Compose service · entrypoint 구조 (local migration one-shot 포함) | RT-13 착수 전 (M4 Provisional) | RT-13 | 아니오 (RT-09 뒤) |
| RD-12g — MySQL volume · backup baseline | RT-13 volume 정의 전 (M4 Provisional) · backup은 RT-14 | RT-13 · RT-14 | 아니오 |
| Baseline §5 NOT_BASELINED — Compose healthcheck · `stop_grace_period` · Worker graceful shutdown | RT-13 (Baseline이 M4 Compose slice로 둠) | RT-13 | 아니오 |
| RD-12f — 배포 migration 시점 · 순서 · restore · DB 접속 출처 | RT-14 (M6) | RT-14 | 아니오. local · CI는 RT-02 runner(명시 인자) |
| RD-12h — post-deploy health · 외부 smoke | RT-14 (M6) | RT-14 | 아니오 |
| RD-12b ~ e — artifact 전달 · tag · SSM 명령 · rollback | RT-14 착수 전 | RT-14 | 아니오 |
| RD-13a — production log transport | remote log 구현 전 | RT-14 | 아니오 (local은 stdout + B-O1) |
| RD-13b — 지표를 보는 방식(수동 query / 정기 기록) | 정기 기록 구현 전 | RT-12의 확장분(범위 밖) | 아니오 (query는 RT-12) |
| RD-13c — restart policy · health alert | production restart policy 전 | RT-14 | 아니오 |
| RD-13d — Worker 상태 운영 노출 | RT-14 운영 노출 전 | RT-14 | 아니오 (heartbeat lag는 RT-05 log) |
| RD-11a — log 보관 기간 · CloudWatch retention | RT-14 | RT-14 | 아니오 |
| RD-07c 확인 — EC2 role의 Parameter Store 권한 | M6 전 | RT-14 | 아니오 |
| RD-09a — Worker 안 domain service 인스턴스 범위 (Provisional 가정) | **RT-04 착수 전**(Classification §4.2 M2 — Gate를 옮기지 않음) | RT-04 · RT-10 | **첫 batch는 막지 않음 · 다음 batch(RT-04)의 blocker** — Register 「Issue needed: YES」(recording + runtime Joint)로 가정을 기록한다. 내용은 이 Plan이 정하지 않는다 |
| case 8-6 2단계 — 모듈 결과 process 밖 영속 · 조회 (case 주도, 새 RD 아님) | 실제 handler · cross-process E2E 전 | RT-10 · M5 | 아니오 (첫 비동기 E2E는 single process) |
| P-6 — orphan 판정용 recording 등록 조회 (새 요청 — recording Owner 확인) | RT-12 orphan 부분 착수 전 | RT-12 일부 | 아니오 |
| RD-15a — concurrency > 1 | concurrency ≥ 2 실험 전 | 이 Plan 범위 밖(B-W2 = knob 없음) | 아니오 |
| RD-15c — disk guard · capacity threshold | disk guard 구현 전 | 이 Plan 범위 밖(RT-12는 관측만) | 아니오 |
| RD-10 — Product retention · purge | retention · purge 구현 전 | 이 Plan 범위 밖(RT-12는 운영 잔여물만) | 아니오 |
| RD-08 — pricing/FX artifact | pricing/FX 운영 전 | RT-07 placeholder로 진행 | 아니오 |
| RD-14 — public endpoint · TLS | 외부 공개 · 사용자 데이터 전 | RT-14 일부 | 아니오 |

**새 Decision: 없음.** case 8-6 2단계는 Runtime 결정이 아니라 case가 이미 추적하는 설계 항목(case-store-mysql §1 D1)이라 RD로 올리지 않았다.

---

## 8. Integration test matrix

### 8.1 Test pyramid

| 층 | 무엇 | 실행 | 담당 Task |
| --- | --- | --- | --- |
| Unit | config 검증 · 전이표 · retry/backoff · stale 판정 · heartbeat tick/skip(주입 clock) · status 표 · envelope | 기존 pytest(PR gate) | RT-01 · RT-04 ~ RT-06 · RT-08 |
| MySQL integration | engine · tx 재시도 · claim · 조건부 전이 · sweep · usage | `python-tests.yml` + MySQL service(P-2, PR gate) | RT-02 · RT-03 · RT-05 ~ RT-07 · RT-12 |
| API contract | Contract §3.4 · §5 · §7을 TestClient로 | 같은 gate | RT-08 · RT-11 |
| Runtime async integration | Worker loop thread · short interval config · subprocess kill | 같은 gate(여유 있는 상한) | RT-04 ~ RT-07 · RT-09 |
| Compose smoke | 별도 container · 공유 volume | 수동 / 별도 job(PR gate 편입은 RT-13에서 정함) | RT-13 · RT-10 cross-process |
| Real E2E | 실제 provider · 실제 영상 | 일반 PR gate 밖 — workflow §9 | §9 |

queue · transaction · lease · locking · upload filesystem은 mock으로 끝내지 않는다 — 위 MySQL · filesystem 층에서 검증한다.

### 8.2 핵심 테스트 → Task

| 테스트 | 출처 | Task |
| --- | --- | --- |
| config 불변조건 위반 → startup non-zero · 값 미기록 | Baseline §9 Config | RT-01 |
| 1205/1213 → 전체 rollback · 재시도 · 중복 전이 없음 | Baseline §9 Persistence · B-D8 | RT-02 |
| pool 고갈 · `wait_timeout` 뒤 checkout · recycle | Baseline §9 · Spike F | RT-02 |
| 동시 claim 중복 0 | Tech Spec §16 #1 | RT-03 |
| `available_at` 이전 claim 없음 | #2 | RT-03 |
| command = JobRecord + attempt 1 `QUEUED` 한 commit · 실패 시 둘 다 없음 | #9 | RT-03(Runtime 절반) · RT-08 |
| 미등록 kind → `FAILED`(`RUNTIME_`) · usage 0 | #14 | RT-04 |
| 빈 queue claim 주기 · DB 오류 backoff | Baseline §9 Worker | RT-04 |
| heartbeat 겹침 없음 · 건너뛴 tick 기록 | Baseline §9 Worker · B-L1 | RT-05 |
| heartbeat 성공 → lease 갱신 | Baseline §9 Worker | RT-05 |
| 소유 상실 → 결과 commit 없음 | #13 | RT-05 |
| QUEUED 중단 즉시 · RUNNING checkpoint · 경합 1개 | #12 · #7 · #8 | RT-05 |
| heartbeat 없음 → STALE | #3 · Baseline §9 | RT-06 |
| STALE → B-R1 상한까지만 attempt 생성 · backoff 중 claim 없음 | #4 · #10 · B-R1 | RT-06 |
| 다중 sweeper 중복 없음 · sweep idempotent | #5 · #10 | RT-06 |
| 중단 + STALE → retry 없음 | Baseline §2.4 · Tech Spec §12.5 | RT-06 |
| startup sweep이 lease 남은 row 미변경 | Baseline §9 · B-L5 | RT-06 |
| 긴 handler + 성공 heartbeat → STALE 아님 | Baseline §9 | RT-06 |
| T1/T2 사이 kill → 반영 1회 · 실행 중 kill → attempt 2 | #15 | RT-06 |
| usage begin 실패 → HTTP 없음 · kill 뒤 Final 1 · 재호출 없음 | #6 · #11 | RT-07 |
| usage in-flight recovery · 살아 있는 in-flight 미변경 | Baseline §9 Usage · B-G1 | RT-07 |
| API `200` / `202` · `running_jobs` 비어 있지 않음 | HTTP Contract §5.3 · §7-2 | RT-08 |
| API `503` / `500` 분기 | B-D8 · Contract §3.4 | RT-08 |
| case_view body preservation | Contract §7-4 | RT-08 |
| ready dependency 실패 · pool 고갈 중 응답 · provider 미호출 | Baseline §9 Health | RT-08 |
| 첫 비동기 E2E | §4 | RT-09 |
| upload `413` · idle 종료 | Baseline §9 API/Upload | RT-11 |
| upload durability(same mount · `fsync` · publish → commit 순서) | Ops §4-2 · Contract §7-6 | RT-11 |
| case isolation · frame 소유 | Contract §3.5 · §7-9 | RT-11 |
| frame header · 동시 생성 제한 · asset header | Baseline §9 Media | RT-11 |
| cleanup safety | Baseline §9 Cleanup | RT-12 |
| false STALE event · 민감 원문 미기록 | Baseline §9 Observability | RT-05 · RT-12 |
| cross-process 비동기 E2E | §4 | RT-10 |
| dispatch registration (kind → capability) | Tech Spec §16 Contract/Boundary · Register C-10 | RT-04(틀) · RT-10 |
| 늦은 usage 관측 보존(false STALE) | Baseline §2.12 · P-7 | RT-07 |
| `runtime.retry.after_case_stopped_count` emit | Baseline §3.2 · §6 | RT-04(b) · RT-06(b) |

### 8.3 Baseline 입력 → Task (누락 확인)

| Baseline ID | Task |
| --- | --- |
| B-W1 · B-W2 | RT-04(knob 없음) · RT-13(service 1개) |
| B-W3 | RT-03 |
| B-W4 | RT-08 · RT-13 |
| B-Q1 ~ B-Q3 | RT-04 |
| B-L1 · B-L2 | RT-05 (B-L2 claim 시점은 RT-03) |
| B-L3 ~ B-L5 | RT-06 |
| B-L6 | RT-03 · RT-05 · RT-06 |
| B-R1 ~ B-R3 | RT-06 |
| B-D1 ~ B-D7 | RT-02 |
| B-D8 | RT-02(helper) · RT-04 · RT-05(Worker 쪽) · RT-08(API 쪽) |
| B-D9 | RT-02(factory) · RT-05(사용) |
| B-U1 · B-U3 · B-U4 | RT-11 |
| B-U2 · B-U5 | RT-08 |
| B-P1 | RT-12(관측 — 가정이며 구현 대상 아님) |
| B-F1 · B-F2 | RT-11 |
| B-C1 ~ B-C4 | RT-12 |
| B-H1 ~ B-H3 | RT-02(probe 연결) · RT-08 |
| B-X1 | RT-05 |
| B-G1 | RT-07 |
| B-O1 | RT-13 |
| B-O2 | RT-01 |
| §9 Config / Secret | RT-01 |
| §9 Observability | RT-01 · 각 Task · RT-12 |

Baseline §9의 11개 묶음 모두 Task에 배치됐다.

---

## 9. PR plan

| Task | PR | 독립 merge 단위 | 선행 PR |
| --- | --- | --- | --- |
| RT-01 | (a) config (b) log | 각각 | — |
| RT-02 | (a) 의존성 · engine · tx helper · harness · CI (b) Alembic 배치 · runner | 각각 | (a): RT-01(a) interface · #282 의존성 순서 |
| RT-03 | (a) schema · enqueue · read port (b) claim · finish | 각각 | RT-02(b) |
| RT-04 | (a) loop · registry · T1 (b) T2 port · E2E-0 | 각각 | RT-03 |
| RT-05 | (a) heartbeat · lease · fencing (b) cancel | 각각 | RT-04 |
| RT-06 | (a) sweep · retry (b) T2 재전달 · kill 테스트 | 각각 | RT-05 |
| RT-07 | (a) schema · `DECIMAL` · Final append (b) sink · finalize (c) reconciliation | 각각 | (a): RT-02(b) · (b): RT-03 · (c): RT-06(a) |
| RT-08 | (a) app · envelope · health (b) `/cases` · `/view` (c) `/commands` · enqueue (d) 중단 배선 | 각각 | (a): RT-01 · RT-02(a) · (b): #282 · 8-10 · (c): RT-03 · #284 · (d): RT-05(b) · 8-9 |
| RT-09 | 1 | — | RT-04(b) · RT-08(c) · 8-8 |
| RT-10 | kind 묶음별 2 ~ 3 | 각각 | RT-09 · Gate |
| RT-11 | (a) upload (b) frames (c) assets | 각각 | RT-08(a)(b) · #282 · REC-1 해당 PR |
| RT-12 | (a) cleanup (b) 관측 집계 · catalog | 각각 | RT-11(a) · RT-06 · RT-07 |
| RT-13 | (a) Dockerfile · compose (b) migration 단계 · smoke | 각각 | RT-09 · Gate |
| RT-15 | (a) Ruff · type (b) import 경계 (c) secret scan | 각각 | RT-01 · RT-02(a) |

**금지:** DB + Worker + API + Compose를 한 PR에 묶기 · 한 PR에서 Final Contract · Baseline 값 변경과 구현을 함께 하기.

---

## 10. First Implementation Batch

| # | Task | 왜 먼저 |
| --- | --- | --- |
| 1 | **RT-01** (정철원) | 모든 Task가 읽는 config · log 기반이다. 의존 없음 · 작은 PR |
| 2 | **RT-02** (정철원) | 이후 모든 MySQL 테스트와 CI gate의 바닥이다. RC · lock wait · tx 재시도 위험을 가장 먼저 실측한다. #282 case MySQL 테스트도 CI에서 돌기 시작한다. (a)는 RT-01과 dependency상 병렬 가능 |
| 3 | **RT-03** (정철원, RT-02(a)(b) 뒤) | critical path 핵심 — claim 중복 · transaction 경계 위험을 조기에 제거한다 |
| 4 | **RT-08(a)** (정철원, **RT-01 + RT-02(a) 뒤**) | case PR과 무관한 app skeleton · envelope · health로 HTTP 층 위험을 일찍 드러내고 RT-08(b)(c)를 case PR merge 즉시 붙일 수 있게 한다 |

```text
RT-01 ∥ RT-02(a)
        ↓
RT-02(b) → RT-03
        ∥
     RT-08(a)        ← RT-01 + RT-02(a)
```

∥는 dependency상 병렬이 **가능하다**는 뜻이다. Implementer가 한 명이라 실제 실행 순서는 상황에 따라 순차로 정한다. dependency는 §3 · §9 표가 맞다.

RT-04는 RT-03 merge 직후 다음 순서다. **RT-04 착수 전 RD-09a Provisional 가정 기록이 필요하다(§7)** — 정철원(recording) · 김준영(runtime) Joint로, 첫 batch 동안 Register 절차대로 연다.

---

## 11. Parallel work

아래 ∥는 dependency상 함께 진행해도 되는 조합이다. 두 사람이 동시에 작업한다는 뜻이 아니다 — RT는 Implementer가 한 명(§12)이라 실제로는 순서를 고른다. 사람 사이 병렬은 Runtime ∥ 다른 Owner 작업(case · search)뿐이다.

| 동시에 | 조건 |
| --- | --- |
| RT-01 ∥ RT-02(a) | RT-02가 RT-01의 `DbSettings` 필드(B-D* · B-H1)를 interface로 맞추고, 늦게 merge되는 쪽이 연결한다 |
| RT-03 ∥ RT-08(a) | 파일 겹침 없음 |
| RT-05 · RT-06 ∥ RT-08(b)(c) · RT-09 | RT-09는 RT-05 · RT-06을 기다리지 않는다(§4) |
| RT-07(a) ∥ RT-04 ~ RT-06 | RT-07(b)는 RT-03 read port 파일을 확장하므로 RT-03 merge 뒤 |
| REC-1 ∥ RT-03 ~ RT-06 | 같은 사람(정철원)이라 실제 병렬도는 capacity에 달렸다 — §12.7 위험 |
| SRCH-1 ∥ RT-08 ~ RT-10 | RT-07(b) sink port merge 뒤 |
| RT-15 ∥ RT-03 이후 전부 | 정적 검사만 — 다른 Task와 파일이 겹치면 늦게 merge되는 쪽이 맞춘다 |
| case 8-8 · 8-9 · 8-10 · 8-6 2단계 ∥ Runtime 전부 | case 소유 |

억지로 병렬화하지 않는 것: RT-03 ↔ RT-07(b)(같은 read port) · RT-04 ↔ RT-05(같은 worker loop) · RT-08(c) ↔ RT-11(a)(같은 app composition — 순서대로).

---

## 12. Implementation responsibility — Single Implementer + Deferred Owner Review

2026-10-06 §8 실행 모델 보정이다. §7 reopen이 아니고 Architecture · Contract · Accepted Decision · Baseline · Task 범위 · dependency를 바꾸지 않는다. 구현 중 Owner 사이 handoff와 PR마다 승인 대기를 없애고, 나중에 문서만 보고 audit할 수 있게 기록 의무를 둔다.

### 12.1 책임 구조

| 역할 | 사람 | 하는 일 |
| --- | --- | --- |
| **Primary Implementer — RT-01 ~ RT-15** | 정철원 @cheol1203 | 코드 작성 · implementation detail 선택(§12.3) · PR 작성 · 검증 · merge(§12.2) · Implementation Notes(§12.4) · Implementation Log(§12.5) |
| **Runtime/Ops Owner · HTTP API Contract Owner** | 김준영 @flosure23 | Architecture · Contract authority. Contract · Accepted Decision · Baseline 의미 변경의 확인처(§12.3) |
| **Deferred Acceptance** | 김준영 @flosure23 | 구현 도중이 아니라 구현 뒤 Plan · Log · PR Notes · E2E evidence로 확인(§12.6). integration acceptance |

**ownership 이전이 아니다.** Runtime/Ops Owner와 HTTP API Contract Owner는 김준영 그대로이고 [`ownership.md`](../management/ownership.md)를 바꾸지 않는다. 바뀌는 것은 「누가 코드를 쓰고 implementation detail을 고르는가」뿐이다 — 그 권한을 정철원에게 위임한다. 그래서 원래 김준영이 Primary였던 RT-01 · RT-07 ~ RT-15도 정철원이 직접 구현한다.

| 사람 | 이 Plan에서 할 일 | 기다릴 dependency | 완료 기준 |
| --- | --- | --- | --- |
| **정철원** @cheol1203 (Primary Implementer · recording Owner) | RT-01 ∥ RT-02(a) → RT-02(b) → RT-03 · RT-08(a) → 이후 §3 · §4 순서로 RT-04 ~ RT-15. REC-1은 recording Owner로서 capacity에 따라 | case 선행(§6.1) · Gate(§7). RT-04 전 RD-09a 가정 기록(recording + runtime Joint) | 각 Task acceptance · RT-09 CI 통과가 첫 milestone · Implementation Log 누적 |
| **김준영** @flosure23 (Runtime/Ops · HTTP Contract Owner) | 구현 Task 없음. §12.3 확인 요청 응답 · §7 Gate Decision · RD-09a Joint(runtime 쪽) · §12.6 Audit | — | Audit A · B · C |
| **유소연** @yuusoyeon (case) | Runtime Plan의 새 Task 없음. 기존 8순위 — #282 · #284 · 8-8 · 8-10 · 8-9 · 8-1 · 8-6 2단계가 RT-08 · RT-09 · RT-10의 선행(§6.1). Runtime이 case 공개 interface를 소비하는 코드는 Implementer가 쓴다. 새 case surface가 필요하면 유소연 확인 | RT-02(b) Alembic 배치(P-1 = #282 배치 채택) · RT-02(a) CI | case 자체 기준 |
| **서어진** @kong2488-star (search) | SRCH-1 Primary(변경 없음) — RT-07(b) sink port merge 뒤. Runtime 쪽 `UsageSink` port(RT-07)까지는 Implementer, Search adapter 안의 배선은 search Owner 범위다(서어진이 명시적으로 위임하면 별도) | RT-07(b) | SRCH-1 acceptance |
| **신유민** @uminshin (web · readout) | 없음 — RT-08 · RT-11 merge 공지 뒤 Contract §6 흐름 실연동(기존 Consumer 역할) · RT-10 readout handler Consult | RT-08 · RT-11 | — |
| **김대원** @kim1034 (eval) | 없음 | — | — |

**첫 Task — RT-01 · RT-02(a)를 바로 잡는 데 필요한 것:** RT-01 — Tech Spec §15.2 · Baseline §2 Config 칸 · §9 Config / Secret 행 · B-O2 · Ops §6 · §6-1 · §7 · §0.1 P-8. RT-02(a) — §0.1 P-1 · P-2 · RT-02 본문 · Baseline B-D1 ~ B-D9 · B-H1 · Research 01 Spike F · #282 diff(`pyproject.toml` · `migrations/case/` · `tests/case/conftest.py`). 추가 설계 입력은 없다.

### 12.2 Merge authority

- Implementation PR은 **Primary Implementer가 acceptance criteria와 CI를 만족하면 merge할 수 있다.**
- Runtime/Ops Owner의 동시 approval은 기본 merge gate가 아니다. Issue · 이 Plan의 「Owner / Acceptance」 · 「Consult」는 merge 전 승인 요구가 아니다 — Owner review는 merge 뒤 · milestone(§12.6)에서 한다.
- 단 Contract · Accepted Decision · Baseline 의미 · 다른 Owner surface를 바꾸는 PR은 해당 authority 확인이 필요하다(§12.3). 상위 문서가 merge 전 승인을 명시한 경우도 그 문서가 맞다.
- **Consult는 승인이 아니다.** 그 Owner의 공개 surface에 닿는 interface 모양(예: RT-04 T2 port · RT-05 cancel port · RT-08 case 함수 호출 · 잠금 순서 · RT-02 #282 의존성 순서)을 정하기 **전에** 한 번 맞추는 것이다. 응답을 기다리는 동안은 port · fake로 진행하고(RT-04 방식) 실제 배선은 확인 뒤 붙인다. 맞춘 결과 그 Owner에게 새 의무가 생기면 §12.3 「멈춤」이다.

김준영 사전 승인 없이 「구현 → PR → 검증 → merge」로 가는 조건:

1. Final Contract 의미를 바꾸지 않는다
2. Accepted Decision을 바꾸지 않는다
3. Provisional Baseline 의미를 바꾸지 않는다
4. 다른 Owner에게 새 의무를 만들지 않는다
5. 이 Plan 범위 안이거나 합리적인 implementation detail 변경이다
6. 해당 Task의 acceptance · integration test가 통과한다
7. PR에 Implementation Notes(§12.4)가 있다

### 12.3 진행할지 멈출지

| 상황 | 처리 |
| --- | --- |
| implementation detail — 파일 위치 · class/function 구조 · composition root 위치 · helper · repository 내부 구성 · thread helper · FastAPI app factory · DI 구조 · test harness · logging helper · internal API 이름 | **그냥 진행.** PR Notes와 Log에 남긴다. 이 Plan의 Expected files/modules · Scope 모양과 달라도 된다 |
| Contract 의미 — HTTP status · request/response schema · route 의미 · JobExecution · UsageRecord Contract 의미. 또는 Contract가 애매해 어느 쪽을 고르느냐에 따라 외부 동작이 달라지는 경우 | **멈추고** 해당 Contract Owner 확인(HTTP · Runtime 쪽은 김준영) |
| Accepted Decision 변경 — 예: `FAILED` Runtime auto retry · Redis · SQS · 새 queue model · 새 ownership model | **멈추고** 해당 Decision Owner 확인 |
| Baseline 의미 변경 — 예: heartbeat · lease · retry 상한 · upload 상한 값 | **멈추고** 김준영 확인. 실측으로 조정 후보가 생기면 구현 PR에서 바꾸지 않고 Log의 「Baseline revisit 후보」에 근거와 함께 기록한다(workflow §10 → §11 경로) |
| 다른 Owner의 새 의무 — 예: case 새 callback 필수 · Search가 Contract에 없는 값 제공 · recording 새 public capability 필수 · Web contract 변경 | **멈추고** 해당 Owner 확인. recording 쪽(P-6 등)은 Implementer가 recording Owner를 겸하므로 recording Owner 판단으로 recording 문서에 남긴다 — 구현 PR 안에서 조용히 정하지 않는다 |
| SoT 사이 모순 발견 | §0과 같다 — Task 안에서 고치지 않고 SoT Owner에게 올린다 |

구현 중 선택한 값 · 구조가 나중에 중요해질 수 있으면(예: `DECIMAL` precision/scale · thread lifecycle 구조 · DB 재시도 helper · DI 구조 · migration runner 모양) **별도 RD Issue를 만들지 않고** Log의 「Implementation detail 색인」에 남긴다. 새 Architecture Decision이 아니기 때문이다.

### 12.4 Implementation Notes — 모든 Runtime 구현 PR 필수

RT-xx 구현 PR 본문에 아래 절을 넣는다. 해당 사항이 없어도 절을 지우지 않고 `없음`이라고 적는다.

```markdown
## Implementation Notes

### 구현 결과
- 실제 구현 구조
- 주요 파일 / module
- 주요 실행 흐름

### Plan 대비 변경
- Runtime Implementation Plan과 달라진 부분
- 왜 변경했는지
- 단순 implementation detail인지 여부

### 새로 고정된 implementation detail
- 이번 PR에서 처음 확정한 구현 선택
- 선택 이유
- 대안이 있었으면 간단 비교

### Contract / Decision / Baseline 영향
- Contract 변경: 없음 / 있음
- Decision 변경: 없음 / 있음
- Baseline 변경: 없음 / 있음

### Owner 확인 포인트
- 김준영이 나중에 확인해야 할 부분
- Runtime/API boundary
- 운영상 중요한 선택
- 후속 revisit가 필요한 부분

### Verification
- unit
- integration
- CI
- 수동 / E2E
```

「Contract / Decision / Baseline 영향」에 `있음`이 하나라도 있으면 §12.3 확인을 거친 PR이어야 한다.

### 12.5 Plan과 Implementation Log

| 문서 | 담는 것 |
| --- | --- |
| 이 Plan | 구현 **전에** 계획한 것. 구현에 맞춰 다시 쓰지 않는다 |
| [`runtime-implementation-log.md`](./runtime-implementation-log.md) | **실제로** 구현된 것 · 이 Plan 대비 차이와 이유 · 새 implementation detail · Owner 확인 포인트 · 남은 위험 |

각 Runtime PR은 가능하면 같은 PR에서 Log의 해당 Task 절을 갱신한다. merge 전이라 SHA가 없으면 `pending`으로 두고 다음 PR에서 채운다 — Log 갱신을 이유로 구현 PR merge를 막지 않는다. 기록 항목 · 형식은 Log의 「사용 규칙」이 원문이다.

### 12.6 Milestone audit

김준영은 PR마다 보지 않고 아래 묶음 단위로 Plan · Log · PR Notes · Integration/E2E evidence를 읽고 확인한다. **workflow gate가 아니다** — 다음 Task 착수를 막지 않고, 나중에 읽기 쉽게 묶는 용도다.

| Audit | Task | 확인 대상 |
| --- | --- | --- |
| A — Runtime Core | RT-01 ~ RT-06 | config · DB · queue · Worker · heartbeat · STALE · retry · cancel |
| B — Integration | RT-07 ~ RT-11 (+ REC-1 중 Runtime이 소비하는 surface) | Usage · API · 첫 비동기 E2E · Worker composition · Media HTTP |
| C — Operations | RT-12 ~ RT-15 | cleanup · observability · Compose · deployment · CI |

Audit 결과(확인 · 후속 요청)는 Log의 해당 Audit 절에 남긴다. Audit에서 Contract · Decision · Baseline 문제가 나오면 해당 SoT 절차로 보낸다.

### 12.7 위험 — 한 사람 집중

RT-01 ~ RT-15와 REC-1(M5 경로)이 모두 정철원에게 있다. context 전환 비용은 줄지만 일정 · 지식이 한 사람에 몰린다. 완화는 기록이다 — PR Notes와 Log만으로 다른 사람이 이어받을 수 있어야 한다. 첫 비동기 E2E는 REC-1을 기다리지 않도록 짰다(§4). 일정이 막혀 ownership을 조정해야 하면 [`ownership.md`](../management/ownership.md) 범위이고 이 Plan이 재배정하지 않는다.

### 12.8 RT PR 체크리스트

RT 구현(AI로 진행하는 경우 포함)은 이 절을 순서대로 따른다. 각 항목의 규칙 원문은 괄호 안 위치이고, 이 절은 순서만 모은다.

**착수**

- [ ] §6 해당 Task 절 · §3 선행 · §7 Gate 「필요 시점」 확인 — 예: RT-04는 RD-09a 기록 뒤 · RT-13은 RD-12a · 12g 뒤
- [ ] Log 해당 Task Status `NOT_STARTED` → `IN_PROGRESS`
- [ ] 다른 Owner surface에 닿는 interface가 있으면 모양을 정하기 전에 Consult(§12.2)

**PR 열 때**

- [ ] Issue 연결 — 중간 PR은 `Refs #N (RT-xx(a))`. **`Closes`는 Task 마지막 PR에서만** 쓴다
- [ ] `## Implementation Notes`(§12.4) — 해당 없는 절도 `없음`
- [ ] Log 해당 Task 절 — PR 행(SHA `pending`) · 구현 결과 · Plan 대비 변경 · Owner 확인 포인트 · Verification · 남은 위험(Log 「사용 규칙」)
- [ ] 해당하면 Log에 추가 — 새 implementation detail → 「색인」 · Baseline 조정 근거 → 「Baseline revisit 후보」 · §12.3 확인을 거침 → 「Owner 확인 기록」
- [ ] `src/daesingo/{api,worker,common}/README.md` 상태 문구가 사실과 달라졌으면 수정(§6 공통 DoD)
- [ ] 최상위 경로 · `pyproject.toml` · `.github/workflows/` · 모듈 골격→구현 전환을 건드렸으면 루트 README 사실 절 확인(`/update-readme` · PR 템플릿) — RT-02 · RT-13 · RT-15가 해당되기 쉽다
- [ ] queue · transaction · lease · locking · upload를 mock으로 끝내지 않았고 CI MySQL 테스트 skip 0(§8.1 · P-2)

**merge**

- [ ] §12.2 조건 충족 → Implementer가 merge

**다음 PR**

- [ ] 직전 PR의 Log `pending` SHA를 채운다

**Task 마지막 PR**

- [ ] 본문에 `Closes #N` — Task의 PR이 모두 merge되고 acceptance가 통과하는 PR이다
- [ ] Log Status `DONE`. **Issue close = Log `DONE`**이다. 둘이 어긋나면 Audit(§12.6)에서 맞춘다

---

## 13. §8 Entry Criteria

- [x] Implementation Plan 작성 · consistency check(§14)
- [x] critical path 순서 고정(§4)
- [x] Task · Issue Owner 고정(§6 · §15 — #287 umbrella · #288 ~ #303)
- [x] blocking Decision gate 식별 — 첫 batch를 막는 Gate 없음(§7)
- [x] First Implementation Batch 선택(§10)
- [x] 이 Plan PR merge — PR #304

---

## 14. Consistency check

| 검사 | 결과 |
| --- | --- |
| Task 없는 Baseline §9 implementation input | 0 (§8.3) |
| Owner 없는 Task | 0 |
| Implementer 없는 RT Task | 0 — RT-01 ~ RT-15 전부 정철원(§12.1) |
| 구현 중 Owner handoff · merge 전 Owner 승인 요구 | 0 — 확인은 §12.3 조건에서만 |
| dependency 없는 blocker | 0 — 모든 Gate가 막는 Task와 시점을 가진다(§7) |
| acceptance test 없는 Runtime core Task(RT-02 ~ RT-07) | 0 (dispatch registration test는 RT-04 틀 · RT-10 완성) |
| Final Contract와 충돌 | 0 — HTTP status · body · header는 Contract 표를 가리키기만 한다 |
| Accepted Decision과 충돌 | 0 — #244 ~ #250 범위를 Task 입력으로만 씀 |
| Baseline 값 재결정 | 0 — 숫자는 B-ID로만 가리킴 |
| 새 정책 · Decision | 0 — §0.1은 위임 원문이 있는 구현 선택만 |
| 다른 Owner의 새 의무 | 0 — REC-1 · SRCH-1 · §6.1은 #244 · #246 · HTTP Contract §9.1 · Baseline B-C3 · case 8순위에 이미 있는 의무. 새 요청 1건(P-6 orphan 판정 조회)은 의무로 두지 않고 RT-12 Gate로만 표시. RD-09a 가정은 기존 Register 절차 |

---

## 15. GitHub Issues

| Task | Issue | Assignee (= 실제 구현자) |
| --- | --- | --- |
| Umbrella | #287 | 김준영 (추적) |
| RT-01 | #288 | 정철원 |
| RT-02 | #289 | 정철원 |
| RT-03 | #290 | 정철원 |
| RT-04 | #291 | 정철원 |
| RT-05 | #292 | 정철원 |
| RT-06 | #293 | 정철원 |
| RT-07 | #294 | 정철원 |
| RT-08 | #295 | 정철원 |
| RT-09 | #296 | 정철원 |
| RT-10 | #297 | 정철원 |
| RT-11 | #298 | 정철원 |
| RT-12 | #299 | 정철원 |
| RT-13 | #300 | 정철원 |
| RT-14 | — RT-13 착수 때 생성(§6 RT-14) | 정철원 (생성 시) |
| RT-15 | #301 | 정철원 |
| REC-1 | #302 | 정철원 (recording Owner) |
| SRCH-1 | #303 | 서어진 (search Owner) |

Issue 본문은 이 문서의 Task 절을 가리키는 추적용이다. 범위가 다르면 이 문서가 맞다. Assignee는 실제 구현자이고, Runtime/Ops · HTTP Contract authority는 assignee와 무관하게 김준영에게 있다(§12.1).

## Change log

| 날짜 | 변경 | 기준 |
| --- | --- | --- |
| 2026-10-06 | 최초 작성 — workflow §7. Gap audit · critical path · 17 Task(RT-01 ~ RT-15 · REC-1 · SRCH-1) · Decision gate · test matrix · PR plan · handoff | `origin/develop` `4052ada` |
| 2026-10-06 | §8 실행 모델 보정(§7 reopen 아님) — RT-01 ~ RT-15 Implementer를 정철원으로 단일화, 김준영은 Runtime/Ops · HTTP Contract Owner · deferred acceptance 유지. §12를 handoff 표에서 책임 구조 · merge authority · 확인 조건 · Implementation Notes · Implementation Log · Milestone audit로 교체. §6 책임 표기 · §10 · §11 · §15 정규화. Contract · Accepted Decision · Baseline · Task 범위 · dependency · 다른 Owner 소유 변경 없음 | PR #305 |
| 2026-10-06 | §12.2에 Consult 성격(승인 아님 · interface 모양을 정하기 전 확인) 명시 · §12.8 RT PR 체크리스트 추가(Issue 연결 · close = Log `DONE` 규칙 포함). 실행 모델 · Contract · Decision · Baseline 변경 없음 | PR #307 |
