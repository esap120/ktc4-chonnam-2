# `common` — runtime 기반 (도메인 모듈이 아니다)

**Owner:** 김준영 (공통 기반/운영) · **Architecture 경계:** `docs/architecture/module-architecture.md` §6-2 · §2 원칙 6 · §5-13  
**Runtime 문서:** [`docs/runtime/README.md`](../../../docs/runtime/README.md)

여덟 번째 도메인 모듈이 아니다. 「이 작업이 왜 필요한가」를 판단하지 않고 **실제로 실행만** 한다.

```text
db        MySQL 8.4 / InnoDB 기반 Runtime persistence
jobs      DB Queue · JobExecution lifecycle · retry · lease · heartbeat · stale recovery
usage     UsageRecord — 외부 capability/provider invocation 단위 사용량·비용 원장
logging   structured operational logging 기반
config    Runtime configuration
storage   storage adapters
```

- **JobRecord는 case가 소유하는 append-only Intent**다. Queue row나 execution lifecycle과 동일시하지 않는다.
- **JobExecution은 common/runtime이 소유하는 실행 1회분 기록**이다.
- 사용자 재실행은 새 JobRecord / 새 `job_id`, 자동 인프라 retry는 같은 `job_id` + 새 `execution_id` + 증가한 `attempt`를 사용한다.
- 작업 **발주 의도와 부분 재실행 정책**은 `case`가 소유한다. 여기는 execution lifecycle만 소유한다.
- `case`가 Worker 구현을 import하고 Worker가 다시 `case`/domain module을 import하는 순환을 만들지 않는다. 연결은 `api/`·`worker/` composition root가 한다.
- Runtime 구현 세부는 [`docs/runtime/runtime-tech-spec.md`](../../../docs/runtime/runtime-tech-spec.md), 배포·운영 기준은 [`docs/runtime/ops-spec.md`](../../../docs/runtime/ops-spec.md)를 따른다.

## 현재 구현

1차 Mock E2E 범위로 `JobExecution` v1.1 모델, 공용 fixture loader와 in-memory lifecycle을 구현했다. `InMemoryJobExecutionStore`는 attempt 증가와 허용 상태 전이를 검증한다.

RT-01은 `config/`의 불변 RuntimeConfig/DbSettings와 api·worker별 Baseline 기본값·불변조건 검증, `bootstrap.py`의 파일 1회 로딩·모듈 factory 검증·fail-fast, `logging/`의 JSON line stdout event·contextvars·trace/thread helper를 추가했다. `load_env_file()`의 기존 cwd `.env` 동작은 유지한다. DB URL·경로·credential 값과 exception 원문은 운영 event에 넣지 않는다. event helper의 식별자 필드에는 신뢰된 ID/코드만 전달하며 일반 free text를 전달하지 않는다. root/타사 logger 전체를 마스킹하는 기능은 아니다.

RT-02(a)는 `db/`에 역할별 MySQL engine factory와 `Connection` callback transaction helper를 추가했다. API는 한 번 실행하고 COMMIT 전 실패와 결과 불명을 구분한다. Worker는 DB callback만 전체 rollback 뒤 최대 3회(최초 1회 + 추가 2회) 실행한다. 외부 capability는 callback 밖에서 호출하며 Python callback 자체가 외부 I/O를 차단하는 sandbox는 아니다. heartbeat·ready는 일반 pool과 분리되고 migration engine은 별도 정책을 받는다.

RT-02(b)는 `db/migrate.py`에 명시 URL API와 `python -m daesingo.common.db.migrate --database-url-stdin` CLI를 추가했다. frozen registry `case → runtime` 순서로 env를 `head`까지 올리고 첫 실패에서 중단한다. engine 하나에서 모듈마다 새 transaction connection을 열며, process 내부 중첩/동시 호출은 거부한다. **단일 실행 전제이고 cross-process 동시 실행 안전성은 보장하지 않는다.** 자동 retry·stamp·downgrade·resume 기능과 startup migration은 없다. stdin 전달자는 credential을 argv·로그에 노출하지 않아야 한다. URL 출처·배포 실행 위치는 RT-14 범위다.

RT-03(a)는 `migrations/runtime/versions/0001_job_execution.py`(`runtime_0001`)에 실행 원장 겸 queue인 `job_execution`을 추가한다. `common/jobs/repository.py`의 `enqueue(conn, job_records, trace_id)`는 호출자의 열린 transaction에 attempt 1 `QUEUED`를 넣고 execution ID 목록을 반환한다. commit·rollback·retry를 하지 않으며 같은 `(job_id, attempt)`는 DB unique 제약이 거부한다. batch 입력을 쓰기 전에 검증하고 하나의 INSERT로 기록한다. 등록되지 않은 kind도 받아 Worker dispatch에 판단을 맡긴다.

