# `worker` — Worker composition root

**Owner:** 김준영 (공통 기반/운영) · **경계:** `docs/architecture/module-architecture.md` §1-5 · §6-2 · §8-2

- 배포 단위 「Worker 1」. `common/jobs`에서 row를 claim → RUNNING + heartbeat → 도메인 모듈의 **public capability**를 dispatch → 결과 ref + usage 기록.
- `STALE`은 실행 중 Worker가 살아 있지 않다고 Runtime이 판정한 terminal 실행 상태다. `case`가 현재 context에 유효하지 않다고 판단해 반영하지 않는 늦은 결과(중단된 job 등)와는 다른 개념이다 — 그런 실행은 `SUCCEEDED`를 유지하고, `case`가 그 `produced`를 domain state에 반영하지 않아 현재 `CaseView`를 덮지 않는다 (`docs/architecture/contracts/contract-job-execution.md` §6 · §9-8).
- Background로 가는 것(§8-1): 큰 source/proxy 준비 · RemoteCopy upload · Coarse/Fine 외부 AI · 장시간 OCR · Incident Clip / Report Video export.

## 상태

RT-01의 `bootstrap.py`를 구현했다. `bootstrap(revision=...)`은 `DAESINGO_ENV_FILE`(미지정 시 cwd `.env`)을 명시적으로 읽어 불변 Worker RuntimeConfig를 만들고, Search의 기존 `GeminiSearchConfig.from_dotenv(mapping)` 및 추가 등록 모듈의 factory/validator를 startup에서 호출한다. 실패 시 설정 key 이름만 기록하고 `SystemExit(1)`로 종료한다. `revision`은 호출자가 전달하는 commit SHA 등 안전한 식별자다.

필수 파일 key는 `DAESINGO_RUNTIME_DB_URL` · `DAESINGO_RUNTIME_MEDIA_ROOT` · `DAESINGO_RUNTIME_WORKER_TEMP_ROOT`와 현재 Search가 사용하는 `GEMINI_API_KEY`다. Search key rename/alias 의미는 바꾸지 않는다. pricing/FX는 필수값으로 강제하지 않는다. 반환된 `Startup.modules["search"]`는 마스킹된 credential과 검증된 Search config를 보관한다.

RT-04(a)는 `python -m daesingo.worker` 진입점 · 단일 kind registry · claim loop · ExecutionContext · T1 terminal 기록을 구현한다. 기존 Worker engine/claim/finish/transaction helper를 재사용하며 claim commit 후 handler를 실행한다. 빈 queue는 B-Q1, 완료 후 다음 claim은 즉시, DB 오류는 B-Q3 대기다. T1은 B-D8 재시도 소진 뒤에도 결과를 유지하고 B-Q3 간격으로 재기록한다. SIGINT/SIGTERM은 실행 중 handler·T1을 중단하지 않고 다음 idle 지점에서 반영한다.

실제 handler 등록은 비어 있다. 미등록 kind는 `RUNTIME_UNREGISTERED_KIND`로 `FAILED`다. 성공·모듈 failure taxonomy·예외 처리와 registration은 fake handler 및 실제 MySQL로 검증한다. RT-07(b)는 execution별 UsageSink 주입·begin/finish/explicit finalize를 구현한다. 실제 Recording/Search handler는 RT-10 범위다.

WorkerLoop는 heartbeat 시작 뒤 dispatch 전 cancellation checkpoint를 확인하고, composition이 공급한 factory로 execution마다 새 sink를 만든다. sink에 주입하는 transaction runner는 usage DB callback만 재시도하며 provider HTTP를 포함하지 않는다. `KindRegistry`가 UsageError를 재전파하고 loop는 `RUNTIME_USAGE_PERSISTENCE/VALIDATION/CONFLICT/STATE`로 FAILED를 기록한다. T1 retry는 이 결과만 보존하고 handler를 다시 호출하지 않는다. sink는 connection을 method 사이에 유지하지 않으며 이미 관측한 usage에는 ownership fence를 적용하지 않는다.

RT-07(c)는 정상 T1 commit 이후 별도 usage transaction과 기존 startup/periodic sweep hook에 terminal reconciliation을 연결한다. begin의 예정 Run ref는 존재 근거가 아니며 terminal `JobExecution.produced`에 그 ref가 있을 때만 실제 Run에 연결한다(FAILED 포함). 없으면 `RUN_NOT_PRODUCED`, 명시적 no-Run 선언은 `DIRECT_NO_RUN`이다. Run 의도가 불분명한 legacy/pending 행은 보류한다. 살아 있는 RUNNING 행은 변경하지 않는다. recovery 이후 늦은 finish는 Final을 고정한 채 tracker에 관측값·late event marker를 보존한다. 같은 관측 replay는 no-op, 다른 관측·관계는 conflict다. 일반 metric/logger/observer 오류는 durable 결과를 바꾸지 않으며 기존 fatal/cleanup/thread 정책은 유지한다. 실제 Search adapter 배선은 SRCH-1 범위다.