RT-03(b)는 `0002_claim_token.py`(`runtime_0002`)의 nullable 내부 `claim_token`으로 공개 claim 호출을 재시도 사이에 식별한다. 기존 첫 revision은 바꾸지 않는다. `claim_one(engine, worker_id, *, lease_duration_sec, logger=None)`는 ID만 `LIMIT 1 FOR UPDATE SKIP LOCKED`로 선택하고 조건부 RUNNING/lease UPDATE 뒤 PK snapshot을 읽는다. `lease_duration_sec`의 기본값은 기존 WorkerSettings이며 composition root가 설정값을 주입할 수 있다. token·선택된 ID는 호출 전체에서 고정되고, COMMIT 결과 불명 뒤에는 같은 PK의 durable receipt만 확인한다. owner/token 불일치·terminal·만료·복구 불가 상태는 `ClaimLostError`이며 빈 queue와 다르다. claim transaction에는 INSERT나 handler 호출이 없고 확인된 commit 후에만 frozen `ClaimedExecution`을 반환한다.

application/worker engine은 새 연결과 pool checkout에서 session timezone을 UTC로 고정한다. B-L6 그대로 `NOW(6)`으로 eligibility·lease·시작/종료 시각을 계산하며 UTC DATETIME(6)와 비교한다. 임의 engine 대신 공용 RC/UTC engine을 사용하고, 빌린 connection의 session 정책을 application transaction 도중 변경하지 않는다.

`finish(conn, execution_id, owner, *, status, produced=(), failure_kind=None) -> int`는 열린 호출자 transaction에 참여한다. SUCCEEDED/FAILED/CANCELLED만 허용하며 CANCELLED produced는 빈 배열이다. 기존 공용 전이표와 JobExecution validator로 검증하고 `RUNNING ∧ lease_owner=owner` 조건부 UPDATE가 경쟁을 결정한다. 다른 owner·없는 ID·비-RUNNING은 0 rows다. commit/rollback/retry는 호출자 소유이며 STALE 전이는 RT-06 범위다. lease/heartbeat/receipt metadata는 terminal 이후에도 감사 근거로 보존한다.

claim latency는 transaction 시작부터 COMMIT 응답 확인까지의 monotonic 시간이다. checkout·checkin·retry 대기·handler 시간은 제외하며 실패/COMMIT_UNKNOWN은 성공 분포와 구분한다. 같은 receipt의 read 복구는 `runtime.db.claim_recovery_latency_ms`로 분리한다. 선택적 RT-02 attempt observer와 운영 logger의 오류는 DB 결과나 재시도 여부를 바꾸지 않는다.

`common/jobs/read_port.py`의 `read_executions(conn, job_ids)`는 요청한 Job의 모든 attempt를 JSON 호환 JobExecution v1.1 모양으로 돌려준다. 대표 execution 선택은 case가 한다. claim_token을 포함한 내부 column은 allowlist projection으로 제외하고 `usage_refs`는 Final `usage_record.execution_ref`별 usage identity를 결정적인 순서로 projection한다. pending tracker는 포함하지 않고 Final이 없으면 `[]`다. enqueue 시각은 DB `UTC_TIMESTAMP(6)`으로 생성해 UTC `DATETIME(6)`에 저장하고 read model에 UTC offset을 붙인다. claim lease 계산·판정은 UTC session의 `NOW(6)`으로 Baseline B-L6을 따른다.

runner 성공 후 재실행은 version 기준 no-op이다. MySQL implicit-commit DDL은 전체 rollback되지 않으므로 실패한 revision에 부분 DDL이 남으면 검사·복구가 필요하다. RT-02는 Implementation Log 기준 `DONE`, RT-03은 (b) 독립 재리뷰 전까지 `IN_PROGRESS`다.

RT-06(a)는 `jobs/retry_policy.py`의 만료·상한·backoff pure logic과 `jobs/sweep.py`의 caller transaction 참여·주기 thread를 추가한다. STALE과 다음 QUEUED는 같은 commit이며, 원본 row 잠금 재확인·기존 UNIQUE(job_id, attempt)·재시도 동안 고정한 retry ID로 중복을 막는다. 만료 판단과 시각은 DB `NOW(6)`을 사용한다. Worker startup에서 첫 claim 전 실행하고 handler와 별개 thread로 반복한다. RT-07 hook은 sweep commit·connection 반환 뒤 실행한다. claim receipt의 내부 `queued_at`으로 attempt별 queue 대기 지표를 기록한다.