RT-06(a)는 첫 claim 전에 startup sweep을 실행하고, handler와 독립적인 `runtime-sweep` thread에서 같은 만료 조건으로 주기 sweep을 수행한다. 만료 후보마다 짧은 transaction에서 row 잠금·lease·중단 표식을 재확인하고 STALE과 상한 내 다음 attempt QUEUED를 함께 기록한다. backoff는 DB 생성 시각에 더한 `available_at`으로 적용한다. startup DB 장애는 성공할 때까지 B-Q3 대기하며 claim을 막고, 종료 시 sweep thread를 stop/join한다. `compose_worker(sweep_hooks=(...))`는 RT-07용 등록 지점이며 hook은 connection 반환 뒤 startup/주기 sweep에서 호출되고 일반 예외는 격리된다. RT-06(b)의 재전달 배선은 아래에 기록한다.

`runtime.queue.wait_ms`는 DB `queued_at → started_at`을 측정하고 `status=INITIAL/RETRY`로 attempt 묶음을 구분한다. retry의 계획된 backoff도 포함한다. 로그 sink가 느려도 lease를 갱신할 수 있도록 heartbeat 시작 뒤 기록한다.

RT-05(a)는 claim된 execution별 heartbeat thread를 handler/T1 동안 유지한다. monotonic fixed-rate tick에서 동기 lease 갱신을 한 번만 실행하고, 느린 시도나 관측 때문에 지난 tick은 집계하여 건너뛴다. B-D9 전용 Connection은 Worker QueuePool과 분리되며 실패하면 다음 tick에 재연결한다. heartbeat에는 transaction retry를 적용하지 않는다. 0행 UPDATE는 COMMIT 성공 여부와 무관하게 ownership fence를 설정한다. T1의 기존 owner 조건부 UPDATE에 더해 B-D8 매 시도와 COMMIT 직전에도 fence를 확인한다. 실행이 끝나면 finally에서 thread를 stop/join하고 연결과 소유 engine을 닫는다. 단계별 I/O timeout은 전체 시도나 join의 hard deadline을 뜻하지 않는다.

RT-05(b)의 `common.jobs.cancel.request_cancel(conn, job_ids) -> None`은 Case caller transaction에 참여한다. 전체 입력 검증·중복 제거 후 job_id/attempt/execution_id 순서의 unique index 잠금을 먼저 얻고, QUEUED는 즉시 CANCELLED, RUNNING/STALE은 최초 cancel marker를 기록한다. terminal과 없는 job은 no-op이다. heartbeat는 같은 lease 갱신 transaction에서 marker와 DB 시간 지연을 읽고 commit 성공 후 `ExecutionContext.cancel_signal`에 한 번 전달한다. `ctx.checkpoint()`는 전용 `CancellationRequested`를 발생시키며 WorkerLoop는 ownership 조건부 T1으로 CANCELLED와 빈 produced를 기록한다. 마지막 checkpoint 이후 정상 완료는 SUCCEEDED를 유지한다. observe 지연은 DB marker 나이에 SELECT 시작부터 signal 전달까지 monotonic 경과를 더해 읽기/COMMIT 대기를 포함한다. Baseline의 `runtime.cancel.terminal_latency_ms`는 DB 최초 요청 기록부터 durable CANCELLED의 T1 COMMIT acknowledgement까지다. 별도 `runtime.cancel.checkpoint_to_terminal_ms`는 최초 cancellation checkpoint부터 같은 acknowledgement까지다. COMMIT 확인 직후 monotonic 종료 시각을 고정해 terminal logger·pool cleanup·heartbeat join 시간은 제외한다. 지표 계산·sink 오류는 확정된 T1을 재시도하지 않는다. Case는 이미 중단 job을 정산하므로 이 내부 CANCELLED 결과를 기존 성공/실패 전용 T2 reflector에 전달하지 않는다. Case command·HTTP 배선·강제 provider/thread 중단은 구현하지 않는다. RT-05는 독립 재리뷰 전까지 IN_PROGRESS다.