RT-07(a)는 `usage/`에 typed `usage_inflight`·append-only `usage_record`와 exact `DECIMAL(65,30)` 경계를 추가했다(`runtime_0003`, 기존 `runtime_0002` 뒤). `append_final(conn, record)`는 caller transaction에 INSERT하며 같은 `usage_id`·snapshot의 replay는 no-op, 다른 snapshot은 `UsageIdentityConflict`다. 내부 commit/rollback·ID 발급·in-flight 변경·provider 호출은 없다. `read_final`의 금액은 문자열 또는 null이고, null과 0을 구분한다. live Core binder도 Decimal/문자열만 받으며 float·초과 precision/scale을 DB 변환 전에 거부한다. raw SQL로 binder를 우회하면 MySQL 자체의 소수 반올림이 가능하다. `execution_ref` index가 있으며 tracker와 Final은 같은 PK로 논리 연결하고 FK를 두지 않는다. frozen migration과 live metadata는 실제 MySQL DDL로 대조한다.

RT-07(b)는 stdlib-only `usage.port.UsageSink`와 execution별 `DurableUsageSink`를 추가한다. Worker composition이 DB-only transaction runner를 주입한다. `begin`은 Runtime identity를 발급해 STARTED를 commit한 뒤 반환하며 실패하면 호출자는 HTTP를 보내지 않는다. 실패한 begin의 `UsagePersistenceError.usage_id` 또는 성공 반환 ID로 같은 sink에 persistence replay할 수 있다. `finish`는 관측값을 OBSERVED로 먼저 보존하고, caller가 실제 Run 관계를 확정한 뒤 `finalize`가 기존 `append_final`과 FINALIZED 표시를 같은 transaction에서 처리한다. 동일 snapshot은 no-op, 다른 snapshot은 conflict다. usage 오류는 provider retry와 분리하며 완료된 HTTP를 재호출하지 않는다. 관측 저장은 ownership fence로 버리지 않는다.

RT-07(c)는 `runtime_0004`에서 tracker에 예정 Run 관계·명시적 no-Run 선언·복구 시각·late event 시각을 추가한다. Final schema는 변경하지 않는다. begin의 예정 ID와 terminal `JobExecution.produced`를 대조해 FAILED Run도 실제 ref에 연결하고, 산출되지 않은 예정 Run은 `RUN_NOT_PRODUCED`, 명시적으로 Run 개념이 없는 호출은 `DIRECT_NO_RUN`으로 기록한다. 정상 T1 뒤 및 startup/periodic hook에서 같은 DB-only 관계 판정을 사용한다. RUNNING과 의도 불명 행은 변경하지 않는다. P-7은 Final을 고정한 채 tracker의 늦은 관측과 event marker를 durable 보존한다. recovered/inflight count와 DB 시각의 oldest age는 observer 및 안전한 structured log로 관측한다. 실제 Search adapter 연결은 SRCH-1 범위다.

아직 실제 구현되지 않은 범위:

- 기본 Worker entrypoint의 실제 Case reader/timeline 조립(RT-10). RT-06(b)의 `jobs/redelivery.py` startup/periodic scan과 Worker-owned Case adapter·실제 process-kill MySQL 테스트는 구현했다. 대상은 SUCCEEDED/FAILED이고 CANCELLED·STALE은 제외한다. 후보 scan/replay receipt read는 비잠금이며 Case→Runtime 순서의 기존 T2를 재사용한다. 후보 오류는 격리하고 COMMIT 불명은 durable receipt로 복구한다.
- 실제 Search adapter 연결(SRCH-1)
- Case/command HTTP route(RT-08(b/c/d)) · 기본 Worker 실제 handler 조립(RT-10)
- media HTTP(RT-11). API app/envelope와 Runtime health는 RT-08(a)의 API composition이 RT-01 config와 RT-02 engine을 소비하여 구현한다.

따라서 README의 Runtime 항목을 구현 완료로 해석하지 않는다.

API 소유 structured handler는 emission I/O lock을 stdlib handler cleanup lock과 분리하며, 정상 emission에서 flush하고 종료 cleanup에서 sink를 재호출하지 않는다. 실제 stdout 및 고정 stderr fallback은 unbuffered fd write를 사용한다. 이는 RT-08(a)의 bounded telemetry 종료 경계이며 Worker strict handler·allowlist/formatter·root/제3자 handler는 변경하지 않는다.