RT-04(b)는 `compose_worker(reflector=...)`로 `ResultReflector`를 주입한다. T1 commit 후 별도 B-D8 transaction에서 reflector → 후속 enqueue → `case_applied_at`을 처리한다. reflector는 전달된 Connection에서 Case 행을 먼저 잠그고 `execution_id` 중복 반영을 판정하며 직접 commit·rollback·retry하지 않는다. `APPLIED`만 immutable `RuntimeJobRecord(job_id, case_id, kind)` 목록을 반환할 수 있다. `ALREADY_APPLIED`와 `NOT_APPLIED(STOPPED_WAITING/CANCELLED/SUPERSEDED)`도 전달 완료 표식을 기록한다. T2 실패는 전체 rollback하고 이미 확정된 T1을 유지한다. T2 DB 오류(재시도 소진 포함)는 안전한 DB 오류 event와 `runtime.reflect.failed`를 기록하고 다음 claim 전에 interruptible B-Q3 대기를 거친다. 일반 reflector 예외는 `runtime.reflect.failed`만 기록하고 DB 장애 대기 없이 다음 claim으로 진행한다. 표식 없는 terminal 재전달 scan은 RT-06(b)가 연결한다.

Case lock 이후 Runtime terminal facts와 표식을 잠금 확인한다. COMMIT 응답 유실 재실행은 Case idempotency와 이미 기록된 표식을 확인해 후속 execution을 다시 enqueue하지 않는다. `runtime.retry.after_case_stopped_count`는 commit된 `attempt >= 2 AND NOT_APPLIED(STOPPED_WAITING)`에서만 기록하며, 이미 전달된 결과는 집계하지 않는다. sink 장애 시 event 유실은 가능하다.

RT-06(b)는 `worker.case_reflector.CaseReflector(reader=..., timelines=..., store_factory=...)`로 실제 Case 8-8 공개 함수를 연결한다. 기본 store는 caller Connection을 공유하는 MySQLCaseRepository와 Runtime read port다. reader와 timeline은 composition에서 주입하며 실제 모듈 결과 저장소는 RT-10 선행 경계다. 이 reflector를 `compose_worker`에 전달하면 direct T2와 startup/periodic redelivery가 같은 adapter를 사용한다. 기본 entrypoint의 reflector는 여전히 비어 있다.

`common.jobs.redelivery.redeliver_once`는 SUCCEEDED/FAILED 중 `case_applied_at IS NULL`인 후보를 잠금 없이 읽고 connection을 반환한 뒤 후보마다 B-D8 transaction을 실행한다. replay마다 receipt를 비잠금 재조회하고, Case lock → Runtime lock/후속 enqueue/receipt 순서로 처리한다. CANCELLED와 STALE은 전달하지 않는다. startup scan 완료 전 첫 claim을 막으며 일반 reflector/DB 오류는 후보 단위로 격리하고 다음 후보·다음 주기에 진행한다. scan DB 오류는 startup admission 재시도 대상이다. post-commit `runtime.reflect.redelivery_count`와 기존 STOPPED_WAITING retry 지표를 안전한 logger로 기록한다.

Case가 지원하지 않는 kind는 T2 오류로 남고 receipt를 기록하지 않는다. 미등록 kind도 `FAILED/RUNTIME_UNREGISTERED_KIND`로 T1 뒤 T2에 도달한다. Worker 등록 가능 kind와 Case 반영 가능 kind의 호환성·fail-fast 책임은 RT-10에서 확인해야 하며, 이번 adapter가 Case 반영기를 확장하거나 조용히 APPLIED 처리하지 않는다. 실제 MySQL에서 T1–T2 kill 및 실행 중 kill→lease 만료→STALE→다음 attempt 성공→Case 반영을 spawned Worker process로 검증한다.

RD-09a에 따라 실제 Recording invocation은 execution마다 새 `RecordingService`를 만들고 `finally`에서 닫아 mutable cache/working state를 제한한다. durable repository/persistence를 execution마다 새로 격리한다는 뜻은 아니다. 이 PR은 service lifecycle을 구현하거나 process-global cache를 추가하지 않는다.

structured event에는 queue의 trace/case/job/execution ID를 연결한다. 저장 가능한 ID라도 경로·제어문자가 포함돼 event token으로 안전하지 않으면 로그에서만 일관된 opaque alias를 쓴다. handler context와 DB의 원래 ID는 유지한다. thread에 correlation을 전달할 때는 `common.logging.copy_context_call`로 제출 시점의 context를 캡처한다. 세부 선택과 검증 결과는 [Implementation Log](../../../docs/runtime/runtime-implementation-log.md)에 기록한다.
