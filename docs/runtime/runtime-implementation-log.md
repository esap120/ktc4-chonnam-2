# Runtime Implementation Log

**Status:** workflow §8 Implementation Log — 구현이 진행되며 누적하는 living record**Owner:** Runtime/Ops 김준영(@flosure23) · Primary Implementer 정철원(@cheol1203)**Plan:** [Runtime Implementation Plan](./runtime-implementation-plan.md) — 구현 **전** 계획. 이 Log는 **실제로** 구현된 것이다(Plan §12.5)**Started:** 2026-10-06 · 기준 `origin/develop` `960a046`

> 이 문서는 무엇이 만들어졌고 Plan에서 무엇이 달라졌는지를 한곳에 남겨, Runtime/Ops Owner가 PR마다 따라가지 않고 나중에 이 문서와 PR Implementation Notes만으로 확인(Plan §12.6 Audit)할 수 있게 한다. **규칙을 만들지 않는다.** Contract · Accepted Decision · Baseline이 바뀌면 그 결정은 각 SoT에 있고 여기에는 「바뀌었다 + 어디」만 적는다. 실행 모델(merge authority · 멈춰야 하는 경우 · PR Notes 형식)의 원문은 Plan §12다.

## 사용 규칙

- **언제** — PR 단위 순서는 Plan §12.8 체크리스트다. RT Task의 구현 PR이 merge될 때, 가능하면 **같은 PR에서** 해당 Task 절을 갱신한다. merge 전이라 SHA가 없으면 `pending`으로 두고 다음 PR이나 정리 PR에서 채운다. Log 갱신을 이유로 구현 PR merge를 막지 않는다.
- **최소 기록** — Task · Issue · PR · Merge SHA · 구현 요약 · Plan 대비 변경 · Owner 확인 포인트 · Tests · 남은 위험.
- **출처** — PR 본문의 Implementation Notes(Plan §12.4)를 Task 단위로 요약해 옮긴다. 상세는 PR이 원문이다.
- **Plan을 고치지 않는다** — Plan과 다르게 구현했으면 Plan을 다시 쓰지 않고 아래처럼 「Plan 대비 변경」에 적는다.

  ```text
  (예시)
  Plan:          heartbeat.py + cancel.py 분리 예상
  Actual:        execution_lifecycle.py로 통합
  Reason:        공유 state · fencing 경계가 하나라 분리하면 순환 dependency 발생
  Contract 영향: 없음
  ```

- **implementation detail** — 나중에 중요해질 수 있는 구현 선택(값 · 구조)은 Task 절과 함께 아래 「Implementation detail 색인」에 한 줄 남긴다. 별도 RD Issue를 만들지 않는다(Plan §12.3).
- **Baseline 조정 후보** — 실측으로 Baseline 값을 바꿀 근거가 생기면 구현 PR에서 바꾸지 않고 「Baseline revisit 후보」에 적는다. 결정은 workflow §10 → §11 경로다.
- **Status 값** — `NOT_STARTED` · `IN_PROGRESS` · `DONE`(Task의 PR 전부 merge · acceptance 통과 — Issue close와 같은 시점, Plan §12.8) · `AUDITED`(Plan §12.6 Audit 확인 뒤).
- 비어 있는 항목은 `—`로 둔다.

## Implementation detail 색인

Plan §0.1이 Task PR로 넘긴 선택은 미리 행을 둔다. 그 밖의 선택은 구현하며 추가한다.

| 항목 | 선택 | Task · PR | 근거 위치 |
| --- | --- | --- | --- |
| Baseline 밖 config key 이름 — DB 접속 · 공유 mount root · service별 temp root (Plan P-8) | `DAESINGO_RUNTIME_DB_URL` · `DAESINGO_RUNTIME_MEDIA_ROOT` · `DAESINGO_RUNTIME_API_TEMP_ROOT` · `DAESINGO_RUNTIME_WORKER_TEMP_ROOT` — 필수, 기본값 없음 | RT-01 · PR pending | 아래 RT-01 · `common/config/` |
| RuntimeConfig · startup module 검증 경계 | frozen Runtime snapshot + frozen Pydantic 설정 묶음 · service별 defaults · read-only mapping 1회 전달 · `ModuleFactory` registry | RT-01 · PR pending | 아래 RT-01 |
| structured log · revision · correlation | 전용 stdout JSON logger · 안전한 event 필드 허용 목록 · `revision` 명시적 인자 · contextvars + thread 제출 helper | RT-01 · PR pending | 아래 RT-01 · `common/logging/` |
| DB 역할별 engine · callback transaction | API/Worker QueuePool · heartbeat/ready/migration NullPool · `Connection` callback과 내부 context manager · B-D8 최초 포함 총 3회 | RT-02(a) · PR #319 · `4a513c0` | 아래 RT-02 · `common/db/` |
| MySQL 실제 장애 · CI 실행 증거 | 테스트별 schema · COMMIT OK 폐기 proxy · 실제 1205/1213/KILL · JSON/JUnit 대조 · 기존 Case 18개 실행 목록 | RT-02(a) · PR #319 · `4a513c0` | 아래 RT-02 · `tests/mysql_harness.py` · `scripts/check_mysql_test_report.py` |
| Alembic runner · 빈 Runtime env | frozen registry `case → runtime` · 명시 URL API/stdin CLI · 모듈별 transaction connection · 빈 Runtime version table · 첫 실패 중단 · process 내부 중복 거부 | RT-02(b) · 로컬, PR 미생성 | 아래 RT-02(b) · `common/db/migrate.py` |
| 실행 원장 schema · enqueue · read model | `runtime_0001` · 내부 시각 표식 column · ascii_bin ID · DB UTC microseconds · 단일 batch INSERT · Contract allowlist projection · usage_refs 비저장 | RT-03(a) · PR #332 · `7872c7aa989d0907e5a71608136de5196c230ac0` | 아래 RT-03 · `common/jobs/` |
| claim receipt · unknown COMMIT 복구 | nullable 내부 `claim_token`의 `runtime_0002` · 공개 호출의 ID/token 고정 · 같은 PK durable receipt만 복구 · Contract validation 입력 allowlist | RT-03(b) · 로컬, PR 미생성 | 아래 RT-03(b) · `common/jobs/repository.py` |
| application/worker UTC checkout | connection 생성·checkout에서 UTC session 복원 · B-L6 `NOW(6)` 유지 | RT-03(b) · 로컬, PR 미생성 | 아래 RT-03(b) · `common/db/engines.py` |
| attempt observer · claim latency | sanitized outcome/duration · transaction 시작 → COMMIT acknowledgement · checkout/checkin/retry 대기 제외 · 관측 실패와 retry 분리 | RT-03(b) · 로컬, PR 미생성 | 아래 RT-03(b) · `common/db/transactions.py` |
| Worker invocation · T1 replay | 불변 kind registry · execution context/result · claim/handler/T1 분리 · 결과 보존 재시도 · durable terminal facts 재조회 | RT-04(a) · 로컬, PR 미생성 · `Refs #291` | 아래 RT-04 · `worker/composition.py` · `common/jobs/worker_loop.py` |
| heartbeat lifecycle · commit fencing | 실행별 전용 thread/NullPool connection · monotonic fixed-rate/skip · 내부 ownership fence · B-D8 매 시도/COMMIT 직전 guard · BaseException 소유 thread 전파 | RT-05(a) · 로컬 미커밋 · `Refs #292` | 아래 RT-05 · `common/jobs/heartbeat.py` · `common/db/transactions.py` |
| `DECIMAL` precision/scale (Plan P-10) | `DECIMAL(65,30)` · 정수 35/소수 30자리 · Decimal/문자열 bind · 초과 precision/scale 거부 | RT-07(a) · PR #349 · `fa5a0fcbd5f88e70e7a4c9ba0a457b42a65a27a1` | 아래 RT-07 · `common/usage/amount.py` |
| usage identity · Final replay · 참조 | 양 table `usage_id` 단독 PK · FK 없이 snapshot 보존 · 고정 ID INSERT/1062 locked read · 동일 snapshot no-op/상이하면 conflict · caller tx | RT-07(a) · PR #349 · `fa5a0fcbd5f88e70e7a4c9ba0a457b42a65a27a1` | 아래 RT-07 · `common/usage/{schema,repository}.py` |
| UsageSink · explicit finalize | execution별 sink · DB-only runner 주입 · 고정 begin identity/snapshot · locked read/조건부 전이 · append+FINALIZED 원자성 · sanitized UsageError | RT-07(b) · PR #353 · `95dfff8b3ba11f95b76a168dd18ccc1573c02b39` | 아래 RT-07(b) · `common/usage/{port,sink}.py` |
| cancel 잠금 · signal · 지연 측정 | 전체 입력 검증 후 sorted job별 unique index 순회 잠금 · 최초 marker 유지 · heartbeat commit 후 signal 한 번 전달 · DB 요청→terminal/추가 monotonic checkpoint→commit 지연 | RT-05(b) · 로컬 미커밋 · `Refs #292` | 아래 RT-05(b) · `common/jobs/cancel.py` |
| STALE sweep · retry · hook lifecycle | 후보 scan 후 execution별 짧은 tx · PK SKIP LOCKED 재확인 · retry ID 고정/unknown COMMIT 복구 · startup gate + 독립 주기 thread · connection 반환 뒤 immutable hooks | RT-06(a) · 로컬 미커밋 · `Refs #293` | 아래 RT-06 · `common/jobs/{sweep,retry_policy}.py` |
| attempt별 queue 대기 관측 | claim receipt 내부 queued_at · DB queued_at→started_at · INITIAL/RETRY 묶음 · heartbeat 시작 뒤 sink 호출 | RT-06(a) · 로컬 미커밋 · `Refs #293` | 아래 RT-06 · `repository.py` · `worker_loop.py` |
| STALE 관측 · fatal hook 비노출 | DB STALE ended_at − 마지막 heartbeat_at · post-commit 측정/누락 fallback 없음 · fatal cleanup 후 process 경계에서 원문 비노출·고정 코드 1 | RT-06(a) 후속 P2 · 로컬 미커밋 · `Refs #293` | 아래 RT-06 · `sweep.py` · `worker/__main__.py` |
| T2 재전달 · Case adapter · kill 복구 | 비잠금 후보/receipt 조회 → 후보별 기존 T2 · Case→Runtime 잠금 · startup admission gate · 주입형 Case 8-8 bridge · 실제 spawned process kill/DB 상태 관측 | RT-06(b) · PR/merge SHA pending · `Refs #293` | 아래 RT-06(b) · `common/jobs/redelivery.py` · `worker/case_reflector.py` |
| type checker 도구 (Plan RT-15) | pending | RT-15 | — |
| secret scan 배치 — PR gate 편입 여부 (Plan RT-15) | pending | RT-15 | — |
| Compose smoke의 CI 편입 여부 (Plan RT-13) | pending | RT-13 | — |
| API factory · readiness · safe telemetry | dedicated NullPool + deadline/in-flight 공유 · metadata-only mount · bounded daemon events · workers=1 CLI | RT-08(a) · PR pending | 아래 RT-08 · `api/{app,composition,errors,health,storage,events,__main__}.py` |

## Baseline revisit 후보

| Baseline ID | 관측 | Evidence | 처리 (workflow §10 → §11) |
| --- | --- | --- | --- |
| 없음 | — | — | — |

## Owner 확인 기록

Plan §12.3에서 「멈추고 확인」에 해당해 Owner에게 확인한 건만 남긴다.

| 날짜 | Task · PR | 확인 내용 | 확인처 | 결과 · 기록 위치 |
| --- | --- | --- | --- | --- |
| 2026-10-08 확인 | RT-02(b), PR 미생성 | Case env 입력 우선순위 최소 수정·외부 transaction 참여. Case fixture/revision/metadata/version table 의미 변경 없음, 공통 helper 의무 없음 | 유소연 @yuusoyeon | [Issue #289 승인 댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/289#issuecomment-6055765577). Consult 결과이며 Case env는 향후 PR에서 Owner 리뷰 예정 |
| 2026-10-14 직접 조회 | RT-07(c), PR #360 | Search에는 durable Run 저장소가 없고 최초 영속화는 T1 produced. 예정 Run ref 대조로 복구하며 명시적 DIRECT_NO_RUN 허용 | 김준영 @flosure23 · 서어진 @kong2488-star · 정철원 최종 확인 | [Runtime 답변](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/294#issuecomment-6145102027) · [Search 답변](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/294#issuecomment-6148574716) · [최종 확인](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/294#issuecomment-6150512406). 이 세션은 댓글을 작성하지 않고 직접 읽었다 |

## Milestone audit

묶음 정의는 Plan §12.6이다. workflow gate가 아니다.

| Audit | Task | 상태 | 확인일 | 결과 · 후속 |
| --- | --- | --- | --- | --- |
| A — Runtime Core | RT-01 ~ RT-06 | 대기 | — | — |
| B — Integration | RT-07 ~ RT-11 (+ REC-1 소비 surface) | 대기 | — | — |
| C — Operations | RT-12 ~ RT-15 | 대기 | — | — |

---

## RT-01 — Runtime config · composition bootstrap · structured log 기반

Status: DONE · Issue: #288 · Audit: A

완료 근거: 최종 common/api/worker 121 passed · 신규 회귀 22 passed · 전체 pytest 1826 passed / 44 skipped · boundary / Contract fixture / diff 검사 PASS. 사용자에게 전달받은 독립 재리뷰 결과는 병합 차단 문제 없음 · RT-01 전체 완료 PR 생성 가능이다. 사용자 요청에 따라 구현 완료 상태를 `DONE`으로 기록하며, PR 생성·merge 및 Owner Audit 완료를 뜻하지 않는다(PR·Merge SHA는 pending 유지).

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| pending (로컬, PR 미생성) | RT-01 config/bootstrap + structured logging 한 단위 | pending |

### 구현 결과

- `common/config/`: api·worker 공용 불변 `RuntimeConfig`와 DB/heartbeat/worker/upload/frame/cleanup/ready 묶음. API와 Worker의 key 집합·pool 기본값을 분리하고, Baseline §2 Config 표 후보 이름(P-8)·기본값·§9 불변조건을 검증한다. Baseline에 config가 아닌 값은 새 knob으로 열지 않았다. heartbeat I/O timeout 합을 interval과 비교하지 않는다.
- `api/bootstrap.py` · `worker/bootstrap.py` → `common/bootstrap.py`: composition root만 shell의 `DAESINGO_ENV_FILE`을 읽어 명시적 경로를 전달한다. 파일은 한 번 읽고 같은 read-only mapping으로 Runtime 및 module factory/validator를 검증한다. shell의 다른 값과 병합하지 않고 `load_env_file()` 무인자 동작은 그대로다.
- Worker는 현재 Search의 `GeminiSearchConfig.from_dotenv(mapping)`를 실제 호출하고 현재 credential key를 검증한다. api에는 현재 파일 기반 module config가 없어 기본 registry가 비어 있다. 추가 module factory는 service 조립 시 등록한다. factory 결과를 `Startup.modules`에 보관하여 후속 조립에 재사용한다. Search key rename/alias, pricing/FX 필수화, 타 Owner 코드는 변경하지 않았다.
- `common/logging/`: stdout JSON line · `trace_id/case_id/job_id/execution_id/module` contextvars · trace 생성 · nested reset · asyncio 격리 · thread 제출 시 명시적 context 복사. event helper는 허용 필드·안전한 코드/ID·유한 숫자만 받으며 raw message/exception/stack/arbitrary extra를 JSON으로 내보내지 않는다.
- 검증된 Runtime 설정 오류와 모듈 factory 예외는 `runtime.config.invalid`에 key 이름만 기록하고 `SystemExit(1)`로 종료한다. 모든 `ModuleFactory.keys` 선언은 factory 실행 전에 검사한다. 잘못된 선언은 원문 없이 `keys=[]`, 고정 `status=INVALID_MODULE_FACTORY_KEYS` 진단과 종료 코드 1을 남긴다. 미지의 Runtime key는 `runtime.config.unknown` 경고만 남긴다. 검증 성공 뒤 `process.started`에 service·명시적 revision을 남긴다. 이 설명은 아래 회귀 테스트로 확인한 경로의 보장이며 임의의 모든 startup 예외에 대한 포괄 보장이 아니다.

### Plan 대비 변경

- Plan의 1~2 PR 허용 범위에서 config와 log를 한 단위로 구현했다. startup 오류의 안전한 관찰까지 함께 검증하기 위함이다. Task 범위·dependency 변경 없음.
- 공통 startup mechanics는 `common/bootstrap.py`, 파일 경로 선택과 실제 module factory 등록은 api·worker에 둔다. 파일/class 배치에 해당하는 implementation detail이다.
- HTTP app·Worker 실행 조립은 각각 RT-08/RT-10 이후다. RT-01은 config/bootstrap 기반과 실제 Search config factory 검증까지 제공한다. DB engine/transaction·migration·route·loop·배포는 추가하지 않았다.
- Contract 변경 없음 · Accepted Decision 변경 없음 · Provisional Baseline 값/의미 변경 없음. SoT 모순 없음.

### 새 implementation detail

- 필수 key: `DAESINGO_RUNTIME_DB_URL`(SQLAlchemy `mysql+pymysql` URL, host/user/database 필요) · `DAESINGO_RUNTIME_MEDIA_ROOT` · 해당 service의 `DAESINGO_RUNTIME_API_TEMP_ROOT` 또는 `DAESINGO_RUNTIME_WORKER_TEMP_ROOT`. 배포 경로·접속값은 임의 default를 만들지 않았다. 경로 존재/쓰기 가능 probe는 후속 health/storage 단계다.
- Baseline B-R2의 후보 `…_BACKOFF_MAX_SEC`는 P-8대로 `DAESINGO_RUNTIME_BACKOFF_MAX_SEC`로 고정했다. Python 내부 필드명은 `worker.stale_retry_backoff_max_sec`다. 별도 heartbeat lock-wait/ready-budget/concurrency key는 만들지 않는다.
- `DbSettings.url`은 `SecretStr`이며 RT-02에서 `get_secret_value()`로 소비한다. pool과 I/O timeout은 검증된 필드로 전달한다. engine 생성은 하지 않는다. heartbeat lock wait와 ready budget은 해당 Baseline 고정값이며 별도 key가 아니다.
- `ModuleFactory(name, keys, factory)`: 의미 해석은 모듈 factory 소유다. `keys`는 선언된 `tuple[str, ...]` 형태와 프로젝트 기존 환경변수 key 형식 `[A-Z][A-Z0-9_]*`를 startup에서 검증한다. 전체 registry 검증이 끝나기 전에는 어떤 factory도 실행하지 않는다. opaque 예외에서 key를 추측하지 않고 검증된 관련 key 목록만 기록한다. 잘못된 선언의 원문·factory 이름·예외 원문은 진단에 넣지 않는다. credential은 Search의 현재 `GEMINI_API_KEY`를 사용하며 `Startup` repr에서 module 설정을 제외한다.
- `bootstrap(revision=...)`: revision은 호출자가 commit SHA 등 안전한 식별자로 명시한다. 새 revision 환경변수는 만들지 않는다. startup 진단과 started event를 먼저 기록한 뒤 설정된 log level을 적용해 ERROR 설정에서도 시작 진단이 사라지지 않게 했다.
- 전용 `daesingo.runtime.api/worker` logger의 root 전파는 끈다. formatter는 거대 숫자 등 잘못된 metadata를 안전한 event로 치환하고, 출력 stream 실패에서는 표준 logging의 raw traceback 대신 고정된 `log.write.failed` JSON만 stderr에 기록한다. correlation/thread helper는 process 내부용이며 durable trace column 연결은 RT-03이다. event 이름·ID/코드 필드는 신뢰된 metadata 전용이다.

### Owner 확인 포인트

- 김준영 deferred Audit A: api/worker schema 분리와 필수 key 명칭, `DbSettings` 소비 형태, startup 진단 순서와 안전한 event 필드 API.
- RT-02에서 실제 engine·heartbeat/probe 연결에 검증된 설정이 그대로 전달되는지 확인. RT-08/RT-10에서 사용하는 모듈의 factory 등록 및 반환 config 재사용을 확인.
- `process.started`는 RT-01 bootstrap 검증 완료 이벤트다. HTTP readiness·claim 가능성·provider 연결 성공을 의미하지 않는다. 후속 composition이 완료된 시점으로 호출 위치를 연결해야 한다.
- 정본 의미나 타 Owner surface 변경이 없어 사전 Owner 확인 대상은 없었다. Owner acceptance와 CI/E2E를 이번 local unit 검증으로 대체하지 않는다.

### Verification

- RED: 새 config/logging/bootstrap import 부재 3 collection error 확인 후 구현. 이후 잘못된 DB URL 예외·subprocess stderr 경로 4 failed / 69 passed 확인 → SQLAlchemy `ArgumentError`를 key-only 오류로 정규화하여 GREEN.
- 기존 common baseline: 14 passed. key 선언 검증 수정 전 RT-01 targeted unit: 85 passed · common/api/worker 회귀: 99 passed. 수정 후 common/api/worker 회귀: **121 passed** (`.venv/Scripts/python.exe -X utf8 -m pytest -q tests/common tests/api tests/worker -p no:cacheprovider --basetemp=.codex-scratch/rt01-keys-regression-001 --tb=short`). Baseline §2 표를 직접 파싱해 모든 canonical key와 P-8 추가 key가 실제 registry와 일치하는 대조 테스트를 포함한다.
- 초기 독립 코드 리뷰: Important 1건 — 거대 숫자 formatter 오류 시 표준 logging의 stderr 진단이 원문을 노출. 실제 venv에서 실패 재현 후 수정했고, 같은 위험이 있는 출력 stream 실패도 별도 RED→GREEN으로 검증했다. 이후 독립 리뷰가 `ModuleFactory.keys` 미검증에 따른 추가 병합 차단 문제를 발견했고, 아래 회귀 테스트로 수정했다.
- 추가 병합 차단 수정 RED→GREEN: `tests/common/test_module_factory_keys.py`에서 **21 failed · 1 passed → 22 passed**. 혼합 None/정수/unhashable 항목 · `bad-key` · 민감 문자열/로컬 경로 · 잘못된 container를 검사하며, api·worker에서 앞선 정상 factory까지 실행되지 않음, 코드 1, 안전한 고정 `runtime.config.invalid` 진단을 확인한다. subprocess에서는 stderr가 비어 있고 stdout JSON에 잘못된 key/예외/secret/경로 원문이 없음을 확인한다. 정상 key의 factory 예외 비노출도 유지됨을 확인한다.
- 독립 재리뷰 통과: 사용자 확인 — 병합 차단 문제 없음 · RT-01 전체 완료 PR 생성 가능 판정. 위 최종 검증 결과와 재리뷰 통과를 근거로 사용자 요청에 따라 `DONE`으로 변경했다. 이번 문서 갱신에서는 테스트를 재실행하지 않고 `git diff --check`만 최종 확인한다.
- key 선언 검증 수정 후 최종 전체 pytest: **1826 passed · 44 skipped**, 실패 0 (`.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp=.codex-scratch/rt01-keys-full-001 --tb=short`) — MySQL URL 미지정 · 로컬 실영상/평가 미디어 없음 · 선택 의존성 `typer` 없음에 따른 기존 skip이다. 신규 회귀에는 skip이 없다. 수정 전 전체 결과는 1804 passed · 44 skipped였다.
- `scripts/check_boundaries.py`: `python -X utf8`로 PASS, 위반 0건. Windows 기본 cp949 출력에서는 UnicodeEncodeError가 있어 UTF-8 모드로 실행했다(스크립트 수정 없음).
- `scripts/check_contract_fixtures.py`: PASS — 문서 구조 62 · JSON 파싱 26 · 의미 fixture 104 검사, 실패 0.
- `git diff --check`: PASS. Commit/push/PR 미실행. `recording-baseline-negative-001.json`과 기존 사용자 파일은 수정하지 않았다.
- 기존 venv에 정본 의존성이 없어 `uv sync --locked --extra test --extra eval-gemini` 실행. `pyproject.toml`/`uv.lock` 변경 없음. Windows sandbox/기존 pytest temp ACL 문제로 pytest는 승인된 권한과 새 전용 basetemp, `-p no:cacheprovider` 사용. 기존 pytest/user 파일은 변경하지 않았다.
- integration · CI · 수동/E2E: 미실행(RT-01 unit only, commit/push/PR 없음).

### 남은 위험

- Search factory가 현재 제공하는 검증 범위만 사용한다. 모듈 내부의 추가 의미 검증/rename은 해당 Owner 소유이며 Runtime에서 복제하지 않는다. 실제 서비스 조립에서 추가 factory 등록을 빠뜨리지 않아야 한다.
- 전역/타사 logger masking·log transport·rotation/retention은 구현하지 않았다. event helper의 허용 문자열에 실제 secret/free text를 ID로 잘못 넘기지 않아야 한다(Ops §7). 실사용/provider/배포 전 security review는 별도다.
- MySQL 연결·filesystem mount probe·queue 경유 trace 전파·module handler 실행은 후속 Task 검증이다. 이 기록은 배포 준비 완료나 Owner acceptance를 뜻하지 않는다.
- 비차단 후속 후보: logger handler 소유권/재설정 시 공유 handler 처리. 현재 `src`/`tests` 검색에서 실제 공유 handler 사용처는 확인되지 않아 이번 수정에 포함하지 않았다. `common/logging/`의 handler 동작 변경 없음.

---

## RT-02 — DB access 기반 · Alembic 배치 · MySQL integration harness · CI

Status: DONE · Issue: #289 · Audit: A

**RT-02(a)는 PR #319, `4a513c0`으로 병합됐다. RT-02(b)는 최종 독립 리뷰에서 병합 차단 문제 없음·완료 처리·커밋·PR 생성 가능 판정을 받았다(사용자 전달).** 사용자 요청에 따라 구현 완료 상태를 `DONE`으로 기록한다. RT-02(b) PR 번호와 merge SHA는 아직 `pending`이며, 원격 GitHub Actions는 PR 생성 후 확인한다. RT-02(b)는 Task의 마지막 PR이므로 PR 본문에 `Closes #289`를 사용한다. 이번 문서 갱신에서는 커밋·push·PR 생성을 하지 않는다. 아래 (a)의 최초 구현·검증 기록은 당시 결과이며, (b)의 현재 상태는 별도 절을 따른다. 향후 PR Implementation Notes에도 B-D8의 `max_attempts=3 = 초회 포함 총 3회` 명확화를 유지한다.

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| [#319](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/319) | RT-02(a) DB factory · callback transaction helper · MySQL harness · CI | `4a513c0` |
| pending (로컬, PR 미생성) | RT-02(b) Alembic env · runner · migration acceptance · 기존 gate 보강 | pending |

### 구현 결과

- `common/db/engines.py`: RT-01 `DbSettings`를 소비하는 API·Worker engine(RC · B-D1 · B-D2~D7), heartbeat 전용 engine(B-D9), ready 전용 engine(B-H1), 명시적 URL/timeout을 받는 migration engine 기반. engine 생성은 연결·migration을 실행하지 않는다. 물리 connection의 `connect` event로 lock wait를 적용하여 recycle/disconnect 교체에도 유지한다.
- `transactions.py` · `errors.py`: `Callable[[Connection], T]` 외부 interface와 내부 context manager. Worker는 1205·1213·SQLAlchemy가 invalidation으로 판정한 disconnect에 전체 DB transaction을 정리한 뒤 처음부터 재실행한다. API는 한 번만 실행하고 pool/초기 연결/COMMIT 전 장애와 COMMIT transport 결과 불명을 구분한다. domain·기타 SQL 오류는 원래 의미를 유지한다. rollback의 2차 오류가 domain 오류를 재시도로 바꾸지 않게 원래 오류를 보존하고 해당 connection을 폐기한다.
- `tests/mysql_harness.py`: 테스트별 빈 schema · 공용 `mysql_engine` · opt-in/require 모드 · MySQL 8.4 실제 연결과 CREATE/DROP 권한 preflight. 기존 Case fixture·테스트는 변경하지 않고 MySQL 대상 marker만 루트 hook에서 식별한다. 기존 Case migration/repository와 공용 factory의 호환성은 별도 integration으로 확인한다. 공용 migration fixture/env/runner는 RT-02(b)에 남긴다.
- 기존 `python-tests.yml`: MySQL 8.4 service, require flag, 전체 pytest JSON/JUnit 보고서, MySQL 대상 skip/xfail 0·필수 시나리오·기존 Case MySQL 18개 실행 검증. 기존 media smoke와 의존성 설치 절차를 유지한다.

### Plan 대비 변경

- §6의 (a)/(b) 분할 그대로다. `migrations/runtime/`, Alembic 재배치·runner·모든 모듈 upgrade acceptance는 (b)에 남긴다. Runtime table·HTTP status 매핑·startup migration·배포 실행 위치를 구현하지 않았다.
- harness는 세션 공유 schema 대신 테스트마다 schema를 생성한다. Case child fixture의 기존 동작은 그대로 유지하고, 공용 engine 참여를 독립 테스트로 검증한다. 타 Owner의 코드/의무 변경 없음.
- 새 의존성이 필요하지 않아 `uv.lock`과 의존성 선언을 변경하지 않았다. `pyproject.toml`은 pytest marker 등록만 추가했다. 루트·common README의 사실 문구를 갱신했다.
- Contract 변경 없음 · Accepted Decision 변경 없음 · Provisional Baseline 값/의미 변경 없음. B-D8 카운팅은 아래 PM 명확화에 따른다.

### 새 implementation detail

- **B-D8:** `max_attempts=3`, 1회차는 최초 시도이며 추가 재시도 최대 2회다. 총 3회 모두 실패하면 소진이고 재시도 사이 대기는 1초다. Baseline의 기존 「최대 3회」 카운팅 의미 명확화이며 값 변경이 아니다. [Issue #289 PM 확인](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/289#issuecomment-6036679371). future PR Implementation Notes에도 동일하게 기록한다.
- API/Worker pool 값은 전달된 service별 RuntimeConfig.db를 사용한다(Worker는 Worker config의 2+2). heartbeat/ready/migration은 각각 별도 `NullPool`이며 일반 checkout 대기를 공유하지 않는다. heartbeat thread의 connection 보관·재연결 tick·겹침 금지는 RT-05 소유다.
- ready 기본 connect/read/write=1/1/1초. 단계별 I/O timeout은 end-to-end 2초 deadline 증명이 아니며 `/health/ready` 전체 budget은 RT-08에서 검증한다. migration은 app의 5/30/30초를 복사하지 않고 인자가 없으면 driver 기본값을 유지한다.
- URL의 timeout query는 역할 정책으로 대체하고 autocommit/init_command/default-file 등 session 정책 우회 option은 거부한다. TLS 등의 일반 접속 option은 유지한다.
- callback은 시도마다 상태를 다시 읽고 stable identity로 이미 반영된 결과를 판정해야 한다. COMMIT 응답 유실 후 재시도가 이전 성공을 rollback하지는 못한다. exhaustion은 이전 시도 중 COMMIT 결과 불명이 있었는지 보존한다. helper는 domain의 idempotency를 대신 구현하지 않는다.
- capability/provider/file publish는 callback 밖에서 호출한다. 일반 `Connection.commit()/rollback()` 오용은 event guard가 탐지하지만 raw SQL/DBAPI/DDL/stored procedure로 transaction을 끝내는 것은 callback 계약 위반이며 임의 Python의 외부 부작용 차단을 보장하지 않는다. handler 전체 sandbox를 구현했다고 주장하지 않는다.
- test proxy는 local TLS-disabled sequential MySQL packet만 중계한다. callback 진입 후 arm하여 driver 초기화 COMMIT은 제외하고, 실제 server COMMIT OK packet을 소비한 뒤 EOF를 보낸다. 별도 connection으로 실제 반영을 확인한다. 운영 proxy가 아니다.
- CI gate는 collected/selected/각 실행 phase/JUnit을 대조하고 17개 scenario group, 명시적인 role/scenario 32개 조합과 기존 Case 5개+13개를 요구한다. skip/xfail/deselection/수집 오류/보고서 누락을 실패시킨다. mock unit과 실제 integration을 별도 파일로 두며 실제 fault 경로에는 mock을 사용하지 않았다.

### Owner 확인 포인트

- 김준영 deferred Audit A: DB-only callback 조립 경계, unknown commit 후 read/idempotency, 세 역할별 timeout 및 후속 heartbeat/ready lifecycle 연결. B-D8 총 시도 수는 위 PM 확인으로 명확하다.
- Case Owner의 새 callback/fixture 의무를 만들지 않았다. Plan의 Consult 대상인 공용 interface와 기존 저장소 참여 호환성은 코드·테스트·Notes에서 검토할 수 있다. Contract·Decision·Baseline 재결정이나 추가 Owner 승인이 필요한 의미 변경은 없다.
- 전체 acceptance의 권한 실패 시나리오는 schema CREATE/DROP·자기 connection KILL 외에 테스트 사용자 CREATE/GRANT SELECT/DROP 권한도 요구한다. 폐기 가능한 관리자 계정 전용이며 app 계정 권한 요구가 아니다.

### Verification — 최초 구현 기록(2026-10-07)

- TDD: factory 10 RED → 10 GREEN; transaction 15 RED → 15 GREEN. callback commit 정리 누수·rollback 오류 마스킹·API 초기 연결 실패·preflight URL option 원문 노출·부분 Case 누락을 각각 RED로 확인하고 수정했다. proxy import 부재 3 RED → 실제 MySQL proxy 3 GREEN; 권한 실패까지 포함한 focused fault 재검증 4 PASS.
- 실제 MySQL: 기존 Windows MySQL 8.0은 사용하지 않고 workspace의 ignored scratch에 공식 MySQL 8.4.7 배포본을 추출해 WSL에서 독립 port로 실행했다. 프로젝트/시스템 패키지를 설치하지 않았고 Python은 기존 venv를 사용했다. sandbox DLL 제한 때문에 승인된 권한과 새 basetemp·`-B -p no:cacheprovider`를 사용했다.
- 중간 전체 common DB+Case: **413 passed · 2 skipped**, MySQL 대상 **36 passed · skip 0 · xfail 0**, JSON/JUnit gate PASS. skip은 기존 Case 실영상 2개다. 이후 API replacement/초기 연결 실패와 gate 회귀를 추가했다.
- 최종 전체 pytest: **1935 passed · 26 skipped · 실패 0**, 253.67초. `DAESINGO_REQUIRE_MYSQL=1`과 실제 MySQL 8.4.7을 사용했다. 명령: `.venv/Scripts/python.exe -B -X utf8 -m pytest -q -p no:cacheprovider --basetemp=.codex-scratch/rt02a-final-full --mysql-report=.codex-scratch/rt02a-final-full.json --junitxml=.codex-scratch/rt02a-final-full.xml --tb=short`.
- 최종 MySQL gate: **40 passed · skip 0 · xfail 0**, 17개 필수 scenario group, setup/call/teardown 120개 phase PASS. 기존 Case MySQL 18개(전용 5 + repository 계약 13), 신규 integration 22개(session 11 + 실제 transaction fault 7 + COMMIT proxy 3 + Case 호환 1). `scripts/check_mysql_test_report.py .codex-scratch/rt02a-final-full.json .codex-scratch/rt02a-final-full.xml` PASS.
- skip 26개는 MySQL 외 기존 opt-in이다: 선택 의존성 `typer` 부재의 Search collection skip 4 · Case 실영상 없음 2 · eval 로컬 미디어 없음 5 · Recording 실영상/VIDEO_INDEX/연속 원본 opt-in 없음 15. 신규 테스트 skip 없음. 실제 MySQL acceptance를 mock/skip으로 대체하지 않았다.
- boundary PASS(위반 0) · Contract fixture PASS(문서 62 · JSON 26 · 의미 104) · `git diff --check` PASS. Case 코드/fixture/테스트, migration, Baseline/Contract/Decision, `uv.lock`, `recording-baseline-negative-001.json`은 수정하지 않았다. 커밋·push·PR 없음.
- 최초 read-only 리뷰에서는 API 획득 실패 분류·preflight 진단 수정 뒤 차단 finding 없음으로 평가받았으나, 이후 독립 리뷰에서 아래 3건이 재현됐다. 최초 평가를 현재의 무결성 보장으로 해석하지 않는다. 이 최초 기록 당시에는 해당 수정의 독립 재리뷰를 받기 전이었다.
- GitHub Actions 자체는 미실행(커밋·push·PR 없음). 로컬에서 실제 MySQL과 동일한 report gate를 실행했다. service image/Ubuntu runner 검증은 향후 CI 실행이 필요하다.
- 검증 뒤 port/version/datadir로 작업 소유를 확인하고 격리 MySQL을 종료했다. 기존 Windows MySQL service는 변경하지 않았다. 보조 YAML parser 검사는 로컬 PyYAML 부재로 미실행이며 설치하지 않았다; workflow는 diff·독립 리뷰로 확인했고 실제 Actions 실행은 위와 같이 남아 있다.

### 2026-10-08 독립 리뷰 finding 수정 · 재검증

| Finding | 원인과 최소 수정 | RED → GREEN 근거 |
| --- | --- | --- |
| 테스트 schema 격리 우회 | SQLAlchemy가 URL query를 path 접속 인자에 덮어쓴다. PyMySQL의 database/db, init_command, read_default_file/group, endpoint/account 재지정 및 미지 option을 공용 harness의 query 허용 목록으로 fail-closed 거부한다. URL 검증·control engine 생성·schema CREATE 전에 검사하며 값/URL/경로 없는 고정 UsageError만 낸다 | 단위 41 RED → 41 GREEN. 실제 MySQL override 3 RED → schema identity 포함 4 GREEN. SELECT DATABASE()가 생성 UUID schema와 정확히 일치하고, 거부 경로 SQL 0건·기존 sentinel DDL/row/table 목록 불변 확인 |
| COMMIT 결과 불명이 cleanup에 덮임 | connection context 바깥까지 원래 transaction failure를 보존한다. COMMIT 오류 처리 중 SQLAlchemy checkin이 덮어쓴 DBAPIError도 예외 체인에서 복원한다. 우선순위는 확인된 COMMIT 성공 > 원래 transaction 오류 > cleanup 오류다. 실패한 invalidate도 원래 body/domain 오류를 덮지 못한다 | 신규 8 RED → 8 GREEN; 기존 transaction/proxy 합계 29 PASS. 실제 COMMIT OK 폐기 뒤 context 종료와 pool checkin TimeoutError를 각각 주입하고 독립 observer row 1개·최종 CommitOutcomeUnknown·안전한 오류/event 확인 |
| 역할별 필수 검사 누락 허용 | scenario 합집합에 더해 mysql_check(role, scenario) metadata를 수집하고 필수 32개 조합을 별도로 요구한다. API가 Worker의 session/recycle/disconnect/wait_timeout 검사를 대신 충족할 수 없으며 초기 연결 거부·heartbeat/ready·각 실제 fault도 필수다. 기존 Case 18개 목록은 유지한다 | 메모리 report 복사본에서 각 필수 조합의 node를 collected/selected/execution에서 제거: 기존 gate 32 RED → 수정 gate 32 GREEN. gate 회귀 합계 52 PASS |

- 기존 `.codex-scratch/`와 `recording-baseline-negative-001.json`을 변경하지 않았다. 서버·검증 도구·pytest basetemp·JSON/JUnit은 별도의 OS 임시 디렉터리 `rt02a-review-20261008-*`를 사용했다. 당시에는 독립 재리뷰 전이어서 차단 문제가 모두 없다고 단정하지 않았다.
- 로컬 opt-in에서도 기존 Case child fixture가 engine을 만들기 전에 pytest_configure에서 URL을 검증한다. require=0에서 위험 URL을 허용하던 경로를 추가 RED로 확인했고 require=0/1 두 subprocess 회귀를 포함한 schema 단위 43 PASS를 확인했다. Case fixture·테스트는 수정하지 않았다.
- 실제 MySQL 8.4.7 require 모드의 DB+Case 회귀: **509 passed · 2 skipped**(기존 Case 실영상 없음). MySQL 대상 **46 passed · skip 0 · xfail 0**, 기존 Case 18개 포함, role/scenario 32개·JSON/JUnit gate PASS. 실제 실행 report의 메모리 복사본에서도 필수 조합별 node를 하나씩 제거한 32가지가 모두 거부됐다.
- workflow 검사: 공식 release의 actionlint **1.7.12** + ShellCheck **0.11.0**, YAML parse/actionlint 오류 0건. Ubuntu Python의 기존 YAML parser로 service·require flag·gate 연결을 검사하고 5개 run step의 `bash -n`·ShellCheck PASS. repo workflow·프로젝트 의존성·lockfile은 이번 finding 수정에서 변경하지 않았다. 원격 Actions 실행을 뜻하지 않는다.
- 최종 전체 pytest(추가 opt-in 경로 수정 포함): **2022 passed · 26 skipped · 실패 0**, 222.75초. 실제 MySQL 8.4.7 · `DAESINGO_REQUIRE_MYSQL=1` 사용. 최종 JSON/JUnit gate도 **46 passed · skip 0 · xfail 0**, role/scenario 32개·기존 Case 18개·실행 phase 138개 PASS다. 보고서는 작업 전용 OS 임시 디렉터리의 `final-complete.json/xml`에 보관했다.
- skip 26개는 기존 Search 선택 의존성 typer 부재 4 · Case 실영상 없음 2 · eval 로컬 미디어 없음 5 · Recording 실영상/VIDEO_INDEX/연속 원본 opt-in 없음 15다. 신규 회귀에 skip/xfail이 없으며 실제 MySQL 검증을 mock/skip으로 대체하지 않았다.
- boundary PASS(위반 0) · Contract fixture PASS(문서 62 · JSON 26 · 의미 104) · `git diff --check`와 미추적 신규 소스 18개 diff 공백 검사 PASS. Case 코드/fixture/테스트, runtime migration·table, HTTP 매핑, Baseline/Contract/Decision, `uv.lock`은 수정하지 않았다. 커밋·push·PR 생성 없음.
- 최종 검증 뒤 version/port/datadir로 이번 작업 소유임을 확인하고 임시 MySQL 서버를 종료했다. 기존 MySQL service와 `.codex-scratch/`는 변경하지 않았고 JSON/JUnit 증거는 OS 임시 디렉터리에 남겼다.

### 2026-10-08 독립 재리뷰 P2 — ambient 예외의 COMMIT 분류 유입

- Finding: 앞선 cleanup 우선순위 수정의 예외 체인 순회가 현재 `_attempt()`에서 발생하지 않은 과거 DBAPIError까지 선택했다. 실제 MySQL 1205를 처리하는 `except` 안에서 새 API transaction의 COMMIT OK를 proxy로 폐기하면, 독립 observer에 INSERT 1건이 있는데도 `BeforeCommitFailure(lock_wait_timeout)`을 반환했다. 앞선 세 finding의 검증이 이번 결함까지 증명한 것은 아니다.
- 수정: 예외 체인 순회를 제거했다. SQLAlchemy의 공개 `handle_error` event에서 disconnect invalidation/checkin **전**의 COMMIT DBAPIError를 직접 보존한다. `ContextVar`로 이번 시도와 정확한 Connection을 식별하고 COMMIT 구간의 non-query 오류만 기록하므로, 이전 `__cause__`/`__context__`, 다른 connection, commit listener에서 처리된 query 오류는 분류 근거가 되지 않는다. 특정 MySQL 오류 코드에 대한 예외 처리는 추가하지 않았다.
- event observer는 한 번 등록하고 오류를 재작성하거나 로그에 원문을 남기지 않는다. 시도별 token은 `finally`에서 복원하고 connection context 종료 전에 관찰을 끝낸다. body/domain 원래 오류와 직접 발생한 오류를 유지하며, 확인된 COMMIT 성공 > 현재 transaction 원래 오류 > cleanup 오류의 우선순위도 유지한다. cleanup 자체가 DBAPIError인 경우에도 현재 COMMIT 오류를 덮지 못한다.
- RED → GREEN: 기존 구현에서 ambient context/cause 단위 **8 FAIL**, 실제 MySQL 1205 + COMMIT 응답 유실의 cleanup 없음/TimeoutError/DBAPIError **3 FAIL**을 확인했다. 세 실제 재현 모두 최종 오류를 검사하기 전에 observer row 1건을 확인했다. 오류 포착 범위를 보완할 때 처리된 query 오류의 오인도 **1 RED → GREEN**으로 검증했다. 관련 unit/proxy 최종 **66 PASS**(unit 58 + 실제 MySQL proxy 8)다.
- 실제 MySQL **8.4.7 require 모드**의 전체 MySQL 대상 **49 PASS · skip 0 · xfail 0**. 기존 Case MySQL **18개**, 역할/시나리오 **32개 조합**, 수집/선택/실행 **49/49/147 phase**의 JSON/JUnit gate PASS. `-m mysql` 실행 시 별도의 Search collection skip 4개는 선택 의존성 typer 부재이며 MySQL 대상 skip이 아니다.
- 중단된 전체 pytest 프로세스의 정상 종료(exit 0)와 최종 JSON/JUnit을 회수해 결과를 확정했다. **2059 passed · 26 skipped · failed 0 · error 0**, 184.37초다. 실제 MySQL 8.4.7 · `DAESINGO_REQUIRE_MYSQL=1`로 실행한 기존 `ambient-full` 결과를 사용했으며 구현을 다시 시작하거나 pytest를 중복 실행하지 않았다. 이 수치는 재리뷰 이전의 최종 전체 실행 결과이며, 최종 독립 재리뷰에서는 전체 pytest를 재실행하지 않았다. 최종 JSON/JUnit gate 재실행도 **49 PASS · skip 0 · xfail 0**, Case 18개·필수 조합 32개·실행 phase 147개 PASS다.
- 전체 skip 26개: Search의 typer 부재 collection 4 · Case 실영상 없음 2 · eval 로컬 미디어 없음 5(B tier 1 + VL.zip 4) · Recording opt-in 없음 15(영상 지정 없음 8 + VIDEO_INDEX/영상 조건 없음 5 + 연속 원본 pair/placement 없음 2). MySQL 대상과 신규 회귀의 skip/xfail은 없다.
- 최종 정리에서 actionlint 1.7.12 · YAML parse/policy · 5개 workflow run step의 Ubuntu bash 구문/ShellCheck 0.11.0을 다시 실행해 PASS를 확인했다. boundary 위반 0 · Contract fixture 문서 62/JSON 26/의미 104 PASS. `git diff --check` 및 P2 신규 소스의 diff 공백 검사 PASS.
- 임시 MySQL의 version/port/datadir 소유 정보와 `rt02a_test_` schema **0개**를 확인한 뒤 해당 서버만 SHUTDOWN했다. 서버 프로세스 exit 0 · port 13307 닫힘 · PID 파일 제거 · 정상 종료 로그를 확인했다. 기존 Windows MySQL80은 종료 전후 Running/동일 PID/Auto로 유지됐다. 검증은 격리 서버와 작업용 DB에서만 수행했으며 기존 Windows service나 사용자 DB에는 변경 작업을 하지 않았다. 검증용 배포본과 JSON/JUnit 증거는 OS 임시 디렉터리에 남긴다.
- `git status`/`git ls-files`/staged diff로 `recording-baseline-negative-001.json`은 미추적, `.codex-scratch/`는 기존 `.gitignore` 규칙으로 제외되고 두 경로 모두 추적·staging·tracked diff에 없음을 확인했다. 두 경로나 ignore 규칙은 변경하지 않았다. 검증 재개에서는 이 Log의 결과 기록만 갱신했다.
- 이번 수정 파일은 `transactions.py`, transaction unit test, COMMIT proxy integration test, 이 Log뿐이다. schema 격리와 CI gate, Case 소유 코드/fixture/테스트, RT-02(b), Contract/Decision/Baseline, 의존성/lockfile은 변경하지 않았다. `.codex-scratch/`와 `recording-baseline-negative-001.json`도 변경하지 않았다. 검증 증거는 OS 임시 디렉터리의 `ambient-*` 파일에 보관한다.
- 최종 독립 재리뷰 결과(사용자 전달): **RT-02(a) 병합 차단 문제 없음 · P2 수정 재리뷰 통과**. transaction targeted unit **58 passed**, 실제 MySQL 통합 **62 passed**, MySQL 필수 대상 **49 passed · skip 0 · xfail 0**를 확인했다. 기존 Case MySQL **18개**, COMMIT proxy **8개**, 필수 role/scenario **32개 조합**, 실행 phase **147개**를 포함한다. 동일 Engine의 **8-thread 상태 격리** 확인 및 `git diff --check` PASS도 기록했다.
- RT-02(a) P2 재리뷰 당시에는 RT-02(b)가 남아 있었다. P2 수정은 **독립 재리뷰 통과** 판정이었으며, 당시 원격 GitHub Actions 실행·커밋·push·PR 생성은 없었다.

### 2026-10-08 RT-02(b) — Alembic env · runner (최종 독립 리뷰 통과)

**구현 결과**

- `common/db/migrate.py`: frozen registry의 `case → runtime`만 실행한다. 디렉터리 탐색은 미등록/누락 env 검증에만 쓴다. API `upgrade_all(url, *, migrations_root, connect_timeout, read_timeout, write_timeout)`는 명시 URL을 받아 migration engine 하나를 만들고, 모든 DB revision을 읽기 전용 connection으로 사전 검사한 뒤 모듈마다 새 `engine.begin()` connection을 전달한다.
- registry 중복 module/경로/version table, 경로 누락·미등록 env, ini의 version table/script 경로 불일치, script multiple heads를 DB 작업 전에 거부한다. DB unknown revision/multiple version rows는 모든 모듈의 DDL 전에 거부한다. 이것은 version graph 검사이며 수동 schema drift 전체를 탐지하는 기능은 아니다.
- `migrations/runtime/`: env·ini·forward-only template·revision 없는 `versions/`. `upgrade head`는 `runtime_alembic_version`을 생성하지만 0행이다. `job_execution`·usage 등 **Runtime 업무 schema/revision은 추가하지 않았다**(RT-03·RT-07).
- Case Owner 승인에 따라 `migrations/case/env.py`만 최소 수정했다. online `connection → sqlalchemy.url → DAESINGO_MYSQL_URL`, offline `sqlalchemy.url → DAESINGO_MYSQL_URL`. 외부 connection이 있으면 URL 환경변수를 조회하지 않는다. 기존 Case fixture·`test_case_compatibility.py`·revision·metadata·업무 테이블·version table 의미는 그대로다.
- stdin CLI: `python -m daesingo.common.db.migrate --database-url-stdin`. argv에는 credential을 넣지 않는다. API/runner는 URL 환경변수·RuntimeConfig·`.env`·URL 파일·secret manager를 읽지 않는다. 입력 resolver와 배포 실행 위치는 RT-14/RD-12f다. caller도 stdin 공급 과정에서 credential을 argv/로그로 노출하지 않아야 한다.
- CLI는 URL·username·host·query·SQL·경로·exception 원문·traceback을 출력하지 않는다. 고정 메시지만 출력하며 exit는 성공 0/실행 실패 1/사용법·입력 오류 2/interrupt 130이다. terminal의 echo 입력은 허용하지 않는다.

**새 implementation detail · Plan 대비 변경**

- Plan P-1·RT-02(b) 범위대로 구현했다. 새 Architecture Decision, Contract, Accepted Decision, Baseline 값/의미 변경은 없다. authoritative Implementation Plan은 수정하지 않았다.
- process 내부 비재진입 lock으로 중첩/thread 동시 호출을 즉시 거부하고 성공·실패·interrupt 후 상태를 복원한다. **단일 실행 전제이며 cross-process 동시 실행 안전성은 보장하지 않는다.** advisory lock은 이번 범위 밖이다.
- 첫 실패에서 즉시 중단한다. 완료 module은 예외에 안전한 식별자로 남긴다. retry·stamp·downgrade·resume-from 기능은 없다. 앱 startup에서 호출하지 않는다.
- 성공한 module은 재실행 시 version 기준 no-op이다. MySQL DDL implicit commit 때문에 실패한 revision의 부분 DDL은 남을 수 있다. caller의 transaction은 전체 DDL rollback 보장이 아니며, 부분 적용 실패는 검사·복구 없이 자동 재시도하지 않는다. migration은 (a)의 Worker retry helper를 사용하지 않는다.
- timeout은 명시 옵션만 factory에 전달하며 생략 시 driver 기본값을 유지한다. 앱 B-D7 제한을 복사하지 않는다. 기본 migration 경로는 cwd와 독립적이다. 소스 checkout 밖 배포 artifact/wheel의 migration 동봉은 이번 검증 범위가 아니다.
- 기존 MySQL 8.4 workflow/service를 재사용하여 JSON/JUnit gate만 보강했다. (a)의 필수 role/scenario 32개와 기존 Case MySQL 18개를 유지하고 migration check 11개를 추가했다. 의존성·lockfile·workflow·CODEOWNERS 변경은 없다.
- 기존 `mysql_schema_url` fixture를 그대로 재사용하고 임시 migration env 생성 helper는 `tests/migration_support.py`에 뒀다. 새 conftest나 Case fixture 전환 없이 production runner를 직접 호출해 검증한다. Expected files/modules와의 차이는 test helper 배치뿐인 implementation detail이다.

**Owner 확인**

- [유소연 승인 댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/289#issuecomment-6055765577)을 실제 조회했다. `engine.begin()`으로 열린 외부 transaction에서 Alembic이 독자 commit/close하지 않고 caller에게 맡기는 것을 실제 MySQL·SQLAlchemy commit event·새 observer로 확인한다. config URL 테스트는 `%`를 `%%`로 escape하고 percent-encoded 비밀번호도 실제 인증한다. Case에 공통 helper/fixture 전환 의무를 추가하지 않았다.
- 김준영 deferred Audit A: registry/배포 artifact, 단일 실행 전제, 부분 DDL 실패 후 복구, stdin 공급 경계. 배포 시점·secret source는 RT-14/RD-12f에서 정한다.

**구현 단계 RED → GREEN · Verification**

- runner unit RED: 구현 부재 20 failed. 실제 MySQL RED: 외부 connection/config URL 우선순위·runner 부재 12 failed, 기존 환경변수 경로 2 passed. 첫 GREEN: unit+실제 migration 34 passed.
- gate RED: 새 check 11개 제거 시 각각 DID NOT RAISE. 실제 MySQL 전체 보고서에서 항목 제거 테스트도 RED. GREEN: gate unit+실제 보고서 회귀 64 passed. 실제 보고서 회귀는 별도 폐기 schema에서 기존 (a)·Case·(b) MySQL 테스트를 실행하고 각 신규 필수 check의 수집/선택/실행 증거를 제거하여 모두 거부하는지 검사한다.
- 추가 RED→GREEN: `python -m`의 `__main__`과 canonical import가 lock을 따로 만들던 문제를 실제 MySQL로 재현하고 parent package의 process lock을 공유하도록 수정했다. malformed graph의 중복 revision warning도 RED로 재현해 경로를 출력하기 전에 안전한 실패로 바꿨다. 최종 targeted 검증은 **101 passed**다.
- 첫 전체 회귀는 **2124 passed · 2 failed · 26 skipped**였다. 새 테스트 계정명이 MySQL의 32자 제한을 넘긴 fixture 오류와 이를 실행하는 실제 report 테스트의 연쇄 실패였다. 계정명을 줄이고 percent-encoded 비밀번호 실제 인증 테스트를 통과시킨 뒤 아래 최종 전체 회귀로 재검증했다.
- Runtime revision template도 별도 임시 경로에서 실제 revision 생성·downgrade 거부를 확인했다. production `migrations/runtime/versions/`에는 Python revision이 없다.
- 구현 단계 최종 전체 pytest: **2128 passed · 26 skipped · failure/error 0**, 245.34초. 실제 **MySQL 8.4.7**, `DAESINGO_REQUIRE_MYSQL=1`, `-B -X utf8 -m pytest -q -p no:cacheprovider`로 실행했다. 최종 보고서는 OS 임시 경로의 `full-final.txt/json/xml`이다. 전체 pytest는 최종 독립 리뷰에서 재실행하지 않았다.
- 최종 JSON/JUnit gate: **66 MySQL tests · skip 0 · xfail 0 · 198 phases · collection error 0**. 기존 Case **18개**, (a) 필수 check **32개**를 유지하고 (b) check **11개**를 더해 총 **43개**다. 신규 migration 관련 실제 MySQL 테스트는 **17개**이며 기존 (a)·Case를 mock/skip으로 대체하지 않았다. 원격 GitHub Actions 실행 결과는 아니다.
- 전체 skip **26개**는 Search `typer` 선택 의존성 4, Case 로컬 실영상 2, Eval 로컬 B-tier 미디어 1·VL.zip 4, Recording 로컬 영상/명시 opt-in 15다. 모든 개별 node/reason을 OS 임시 경로의 `skips.json` 및 `full-final.txt`에 보관했다. MySQL 대상에는 skip이 없다.
- 빈 별도 schema에서 production runner를 두 번 실행한 후 **새 observer connection**으로 직접 조회했다(`acceptance-state.json`). 테이블은 `cases`, `job_records`, `correction_records`, `analysis_scopes`, `case_alembic_version`, `runtime_alembic_version` 여섯 개다. Case version은 `case_0001` 한 행, Runtime version은 0행이며 공용 `alembic_version`·Runtime 업무 테이블은 없다. 해당 inspection schema는 조회 뒤 정리했다.
- boundary PASS(위반 0), Contract fixture PASS(문서 62·JSON 26·의미 104), actionlint PASS, YAML/MySQL require 정책·Ubuntu bash syntax·ShellCheck PASS(기존 workflow run step 5개).
- `git diff --check` PASS. authoritative Plan·Case fixture/revision·기존 `test_case_compatibility.py`·workflow는 변경하지 않았다.
- 증거는 OS 임시 경로 `C:/Users/cheol/AppData/Local/Temp/rt02b-20261008/`에 보관한다. `.codex-scratch/`·`recording-baseline-negative-001.json`은 변경하지 않았다.

**최종 독립 리뷰 결과 — 사용자 전달**

- **병합 차단 문제 없음**. 완료 처리·커밋·PR 생성 가능 판정을 받았다. 아래 수치는 사용자가 전달한 최종 독립 리뷰 결과이며 이번 문서 갱신에서 테스트를 재실행한 결과가 아니다.
- runner·gate·MySQL integration·Case **163 passed**. 실제 MySQL 필수 대상 **66개 · skip 0 · xfail 0**, 기존 Case MySQL **18개**를 포함한다.
- 필수 check **43개**, 실행 phase **198개**. 실제 보고서에서 신규 check의 수집·선택·실행 증거를 제거한 **33가지 모두 gate가 거부**했다.
- actionlint·YAML·Ubuntu bash·ShellCheck·boundary·Contract·diff **PASS**.
- 전체 pytest **2128 passed / 26 skipped**는 위 구현 단계 결과이며 최종 독립 리뷰에서는 전체 pytest를 재실행하지 않았다.
- Case env 최소 수정의 Owner 확인 근거는 [Case Owner 승인 댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/289#issuecomment-6055765577)이다.
- 원격 GitHub Actions는 **PR 생성 후 확인 예정**이다. RT-02(b) PR 번호·merge SHA는 `pending`을 유지하며, Task 마지막 PR의 본문에는 `Closes #289`를 사용한다.

### 남은 위험 · 비차단 후속 후보

- RT-02 구현과 최종 독립 리뷰는 완료됐으며 원격 CI 확인은 PR 생성 후 진행한다. 후속 Runtime domain transaction·heartbeat lifecycle·HTTP probe budget/E2E는 후속 Task 범위로 남아 있으며, RT-02 완료가 배포 준비 완료를 뜻하지 않는다.
- caller가 외부 작업이나 transaction 탈출을 callback에 넣지 않아야 한다. unknown COMMIT의 재실행 안전성은 각 domain callback이 stable identity/read 조건으로 검증해야 하며 이번 helper만으로 모든 중복을 차단하지 않는다.
- 로컬 gate는 검증됐지만 원격 GitHub Actions 결과는 아직 없다. Case의 의도된 테스트 rename/parametrization 변경 시 gate의 기존 실행 목록도 함께 검토해야 한다.
- cross-process runner 중첩과 부분 DDL 실패의 자동 복구를 지원하지 않는다.
- 테스트 계정 생성 후 GRANT 실패·interrupt에서도 `DROP USER`가 실행되도록 테스트 cleanup 보호 범위를 넓히는 개선은 **비차단 후속 후보**다. production migration 차단 문제는 아니며 이번 문서 갱신에서 코드·테스트를 수정하지 않는다.

---

## RT-03 — `job_execution` schema · queue repository

Status: DONE · Issue: #290 · Audit: A

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| [#332](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/332) | RT-03(a) schema · enqueue · read port — `Refs #290` | `7872c7aa989d0907e5a71608136de5196c230ac0` |
| pending | RT-03(b) claim · worker terminal finish · UTC session · durable receipt · P2 수정/독립 재리뷰 통과 — `Closes #290` | pending |

### 구현 결과

- `migrations/runtime/versions/0001_job_execution.py` → `runtime_0001`: `job_execution` 하나가 실행 원장과 queue를 맡는다. 기존 RT-02 runner `case → runtime`을 그대로 사용하며 모듈 간 FK는 없다. claim index `(status, available_at, execution_id)`, `job_id` index, UNIQUE `(job_id, attempt)`, 양수 attempt·닫힌 status CHECK를 둔다.
- `common/jobs/{schema,repository,read_port}.py`: `enqueue(conn, job_records, trace_id) -> list[str]`는 attempt 1 `QUEUED`를 생성한다. 호출자의 열린 transaction이 필요하며 commit·rollback·close·retry를 하지 않는다. batch metadata 전체를 쓰기 전에 검증하고 한 INSERT로 기록하여 중복이 있으면 해당 statement의 새 row 전체가 거부된다. 호출자 transaction의 실패 처리는 호출자가 소유한다.
- `read_executions(conn, job_ids) -> list[dict]`: 요청한 Job의 모든 attempt를 `job_id, attempt` 순서로 반환한다. 기존 JobExecution validator를 통과한 JSON 호환 Contract projection이며 대표 execution 선택은 case 소유다. 내부 column은 SELECT allowlist로 제외하고 `usage_refs=[]`를 반환한다. usage_refs column·usage ledger는 만들지 않았다.
- RT-03(a) 당시 claim_one·finish·Worker·heartbeat/cancel·retry attempt 생성·usage projection·HTTP API는 구현하지 않았다. 당시 RT-03 전체 완료나 Issue close가 아니었고 PR 연결은 `Refs #290 (RT-03(a))`였다. claim/finish 구현과 최종 판정은 아래 RT-03(b) 기록을 따른다.

### Plan 대비 변경

- Plan §9가 나눈 (a) schema/enqueue/read port만 구현했다. (b)의 claim/finish acceptance는 후속 검증 대상이다. authoritative Implementation Plan은 변경하지 않았다.
- RT-02 migration acceptance의 빈 Runtime schema 기대값을 `job_execution`/`runtime_0001`로 갱신했다. 미래 revision 테스트는 새 첫 revision을 parent로 잇는다. 기존 Case-owned fixture·revision·repository·test 파일과 RT-02 helper/runner 동작은 변경하지 않았다.
- 기존 MySQL JSON/JUnit gate에 RT-03(a) 필수 check 5개를 추가하고 실제 보고서 누락 회귀에 jobs 경로를 포함한다. workflow·의존성·lockfile 변경 없는 검증 보강이다. 실행 세부 계획은 `docs/superpowers/plans/2026-10-08-rt03a.md`다.
- Contract·Accepted Decision·Baseline 값/의미 변경 없음. 다른 Owner에게 새 의무를 만들지 않았다.

### 새 implementation detail

- 내부 column 이름: `available_at`, `lease_owner`, `lease_expires_at`, `heartbeat_at`, `cancel_requested_at`, `case_applied_at`, `trace_id`, `kind`, `case_id`. lease/heartbeat/중단/반영 시각은 최초 enqueue에서 null이다. `available_at=queued_at`이며 첫 attempt에는 backoff가 없다.
- UTC `DATETIME(6)` 저장. enqueue 시 MySQL `UTC_TIMESTAMP(6)`를 한 번 읽어 batch의 queued/available 시각을 일치시킨다. session timezone이나 API/container 시계에 의존하지 않는다. read에서 UTC aware 시각으로 변환한다. B-L6의 lease SQL은 이번에 구현하지 않았다.
- `produced`는 native JSON `ContractRef[]`; Contract envelope/version은 read에서 구성한다. ID는 기존 Case storage와 같은 `ascii_bin`을 사용한다. `job_id` 191, `case_id`/`execution_id`/`trace_id`/`lease_owner` 128, `kind` 64, status 16, failure_kind 191자다. consumed metadata의 빈 값/길이/ASCII 등을 입력에서 검증한다. kind registry를 import하거나 등록 여부를 enqueue에서 거부하지 않는다.
- execution ID는 `exec_`+UUID hex다. 반환 순서는 입력 순서이며 DB unique 오류는 그대로 전파한다. unknown COMMIT 뒤 무조건 재호출해도 성공하는 idempotent callback이 아니므로 composition root의 domain read 조건이 필요하다(RT-02 helper와 같은 경계).
- frozen migration은 live metadata를 import하지 않는다. 미래 metadata 수정으로 과거 revision이 바뀌지 않게 한다.

### Owner 확인 포인트

- 김준영 deferred Audit A: 내부 column 명칭·길이, UTC 저장/Contract 변환, enqueue 반환 ID 순서와 batch atomicity, read port가 모든 attempt를 반환하는 경계.
- claim/finish는 (b)에서 기존 전이표·조건부 UPDATE·lease owner·B-W3/B-L2/B-L6·RC locking을 검증해야 한다. 이번 schema의 lease column이 존재하는 것을 해당 lifecycle 구현 완료로 해석하지 않는다.

### Verification

- 실제 MySQL 8.4.7 별도 임시 서버/폐기 schema를 사용한다. 기존 검증 서버가 응답하지 않아 기존 MySQL 배포 파일과 임시 libaio/libnuma로 준비했다. 시스템 설치나 사용자 DB 변경은 하지 않았다. `DAESINGO_REQUIRE_MYSQL=1`로 실행한다.
- schema/enqueue RED **15 failed**(table/repository 부재) → GREEN **15 passed**. read port RED **10 failed**(read_port 부재) → 신규 jobs 합계 **25 passed**. 첫 RED 수집 전 잘못된 transaction helper import를 바로잡았다. 수집 오류는 기능 RED 근거로 세지 않았다.
- gate RED: 신규 필수 check 5개 각각을 뺐을 때 **DID NOT RAISE 5건** → gate unit·jobs·migration targeted GREEN **109 passed**. migration 기대값 갱신 전 **4 failed / 37 passed**, 갱신 후 위 targeted GREEN에 포함된다.
- 독립 리뷰 P2: 기존 Case가 허용하는 ASCII `case_id`의 끝 공백/탭을 enqueue가 `rstrip()` 검사로 새로 거부했다. 실제 `CaseAggregate`·`issue_job`·`MySQLCaseRepository`를 거친 회귀 **2 failed**를 확인하고 추가 제한만 제거했다. 신규 jobs 실제 MySQL 전체 **27 passed**. 독립 재리뷰에서 해당 P2 해결·추가 actionable finding 없음(최종 전체 회귀 조건부 통과)을 확인했다.
- 첫 전체 회귀 **2227 passed · 26 skipped · 1 failed**: 실제 보고서 생성용 하위 pytest에서 production runner가 한 번 `migration: execution_failed`로 실패했다. 예외 원문을 숨기는 runner의 정책은 바꾸지 않았다. OS 임시 진단 plugin으로 실패 코드/context 유형만 수집하며 해당 report 회귀와 migration test를 다시 실행했고 **2 passed**(실제 하위 MySQL 회귀·신규 check 누락 거부 포함), 오류는 재현되지 않았다. 최초 실패의 원인은 확인하지 못했으며 transient 원인이라고 단정하지 않는다.
- 최종 전체 pytest **2230 passed · 26 skipped · failure/error 0**, 391.40초. Case ID 수정까지 포함한 전체 재실행이며 `DAESINGO_REQUIRE_MYSQL=1`, `-B -X utf8 -m pytest -q -p no:cacheprovider`를 사용했다. `full-final.txt/json/xml`에 증거를 저장했다.
- MySQL JSON/JUnit execution gate **PASS — 실제 MySQL 8.4.7 · 93 tests · skip 0 · xfail 0 · 279 phases · collection error 0**. 기존 Case MySQL **18개**, 신규 jobs **27개**를 포함하며 필수 role/check **48개**를 확인했다. 실제 보고서 회귀는 기존 migration check 11개와 신규 jobs check 5개를 각각 제거해 누락을 거부한다. mock·skip·xfail로 대체하지 않았다.
- 전체 skip 26개는 Search 선택 의존성 `typer` 4개, Case 로컬 영상 2개, Eval 로컬 미디어/VL.zip 5개, Recording 영상/명시 opt-in 15개다. 개별 node/reason은 `skips.json`, 집계는 `summary.json`에 보관한다. MySQL 대상에는 skip이 없다.
- boundary PASS(위반 0), Contract fixture PASS(문서 62 · JSON 26 · 의미 104), `git diff --check` PASS. 원격 GitHub Actions 실행·PR 생성은 하지 않았다. 독립 source 재리뷰는 P2 해결 뒤 추가 actionable finding 없음이며, 최종 전체 회귀·gate는 구현자가 위 수치로 실행 검증했다.
- 변경 파일 15개 목록은 OS 임시 `changed-files.txt`다. HEAD·index는 시작 상태 그대로이며 커밋·push 없음. `recording-baseline-negative-001.json`은 미추적 상태와 SHA-256 `27BA6EE8F681F2DF93C4E147589DD932D4632D71631A77EDE194317D42247D99`를 유지했다. authoritative Plan·Contract·Decision·Baseline·Case-owned 파일은 변경하지 않았다.
- 증거 경로: OS 임시 `C:/Users/cheol/AppData/Local/Temp/rt03a-20261008/`. 최종 검증 뒤 이번에 시작한 임시 MySQL 서버만 종료하며 증거와 배포 파일은 보관한다.

### 2026-10-09 독립 리뷰 P2 — 필수 MySQL parameter 누락 거부

- 기존 gate는 `(role, scenario)` 집합만 확인했다. `read_states` 6개 중 한 상태 또는 `enqueue_duplicate` 2개 중 한 경로를 수집·선택·실행·JUnit에서 함께 제거해도 같은 family의 다른 parameter가 남으면 통과했다. 기존 검증은 family 전체 누락을 검사했으며 개별 parameter 필수 실행까지 보장하지 못했다.
- RED: 개별 parameter 누락 unit 검사 **8 failed / 48 passed**. 이전 실제 MySQL `full-final.json/xml`에서 `FAILED`와 중복 `[True]`를 각각 제거해도 JSON/JUnit gate가 통과하는 것을 별도로 재현했다. 해당 RED JSON/XML과 출력은 OS 임시 `C:/Users/cheol/AppData/Local/Temp/rt03a-p2-20261009/`에 보관한다.
- 수정: 기존 필수 check 48개와 Case MySQL inventory는 유지하고 별도 필수 `(role, scenario, parameter)` 8개를 추가했다. 기존 pytest parameter에 명시적 `mysql_check(..., parameter=...)` marker를 붙여 harness가 식별자를 기록한다. 상태는 6개 enum 값, 중복 경로는 `separate_batch`/`same_batch`다. gate 정책은 pytest 함수명이나 node ID 전체/suffix를 파싱하지 않는다. node ID와 JUnit 주소는 수집·선택·실행 증거를 연결하는 데만 사용한다.
- 기존 선택 집합 일치·setup/call/teardown 완전성·JUnit 대조를 그대로 유지한다. 수집에서 parameter 전체가 사라지면 새 필수 tuple 검사가, 선택/실행/JUnit 중 한 곳만 사라지면 기존 연결 검사가 거부한다.
- 신규 mutation은 8개 parameter × 수집·선택·setup·call·teardown·전체 JSON/JUnit·JUnit의 7가지 누락, 총 **56개**다. 나머지 parameter를 남긴 채 하나씩 제거하며 실제 MySQL 보고서에도 동일하게 적용한다. 기존 family/migration 누락 검사도 유지한다.
- 구현 단계 targeted gate GREEN **124 passed**, 10.70초. 첫 일반 sandbox 실행의 4개 실패는 SQLAlchemy DLL 접근 거부였으며, sandbox 밖 재실행으로 위 결과를 확인했다. 테스트 의미나 skip 조건을 바꾸지 않았다.
- 구현 단계 실제 MySQL 8.4.7 targeted **93 passed / 13 deselected**, 120.75초. 13개는 선택 범위 밖의 비-MySQL Case parameter다. JSON/JUnit gate **PASS — 93 tests · skip 0 · xfail 0**이며 `DAESINGO_REQUIRE_MYSQL=1`로 실행했다. 실제 하위 보고서의 개별 parameter 누락 mutation **56/56 거부**를 `mysql-targeted/test_actual_report_rejects_eac0/parameter-mutations.json`으로 확인했다. 기존 migration/jobs family 누락 검사 16개도 통과했다.
- 구현 단계 최종 전체 pytest **2286 passed · 26 skipped · failure/error 0**, 329.69초. `DAESINGO_REQUIRE_MYSQL=1`, 실제 MySQL을 연결한 채 `-B -X utf8 -m pytest -q -p no:cacheprovider`로 실행했다. skip 26개는 기존 비-MySQL 선택 의존성/로컬 미디어 검사다. `full-final.txt/json/xml`에 증거를 저장했다.
- 구현 단계 전체 실행의 JSON/JUnit gate도 **PASS — MySQL 93 collected/selected · 279 passed phases · skip 0 · xfail 0 · collection error 0**, jobs 27개·Case 18개를 확인했다. 전체 회귀가 생성한 실제 하위 보고서에서도 **56/56 parameter mutation 거부**, 각 필수 parameter당 7개 거부를 확인했다(`full-final/test_actual_report_rejects_eac0/parameter-mutations.json`, 집계 `summary.json`).
- 구현 단계 boundary **PASS — 위반 0**, Contract fixture **PASS — 문서 62 · JSON 26 · 의미 104**, 최종 `git diff --check` **PASS**. 당시 독립 source 재리뷰는 추가 차단/비차단 finding 없이 통과했다. 위 구현 단계의 실제 테스트 실행 수치는 구현자가 검증했다.
- 이번 P2 변경은 gate script, harness, marker 설명(`pyproject.toml`), jobs MySQL test 2개의 parameter marker, gate unit/실제 보고서 mutation test, 이 Log의 **8개 파일**로 한정한다. schema/enqueue/read port source와 migration revision의 수정 전후 SHA-256은 동일하다. 검증 증거는 OS 임시 `C:/Users/cheol/AppData/Local/Temp/rt03a-p2-20261009/`에 보관한다.
- schema·enqueue·read port production 동작, migration runner, Case-owned 파일, Contract·Decision·Baseline 의미 변경 없음. 동시 enqueue 추가 실험과 schema assertion 확대는 포함하지 않았다. RT-03 `IN_PROGRESS`, PR 연결 `Refs #290`을 유지하며 커밋·push·PR 생성은 하지 않는다.
- 검증 뒤 port `13310`·datadir `/tmp/rt03a-p2-20261009/data/`·version `8.4.7`로 작업 소유를 확인하고 이번 임시 MySQL 서버만 종료했다(exit 0). 기존 사용자 변경과 `recording-baseline-negative-001.json`을 보존했으며 보호 JSON의 SHA-256·HEAD·index는 시작 상태와 동일하다. 증거 파일과 임시 배포 파일은 보관한다.

### RT-03(a) 독립 재리뷰 — P2 해소 및 검증 주체 구분

- 독립 재리뷰에서 이전 필수 MySQL parameter 누락 P2가 해소됐으며, RT-03(a)에 남은 병합 차단 문제가 없음을 확인했다.
- 재리뷰에서 targeted gate test를 직접 재실행하여 **124 passed**를 확인했다. 보존된 실제 MySQL JSON/JUnit 보고서를 대상으로 필수 parameter 8개 × 누락 위치 7개의 개별 누락 실험을 직접 재실행했고 **56/56 거부**를 확인했다.
- 재리뷰에서 boundary·Contract fixture·`git diff --check`를 직접 실행하여 모두 **PASS**를 확인했다.
- 전체 pytest **2286 passed / 26 skipped**와 실제 MySQL **93 passed · skip 0 · xfail 0**는 위 구현 단계에서 실행한 결과다. 재리뷰에서는 보존된 출력·JSON/JUnit 증거를 확인했으며, 전체 pytest나 실제 MySQL suite를 새로 실행한 결과로 기록하지 않는다.
- 이 판정은 RT-03(a) 범위다. RT-03은 **IN_PROGRESS**, 이번 PR 연결은 **Refs #290**을 유지한다. 최초 migration 실패 **104.502초**와 원인 미확정 위험은 아래 남은 위험 기록 그대로 유지한다.

### RT-03(b) — 승인된 설계의 구현 (2026-10-09)

- `feature/runtime-job-claim-finish`, 기준 HEAD는 RT-03(a) PR #332 merge SHA다. 설계 승인 뒤 직접 TDD로 구현했다. 구현 당시 독립 재리뷰 전까지 `IN_PROGRESS`였고 마지막 PR의 `Closes #290` 여부는 미확정이었다. 최종 판정은 아래 독립 재리뷰 기록을 따른다. 커밋·push·PR 생성은 하지 않았다.
- `claim_one(engine, worker_id, *, lease_duration_sec, logger=None) -> ClaimedExecution | None`: 공용 RC/UTC engine과 RT-02 Worker helper를 사용한다. covering ID SELECT `(status, available_at, execution_id)` + `LIMIT 1 FOR UPDATE SKIP LOCKED`, 조건부 RUNNING/lease UPDATE, PK snapshot, 확인된 commit 후 frozen DTO 반환이다. callback에는 INSERT·handler·외부 I/O가 없다. 기본 lease 값은 기존 WorkerSettings에서 받고 설정 주입을 허용한다.
- 공개 호출마다 token을 만들고 최초 선택 ID와 함께 재시도 사이에 유지한다. 첫 선택 뒤 재시도는 같은 PK의 locking read로 미해결 transaction을 기다리고 durable 상태를 확인한다. 자기 token/owner의 RUNNING이면서 lease가 유효하면 기존 snapshot을 반환하며 lease를 연장하지 않는다. rollback되어 QUEUED/token null이면 같은 row의 eligibility를 재확인한다. token/owner 불일치·terminal·만료·missing/eligibility 상실은 `ClaimLostError`이며 빈 queue로 바꾸거나 다른 row를 claim하지 않는다. helper 소진은 기존 `outcome_unknown`을 보존한다.
- `finish(conn, execution_id, owner, *, status, produced=(), failure_kind=None) -> int`: caller transaction만 사용한다. 대상 snapshot/ref/model 검증 후 `RUNNING ∧ lease_owner=owner` 조건부 UPDATE가 승패를 정한다. commit·rollback·close·retry를 하지 않는다. SUCCEEDED/FAILED/CANCELLED만 허용하고 CANCELLED produced는 `[]`다. 기존 전이표는 public `validate_transition`으로 재사용하며 STALE 허용 전이 자체는 바꾸지 않는다. STALE 판정/sweep·다음 attempt 생성은 RT-06에 남긴다. terminal 이후 lease/heartbeat/token은 감사 근거로 남긴다.
- `runtime.db.claim_latency_ms`는 monotonic transaction 시작 → COMMIT 응답 확인이다. checkout/checkin/retry 대기/handler를 제외한다. EMPTY·CLAIMED·실패·COMMIT_UNKNOWN을 구분하고 receipt read 복구는 `runtime.db.claim_recovery_latency_ms`로 분리한다. RT-02 선택적 attempt observer는 sanitized outcome/duration만 받으며 sink/운영 logger 오류는 DB 결과나 retry 여부를 바꾸지 않는다.

#### Plan 대비 변경 · implementation detail

- 내부 nullable `claim_token`을 새 forward-only `runtime_0002` revision으로 추가한다. 기존 `runtime_0001`은 불변이다. token index나 별도 receipt/queue table은 만들지 않으며 PK 조회를 사용한다. read port allowlist와 Contract envelope는 그대로여서 token은 비노출이다.
- 공용 application/worker session을 생성·checkout 시 UTC로 고정한다. SET SESSION은 rollback으로 복원되지 않으므로 checkout에서도 복원한다. B-L6은 DB server `NOW(6)` 그대로이며 UTC_TIMESTAMP로 lease 기준을 대체하지 않는다. 기존 enqueue UTC 생성은 변경하지 않는다.
- 기존 migration 테스트의 head 기대값/미래 revision parent를 runtime_0002로 갱신한다. Case-owned 파일·runner 정책·Contract·Accepted Decision·Baseline 값/의미·다른 Owner surface는 변경하지 않는다. authoritative Plan은 구현에 맞춰 고치지 않는다.
- gate에 신규 lifecycle/UTC family와 개별 parameter inventory를 추가한다. 실제 보고서 mutation은 parameter가 포함된 marker에서도 role/scenario family를 찾는다. workflow·dependency·lockfile 변경은 없다.

#### Owner 확인 포인트

- 김준영 deferred Audit A: durable receipt와 동일 PK 재시도, session UTC 복원, finish target의 Worker/recovery 구분, commit acknowledgement/latency 경계. 새 사전 Owner 승인 gate를 만들지 않는다.
- RT-04 이후 composition은 공용 engine과 WorkerSettings lease 값을 사용하고, 공개 claim에서 반환된 snapshot 이후에만 handler를 실행한다. 임의 engine이나 transaction 중 timezone 변경은 지원 경계 밖이다.

#### Verification

- 실 MySQL 8.4.7 별도 임시 서버(port 13311, 폐기 schema), 서버 기본 timezone `+09:00`, `DAESINGO_REQUIRE_MYSQL=1`로 검증한다. 재부팅으로 기존 WSL 임시 배포가 없어 보관 archive와 임시 라이브러리를 이번 작업 디렉터리에 풀었다. 시스템 설치나 사용자 DB 변경은 없다.
- UTC/session/migration RED **7 failed** → foundation GREEN **61 passed**. 새 session/reused/replacement에서 NOW(6)=UTC 시각, runtime_0001의 기존 row를 보존한 token nullable upgrade를 확인했다.
- claim/finish 기능 부재 RED **26 failed**; 최초 fixture assertion 오류는 기능 RED로 세지 않고 테스트 본문 실패로 다시 실행했다. 공용 validator RED **11 failed** → lifecycle·전이 모델 GREEN **51 passed**.
- attempt observer RED **5 failed**, 실제 claim latency RED **1 failed / 18 passed** → observer·기존 transaction 정책·실 COMMIT proxy·queue fault 합계 GREEN **90 passed**. 정상 metric endpoint는 실제 commit acknowledgement 이전에 출력되지 않으며, sink가 DBAPIError를 던져도 재시도가 되지 않는다.
- 재시도마다 queue ID를 다시 선택하는 sensitivity mutation에서 receipt 복구/같은 worker 다른 token 검사 **2 failed**를 확인했다. 즉시 원본을 복원했으며 최종 전체 회귀가 복원본을 검증한다.
- 신규 gate inventory RED **63 failed / 358 passed** → GREEN **421 passed**. 기존 필수 checks·Case inventory와 JSON/JUnit 연결 검사는 유지한다.
- 첫 MySQL require 실행 **144 passed / 1 failed**: 실제 누락 mutation에서 UTC parameter marker를 bare dict와 비교한 테스트 오류였다. actual report에서 실행된 UTC parameter를 확인하고 family 비교만 role/scenario로 수정했다. 수정 뒤 MySQL targeted **145 passed / 571 deselected**, 206.53초, gate **PASS — 145 tests · skip 0 · xfail 0**. deselected는 선택 범위 밖의 비-MySQL tests이며 필수 MySQL 누락이 아니다.
- boundary **PASS — 위반 0**, Contract fixture **PASS — 문서 62 · JSON 26 · 의미 104**, workflow **actionlint 오류 0 + YAML policy/bash -n/ShellCheck 5 run steps PASS**. 보관 검사 binary가 없어 공식 고정 release를 이번 임시 디렉터리에 받았으며 시스템 설치는 없다.
- 최초 전체 회귀 **2656 passed / 26 skipped / 1 failed**, 624.13초. 저장소 밖 임시 진단 plugin의 전역 PYTEST_ADDOPTS가 PYTHONPATH를 교체하는 기존 dependency 부재 검사에 전파돼 plugin import가 실패했다. production/test 코드를 바꾸지 않고 임시 runner의 plugin 전파를 실제 migration child suite로 한정했다. dependency 검사 + 실제 MySQL 하위 gate 재검증 **2 passed**, 157.16초. 최초 전체 보고서의 MySQL gate도 **145 tests · skip 0 · xfail 0 PASS**였다. 실패 증거는 보존한다.
- 실제 보고서의 parameter 누락 mutation **329/329 거부**(47 parameter × 7 layer). 신규 family 전체 누락도 독립 inventory로 검사한다.
- 최종 전체 pytest **2657 passed / 26 skipped**, 712.83초, pytest exit **0**(`full-verified.exit`). 최종 JSON/JUnit gate **PASS — 145 tests · skip 0 · xfail 0**, setup/call/teardown **435 passed**. 하위 재귀 방지 suite도 **144 tests · skip 0 · xfail 0 PASS**다.
- 전체 skip 26건은 기존 선택적 검사다: Search `typer` 부재 4, Case 로컬 영상 부재 2, Eval 로컬 미디어/zip 부재 5, recording 영상/pair/VIDEO_INDEX opt-in 미지정 15. MySQL 대상 skip은 없다.
- 이번 targeted/전체 회귀에서 예기치 않은 migration 실패는 재발하지 않았다(임시 진단 JSON 0건). 과거 단발 실패의 원인 미확정 위험은 유지한다. 재발 대비 진단 plugin은 module·classification·DB errno·완료 모듈·허용 table/version 상태만 보존하며 URL/credential/SQL/exception 원문을 기록하지 않는다. 전역 plugin 환경 전파 오류는 위에 별도로 기록했다.
- 최종 self-review에서 README의 초기 lease 설정과 후속 lease 갱신 범위를 구분했다. 기존 `runtime_0001`과 보호 JSON의 SHA-256은 시작 시점과 같고 기존 pytest scratch 폴더는 건드리지 않았다. HEAD/index는 불변이며 커밋·push·PR 생성은 하지 않았다.
- 증거는 OS 임시 `C:/Users/cheol/AppData/Local/Temp/rt03b-20261009/`의 RED/GREEN 출력, JSON/JUnit, `summary.json`, workflow 결과에 보존한다. 이번 MySQL 서버의 port/datadir/version을 확인하고 해당 서버만 SHUTDOWN했으며 process exit 0이다. 증거·임시 DB data는 삭제하지 않았다.

### RT-03(b) 독립 리뷰 P2 — validation 입력의 내부 column 누수 수정

- RUNNING row의 `finish(status="FAILED")`에서 failure_kind를 생략하면 기존 model validator가 실패하고, Pydantic ValidationError의 보존 input에 DB row의 claim_token/lease/운영 metadata까지 포함됐다. read port의 출력 allowlist만으로 오류 입력 누수를 막을 수 없었다.
- `_execution_model`은 DB row 및 변경값에서 Contract 필드만 새 dict로 투영한 뒤 기존 UTC 변환과 JobExecution 검증을 실행한다. 내부 column은 model 입력에 전달하지 않는다. ValidationError를 그대로 유지하고 catch/wrapping/문자열 치환은 하지 않는다. claim receipt 소유권 복구, DTO, finish의 조건부 UPDATE와 caller transaction 동작은 변경하지 않는다.
- 새 단위 회귀는 원본 read-only row와 내부 override의 누수를 모두 검증한다. 실제 MySQL 회귀는 claim으로 생성된 실제 token과 합성 secret/path를 가진 RUNNING row에서 failure_kind 생략을 재현한다. `str(error)`, `repr(error)`, `error.json()`, `repr(error.errors())` 및 이 표현들을 기록한 일반 로그에 내부 column/value가 없고, input은 Contract 필드뿐임을 검사한다. 검증 실패 뒤에도 caller transaction은 열려 있고 row는 바뀌지 않는다.
- 비차단 의견은 이 Log 색인에만 반영했다: RT-03(a) PR #332 merge SHA, RT-03(b) claim receipt·UTC checkout·attempt observer. authoritative Plan·Contract·Decision·Baseline·runtime_0001은 바꾸지 않는다.
- 수정 전 RED **3 failed / 1 passed**, 2.11초 → P2 targeted GREEN **4 passed**, 1.45초. RT-03 전체 회귀 **83 passed**, 67.63초. 실제 MySQL require **146 passed / 437 deselected**, 302.90초, exit 0. JSON/JUnit gate **146 tests · skip 0 · xfail 0 PASS**, setup/call/teardown **438 passed**. 실제 parameter 누락 mutation **329/329 거부**. deselected는 이 command 선택 범위 밖의 비-MySQL 검사다.
- 구현 단계 최종 전체 pytest **2661 passed / 26 skipped**, 568.30초, exit 0. 구현 단계 최종 JSON/JUnit MySQL gate도 **146 tests · skip 0 · xfail 0 PASS**, phase **438 passed** 및 parameter 누락 **329/329 거부**다. 전체 skip은 기존 선택적 검사(Search typer 4 · Case 영상 2 · Eval 로컬 미디어/zip 5 · recording 영상/pair/VIDEO_INDEX opt-in 15)이며 MySQL skip은 없다. Boundary/Contract fixture/workflow 및 git diff --check PASS. 이번 증거는 `C:/Users/cheol/AppData/Local/Temp/rt03b-p2-20261009/`의 RED/GREEN·전체 출력, JSON/JUnit, mutation, summary에 별도로 보존한다.
- 이번 수정 중 예기치 않은 migration 실패는 재발하지 않았다(진단 JSON 0건). 과거 단발 실패 원인 미확정 위험은 유지한다. runtime_0001·보호 JSON의 SHA-256과 HEAD/index는 수정 시작 시점과 같으며 기존 pytest scratch 폴더는 건드리지 않았다. P2 전용 MySQL 8.4.7의 port 13312/datadir/version을 확인하고 해당 서버만 정상 종료했다. DB data와 증거는 삭제하지 않았다.
- P2 수정 당시 독립 재리뷰 전까지 RT-03은 **IN_PROGRESS**였고 `Closes #290`은 미사용이었다. 이후 최종 판정과 PR 연결은 아래 기록으로 갱신한다. 커밋·push·PR 생성은 하지 않았다.

### RT-03(b) 최종 독립 재리뷰 — P2 해소 및 DONE 판정

- 최종 갱신 요청으로 전달받은 독립 재리뷰 결과를 기록한다. token 오류 데이터 노출 P2는 Contract 필드 allowlist의 새 validation 입력으로 수정됐으며 독립 재리뷰를 통과했다. 이번 문서 갱신에서 테스트를 재실행한 결과로 기록하지 않는다.
- 독립 재리뷰에서 실제 MySQL suite를 **직접 실행**하여 **146 passed · skip 0 · xfail 0**을 확인했다.
- 전체 pytest **2661 passed / 26 skipped**는 위 **구현 단계 실행 결과**다. 재리뷰에서는 보존된 출력·JSON/JUnit 증거를 대조했으며, 전체 pytest를 새로 실행한 결과와 구분한다.
- gate parameter 누락 검사는 위 구현 단계의 실제 보고서에서 **329/329 거부**(47 parameter × 7 layer)로 확인된 기록을 유지한다.
- RT-03 최종 상태는 **DONE**이다. 최종 PR 연결은 **`Closes #290`**이며 PR 번호와 merge SHA는 **pending**으로 유지한다. PR 생성·merge 또는 Issue close가 이미 실행됐다는 의미는 아니다. 이번 문서 갱신에서는 커밋·push를 하지 않는다.
- 과거 migration 단발 실패의 **104.502초** 기록과 **원인 미확정 위험**은 아래 남은 위험 그대로 유지한다.

### 남은 위험

- 독립 재리뷰는 통과했으며 deferred Owner Audit A는 별도 기록 대상이다. RT-04 이후 lifecycle은 이번 검증 범위가 아니며 usage_refs는 RT-07 전까지 빈 목록이다.
- MySQL migration DDL의 부분 적용 실패는 runner 자동 retry/rollback으로 복구되지 않는다. 기존 RT-02 운영 경계 그대로다.
- ID/metadata column 상한과 UTC 저장 규칙을 후속 writer도 지켜야 한다. unknown COMMIT 결과의 idempotency와 command 원자성 실제 HTTP 배선은 후속 composition에서 다룬다.
- 첫 전체 회귀의 단발 migration 실패 검사는 하위 JUnit(`rt03a-20261008/full/test_actual_report_rejects_eac0/mysql.xml`)에 **104.502초**로 기록돼 있다. 2026-10-09 해당 testcase의 `time="104.502"`를 직접 확인했다. 원인은 미확정이며 network·timeout·파일 접근 등 특정 원인으로 단정하지 않는다. 실패를 skip/mock/retry 코드로 우회하지 않았고 진단 재실행은 통과했다. 이번 P2를 이유로 migration runner 등 production 동작은 변경하지 않았다.

---

## RT-04 — Worker core: claim loop · kind registry · dispatch · T1/T2 (E2E-0)

Status: DONE · Issue: #291 · Audit: A

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| [#336](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/336) | RT-04(a) loop · registry · T1 — `Refs #291` | `d08b29a` |
| pending | RT-04(b) T2 · E2E-0 · 최종 PR — `Closes #291` | pending |

### 구현 결과

- `python -m daesingo.worker` entrypoint가 RT-01 bootstrap과 RT-02 Worker engine을 연결한다. concurrency knob 없이 한 main thread가 실행하며, SIGINT/SIGTERM은 다음 idle 지점에서 반영한다. 실행 중 handler와 T1 기록은 중단하지 않는다.
- 단일 `KindRegistry`는 kind→invocation mapping의 불변 snapshot이다. 실제 Recording/Search handler 등록은 비어 있으며 fake handler로 경로를 검증한다. 미등록 kind는 invocation 없이 `RUNTIME_UNREGISTERED_KIND`로 `FAILED`, 비정상 반환값·handler/dispatch 예외는 `RUNTIME_` failure로 기록한다.
- `ExecutionContext`는 execution/job/case/kind/attempt/trace와 cancel·usage injection 자리를 갖는다. cancel·usage 동작은 구현하지 않는다. `HandlerResult`는 성공/실패 및 produced만 담고 모듈 failure taxonomy를 재해석하지 않는다.
- claim commit 뒤 connection을 반환하고 handler를 실행한다. T1은 기존 `finish`와 `run_worker_transaction`을 재사용한다. B-D8 소진 뒤 B-Q3 간격으로 같은 결과만 재기록하며 handler를 재호출하지 않는다. 조건부 전이 0 rows는 현재 owner·status·produced·failure를 잠금 재조회해 unknown COMMIT의 동일 결과인지 구분한다.
- started/completed와 DB 오류 event는 RT-01 structured logging으로 기록한다. execution DB 오류에는 trace/case/job/execution correlation을 연결한다. 예외 원문, produced ref, failure taxonomy 원문, 경로, provider/user payload와 claim token은 로그에 전달하지 않는다.

### Plan 대비 변경

- Plan의 두 PR 경계 중 RT-04(a)만 구현했다. T2 `ResultReflector`·후속 enqueue·Case 반영·E2E-0 최종 연결은 RT-04(b)에 남긴다. Expected files/modules에 `common/jobs/execution.py`를 추가해 Runtime이 Worker registry에 의존하지 않게 했다. 구현 구조의 선택이며 Contract·Accepted Decision·Baseline 의미 변경은 없다.
- 기존 MySQL JSON/JUnit gate에 Worker 필수 role/scenario와 parameter를 추가하고 실제 보고서 mutation 검증의 child suite에 Worker MySQL 경로를 포함한다. child timeout의 여유만 늘리며 운영 interval은 바꾸지 않는다. workflow·의존성·migration 변경 없음.

### 새 implementation detail

- scheduler의 idle wait와 T1 DB backoff sleep을 분리한다. idle은 signal event로 깨어나지만 T1 재시도는 종료 요청에도 결과를 유지한다. stop flag는 다음 claim 앞에서만 확인한다.
- terminal completion log는 commit 또는 동일 owner의 동일 durable terminal 결과를 확인한 뒤에만 기록한다. 다른 owner/status/result 또는 missing row는 `runtime.execution.finish_rejected`로 관측하고 성공을 단정하지 않는다. RT-05의 lease 보유 확인·heartbeat는 아직 붙이지 않는다.
- entrypoint의 revision은 build revision 공급 경로가 없는 현재 상태를 `unknown`으로 기록한다. RT-01의 config 파일·Search credential validation은 유지한다.
- job ID의 event token 상한을 기존 DB 저장 경계인 191자에 맞춘다. storage-valid ID라도 경로·제어문자가 있으면 로그에서만 SHA-256 기반 `id_` alias로 일관되게 연결하고 DB/handler의 원래 ID는 유지한다. correlation 오류가 dispatch를 중단하거나 경로 원문을 노출하지 않게 하는 구현 선택이다.

### Owner 확인 포인트

- RD-09a Gate: [Issue #334의 Runtime Owner 승인](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/334#issuecomment-6081077166)을 확인했다. 실제 handler 연결 시 RecordingService mutable cache/working state는 execution마다 새 service + `finally: close()`로 제한한다. durable repository/persistence를 execution마다 새로 격리한다는 의미는 아니다. 이 PR에서는 domain service를 만들거나 lifecycle을 확장 구현하지 않는다.
- RT-04(b)의 T2 공개 반영 port는 Case Owner와 Consult 뒤 연결한다. 이번 작업에서 다른 Owner에게 새 공개 surface 의무를 만들지 않았다.

### Verification

- 초기 unit RED 22 failed → GREEN 22 passed. entrypoint RED 3 failed와 실제 MySQL composition RED 10 failed를 확인한 뒤 Worker 전체 GREEN **42 passed**, 19.43초(실제 MySQL 신규 10개, skip/xfail 없음)를 확인했다.
- Worker 필수 MySQL check 누락 RED **6 failed** → gate GREEN **469 passed**. ID logging 경계 RED **2 failed** → unit/structured logging GREEN **33 passed**. 종료 시 dispose 오류 원문 노출 RED **1 failed**도 확인해 고정된 cleanup failure event로 처리했다.
- 최종 관련 회귀 **540 passed**, 32.43초. Worker 47개(실제 MySQL 12개 포함), structured logging 9개, gate unit 484개이며 skip/xfail 없음.
- 실제 MySQL require `pytest -m mysql`: **158 passed / 4 skipped / 2628 deselected**, 247.33초, exit 0. JSON/JUnit gate **158 tests · MySQL skip 0 · xfail 0 PASS**. 명령의 skip 4개는 `typer` 부재로 수집되지 않은 비-MySQL Search 테스트이며, deselected는 선택 범위 밖 검사다.
- 전체 pytest(MySQL require): **2764 passed / 26 skipped**, 429.12초, exit 0. JUnit **2790 tests / failures 0 / errors 0 / xfail 0**. skip 사유는 Search `typer` 부재 4, Case 로컬 영상 부재 2, Eval 로컬 미디어/zip 부재 5, Recording 실영상·pair·VIDEO_INDEX opt-in 미지정 15다. MySQL test skip은 없으며 Recording synthetic media smoke도 실제 실행 PASS다.
- 전체 실행의 최종 JSON/JUnit MySQL gate도 **158 tests · skip 0 · xfail 0 PASS**, setup/call/teardown **474 passed**. 전체 실행 안의 실제 보고서 parameter 누락 mutation도 **385/385 거부**다. evidence는 이번 작업 전용 `C:/Users/cheol/AppData/Local/Temp/rt04a-20261009/`의 `focused-final.{json,xml}`, `mysql-require.{txt,json,xml}`, `full.{txt,json,xml}`이며 기존 pytest scratch 폴더를 재사용하거나 수정하지 않았다.
- MySQL server **8.4.7**, parent setup/call/teardown **474 passed**. 실제 보고서를 만드는 child suite는 **157 MySQL tests**이며, parameter 누락 mutation **385/385 거부**(Worker 신규 8 parameters × 7 evidence layers = **56/56** 포함)를 확인했다. child 실행 수는 parent 실행 수와 분리해 기록한다.
- boundary PASS(위반 0), Contract fixture PASS(구조 62 / JSON 26 / 의미 104 검사), 저장소 전체 workflow 5개 Actionlint·ShellCheck PASS(0 errors), Python CI YAML policy·Ubuntu `bash -n`·ShellCheck PASS(5 run steps), `git diff --check` PASS. Actionlint의 pyflakes 검사 미실행은 기존 검사 방식과 같으며 여기서 Python type/lint gate 완료를 주장하지 않는다.
- 읽기 전용 독립 코드 리뷰에서 RT-04(a)의 수정 필요 P1/P2/P3 결함 없음. reviewer는 테스트를 재실행하지 않았고, 실제 실행 결과의 검증 주체는 이 작업이다. 최종 gate 통과 조건부 판단이며 RT-04 전체 완료나 Owner acceptance를 뜻하지 않는다.
- 기준 HEAD와 최신 fetch `origin/develop`은 `c319275e482a74974b434f0b2515878517d4d0b4`로 동일했다. HEAD/index 변경 없이 구현했다. 보호 대상 `recording-baseline-negative-001.json`의 SHA-256은 `27BA6EE8F681F2DF93C4E147589DD932D4632D71631A77EDE194317D42247D99`로 유지한다.

### 남은 위험

- heartbeat·lease 갱신·cancel·STALE/sweep·다음 attempt 생성·usage 영속·실제 handler는 제외했다. DB 장기 장애 때 T1은 B-Q3 재시도를 계속하므로 종료 신호 반영도 지연된다. RT-05의 소유 상실 관찰과 RT-06 복구가 필요하다.
- 이번 결과는 RT-04(a)의 T1 경로 검증이며 E2E-0 전체 완료를 뜻하지 않는다. RT-04 상태는 `IN_PROGRESS`, PR 연결은 `Refs #291`이다. 커밋·push·PR 생성 및 Issue close는 하지 않는다.

### 2026-10-09 후속 독립 리뷰 P2 — Worker logging sink 장애 격리

- 후속 독립 리뷰에서 아래 P2 두 건이 발견됐다. 위의 최초 “수정 필요 P1/P2/P3 결함 없음” 기록은 당시 읽기 전용 리뷰 결과로 보존하며, 이번 결함까지 없다는 보장으로 해석하지 않는다. 전달된 finding을 코드와 별도 RED로 검증한 뒤 순서대로 수정했다.

| Finding | RED 재현 | 수정과 GREEN |
| --- | --- | --- |
| loop의 직접 logging 호출에서 filter/handler 예외가 dispatch·T1 또는 DB 회복을 중단 | 실제 MySQL에서 started/completed/claim DB/T1 DB × filter/handler **8 failed**. claim_lost/finish_rejected도 별도 RED **4 failed** | Worker loop의 event 호출만 `log_event_best_effort`로 변경. 실제 commit·terminal facts·produced와 handler 1회, claim B-Q3, T1 B-D8 3회 소진 뒤 B-Q3를 검증. 관련 logging/loop/MySQL/observer **63 passed** |
| main 오류·cleanup 로그의 sink 예외가 원래 오류 위에 전파되어 stderr에 원문 노출 | 실제 subprocess에서 loop/cleanup/동시 오류 × filter/handler **6 failed**, 정상 sink 및 정상 실행 **6 passed**. stderr traceback에 테스트용 secret·경로·payload가 포함됨 | main의 두 오류 event도 같은 helper로 변경. 정상/loop/cleanup/동시 오류 × healthy/filter/handler **12 passed**, stderr 비어 있음·기존 종료 코드·dispose·signal 복원 보존. cleanup 자체 실패의 기존 code 1 정책도 유지 |

- 중앙 `log_event()` 전체의 sink 예외를 삼키는 방식은 기존 API와 다른 모듈의 동작까지 바꾼다. Worker 호출 전체를 `try/except`로 감싸면 event/correlation 검증 오류도 숨긴다. 따라서 검증 코드를 공유하는 별도 helper를 추가하고 Worker만 선택적으로 사용한다. 기존 `log_event()`의 sink 예외 전파 계약은 filter/handler 회귀로 유지 확인했다.
- event/field/context 검증은 sink `try` **밖**에서 수행한다. unsafe name·payload field·경로 ID·NaN duration·미등록 field는 계속 `ValueError`이며 sink 호출 전 거부된다. 같은 `ValueError`라도 filter/handler 호출에서 발생하면 일반 sink 장애로 격리한다. logger 내부의 임의 버그와 transport 장애를 예외 타입만으로 완전히 구분한다는 의미는 아니다.
- 격리는 기존 transaction `_emit`·observer처럼 일반 `Exception`에만 적용한다. `KeyboardInterrupt`/`SystemExit`는 전파되며 fallback traceback·원문·추가 stderr 진단을 출력하지 않는다. 기존 stream `OSError`의 고정 `log.write.failed` event와 정상 structured correlation은 유지한다.
- 실제 MySQL 신규 8개에서 T1 observer에도 DBAPI 형태 예외를 동시에 주입한다. transaction 자체는 기존 helper로 실행하고 실제 `KILL CONNECTION`으로 3회 disconnect를 만든다. DB/queue/transaction mock 또는 skip으로 대체하지 않으며 결과·produced·retry·sleep·observer attempt 횟수를 확인한다.
- JSON/JUnit gate에 `worker_core/logger_isolation`과 8개 필수 parameter를 추가했다. 독립 inventory로 family 또는 개별 parameter 전체 누락을 거부하지 못하는 gate RED **9 failed**를 확인한 뒤 필수 목록을 갱신했다.
- 최종 targeted: Worker·entrypoint·structured logging·gate·observer **640 passed**, 69.98초, skip/xfail 없음. Worker 실제 MySQL **20 tests / 60 passed phases**를 포함한다.
- 실제 MySQL require 필수 경로: **166 passed / 16 deselected / skip 0 / xfail 0**, 371.01초, exit 0. MySQL **8.4.7**, 최종 JSON/JUnit gate **166 tests / 498 passed phases PASS**. child는 **165 MySQL tests**이며 parent 실행 수와 분리한다. 실제 보고서 parameter 누락 mutation **441/441 거부**(Worker 16 parameters × 7 layers = **112/112**, 신규 logger 8 parameters × 7 layers = **56/56** 포함).
- 전체 pytest(MySQL require, 2026-10-10 완료): **2859 passed / 26 skipped**, 718.87초, exit 0. JUnit **2885 tests / failures 0 / errors 0**, MySQL 최종 JSON/JUnit gate **166 tests / 498 passed phases / skip 0 / xfail 0 PASS**. 전체 실행의 child **165 tests**, parameter 누락 mutation도 **441/441 거부**(Worker **112/112**, 신규 logger **56/56**). skip 사유는 Search `typer` 부재 **4**, Case 로컬 영상 부재 **2**, Eval 로컬 미디어/zip 부재 **5**, Recording 실영상·pair·VIDEO_INDEX opt-in 미지정 **15**이며 MySQL skip은 없다. Recording synthetic media smoke도 실제 실행 PASS다.
- evidence는 별도 `C:/Users/cheol/AppData/Local/Temp/rt04a-p2-20261009/`의 `loop-red`, `main-red`, `main-green-gate-red`, `targeted`, `mysql-require`, `full` 보고서이며 pytest basetemp도 새 `rt04a-p2-*` 경로만 사용한다. 기존 보호 JSON과 pytest scratch 폴더는 변경·staging하지 않았다. 보호 JSON SHA-256은 위 최초 기록과 동일하다. 검증 뒤 port/version/datadir로 작업 소유를 확인한 MySQL만 정상 종료했다.
- boundary **PASS — 위반 0**, Contract fixture **PASS — 구조 62 / JSON 26 / 의미 104**, 전체 workflow **5개 Actionlint/ShellCheck PASS — 오류 0**, Python CI YAML policy·`bash -n`·ShellCheck **5 run steps PASS**. 기존 방식과 같이 Actionlint pyflakes는 실행하지 않았다.
- 후속 읽기 전용 source 리뷰에서 이번 P2 수정 범위의 추가 actionable P1/P2/P3 finding 없음. reviewer는 테스트를 재실행하지 않고 RED/targeted artifact와 소스를 확인했으며 당시 require/full은 진행 중이었다. 최종 실제 실행 검증 주체는 구현자다. 이 source 리뷰는 RT-04 전체 완료나 merge/Owner 승인 판정이 아니다.
- 최종 `git diff --check` **PASS**. 변경된 untracked Python 파일의 trailing whitespace도 별도 확인했다. HEAD/index 불변이며 커밋·push·PR 생성은 하지 않았다. 이번 P2 수정 결과는 사용자 독립 재리뷰 요청 가능 상태다.
- Contract·Decision·Baseline 의미, queue/transaction 정책, RD-09a 경계, RT-04(b)의 T2/Case 반영/E2E 범위는 변경하지 않았다. sink 장애 동안 일부 event가 유실될 수 있으며 log delivery 보장은 이번 수정 범위가 아니다. 상태는 계속 `IN_PROGRESS`, PR 연결은 `Refs #291`이다.

### 2026-10-10 RT-04(a) 독립 재리뷰 통과 — P2 해소 및 검증 주체 구분

- 사용자에게 전달받은 독립 재리뷰 통과 결과를 후속 기록한다. 이전 P2 두 건, 즉 logger 장애가 dispatch·T1·B-Q3·B-D8 흐름을 중단하던 문제와 entrypoint 오류·cleanup 로그 실패가 traceback·예외 원문을 노출하던 문제가 해소됐음을 확인했다. 앞선 최초 리뷰 및 P2 발견·수정 기록은 당시 이력으로 보존한다.
- `log_event_best_effort`는 event/field 검증 **이후** sink 호출에서 발생하는 일반 `Exception`만 격리한다. unsafe 입력 검증 오류와 `KeyboardInterrupt`·`SystemExit` 등 `BaseException` 전파는 유지한다. 기존 `log_event()`의 계약은 변경하지 않았다.

**독립 재리뷰 직접 실행 결과 — 사용자 전달**

| 검증 | 결과 |
| --- | --- |
| 비-MySQL 관련 회귀 | **620 passed** |
| 실제 MySQL require | **166 passed · skip 0 · xfail 0** |
| Worker MySQL (위 MySQL 대상에 포함) | **20 passed** |
| entrypoint subprocess (위 비-MySQL 대상에 포함) | **12 passed** |
| gate setup/call/teardown execution phase | **498 passed** |
| parameter 누락 mutation | **441/441 거부** |
| `git diff --check` | **PASS** |

- 전체 pytest **2859 passed / 26 skipped**는 위 **구현 단계 직접 실행 결과**다. 독립 재리뷰에서는 전체 pytest를 다시 실행하지 않고 보존된 증거를 대조했다. boundary·Contract fixture·workflow 정적 검사는 구현 단계에서 통과했으며 이번 독립 재리뷰에서는 반복 실행하지 않았다. 이번 문서 갱신에서도 테스트나 위 정적 검사를 재실행하지 않고 `git diff --check`와 `git status --short`만 확인한다.
- event sink 장애 중 해당 event가 유실될 수 있음은 허용된 한계다. 원격 CI는 미실행이며, T2·Case 반영·E2E-0 최종 연결은 RT-04(b)에 남아 있다.
- RT-04 상태는 계속 **`IN_PROGRESS`**다. RT-04(a)의 PR 연결은 **`Refs #291`**, **PR 번호 `pending` · merge SHA `pending`**이며 Issue를 닫지 않는다. 이번 갱신에서 다른 코드·테스트·문서는 수정하지 않고 커밋·push·PR 생성도 하지 않는다.

---

### 2026-10-10 RT-04(b) — T2 port · 원자적 전달 · fake E2E-0

Status: **IN_PROGRESS** · PR 연결: **`Refs #291`** · RT-04(b) PR 번호 **pending** · merge SHA **pending**. RT-04 전체 독립 재리뷰와 Owner acceptance 전이며, 최종 PR 후보지만 `Closes #291`은 확정하지 않는다. 기존 RT-04(a) 구현·리뷰·P2 이력은 당시 기록 그대로 보존한다.

**기준과 Owner 합의**

- 시작 시 현재 branch는 `feature/runtime-worker-t2-e2e0`, HEAD와 최신 fetch한 `origin/develop`은 `a3e4162afd6850baec4e727cf530d891f8dd4dcd`였다. RT-04(a)는 [PR #336](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/336), merge `d08b29a2701456fabeeee8a9082dc3a5b5f9ef3d`의 구현을 재사용한다. 앞선 (a) 절의 PR pending은 당시 기록이며 현재 기준 상태와 구분한다.
- [Case Owner 합의](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/291#issuecomment-6087010126), [Runtime Owner 승인·metric 정의](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/291#issuecomment-6091819255), [PR #337 이후 진행 승인](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/291#issuecomment-6092077761)을 확인했다. 호출자 Connection · Case 먼저 잠금 · execution_id idempotency · reflector 내부 commit/rollback/retry 금지 · 정상 반환 세 종류 모두 전달 완료라는 경계를 따른다.
- [PR #337](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/337), merge `a3e4162afd6850baec4e727cf530d891f8dd4dcd`로 동기화된 최신 Baseline §6에 따라 metric은 **attempt >= 2 AND NOT_APPLIED AND STOPPED_WAITING**만 집계한다. attempt 1 · CANCELLED · SUPERSEDED · ALREADY_APPLIED · reflector 예외는 제외한다. Tech Spec §12.2 및 Plan §6 RT-04 · §12가 나머지 기준이다.

**구현과 transaction 경계**

- `common/jobs/reflection.py`에 `ResultReflector.reflect(Connection, ReflectionInput)` Protocol과 frozen/slots 입력·출력·후속 `RuntimeJobRecord`를 추가했다. 입력은 execution/job/case/kind/attempt와 terminal snapshot, 후속 JobRecord는 기존 `enqueue`가 소비하는 job_id/case_id/kind projection이다. Case intent/payload/JobRecord schema를 Runtime이 새로 소유하지 않는다.
- `APPLIED`만 같은 Case의 후속 JobRecord를 반환할 수 있다. ALREADY_APPLIED 및 NOT_APPLIED의 후속 JobRecord, 잘못된 reason/status, extra key/value, 객체 변조, 중복 job_id, 다른 Case의 후속 JobRecord를 정적 오류 메시지로 거부한다. mutable 입력 목록은 tuple snapshot으로 보존한다. 잘못된 반환은 T2 rollback 대상이다.
- Worker는 기존 T1 `finish` commit이 확인된 뒤 T2를 호출한다. 종료 신호가 handler 중 설정돼도 T1/T2까지 진행하고 다음 idle 지점에서 반영한다. handler 중 DB connection/transaction이 열리지 않는 보장을 유지한다. T1 거부 시 T2를 실행하지 않는다.
- T2는 기존 Worker engine과 `run_worker_transaction`을 재사용한다. reflector가 Case를 잠금·반영한 후 Runtime이 execution을 잠금 조회하여 terminal status/produced/failure 및 execution/job/case/kind/attempt/trace를 대조한다. 이후 **같은 Connection/transaction**에서 후속 `enqueue`와 조건부 `case_applied_at=UTC DB 시각` UPDATE를 수행한다. Case lock → Runtime lock/write 순서이며 T1 transaction과 분리된다.
- APPLIED · ALREADY_APPLIED · NOT_APPLIED(STOPPED_WAITING/CANCELLED/SUPERSEDED)의 정상 반환은 모두 표식을 남긴다. UPDATE 0 rows는 단순 성공으로 보지 않고 durable terminal facts와 이미 기록된 표식을 잠금 재조회해 확인한다. missing/mismatch/미기록 표식은 rollback한다.
- COMMIT 응답 유실 재실행은 먼저 Case의 execution_id 중복 판정을 받고 Runtime 표식을 확인한다. 이미 완료된 표식은 ALREADY_APPLIED로 복구하여 후속 execution을 다시 생성하지 않는다. 이미 표식이 있는데 APPLIED를 반환하면 Case idempotency 충돌로 안전하게 거부한다. Case 변경·후속 enqueue·표식 중 하나라도 실패하면 T2 전체 rollback하고 기존 T1 SUCCEEDED/FAILED는 유지한다.
- B-D8은 초회 포함 총 3회 · 재시도 간 1초다. retryable DB 오류만 기존 helper가 재시도하며 소진·reflector 예외 이후 안전한 `runtime.reflect.failed`를 기록하고 다음 claim을 계속한다. 표식 없는 terminal은 향후 RT-06 재전달 대상이다. 기존 observer/DB `_emit` 격리 정책과 `log_event_best_effort`를 그대로 사용하여 일반 sink/observer Exception이 DB 결과·retry·sleep 판단을 바꾸지 않는다. BaseException 및 unsafe log 검증 오류를 무조건 삼키는 변경은 없다.
- metric은 T2 commit 확인 후 위 조건에만 기록한다. rollback과 ALREADY_APPLIED 복구/중복 전달은 집계하지 않는다. trace/case/job/execution correlation을 연결하며 내부 token · SQL · 원문 예외 · 경로 · provider/user payload는 event에 전달하지 않는다.

**TDD 및 source 리뷰**

- immutable port/taxonomy/반환 불변조건 **20 RED**, Worker T1→T2 순서·실패 격리 **7 RED**, 실제 MySQL T2 acceptance **35 RED**를 각각 실제 실행한 후 구현했다. 첫 MySQL GREEN은 34 passed / 1 failed였으며 missing execution 전에 fake 확인 코드가 먼저 실패하는 테스트 문제를 수정한 뒤 모델·loop·실제 MySQL 합계 **81 passed**를 확인했다. extra-field 이름 자체의 비밀/경로 노출도 **3 RED**로 재현하고 generated dataclass 오류 대신 정적 검증 오류를 사용했다.
- 실제 MySQL에 B-D8 disconnect 소진 · 다음 Job 진행 · 동시 중복 전달 3개를 추가했다. 최초 assertion의 기존 event 이름/seed 순서 가정 오류를 바로잡았으며 이는 새 production 결함 RED로 집계하지 않는다. T2 신규 MySQL은 총 **38개**다.
- 독립 inventory로 신규 T2 role/scenario 9개 및 parameter 38개 누락을 거부하지 못하는 gate **47 failed / 749 passed** RED를 확인했다. JSON/JUnit gate 필수 목록과 실제 보고서 mutation child suite에 T2를 연결했다.
- fresh 읽기 전용 source 리뷰는 terminal 재검증의 P2 1건을 발견했다: Pydantic serializer warning이 변조 원문을 노출하고 `model_copy` extra 저장 필드를 조용히 제거했다. 입력·Worker의 produced/terminal extra/nested ref extra/type 변조 **8 RED**로 재현했다. `validated_terminal`이 저장 필드 shape를 먼저 검사하고 `warnings="error"`를 정적 ValueError 경계 안에서 처리하도록 수정했으며 관련 **54 passed** GREEN을 확인했다. 기존 Contract reference 파서·extra 정책은 바꾸지 않았다. reviewer는 DB suite를 직접 실행하지 않았고 수정 후 별도 재리뷰를 하지 않았으며 최종 회귀는 구현자 실행이다. Critical/Minor finding은 없었다.

**최종 검증 — 구현자 직접 실행**

- 수정 후 Worker·jobs·structured logging·observer·gate targeted **1075 passed**, 157.55초. 이 command의 실제 MySQL **138 passed · skip 0 · xfail 0**, execution phase **414 passed**이며 T2 신규 **38 passed**가 포함된다.
- 실제 MySQL require **204 passed / 44 deselected**, 443.32초, exit 0. deselected는 해당 command 범위의 비-MySQL 테스트다. JSON/JUnit gate **204 tests · skip 0 · xfail 0 PASS**, execution phase **612 passed**. nested 실제 보고서 suite도 **203 passed · skip 0 · xfail 0**, phase **609 passed**로 검증했다(상위 204와 별도 실행이며 두 수를 하나의 고유 test 수로 합산하지 않는다).
- 실제 보고서 parameter 누락 mutation **707/707 거부**(101 parameter × 7 layer), 신규 T2 **266/266 거부**(38 × 7). 신규 `worker_t2` role 전체 및 scenario 9개 개별 누락도 실제 보고서에서 **10/10 거부**했다. T2 신규 **38 passed**에 metric 포함/제외 · 두 sink 종류 · 실제 Connection kill/COMMIT 응답 유실 · 동시 전달이 포함된다.
- **E2E-0 PASS**: enqueue → claim → transaction 없는 dummy handler → T1 SUCCEEDED → fake reflector 1회 호출/1회 반영 → 후속 QUEUED enqueue 및 case_applied_at → read port SUCCEEDED를 실제 MySQL에서 확인했다.
- 첫 전체 pytest는 **1 failed / 3210 passed / 26 skipped**, 554.36초였다. 하위 실제 suite의 기존 `test_api_real_precommit_failure_never_reexecutes_callback[kill]`에서 blocker rollback이 MySQL 2013/Windows 10053 TLS socket abort로 실패하여 상위 `test_actual_report_rejects_each_missing_migration_check`가 실패했다(하위 **202 passed / 1 failed**). 이 실패 보고서는 JSON/JUnit gate도 정상적으로 거부했다. 같은 설정의 해당 실제 MySQL test를 **5회 직접 재실행해 5/5 passed · skip 0 · xfail 0**였으며 원인은 미확정이다. 실패를 skip/mock/자동 test retry로 우회하거나 DB helper·기존 test 동작·TLS 설정을 바꾸지 않았다. 첫 실패 증거는 보존하고 전체 회귀를 같은 코드/설정으로 새 폴더에서 다시 실행한다.
- 최종 전체 재검증은 **3211 passed / 26 skipped**, 563.91초, exit 0이다. 전체 실행의 MySQL JSON/JUnit gate도 **204 tests · skip 0 · xfail 0 PASS**, phase **612 passed**이며 nested suite **203 passed**, phase **609 passed**, parameter 누락 **707/707 거부**(신규 T2 266)를 다시 대조했다. skip 사유는 기존 선택적 검사 **Search typer 미설치 4 · Case 로컬 영상 없음 2 · Eval 로컬 미디어/zip 없음 5 · Recording 영상/pair/VIDEO_INDEX opt-in 미지정 15**이며 MySQL skip은 없다. gate unit 전체 **816 passed**도 targeted JUnit으로 대조했다.
- Boundary **위반 0**, Contract fixture **구조 62 · JSON 26 · 의미 104 PASS**. workflow **Actionlint 5 files · YAML policy · bash -n/ShellCheck 5 run steps PASS**이며 Python pyflakes는 이 정적 검사에서 비활성이다. 원격 CI는 실행하지 않았다.
- 증거는 이번 작업의 새 폴더 `C:/Users/cheol/AppData/Local/Temp/rt04b-20261010/`에 보존한다. 보호 JSON hash와 HEAD/index를 확인했고 기존 `.pytest-*` 폴더를 테스트 basetemp로 사용하지 않았다. 커밋·staging·push·PR 생성 없음.

**Plan 대비 차이와 남은 위험**

- Plan의 넓은 “case가 반영하지 않았을 때” metric 문구를 수정하지 않고, Owner 승인과 PR #337의 정확한 조건을 따른 차이를 여기 기록한다. `common/jobs/reflection.py`의 port/transaction primitive와 기존 `execution.py`의 안전 terminal snapshot을 추가한 것은 구현 구조 선택이며 Contract·Decision·Baseline 의미 변경은 없다.
- 실제 Case와 8-8 execution_id 영속 연결은 수정하지 않았다. `compose_worker(reflector=...)` 주입이 없으면 기존 entrypoint에는 T2가 연결되지 않으며 실제 Case wiring까지 표식은 남기지 않는다. 테스트 전용 Case/receipt table과 fake 형태는 실제 Case 구현의 새 schema 의무가 아니다. E2E-0은 dummy handler와 fake 반영 경로다.
- Startup/periodic T2 재전달은 RT-06, heartbeat/cancel·lease fencing은 RT-05, usage 영속은 RT-07, 실제 handler는 RT-10에 남긴다. RD-09a의 execution-scope mutable service/close 경계는 보존하며 실제 Recording lifecycle을 확장하지 않았다.
- sink 장애 시 해당 event 유실, COMMIT 응답 유실 후 ALREADY_APPLIED 복구 시 metric 미기록이 가능하다. log 전달·crash 시 exactly-once metric은 보장하지 않는다. B-D8 소진 시 COMMIT 결과 불명은 기존 helper 의미 그대로이며 이미 저장됐을 수 있는 표식을 임의로 지우지 않는다. 임의 raw DBAPI/DDL을 실행하는 Python reflector를 sandbox하는 기능은 없고 기존 Connection commit/rollback guard를 재사용한다.
- 첫 전체 회귀의 기존 API pre-commit kill test에서 blocker rollback TLS socket abort(2013/10053)가 단발 발생했다. 같은 실제 test 5회 재실행은 통과했으나 원인은 미확정이며 특정 network/보안 software 원인으로 단정하지 않는다. RT-04(b)나 기존 DB helper의 결함이 해소됐다는 근거로 해석하지 않고 실패·재검증 증거를 남긴다.
- RT-04 전체는 독립 재리뷰 전까지 **IN_PROGRESS**이며 Owner Audit A·원격 CI·merge 승인을 뜻하지 않는다.
- 구현·최종 검증 증거를 갖춘 독립 재리뷰 요청 가능 상태다. source 리뷰 P2는 위 RED→GREEN 및 최종 회귀로 검증했으며 사용자 독립 재리뷰 통과 판정을 대신하지 않는다. 최종 `git diff --check` **PASS**, 새 untracked Python의 syntax/whitespace **PASS**, HEAD/index 불변을 확인했다. 보호 JSON SHA-256은 시작 시점과 같고 기존 pytest scratch 폴더는 수정·staging하지 않았다. 작업 전용 MySQL의 port/datadir/version을 확인하고 해당 서버만 정상 종료했으며 DB data·증거는 보존했다. 커밋·staging·push·PR 생성 없음.

### 2026-10-11 RT-04(b) 후속 — 독립 리뷰 P2: T2 DB 오류 소진 뒤 B-Q3 누락

Status: **IN_PROGRESS** · PR 연결: **`Refs #291`** · PR 번호 **pending** · merge SHA **pending**. 앞선 구현·리뷰·검증 기록은 당시 결과 그대로 보존하며, 이번 발견과 수정·검증을 별도 후속 기록으로 추가한다. 사용자 독립 재리뷰 전이다.

**발견 · RED → GREEN · 최소 수정**

- 현재 코드에서 독립 리뷰 P2를 먼저 재현했다. T2 `_DB_ERRORS`도 일반 reflector 예외와 같은 분기에서 처리하여 `runtime.reflect.failed`만 남기고 B-Q3 없이 다음 claim으로 진행했다. 실제 MySQL에서 두 Job을 enqueue하고 첫 T2 연결을 3회 끊은 결과 B-D8 대기는 **`[1, 1]`**뿐이었다. 필요한 순서는 **`[1, 1, 5]`**다. 첫 T1 terminal과 T2 rollback 상태는 유지되지만 DB 장애 중 다음 claim을 즉시 시작하는 결함이었다.
- 수정 전 단위 **20 failed / 1 passed / 26 deselected**, 실제 MySQL **2 failed / 37 deselected**로 대기 누락 RED를 확인했다. 단위는 DBAPIError · SQLAlchemy TimeoutError · TransactionRetryExhausted, 두 terminal 상태, 정상/filter/handler sink, stop 경계를 포함한다. MySQL은 기존 소진 검사와 두 Job 검사를 각각 실패시켰으며 두 Job이 실제 처리됐음에도 관측값이 `[1, 1]`임을 확인했다.
- WorkerLoop의 T2 처리에 `except _DB_ERRORS`를 일반 `Exception`보다 먼저 추가했다. 기존 `_db_error`의 안전한 DB event → best-effort `runtime.reflect.failed` → claim 오류와 같은 `idle_wait(settings.error_backoff_sec)` 순서로 다음 claim 전 interruptible B-Q3를 적용한다. B-D8 내부 1초 두 대기와 소진 후 B-Q3 5초는 별개다. T2 자체를 loop에서 다시 실행하지 않으며 T1 결과·produced·failure_kind를 수정하지 않는다. 일반 reflector/domain 예외에는 B-Q3를 적용하지 않고 `BaseException`은 계속 전파한다.
- filter/handler 일반 Exception이 두 event sink에서 모두 발생해도 B-Q3와 다음 claim 판단을 유지한다. B-Q3 중 stop이면 다음 claim을 시작하지 않는다. `log_event_best_effort`의 검증/sink 분리, `log_event()` API, 기존 `_emit`·observer 실패 격리 정책은 변경하지 않았다. 첫 수정 후 회귀는 **85 passed / 1 failed**였으며 기존 enqueue DB 오류 검사에서 테스트 도우미가 빈 queue의 2초 대기만 허용해 새 B-Q3 5초를 거부했다. 종료가 이미 요청된 도우미에는 실제 interruptible `stop.wait` 경계를 적용했고 최종 targeted에서 모두 통과했다.
- 비차단 보강은 테스트만 변경했다. 외부 Case 행 lock을 잡은 채 두 T2의 도착과 MySQL `performance_schema.data_lock_waits`의 **서로 다른 요청 thread 2개**를 확인한 뒤 lock을 해제해 실제 경합을 강제한다. 후속 execution INSERT가 같은 Connection에서 성공한 사실을 확인한 뒤 표식 UPDATE 0 rows를 주입해 Case 변경·후속 execution·표식의 전체 rollback을 검증한다. 두 Job 소진 테스트도 INSERT 뒤 연결 kill을 3회 주입하여 rollback을 확인하고 B-Q3 후 두 번째 Job의 정상 처리와 표식 기록을 검증한다. 이 보강의 실제 MySQL 집중 검사는 **5 passed / 35 deselected**였다. 실제 Case 구현의 의무나 production 정책은 추가하지 않았다.
- 새 `recovery/exhausted_next_job`, `zero_guard/insert_then_marker_failure` parameter를 gate 단위 inventory에 먼저 추가했다. 개별 누락 **2 failed / 719 passed / 109 deselected** RED는 전체 증거 삭제(`all`)가 기존 gate에서 통과하는 문제를 확인한다. gate와 하위 실제 보고서 inventory에 두 parameter를 추가해 GREEN으로 고정했다. README에는 DB 실패의 B-Q3와 domain 예외의 대기 없음만 명시했다. Contract·Decision·Baseline·Plan 의미 및 공용 DB helper는 변경하지 않았다.

**검증 — 이번 후속에서 직접 실행**

- Worker·jobs·structured logging·gate targeted **1107 passed**, 208.74초, exit 0. 실제 MySQL **140 passed · skip 0 · xfail 0**, phase **420 passed**, 신규 T2 전체 **40 passed**, gate unit **830 passed**가 포함된다.
- 실제 MySQL require **206 passed / 44 deselected**, 383.93초, exit 0. deselected는 선택 범위의 비-MySQL 테스트다. JSON/JUnit gate **206 tests · skip 0 · xfail 0 PASS**, phase **618 passed**. 하위 실제 보고서 suite도 별도 **205 passed · skip 0 · xfail 0**, phase **615 passed**로 gate를 통과했다. 상위/하위 수는 서로 다른 실행이며 고유 test 수로 합산하지 않는다.
- 실제 보고서의 필수 parameter **721/721 누락 거부**(103 × 7 layer), T2 **280/280 누락 거부**(40 × 7)를 확인했다. `worker_t2` role 전체와 scenario 9개 개별 누락도 **10/10 거부**했다. 이번 수정 전 gate RED와 수정 후 실제 JSON/JUnit 증거를 모두 보존한다.
- 전체 pytest **3248 passed / 26 skipped**, 633.13초, exit 0. 전체 실행의 MySQL JSON/JUnit gate도 **206 tests · skip 0 · xfail 0 PASS**, phase **618 passed**이며 하위 실제 suite **205 passed**, phase **615 passed**, parameter 누락 **721/721 거부**(T2 280)를 다시 대조했다. skip은 기존 선택적 검사 **Search typer 미설치 4 · Case 로컬 영상 없음 2 · Eval 로컬 미디어/zip 없음 5 · Recording 영상/pair/VIDEO_INDEX opt-in 미지정 15**이며 MySQL skip은 없다. 기존 Recording synthetic media smoke도 전체 실행에서 통과했다.
- Boundary **위반 0**, Contract fixture **구조 62 · JSON 26 · 의미 104 PASS**. workflow **Actionlint 5 files · YAML policy · bash -n/ShellCheck 5 run steps PASS**이며 Python pyflakes는 이 정적 검사에서 비활성이다. 원격 CI는 실행하지 않았다.
- 요청된 코드 리뷰 스킬의 읽기 전용 source 검토에서 새 Critical/Important/Minor 지적은 없었다. 해당 reviewer가 직접 실행한 집중 단위는 **26 passed / 21 deselected**이며 MySQL은 source만 검토했다. 단위 대기 순서 테스트의 B-D8 두 대기는 주입값이므로 실제 B-D8의 3회 소진·전체 `[1, 1, 5]` 증거는 구현자의 실제 MySQL 실행이다. 이 검토는 사용자 독립 재리뷰를 대체하지 않는다.

**남은 위험 · 상태**

- 이전 전체 회귀의 단발 MySQL **2013/10053** 오류는 **원인 미확정 위험으로 유지**한다. 이번 수정이 해당 socket 오류의 원인을 규명하거나 해소했다는 의미가 아니다. sink 장애 시 해당 event 유실 가능성, COMMIT 결과 불명에 대한 기존 helper/idempotency 한계도 유지한다.
- RT-06의 T2 startup/periodic 재전달과 실제 Case 8-8 연결은 여전히 제외한다. 이번 변경은 기존 B-Q3 적용 누락의 수정이며 새 retry 정책이나 즉시 T2 재실행을 추가하지 않는다. RT-04 전체는 재리뷰 전까지 **IN_PROGRESS**, `Refs #291`, PR 번호·merge SHA **pending**을 유지한다.
- 검증 증거는 기존 폴더를 재사용하지 않은 `C:/Users/cheol/AppData/Local/Temp/rt04b-p2-20261010/`에 보존한다. 보호 JSON의 SHA-256과 HEAD/index가 시작 시점과 동일함을 확인했고 기존 `.pytest-*` 폴더는 수정·staging하지 않았다. 작업 전용 MySQL의 port/datadir/version을 확인하고 해당 서버만 정상 종료했다(exit 0). 커밋·staging·push·PR 생성 없음. 최종 `git diff --check`와 status를 확인하고 독립 재리뷰를 요청할 수 있는 상태이며, 이번 검증은 사용자 재리뷰 통과 판정을 대신하지 않는다.

### 2026-10-11 RT-04(b) 최종 독립 재리뷰 — P2 해소 및 DONE 판정

- 사용자가 전달한 독립 재리뷰 통과 결과를 후속 완료 기록으로 추가한다. 기존 리뷰·P2 발견·수정·검증 이력과 당시 IN_PROGRESS/Refs/pending 기록은 그대로 보존하며, 현재 상태와 최종 PR 연결은 이 기록과 위 상태/PR 표를 따른다. 이번 문서 갱신에서 아래 테스트를 새로 실행한 것으로 기록하지 않는다.
- 이전 P2인 **T2 DB 오류 B-D8 소진 뒤 B-Q3 대기 누락은 해소**됐다. 수정 전 실제 MySQL 관측은 **`[1,1]`**, 수정 후는 **`[1,1,5]`**다. B-D8 두 재시도 대기 뒤 interruptible B-Q3를 거쳐 다음 claim을 시작한다. 이미 확정된 T1과 T2 rollback 경계를 보존하고 일반 reflector 예외에는 B-Q3를 적용하지 않으며, T2 즉시 재실행은 추가하지 않았다.

**독립 재리뷰 — 직접 실행 결과**

- Worker 단위 **47 passed**.
- 실제 T2 MySQL **40 passed · skip 0 · xfail 0**.
- 신규 gate parameter 단위 **14 passed**.
- T2 JSON/JUnit **40 tests · 120 phases PASS**.
- 신규 parameter 2개의 증거 제거 **14/14 거부**(2 × 7 layer).
- 보존된 전체 MySQL 보고서에 **현재 gate를 적용하여 206 tests PASS**. 이는 전체 MySQL suite 206건을 재리뷰에서 새로 실행했다는 의미가 아니다.
- `git diff --check` **PASS**.

**구현 단계 실행 결과 — 재리뷰에서는 보존 증거 대조**

- targeted **1107 passed**, 실제 MySQL require **206 passed**, 하위 실제 suite **205 passed**는 위 구현 단계에서 직접 실행한 결과다. 상위/하위는 별도 실행이며 고유 test 수로 합산하지 않는다.
- 전체 pytest **3248 passed / 26 skipped**도 구현 단계 실행 결과이며, 재리뷰에서는 보존된 출력·JSON/JUnit 증거를 대조했다. 전체 pytest를 재리뷰에서 다시 실행한 결과와 구분한다.
- parameter 누락 **721/721**, T2 **280/280**, role/scenario **10/10 거부**는 구현 단계 실행 결과를 대조한 것이다. 재리뷰가 새로 실행한 신규 parameter 증거 제거 **14/14**와 구분한다. 기존 boundary·Contract fixture·workflow 통과 기록도 구현 단계 증거로 보존한다.

**최종 판정 · 합의 · 후속 범위**

- **T2 · E2E-0 최종 판정 PASS**, RT-04 최종 상태는 **DONE**이다. 위에 기록한 Issue #291의 Case Owner·Runtime Owner 합의와 [PR #337](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/337)의 metric 정의를 반영했다. `runtime.retry.after_case_stopped_count`는 **attempt >= 2 AND NOT_APPLIED AND STOPPED_WAITING**만 기록하며 attempt 1 · CANCELLED · SUPERSEDED · ALREADY_APPLIED · reflector 예외는 제외한다.
- RT-04(a)는 **PR #336 · merge SHA `d08b29a`**다. RT-04(b) PR 번호·merge SHA는 **pending**, 최종 PR 연결은 **`Closes #291`**이다. 최종 PR 생성·merge 또는 Issue close가 이미 실행됐다는 의미는 아니다.
- 실제 Case 8-8의 execution_id 영속 연결과 RT-06 startup/periodic 재전달 scan은 후속 범위다. fake reflector로 검증한 T2/E2E-0 판정이 실제 Case 연결 완료를 뜻하지 않는다.
- event sink 장애 중 해당 event 유실 가능성은 허용된 한계로 유지한다. 단발 **MySQL 2013 / Windows 10053** 오류는 해결됐다고 단정하지 않고 **원인 미확정 위험으로 유지**한다.
- **원격 GitHub Actions 미실행**. 이번 갱신은 RT-04 절만 수정하며 커밋·push·PR 생성은 하지 않는다.

## RT-05 — Lease · heartbeat · fencing · 협력적 중단

Status: DONE · Issue: #292 · Audit: A · 최종 PR 연결 문구: `Closes #292` · PR 번호 / Merge SHA: pending

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| pending | RT-05(a) heartbeat · lease · fencing (독립 재리뷰 통과) | pending |
| pending | RT-05(b) cancel · checkpoint (P2 해소·최종 독립 재리뷰 통과, `Closes #292`) | pending |

아래 구현 단계의 IN_PROGRESS / `Refs #292` 및 미구현 범위 표기는 당시 이력으로 보존한다. RT-05의 현재 최종 상태와 검증 주체 구분은 이 절 마지막의 「최종 독립 재리뷰 통과」 기록을 따른다. DONE은 이번 최종 판정이며 PR 생성·merge·Issue close가 이미 실행됐다는 의미는 아니다.

### 구현 결과

- claimed execution마다 `common/jobs/heartbeat.py`의 전용 thread를 생성한다. main thread는 claim → handler → T1을 수행하고, heartbeat thread는 B-D9 engine의 Connection 하나를 보관하여 B-L1 주기로 조건부 lease UPDATE를 실행한다. DB 시간은 `NOW(6)`이며 lease duration은 기존 WorkerSettings를 소비한다.
- thread는 monotonic clock의 `T0 + k × interval`을 따른다. 동기 DB 시도가 interval보다 길면 완료 뒤 해당 시도 중 지나간 tick을 집계하고 다음 미래 tick을 기다린다. 중첩 시도·밀린 tick 몰아 실행·transaction helper 재시도는 없다. 실패한 연결은 닫고 다음 tick에서 새 연결을 연다.
- 갱신 0행은 observer/logger 호출 전에 `ExecutionContext.ownership`의 내부 fence에 기록한다. WorkerLoop의 T1 재기록, B-D8 매 시도 진입, callback 진입, 최종 COMMIT 경계가 fence를 확인한다. 기존 finish의 `RUNNING ∧ lease_owner=owner` UPDATE 조건은 유지한다. ownership 상실은 handler taxonomy FAILED로 바꾸지 않고 `runtime.execution.finish_rejected`로 기록한다.
- handler 성공·모듈 실패·일반 예외·BaseException·종료 신호 이후 모든 실행 종료 경로에서 heartbeat stop + join을 finally로 보장하고 전용 connection/소유 engine을 정리한다. 일반 logger/filter/handler·observer 예외는 격리하고 unsafe logging 검증 오류와 BaseException 정책은 유지한다.

### Plan 대비 변경

- RT-05(a)만 구현한다. cancel port, CancelSignal, checkpoint, 중단 표식 읽기·Case cancel 연결은 RT-05(b)에 남긴다. 기존 reserved cancel injection 필드는 유지한다.
- 갱신 SQL·연결 lifecycle은 별도 repository public API 대신 `LeaseConnection` 내부에 둔다. 후속 cancel이 같은 연결/갱신 경계를 확장할 수 있다. Contract·Decision·Baseline 변경 없이 선택한 implementation detail이다.
- 실행별 factory로 B-D9 NullPool engine을 소유하고 finally dispose한다. 테스트는 별도 heartbeat engine을 주입할 수 있다. Worker 업무 engine의 QueuePool checkout을 공유하지 않는다.

### 새 implementation detail

- `OwnershipFence`의 commit lock은 최종 check부터 DB COMMIT까지 유지한다. 로컬 ownership 상실 표식과 COMMIT의 순서를 직렬화하고, DB owner 이전과 T1 경합은 기존 조건부 UPDATE·InnoDB row lock으로 판정한다. heartbeat DB 호출 전체를 이 lock 안에 넣으면 T1 row lock과 교착할 수 있어 DB 갱신은 밖에서 실행한다.
- `run_worker_transaction`에 선택적 `before_attempt` / `commit_guard` 경계를 추가했다. helper는 Runtime ownership을 import하지 않으며 claim·T2·기존 호출은 기존 동작이다. 모든 T1 DB 재시도에 같은 fence가 적용된다. API transaction 경계는 변경하지 않는다.
- heartbeat thread의 BaseException은 raw threading traceback으로 노출하지 않고 보관·fence 후 소유 main thread의 join에서 재전파한다. cleanup의 추가 BaseException이 기존 primary BaseException을 덮지 않게 한다.
- 관측값은 immutable `HeartbeatObservation`에 attempt_ms·성공 간격 기준 lag_ms·skipped_tick_count·consecutive_failures로 전달한다. 기존 안전한 logging field 계약을 확장하지 않고 duration은 `duration_ms`, 숫자 count는 안전한 `status` 숫자 token으로 기록한다. skip 관측은 느린 시도 완료 뒤에 남는다.
- observer/logger에 시간이 걸려 다음 tick을 놓친 경우도 다음 시도 전에 미래 tick으로 이동하고 누락 tick을 집계한다. 0행 표식은 empty COMMIT 이전에 설정하여 COMMIT 오류에도 유지한다. commit guard 진입의 예외를 transaction helper의 primary 보존 범위에 포함하며 connection close 이후 engine dispose 오류가 첫 BaseException을 덮지 않게 한다. 독립 리뷰에서 재현한 경계 문제를 TDD로 보정한 implementation detail이다.
- 전체 회귀에서 실제 MySQL 하위 suite가 test harness의 300초 subprocess 제한에 걸렸다. migration fixture를 포함한 확대 inventory의 느린 로컬 실행을 허용하기 위해 이 테스트 제한만 900초로 늘렸다. Runtime timeout·Contract·Decision·Baseline이나 gate의 증거 판정 조건을 바꾸지 않는다.

### Owner 확인 포인트

- 김준영 Audit A: 0행 fencing 및 T1 commit 직전 경합, B-D8/loop 재시도 진입 fence, B-L1 skip 계산·관측 지연, B-D9 전용 연결 재사용·재연결, BaseException 보존 경계. Contract·Accepted Decision·Baseline 값/의미 변경 없음. 다른 Owner에 새 의무 없음.

### Verification

- 구현 전 WorkerLoop·claim_one/finish·transaction helper·역할별 engine·기존 테스트와 Issue #292, Plan §6/§12, Baseline을 직접 확인했다.
- 초기 RED: heartbeat lifecycle/composition 부재로 unit 6 + 실제 MySQL 17 = **23 failed**. 추가 gate RED: heartbeat family 누락을 허용하는 **7 failed**. cleanup 중 BaseException이 primary를 덮는 회귀 **1 failed**를 확인한 뒤 수정했다.
- 독립 리뷰 지적과 추가 장애 회귀: 느린 observer의 off-cadence 실행 **1 RED**, 0행 UPDATE 뒤 empty COMMIT 실패 **실제 MySQL 1 RED**, guard loss/KeyboardInterrupt + rollback 실패 **2 RED**, connection close SystemExit + engine dispose 오류 **1 RED**, renewal SQL SystemExit + rollback 오류 **1 RED**를 각각 확인해 수정했다. 신규 gate family 누락(zero_commit_failure/owned_cleanup)도 각각 **1 RED**를 확인했다. 보정 후 core **117 passed**, heartbeat MySQL **27 passed**, 추가 B-D8/B-Q3 retry fence **2 passed**.
- 첫 MySQL require 실행은 실행 도중 소스를 수정하여, 먼저 import된 구버전 LeaseConnection과 뒤에 import된 신버전 composition이 섞였다. traceback의 `unexpected keyword argument 'fence'` 등 **83 failed / 146 passed**를 최종 검증 근거에서 제외하고 원출력을 보존한다(`require.txt`). 이후 고정된 코드로 `require-final`을 실행했으며, 재개 시 해당 실행의 종료 코드와 보존 보고서를 먼저 확인했다.
- 실제 MySQL 8.4.7 작업 전용 서버(port 13329, `/tmp/rt05-20261011/data`)와 `rt05_test`/harness 일회 schema를 사용한다. 기존 Windows MySQL service와 사용자 DB는 변경하지 않는다. 증거는 `C:/Users/cheol/AppData/Local/Temp/rt05-20261011/`에 보관한다.
- **재개 시 보존 증거 대조:** 실행 중이던 `require-final` session의 완료 응답은 **exit 0**, 최종 **234 passed / 4 skipped / 3271 deselected**다. skip 4개는 `typer`가 없는 비-MySQL Search 수집 항목이다. JSON/JUnit의 실제 MySQL **234 tests / 702 phases passed / skip 0 / xfail 0**, heartbeat **28 passed**를 대조했다. 하위 실제 MySQL suite **233 passed / skip 0 / xfail 0**, JSON/JUnit gate PASS, parameter 증거 누락 **896/896 거부**(heartbeat **175/175**), heartbeat role/scenario 누락 **11/11 거부**도 보존 보고서로 확인했다. 기존 standalone heartbeat 27개와 달리 최종 inventory는 transaction/loop retry fencing parameter를 분리하여 28개다.
- **반복하지 않은 검증:** 고정된 구현·테스트·gate·README 11개 SHA-256이 중단 시 manifest와 일치하여 core **117 passed**, gate unit **1025 passed**, boundary **위반 0**, Contract fixture **62/26/104 검사 PASS**, workflow YAML policy·bash syntax·ShellCheck **5 run steps PASS** 및 actionlint **5 files / 0 errors**의 기존 실행 증거를 재사용했다. 독립 source 리뷰에서 지적된 네 경계 수정과 재리뷰 통과도 보존 근거이며, 재개 후 구현·리뷰를 다시 수행하지 않았다.
- **보호 파일 대조:** 기존 manifest에 포함된 미추적 pytest/recording 파일 **1052개**의 SHA-256 변경 0건. 이전 manifest에 빠진 dotfile `.env` 17개는 과거 해시 대조 대상이라고 주장하지 않는다(확인된 최종 수정 시각은 2026-10-07). 재개 시 별도 해시를 보관했으며 해당 경로를 수정·삭제·staging하지 않았다.
- **재개 후 첫 전체 실행:** `full`은 **exit 1 / 3482 passed / 26 skipped / 1 failed**다. 실패는 `test_actual_report_rejects_each_missing_migration_check`의 하위 실제 MySQL subprocess **300초 TimeoutExpired** 한 건이며 원출력·JSON/JUnit을 보존한다. 이전 통과 하위 suite의 JUnit 실행 시간은 **217.049초**다. 실패 뒤 Python 하위 프로세스 잔존 없음, 남은 일회 schema 1개와 테스트 계정 0개를 확인하여 해당 schema만 정리했다. 테스트 제한 변경 후 구현·gate 판정·테스트 10개는 이전 해시와 같고, `test_migration_gate.py`만 제한/설명 주석이 변경됐다. 변경 후 11개 해시를 별도 고정하고 `full-final`을 새 임시 경로에서 실행한다.
- **재개 후 직접 실행 GREEN:** 고정한 `full-final` 전체 pytest **exit 0 / 3483 passed / 26 skipped / 990.27초**, 실제 MySQL **234 tests / 702 phases passed / skip 0 / xfail 0**, heartbeat **28 passed**. skip 26개는 비-MySQL `typer`·로컬 미디어·영상 opt-in 미충족 항목이다. 상위 JSON/JUnit gate **PASS**, 하위 실제 MySQL **233 passed / skip 0 / xfail 0 / 297.527초**와 하위 JSON/JUnit gate **PASS**, 새 parameter 누락 증거 **896/896 거부**(heartbeat **175/175**)를 직접 확인했다. 테스트 harness timeout RED → 전체 GREEN을 별도 기록하며 첫 실패 보고서를 덮어쓰지 않는다.
- **최종 해시:** timeout 수정 뒤 고정한 코드·테스트·gate·README **11개 변경 0**, 기존 보호 파일 **1052개 변경 0**, 재개 시 별도 기록한 `.env` **17개 변경 0**. 이전 require 및 정적 검사 증거는 Runtime/판정 코드가 유지된 범위의 보존 근거로 구분한다. 증거 manifest는 `code-hashes.json`, `code-hashes-post-timeout.json`, `preserved-evidence-hashes.json`, `resume-verification.json`, `final-hashes.json`, `verification-summary.json`이다.
- **MySQL 정리:** 최종 pytest 프로세스 잔존 없음. MySQL **8.4.7 / port 13329 / datadir `/tmp/rt05-20261011/data/`**를 확인한 뒤 test schema·계정 **0**, 기타 비시스템 schema·비기본 계정 **0**을 검사하고 `rt05_test`를 제거했다. SQL SHUTDOWN 성공, 소유 server exec session **59725 exit 0**, 기존 PID·pid file·socket 없음, port **13329 연결 거부(10061)**를 확인했다. 종료 뒤 WSL의 Linux log 경로는 존재하지 않아 shutdown log에 근거한 주장은 하지 않는다. Windows에 정리 JSON과 실행 결과를 보존하며 기존 MySQL service는 변경하지 않았다.
- **최종 diff:** `git diff --check` **PASS**, branch `feature/runtime-heartbeat-fencing`, index 변경 **0**. 작업 변경은 tracked 9개 + 신규 구현/테스트 3개 = **12개**이며 보호된 기존 미추적 경로는 그대로다. 커밋·푸시·PR 생성 없이 독립 재리뷰 상태로 남긴다.

### 남은 위험

- B-D9는 I/O 단계별 timeout이며 whole-attempt 상한이 아니다. DB 호출이 길면 stop/join·skip 기록도 지연될 수 있다. 강제 thread kill이나 임의 join timeout은 도입하지 않는다.
- SIGINT/SIGTERM은 기존 정책대로 handler와 T1을 강제 중단하지 않고 다음 idle 경계에 반영한다. ownership이 유지되는 동안의 T1 DB 장기 장애는 종료를 지연시킬 수 있다.
- T1 COMMIT 응답 유실 뒤 heartbeat가 이미 terminal인 row의 0행을 관찰하면 보수적으로 T1 재시도를 차단한다. durable terminal 자체는 유지되며 T2 재전달은 RT-06이 담당한다.
- cancel·checkpoint(RT-05(b)), STALE/sweep·재전달(RT-06), 실제 handler(RT-10)는 미구현이다. RT-05 전체 상태는 IN_PROGRESS다. 원격 CI 미실행. 이번 작업은 커밋·푸시·PR 생성 없이 독립 재리뷰용 변경으로 남긴다.

### RT-05(a) 독립 재리뷰 통과 — 후속 기록

사용자가 전달한 독립 재리뷰 결과를 기존 구현·검증 이력에 추가한다. **병합 차단 문제 없음**으로 판정됐다. 이번 갱신은 이 절의 문서 기록만 추가하며 코드·테스트 수정이나 테스트 재실행은 하지 않는다.

| 상태 | RT-05(a) PR 연결 | PR 번호 | Merge SHA |
| --- | --- | --- | --- |
| RT-05 IN_PROGRESS | `Refs #292` | pending | pending |

**리뷰어 직접 실행 결과:**

| 검증 | 결과 |
| --- | --- |
| 핵심 단위 회귀 | 168 passed |
| gate unit | 1,025 passed |
| 실제 MySQL inventory | 233 passed · skip 0 · xfail 0 |
| heartbeat MySQL | 28 passed |
| parameter 증거 누락 | 896/896 거부 |
| heartbeat parameter 증거 누락 | 175/175 거부 |
| role/scenario 증거 누락 | 68/68 거부 |

**구현 단계 보존 증거:** 아래 수치는 구현 단계에서 실행해 보존한 결과이며, 이번 리뷰어 직접 실행 결과와 구분한다.

| 검증 | 보존 결과 |
| --- | --- |
| 전체 pytest | 3,483 passed / 26 skipped |
| 실제 MySQL | 234 passed · skip 0 · xfail 0 |

- **정책 판정:** monotonic fixed-rate scheduling, Worker 업무 연결과 분리된 heartbeat 전용 DB 연결, ownership 상실 후 T1 commit·재시도 fencing, 실행 종료 경로의 heartbeat thread cleanup 판정이 통과했다.
- **Timeout 한계:** 전체 heartbeat 시도를 묶는 단일 wall-clock deadline은 없다. Baseline의 단계별 connect/read/write **2/5/5초**를 적용하며, 이는 whole-attempt 상한을 보장하지 않는다. 기존 stop/join 지연 위험은 유지한다.
- **900초 변경 범위:** 전체 실제 MySQL 하위 suite를 실행하는 test harness의 subprocess timeout에만 적용된다. production timeout이나 gate의 통과 조건을 완화하지 않는다.
- **비차단 후보:** `Heartbeat.start()` 중복 호출 방지, tick 경계 및 COMMIT 성공 직후 ownership 상실 회귀 보강, 원격 CI 실행 시간 확인을 후속 검토 후보로 남긴다.
- **남은 범위:** RT-05(b) cancel이 남아 있으므로 RT-05 상태는 **IN_PROGRESS**, RT-05(a) 연결은 **`Refs #292`**를 유지한다. PR 번호와 merge SHA는 **pending**이다.

---

### RT-05(b) cancel · checkpoint — 독립 재리뷰 준비 (2026-10-11)

**Status: IN_PROGRESS · Issue: #292 · 연결: `Refs #292` · PR / Merge SHA: pending.** 이번 범위가 RT-05의 마지막 구현 PR에 해당하지만 독립 재리뷰 이전에는 DONE이나 Issue close를 기록하지 않는다. 커밋·푸시·PR 생성 없이 로컬 변경으로 남긴다.

**구현 결과**

- 공개 port는 승인된 `request_cancel(conn: Connection, job_ids: Iterable[str]) -> None`이다. Case caller transaction에 참여하며 commit·rollback·retry·물리 상태 반환이 없다. 전체 iterable의 안전한 ID 검증과 중복 제거를 모든 SQL보다 먼저 수행한다. 미등록 job/terminal은 no-op이다.
- job_id를 정렬하고 `uq_job_execution_job_attempt` index를 강제한 `ORDER BY job_id, attempt, execution_id FOR UPDATE`로 해당 job의 모든 attempt를 먼저 잠근다. 모든 대상 잠금을 확보한 뒤 QUEUED는 NOW(6) marker/ended_at과 빈 produced로 CANCELLED, RUNNING/STALE은 최초 marker만 기록한다. 미래 available_at도 제외하지 않는다. MySQL EXPLAIN으로 filesort 없는 unique index 접근을 검증한다.
- thread-safe CancelSignal은 첫 request만 true를 반환하며 최초 취소 checkpoint monotonic 시각을 보존한다. ExecutionContext에 구체 타입과 checkpoint를 연결하고 KindRegistry는 CancellationRequested를 재전파한다. WorkerLoop는 기존 ownership fence/owner 조건부 finish와 retry 경계에서 내부 CANCELLED 결과를 기록한다. 일반 handler taxonomy와 KeyboardInterrupt/SystemExit 정책은 유지한다. 마지막 checkpoint 뒤 정상 완료를 취소로 덮지 않는다.
- 전용 heartbeat transaction은 lease UPDATE와 owner/status가 일치하는 marker SELECT를 수행한다. 성공한 commit 이후 signal을 설정하고 DB `TIMESTAMPDIFF(MICROSECOND, cancel_requested_at, NOW(6))` marker 나이에 SELECT 시작부터 signal 전달까지 monotonic 경과를 더해 `runtime.cancel.observe_latency_ms`로 한 번 기록한다. host wall-clock과 DB 시각을 빼지 않으며 읽기·COMMIT 대기를 포함한다. DB SELECT의 server 시작과 client 시작 차이만큼 보수적으로 측정될 수 있다.
- Baseline §9의 `runtime.cancel.terminal_latency_ms`는 DB `TIMESTAMPDIFF(MICROSECOND, cancel_requested_at, ended_at)`이다. 성공한 T1 commit acknowledgement 뒤에만 로그를 내고 unknown-COMMIT receipt 복구에서도 같은 DB facts를 사용한다. 요청된 checkpoint부터 T1 commit acknowledgement까지의 monotonic 지연은 **별도 `runtime.cancel.checkpoint_to_terminal_ms`**로 기록하여 Baseline metric 의미를 유지한다. 이 추가 지표는 DB retry 대기를 포함하고 heartbeat join은 제외한다. 일반 logger/filter/handler/observer 장애는 signal/terminal을 바꾸지 않는다. DB 읽기·commit 오류는 signal 전달 없이 다음 tick으로 넘긴다. 0행 ownership loss는 별도 fence다.

**Plan 대비 변경 / 새 implementation detail**

- 갱신 UPDATE 뒤 같은 transaction의 marker SELECT를 사용한다. MySQL UPDATE RETURNING을 전제하지 않고 UPDATE row lock 아래 상태·marker·DB 시간을 읽기 위한 내부 구현 선택이다. transaction이나 B-L1/B-D9 값은 바꾸지 않는다.
- `HandlerResult`와 기존 Case `ReflectionInput`은 성공/실패 전용 surface를 유지한다. checkpoint 취소는 별도 내부 `CancelledExecution`으로 T1에만 전달한다. Case가 같은 transaction에서 이미 CANCELLED 정산한 job에 새 reflector 의무를 만들지 않기 위해 CANCELLED는 기존 T2 reflector에 전달하지 않는다. QUEUED 즉시 취소도 Worker/T2를 거치지 않는다. RT-06은 이 경계를 재전달 설계에 반영해야 한다.
- production sweep이 아직 없으므로 MySQL 테스트의 `sweep_boundary`만 STALE row 잠금 → marker 재확인 → attempt 2 INSERT 경계를 재현한다. RT-06 production scheduler나 retry 정책을 이번에 구현하지 않는다.
- RT-07 Usage ledger table도 아직 없다. QUEUED 취소 후 claim 불가/started_at 없음과 handler/provider 진입 불가를 검증한다. 영속 UsageRecord table에서 0건을 직접 조회했다고 주장하지 않는다.
- 요청문의 checkpoint 구간을 기존 terminal metric 전체 의미로 해석하지 않고 별도 내부 진단 지표로 보완한다. Baseline이 정의한 요청→CANCELLED metric은 DB facts 그대로 유지한다. Baseline 변경이나 새 Owner 의무가 없는 implementation detail이다.
- Contract 변경: 없음. Accepted Decision 변경: 없음. Baseline 값/의미 변경: 없음. Case 코드/Contract/HTTP command 변경: 없음. Plan 수정: 없음.

**Owner 확인 포인트**

- [Case Owner 승인 댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/292#issuecomment-6107446434)의 None 반환·Case 먼저/Runtime 나중 잠금·caller-owned transaction·모든 비terminal attempt 취소 요구를 실제 issue/comments에서 확인했다. 기존 Case repository를 소비해 CANCELLED 정산과 Runtime 전이가 함께 commit/rollback되는 것을 검증한다.
- Runtime/Ops Audit A: ordered index 잠금, claim/sweep/finish commit 경합, ownership/cancel 구분, DB 기반 observe/terminal 지연 및 추가 checkpoint 구간, Case 성공/실패 T2 surface 유지, RT-06 marker 재확인 경계.

**Verification**

- RED: signal/checkpoint/port 부재로 unit **14 failed** (`.codex-scratch/rt05b-red-unit.txt`). heartbeat 연결 전 실제 MySQL **14 failed / 1 passed** (`rt05b-red-heartbeat.txt`, `cancel_observe` 연결 부재). 새 gate 필수 증거 제거를 기존 gate가 허용해 **40 failed / 1199 passed** (`rt05b-gate-red.txt`). 구현 뒤 초기 targeted **146 passed**, 확장 gate unit **1257 passed**, checkpoint→commit metric unit 포함 cancel unit **15 passed**.
- 초기 MySQL 서버 라이브러리 경로 누락, sandbox 접속 실패, 테스트 파일명 충돌, 미구현 Usage table 조회, SQLAlchemy event listener 실행 중 제거 오류는 원출력에 보존한다. 해당 실행을 최종 통과 증거로 사용하지 않는다.
- 읽기 전용 source 사전 검토는 지표 2건을 P2로 지적했다. checkpoint 구간으로 terminal metric 의미가 달라진 문제와 성공 COMMIT 대기를 observe metric에서 빠뜨린 문제를 **3 RED**로 재현했다(`rt05b-latency-red.txt`). 초기 보정 targeted는 **128 passed / 1 failed**로, 남은 실패는 DB Decimal→float와 Python timedelta float 표현의 미세 오차였다. DB microsecond 정밀도보다 작은 0.000001 ms 절대 오차만 테스트에서 허용한다. 실제 경쟁 connection/schema의 `performance_schema.data_lock_waits` 확인을 추가한 경합 테스트 **19 passed**. 이 사전 검토는 최종 독립 재리뷰/acceptance가 아니다.
- 보정 전 전체 MySQL require는 **271 passed / MySQL skip 0 / xfail 0**, 하위 inventory **270 passed**, 7단계 parameter 누락 **1113/1113 거부**(cancel **217/217**). 전체 명령의 비-MySQL 수집 skip 4개는 typer 부재다. 이후 지표 수정/테스트 보강이 있어 이 실행을 최종 소스 전체 검증으로 주장하지 않는다.
- 최종 보정 targeted **129 passed** (`rt05b-corrected-green.{json,xml}`), gate unit **1259 passed**, cancel 단위 **15 passed**. 앞선 넓은 jobs/Worker targeted **346 passed**는 지표 보정 전 결과이며 보정 후 subset/전체 검증과 구분한다.
- 최종 MySQL 8.4.7 require: **272 passed / MySQL skip 0 / xfail 0**, setup/call/teardown **816 phases passed**, JSON/JUnit gate PASS. 명령: `.venv/Scripts/python.exe -B -X utf8 -m pytest -m mysql --ignore=tests/common/db/integration/test_migration_gate.py -q -p no:cacheprovider --basetemp=.codex-scratch/rt05b-require-final --tb=short --mysql-report=.codex-scratch/rt05b-require-final.json --junitxml=.codex-scratch/rt05b-require-final.xml`。`DAESINGO_REQUIRE_MYSQL=1`을 사용했다. 전체 명령의 skip 4개는 typer 부재의 비-MySQL 수집 항목이다. inventory 재실행/7단계 mutation 테스트 자체는 다음 전체 pytest에서 실행하여 acceptance suite를 이 단계에서 중첩 반복하지 않는다.
- 실제 최종 require JSON에서 모든 role/scenario 제거와 각 필수 parameter mark의 role/scenario/parameter 필드 일부 제거 **593/593 거부** (`rt05b-require-final-partial-mutations.json`). 모든 기존 Case acceptance inventory를 유지한다.
- Boundary **PASS — 위반 0**, Contract fixture **구조 62 / JSON 26 / 의미 104 PASS**, workflow **Actionlint 5 files / 오류 0 + YAML policy / bash -n / ShellCheck 5 run steps PASS**(pyflakes 비활성), `git diff --check` PASS. workflow source/의존성은 변경하지 않았다.
- 최종 전체 pytest: **exit 0 / 3771 passed / 26 skipped**, **696.60초**. 명령: `.venv/Scripts/python.exe -B -X utf8 -m pytest -q -p no:cacheprovider --basetemp=.codex-scratch/rt05b-full --tb=short --mysql-report=.codex-scratch/rt05b-full.json --junitxml=.codex-scratch/rt05b-full.xml`。실제 MySQL require 환경이며 26 skip은 비-MySQL optional dependency/로컬 원본 영상 opt-in 항목이다. 실제 MySQL **273 tests / 819 phases passed / skip 0 / xfail 0**, 최종 JSON/JUnit gate PASS.
- 전체 실행 안의 실제 하위 inventory도 **272 passed / skip 0 / xfail 0**다. collection/selection/setup/call/teardown/all/JUnit의 7단계 parameter 증거 누락 **1113/1113 거부**, cancel subset **217/217 거부** (`rt05b-full/test_actual_report_rejects_eac0/parameter-mutations.json`). 최종 전체 JSON의 role/scenario 및 parameter metadata 일부 누락도 **593/593 거부** (`rt05b-full-partial-mutations.json`).
- 최종 검증에 고정한 Python 소스/테스트 **13개 SHA-256 변경 0**, 보호 대상 pytest 폴더/recording JSON **1069개 SHA-256 변경 0** (`protected-before.json`, `protected-final.json`). `recording-baseline-negative-001.json` SHA-256은 `27BA6EE8F681F2DF93C4E147589DD932D4632D71631A77EDE194317D42247D99`다. 해당 경로를 수정·삭제·staging하지 않았다. 변경 파일은 15개, staging 0개다.
- 작업 전용 MySQL은 **8.4.7 / port 13331 / `/tmp/rt05b-20261011/data/`** 소유를 SQL assert로 확인한 뒤 종료했다. 잔여 일회 schema/테스트 계정 **0/0**을 확인했다. 정리 보조 script의 LIKE binding 오류를 고친 뒤 SHUTDOWN은 실행됐으나 SQLAlchemy close-time ROLLBACK에서 2013이 발생했다. 별도로 mysqld session **exit 0**과 port closed를 확인했다. 이후 WSL log 경로는 없어서 log 기반 종료 확인을 주장하지 않는다. 기존 Windows MySQL service/사용자 DB 변경 없음.
- 최종 증거·15개 변경 파일 목록·미추적 신규 파일까지 포함한 diff·source hash는 `.codex-scratch/rt05b-20261011/review-package.md`에 묶는다. 최종 검증 이후 수정은 Log/검토 패키지 기록뿐이며 product/test source는 바꾸지 않았다. RT-05는 **IN_PROGRESS / `Refs #292`**, 커밋·push·PR 생성 없음.

**남은 위험**

- B-X1은 DB 정상 구간 p95 20초 측정 목표다. 테스트 전용 짧은 cadence·DB 시간 검증은 운영 p95나 강제 취소 deadline의 실측 증거가 아니다. 실제 capability checkpoint는 RT-10이며 진행 중 provider HTTP·capability 내부 retry·backoff는 반환까지 계속된다.
- 기존 B-D9 단계별 timeout은 heartbeat 전체 시도/join hard deadline이 아니다. sink 장애 시 metric 유실은 가능하다. 원격 GitHub Actions는 실행하지 않는다.
- 실제 RT-06 sweep과의 통합은 RT-06에서 다시 검증해야 한다. 독립 재리뷰 전까지 RT-05는 IN_PROGRESS다.
- RT-06의 unmarked terminal scan은 성공/실패 전용 현재 reflector에 CANCELLED를 반복 투입하지 않도록 Audit A에서 경계를 확인해야 한다. 현재 cancelled row의 case_applied_at을 Runtime이 임의로 채우지 않는다. 모든 terminal의 재전달 구현이 완료됐다고 주장하지 않는다.

---

### RT-05(b) 독립 리뷰 P2 후속 — cancel 지표의 COMMIT acknowledgement 경계 (2026-10-11)

**Status: IN_PROGRESS · `Refs #292` · 독립 재리뷰 전 DONE / Closes / commit / push / PR 생성 없음.** 앞선 RT-05(b) 기록의 terminal 지표 `ended_at` 계산 설명은 구현 당시 상태이며, 아래 후속 수정으로 정정한다.

**발견과 원인**

- 독립 리뷰 P2에서 terminal UPDATE 직후와 COMMIT acknowledgement 사이의 대기가 `runtime.cancel.terminal_latency_ms`에서 누락됨을 확인했다. 로그 출력은 commit 뒤였지만 계산은 DB `cancel_requested_at → ended_at`으로 끝났다. checkpoint 지표는 record 함수가 terminal logger를 호출하고 반환한 뒤 시간을 읽어 logger 지연도 포함했다.
- 실제 MySQL 8.4.7에 DBAPI COMMIT 직전 400ms 지연을 주입한 RED에서 terminal 지표 **11.793ms**가 380ms 하한에 미달했다. 400ms terminal logger 지연 RED에서 checkpoint 지표 **422ms**가 독립 COMMIT acknowledgement 측정 **16ms**와 불일치했다. terminal UPDATE의 row lock 대기 RED에서도 terminal 지표 **12.633ms**가 지연을 누락했다. 세 parameter가 모두 실패했다 (`red2.json`, `red2.xml`).
- 신규 `terminal_ack / commit_delay` parameter의 collection·selection·모든 phase·JUnit 증거를 함께 제거했을 때 기존 gate가 통과한 RED도 확인했다 (`gate-red.xml`: DID NOT RAISE).

**최소 수정과 implementation detail**

- 기존 ownership commit guard를 composition 안에서 감싼다. transaction helper가 `conn.begin()`을 성공적으로 종료한 직후, ownership guard가 풀리기 전의 monotonic 시각을 고정한다. pool cleanup·transaction observer·terminal logger보다 앞선 경계다. 공통 transaction helper·fencing·잠금 순서·cancel port·상태 전이를 바꾸지 않는다.
- terminal UPDATE 또는 기존 unknown-COMMIT receipt의 locking read로 terminal facts가 확인된 같은 T1 안에서 DB `NOW(6) - 최초 cancel_requested_at`을 읽는다. 이 DB marker 나이에 SELECT 시작부터 고정된 acknowledgement까지 monotonic 경과를 더한다. `ended_at`과 marker의 저장값은 변경하지 않는다. SELECT 이전 lock wait와 retry 대기는 DB 나이에 포함되며, SELECT 이후 COMMIT 대기는 monotonic 구간에 포함된다. DB/monotonic clock 연결에는 SELECT 전송 시간과 clock 해상도에 따른 측정 오차가 있다. 테스트는 별도 DB 시간 sample의 client 전후 시각으로 구간을 만들고 acknowledgement와 30ms 허용 오차 내에서 비교한다.
- 내부 `TerminalCommit` receipt가 동일한 종료 시각을 WorkerLoop로 전달한다. 최초 cancellation checkpoint부터 이 시각까지 별도 지표를 기록하므로 느린 terminal logger·pool cleanup·heartbeat join이 추가되지 않는다. bool record를 사용하는 기존 내부 test adapter는 기존 호환 동작을 유지한다. Case 공개 port의 None 반환은 그대로다.
- 매 transaction attempt에서 이전 sample을 지운다. 실제 COMMIT 응답 유실은 성공 경계를 고정하지 않고, B-D8 재시도에서 owner/status/produced/failure가 일치하는 durable CANCELLED를 잠금 확인한 최종 성공 acknowledgement만 사용한다. checkpoint·signal 중복에도 지표는 한 번만 시도한다. 재시도 테스트는 backoff 호출값 1초를 검증하되 실행 대기는 50ms로 줄였다.
- durable 결과 이후 계산과 logging은 terminal transaction 재시도 경계에서 분리하고 일반 Exception을 격리한다. 계산에 DB 오류 타입을 주입해도 추가 UPDATE/COMMIT/retry가 없다. 일반 handler taxonomy 및 KeyboardInterrupt/SystemExit 정책은 유지한다. late SUCCEEDED·ownership 상실·복구 receipt가 아닌 UPDATE 0행에는 cancel terminal/checkpoint 지표가 없다. sink 장애로 metric 유실은 가능하다.
- Contract·Decision·Baseline 값/의미·Plan·Case Owner surface 변경 없음. 요청→CANCELLED 기록의 종료점을 durable acknowledgement에 정합화한 내부 구현 수정이다. **observe 지표의 SELECT 전 구간 보수적 과대계상은 비차단 의견으로 유지하며 수정하지 않았다.**

**RED → GREEN 및 검증**

- 관련 targeted **1493 passed**. 최종 MySQL 지표 parameter **10 passed**: commit_delay / slow_logger / lock_wait / unknown_commit / retry / logger / filter / handler / calculation / zero_rows. lock_wait는 schema와 writer connection이 일치하는 `performance_schema.data_lock_waits`를 확인한 뒤 400ms 지연을 주입한다.
- 최종 targeted 측정: 400ms COMMIT 지연에서 terminal **469.661ms**, checkpoint와 독립 acknowledgement **453ms**. 400ms logger 지연에서는 checkpoint와 acknowledgement **15ms**, terminal **16.788ms**. 실제 row lock 대기에서 terminal **497.776ms**, checkpoint와 acknowledgement **438ms**. COMMIT OK packet 유실 후 복구에서도 두 지표/성공 acknowledgement가 각 1회다 (`final-target.xml`). 이는 시험 지연 회귀이며 운영 p95 측정이 아니다.
- 실제 MySQL require inventory **282 tests / 846 phases passed / MySQL skip 0 / xfail 0** 및 JSON/JUnit gate PASS. 전체 collection의 비-MySQL optional `typer` module skip 4건은 MySQL target에 속하지 않는다. 기존 cancel·claim·sweep·finish 경합도 포함한다 (`mysql.json`, `mysql.xml`).
- 실제 report의 scenario 전체 및 role/scenario/parameter metadata 일부 누락 **624/624 거부** (`mysql-partial-mutations.json`). 신규 10 parameter를 독립 test inventory와 gate에 모두 추가했다.
- boundary 위반 **0**, Contract fixture 구조/JSON/의미 **62/26/104 PASS**. workflow actionlint **5 files / 0 errors**, YAML 정책·bash -n·ShellCheck **5 run steps PASS** (pyflakes disabled). 원격 workflow 실행을 주장하지 않는다.

**최종 검증 / 독립 재리뷰 상태**

- 전체 pytest **3852 passed / 비-MySQL skip 26 / 1018.11s**. skip은 optional dependency·로컬 미디어 opt-in 항목이다. 최종 실제 MySQL **283 tests / 849 phases passed / skip 0 / xfail 0**, JSON/JUnit gate PASS (`full.json`, `full.xml`, `verification-summary.json`).
- 전체 회귀 안의 실제 하위 inventory **282 tests / 846 phases passed**. collection/selection/setup/call/teardown/all/JUnit의 7단계 parameter 누락 **1183/1183 거부**, cancel subset **287/287**, 신규 terminal_ack **70/70** 거부 (`full-tmp/test_actual_report_rejects_eac0/parameter-mutations.json`). 최종 전체 report의 scenario 전체 및 role/scenario/parameter 일부 누락도 **624/624 거부** (`full-partial-mutations.json`).
- 최종 Python 소스/테스트 **13개 SHA-256 변경 0**. 기존 보호 pytest 폴더·recording JSON·전체 `.codex-scratch/`의 **14372개 항목 목록 변경 0**, 읽을 수 있는 **14334개 내용 SHA-256 변경 0**. Windows에서 내용 해시를 읽을 수 없는 **38개 항목은 경로·크기 보존만 확인**했다 (`protected-before.json`, `protected-current.json`, `protected-final-verification.json`). 보호 경로 수정·삭제·staging 없음.
- 전용 MySQL **8.4.7 / port 13341 / `/tmp/rt05b-p2-20261011/data/`**를 SQL로 확인하고, 잔여 테스트 schema/계정 **0/0**을 확인한 뒤 SHUTDOWN했다. mysqld session exit **0** 및 port closed를 확인했다 (`mysql-cleanup.json`). localhost 전용 바인딩과 임의 비밀번호 계정을 사용했다.
- 이번 P2 수정 파일은 composition / worker_loop / cancel checkpoint MySQL test / gate script / gate unit inventory / 실제 gate integration inventory / Worker README / 본 Log의 **8개**다. 이전 RT-05(b) 작업까지 합친 브랜치 변경은 **15개**, staging **0개**다. 검토 diff는 보호 파일을 제외하고 미추적 신규 파일 4개를 포함한다 (`branch-review.diff`). 커밋·push·PR 생성 없음. RT-05는 **IN_PROGRESS / `Refs #292`**, 독립 재리뷰 대기다.
- boundary·Contract fixture·workflow 정적 검사·`git diff --check` PASS. Plan·Contract·Decision·Baseline·Case surface 변경 없음. observe의 보수적 과대계상·clock 연결 오차·sink 장애 시 metric 유실·운영 p95 미측정 한계는 유지한다.

증거는 새 `C:/Users/cheol/AppData/Local/Temp/rt05b-p2-20261011/`에만 기록했다. 기존 `.codex-scratch/` 및 보호 파일에는 쓰지 않았다.

### RT-05 최종 독립 재리뷰 통과 — P2 해소 및 검증 주체 구분

사용자가 전달한 독립 재리뷰 통과와 「RT-05(b) 리뷰」의 최종 결과를 기록한다. **이전 terminal 지표 P2 해소 · 추가 병합 차단 문제 없음**으로 판정됐다. P2 이후 변경된 8개 파일을 중심으로 검토했으며, RT-05 최종 상태는 **DONE**이다.

**재리뷰 직접 실행 결과**

| 검증 | 리뷰어 직접 실행 결과 |
| --- | --- |
| bool adapter · terminal · T2 단위 회귀 | 4 passed |
| 신규 gate family · 10 parameter × 7단계 누락 검사 | 71 passed |
| 실제 MySQL 신규 지표 10개 · late success · ownership 회귀 | 13 passed · skip 0 · xfail 0 |
| 보존된 실제 보고서에서 신규 parameter 개별 누락 검사 | 110/110 거부 |
| cleanup · observer · logger 시간 제외 및 장애 격리 독립 probe | 3개 통과 |
| `git diff --check` | PASS |

- 실제 MySQL의 400ms COMMIT 지연에서 terminal 약 **442ms**, checkpoint / 독립 ACK **421ms / 421ms**를 측정했다. 실제 row lock wait + 400ms 지연에서는 terminal 약 **486ms**, checkpoint / ACK **437ms / 437ms**였다. 400ms terminal logger 지연에서는 terminal 약 **26ms**, checkpoint / ACK **16ms / 16ms**였다.
- cleanup·observer·logger 합계 600ms 지연으로 기록 함수가 약 625ms 걸려도 receipt의 ACK 종료 시각은 늘어나지 않았다. cleanup·observer·ACK clock에 DB 오류 타입을 주입해도 COMMIT은 한 번이었다. UPDATE 0행·late success·ownership 상실의 지표 미발행, unknown COMMIT 복구 성공 시 각 지표 1회, attempt마다 timestamp/sample 초기화와 기존 bool adapter 호환성을 확인했다.
- 직접 probe 증거: [independent-probe.json](C:/Users/cheol/.codex/visualizations/2026/10/11/01a12ac2-823b-7ab2-80a5-3bc5e29c406b/rt05b-p2-review/independent-probe.json).

**구현 단계 실행 결과 — 재리뷰에서는 보존 증거 대조**

- 전체 pytest **3852 passed / 비-MySQL 26 skipped**는 구현 단계의 직접 실행 결과다. **재리뷰에서 전체 pytest를 다시 실행한 결과가 아니다.** 리뷰어는 보존 JSON/JUnit을 현재 gate로 대조하고 소스/테스트 13개 해시 일치를 확인했다.
- targeted **1493 passed**, MySQL require **282 tests / 846 phases passed**, 전체 실행 MySQL **283 tests / 849 phases passed**도 구현 단계 보존 결과다. 재리뷰 직접 실행의 MySQL 13개와 구분하며 고유 test 수로 합산하지 않는다.
- 증거 대조: [preserved-evidence.json](C:/Users/cheol/.codex/visualizations/2026/10/11/01a12ac2-823b-7ab2-80a5-3bc5e29c406b/rt05b-p2-review/preserved-evidence.json). 이번 Log 갱신에서는 코드·테스트를 수정하거나 재실행하지 않고 `git diff --check`만 확인한다.

**두 지표의 최종 시간 의미**

| 지표 | 시작점 | 공통 종료점 |
| --- | --- | --- |
| `runtime.cancel.terminal_latency_ms` | DB 최초 `cancel_requested_at` | 성공적으로 확인한 durable CANCELLED transaction의 COMMIT acknowledgement |
| `runtime.cancel.checkpoint_to_terminal_ms` | 최초 cancellation checkpoint의 monotonic 시각 | 동일한 COMMIT acknowledgement |

- COMMIT 확인 직후 고정한 monotonic 종료 시각을 공유한다. terminal 지표는 DB sample과 monotonic 구간을 연결한 추정 지연이며, checkpoint 지표는 monotonic 지연이다. lock wait·재시도·COMMIT 대기는 포함하고 종료점 이후 pool cleanup·observer·logger·heartbeat join은 제외한다.
- unknown COMMIT 복구에서는 최초 COMMIT의 미확인 시각을 재사용하지 않고 **durable terminal을 확인한 복구 transaction의 성공 ACK 시각**을 사용한다. 확정된 terminal 이후 지표 계산·Runtime logger 장애는 transaction 재시도를 유발하지 않는다.

**비차단 경계 · 남은 한계 · 최종 PR**

- `observe_latency_ms`의 SELECT 전 구간 보수적 과대계상은 그대로다. terminal 지표의 **DB sample ↔ monotonic 연결에도 SQL 전송 시간·clock 해상도에 따른 오차**가 있다. 이번 재리뷰가 이를 해결했다고 주장하지 않는다. **B-X1 운영 p95는 미측정**이며 시험 지연 회귀는 운영 p95나 강제 중단 deadline의 증거가 아니다.
- **제3자 logger의 원문 비노출은 보장하지 않는다.** 리뷰어가 원문을 가진 pool-reset 예외를 주입했을 때 SQLAlchemy 자체 logger는 traceback·SQL·경로를 stderr에 출력했다. 새 지표 계산·Runtime logger 경로에서는 누수를 발견하지 못했으나, 전역/제3자 logger의 masking까지 구현된 상태는 아니다. 이는 비차단 경계로 남긴다.
- sink 장애 중 metric 유실, B-D9 단계별 timeout의 whole-attempt/join 상한 미보장, 실제 RT-06 sweep·CANCELLED T2 재전달 경계 및 RT-10 capability checkpoint의 후속 검증 한계는 유지한다. 원격 GitHub Actions 실행을 주장하지 않는다.
- RT-05 **DONE**, 최종 RT-05(b) PR 연결은 **`Closes #292`**, **PR 번호와 merge SHA는 pending**이다. 최종 PR의 CI 및 Plan §12 Implementation Notes·Log 요건을 반영한다. 이번 갱신은 RT-05 절만 수정하며 커밋·push·PR 생성은 하지 않는다.

---

## RT-06 — STALE sweep · 자동 retry · T2 재전달

Status: DONE · Issue: #293 · Audit: A

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| [#347](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/347) (`Refs #293`, RT-06(a)) | sweep · retry — 두 P2 해소 · 독립 재리뷰 통과 | `2f046954` |
| pending (`Closes #293`, RT-06(b) 최종 PR) | 병합된 RT-06(a) PR #347에 이어 terminal T2 재전달 · 실제 Case adapter · process kill 복구 완료 — 독립 재리뷰 통과, 병합 차단 문제 없음 | pending |

### 구현 결과

- 최초 RT-06(a) 구현 기준(2026-10-11): 당시 최신 `origin/develop` `184dd3b8be26a96c3b2b5ea7ef66edaf25e0dd76`의 Plan §6 RT-06 · §12 전체/§12.8, Baseline B-L3~B-L5 · B-R1~B-R3 · §2.4 · §3.2 · §9, Tech Spec §6.2 · §6.3 · §7.2 · §7.3 · §12.2, 이 Log와 Issue #293을 확인했다. 당시 브랜치 HEAD도 같은 커밋이었다. 저장소/부모에서 AGENTS.md 파일은 발견되지 않았고 사용자가 제공한 AGENTS 지침을 적용했다.
- **RT-06(a)의 구현 범위:** `retry_policy.py`는 lease 만료·STALE-only retry·상한·중단 표식·지수 backoff/cap을 pure logic으로 분리한다. 실패 횟수와 failure_kind는 STALE/retry 판정에 쓰지 않는다.
- `sweep_expired(conn, execution_id, settings)`는 caller-owned transaction에서 원본 row를 잠그고 DB 시각과 marker를 재확인한다. 조건부 RUNNING→STALE과 허용되는 attempt+1 QUEUED INSERT가 같은 commit이다. 원본/새 attempt의 ended_at/queued_at은 같은 DB sample이며 available_at에 backoff를 더한다. 새 attempt는 job/case/kind/trace만 이어받고 execution ID·lease·cancel·produced는 재사용하지 않는다.
- `sweep_once()`는 후보 scan 뒤 execution별 B-D8 transaction을 실행한다. 중복 sweep은 원본 row 잠금 재확인과 기존 UNIQUE(job_id, attempt)로 차단한다. retry ID는 callback replay 동안 고정하고, unknown COMMIT 뒤에는 같은 원본 PK를 blocking read하여 durable STALE과 자신이 만든 child를 확인한다. 이미 STALE인 row에 추가 attempt를 만들지 않는다.
- `SweepService`는 startup sweep 성공 전 claim을 막고 DB 오류는 B-Q3 대기한다. 이후 handler와 독립적인 단일 `runtime-sweep` thread로 주기 sweep을 실행한다. WorkerLoop finally에서 stop/join하며 기존 handler/heartbeat 종료 경계를 유지한다.
- `compose_worker(sweep_hooks=(...))`가 RT-07 reconciliation 등록 지점이다. immutable hook 목록은 startup/주기 sweep transaction과 connection 반환 뒤 실행하고 일반 hook 예외는 다음 hook과 다음 주기에 영향을 주지 않는다. RT-07 import·usage 구현은 없다.
- commit된 STALE/auto retry/exhausted와 detect latency event를 기록한다. detect latency의 최종 의미는 **durable STALE row의 DB `ended_at` − 같은 row의 마지막 DB `heartbeat_at`**이다(Baseline §6). lease duration과 sweep 지연을 함께 포함하고 retry 생성/상한/중단 여부와 무관하다. 기존 safe logger의 duration_ms 필드를 유지하므로 `runtime.stale.detect_latency_s`의 초 단위 집계는 duration_ms/1000이다. `runtime.queue.wait_ms`는 DB queued_at→started_at을 기록하고 INITIAL/RETRY로 attempt 묶음을 구분한다. retry backoff도 포함한다.

### Plan 대비 변경

- sweep 전체를 큰 transaction으로 묶지 않고 후보별 짧은 transaction으로 나눴다. 각 attempt의 STALE+QUEUED 원자성은 유지하며 긴 handler·다른 job의 cancel/finish가 전체 scan 잠금에 묶이지 않게 한다. 앞 후보가 commit된 뒤 뒷 후보가 실패하면 앞 결과는 유지되고 다음 pass가 나머지를 재평가한다. implementation detail이며 Contract/Decision/Baseline 변경은 없다.
- RT-06(a)에서는 terminal T2 재전달 scan·실제 kill E2E·Case 8-8 배선을 RT-06(b)로 분리했다. CANCELLED의 기존 T2 경계는 변경하지 않았다. 당시 전체 상태는 IN_PROGRESS, 연결은 `Refs #293`이었다. RT-06(b)의 구현·최종 독립 재리뷰 결과는 아래에 기록한다.
- claim receipt에 내부 queued_at을 optional/default 필드로 추가하여 기존 positional adapter를 유지했다. 공개 JobExecution/read-port schema는 바꾸지 않았다.

### 새 implementation detail

- ① 후보 scan→PK 잠금/재확인→원자적 전이를 선택했다. 별도 commit이면 retry 유실/대표 execution의 일시 FAILED 표시, 재확인 없는 INSERT면 cancel 경합/중복 retry가 생긴다.
- ② DB NOW(6)·기존 config 상한/backoff·available_at을 선택했다. host 시계는 조기 판정 위험이 있고 Worker sleep backoff는 다른 QUEUED의 실행 슬롯을 점유한다. B-L/B-R 의미·값은 변경하지 않는다.
- ③ startup gate→독립 thread→post-commit hook을 선택했다. claim 사이 sweep이면 긴 handler 동안 복구가 멈추고, transaction 내부 hook이면 후속 reconciliation의 지연/오류와 row 잠금·retry가 결합한다.
- 주기 thread는 한 pass 종료 뒤 다음 interval을 기다리며 동시 sweep을 겹치지 않는다. startup DB 오류는 B-Q3, 주기 오류는 sanitized event 뒤 다음 주기에서 다시 시도한다. stop/join에 별도의 whole-attempt hard timeout을 만들지 않는다.
- 별도 소스 리뷰가 queue wait logger를 heartbeat 이전에 호출하는 P2를 발견했다. 실제 MySQL에서 lease보다 긴 sink 지연으로 실패를 재현한 뒤 heartbeat.start 이후 try/finally 안으로 옮겼다. heartbeat가 느린 sink 중에도 갱신하고 단일 SUCCEEDED를 유지하는 회귀를 CI gate에 넣었다.
- **후속 독립 리뷰 P2-1(2026-10-12):** 원인은 `now − lease_expires_at`을 detect latency로 써 lease 구간을 제외한 것이다. STALE UPDATE 자체의 `NOW(6)`를 `ended_at`에 저장하고 이를 다시 읽어 receipt·다음 attempt queued_at에 사용한다. immutable receipt에는 계산 대신 원본 heartbeat 시각을 보존하고 측정 계산은 commit/connection 반환 뒤로 옮겼다. 측정·sink 오류는 durable STALE/retry transaction을 rollback/replay하지 않는다.
- schema/migration에서 heartbeat_at은 nullable이고 공개 JobExecution Contract에는 없는 Runtime 내부 column이다. 정상 claim/renew는 DB NOW(6)로 기록한다. NULL·STALE 기록보다 미래인 heartbeat에는 lease/start/host 시각·0 같은 fallback을 만들지 않고 해당 latency 측정만 생략한다. lease 만료만으로 STALE/retry를 처리하는 정책은 유지한다.
- **후속 독립 리뷰 P2-2(2026-10-12):** hook의 BaseException이 cleanup 후 `main()`의 `except Exception`을 통과해 SystemExit 원문 또는 traceback을 인터프리터가 stderr에 출력했다. sweep의 fatal 전파·stop/join은 유지하고 프로세스 경계에서 BaseException을 잡아 Worker stop과 안전한 실패 event, 고정 종료 코드 **1**로 처리한다. SystemExit가 요청한 0/임의 코드는 사용하지 않는다. 실패/cleanup logger·filter·handler가 BaseException을 다시 발생시켜도 원문/traceback을 전파하지 않는다. 일반 hook Exception 격리·다음 hook/주기 실행과 기존 signal graceful stop 의미는 유지한다.

### Owner 확인 포인트

- 사전 Owner 확인이 필요한 Contract·Accepted Decision·Baseline 의미 변경, 다른 Owner의 새 surface/의무, SoT 충돌은 발견하지 않았다. 기존 Runtime cancellation port만 소비하며 case schema/callback을 추가하지 않는다.
- Deferred Audit A: 후보별 commit 경계와 unknown-COMMIT receipt 확인, cancel이 먼저 잠근 row의 skip/다음 pass 재평가, sweep이 먼저 잠근 경우 cancel이 새 QUEUED까지 취소하는 경계, startup DB 장애 claim admission, post-commit hook 배선과 thread shutdown.

### Verification — 구현 단계 보존 결과

- TDD RED: pure policy 19개·thread lifecycle 6개·실제 MySQL sweep 14개·production composition 3개를 미구현 실패로 확인했다. initial/retry queue wait 2개도 누락을 재현했다. 리뷰 P2는 실제 MySQL slow logger 회귀에서 실패한 뒤 수정 후 통과했다.
- MySQL 대상은 실제 MySQL 8.4.7 disposable schema이며 mock/skip 대체는 없다. 자연 lease 만료·late finish fencing, commit/rollback, backoff claim, 상한/중단, 두 sweeper, heartbeat/finish/cancel 재확인, 실제 cancel lock wait, 실제 1213 전체 rollback 재시도, COMMIT OK 폐기 proxy 복구를 검증한다.
- 새 MySQL acceptance family/parameter는 JSON/JUnit CI gate의 필수 목록에 추가했다. family 누락과 collection/selection/setup/call/teardown/all/JUnit 누락이 거부되는 RED를 확인했다. `.github/workflows/`는 변경하지 않았다.
- 최초 RT-06(a) 전체 회귀 내부 MySQL 실행(2026-10-11): 306 tests, skip=0, xfail=0, JSON/JUnit gate PASS. 실제 보고서의 parameter 증거 누락 1,267건 모두 거부(새 sweep parameter 증거 누락 84건 포함). 증거는 `full-verified/test_actual_report_rejects_eac0/{mysql.json,mysql.xml,parameter-mutations.json}`이다.
- 최초 RT-06(a) 검증(2026-10-11): 전체 pytest **4,001 passed, 26 skipped** (1,206.91s). 비-MySQL skip은 선택 의존성 `typer` 미설치 4건과 로컬 미디어/opt-in 조건 22건이다. 실제 **MySQL 307 tests, skip=0, xfail=0**, JSON/JUnit gate PASS(필수 scenario/parameter와 setup/call/teardown 증거 충족). mock/skip으로 대체하지 않았다.
- 실행: `DAESINGO_REQUIRE_MYSQL=1`, 실제 disposable MySQL URL 환경에서 `.venv/Scripts/python.exe -B -m pytest -vv --tb=short -p no:cacheprovider --basetemp=.codex-scratch/rt06a-20261011/full-verified --mysql-report=.codex-scratch/rt06a-20261011/full-verified.json --junitxml=.codex-scratch/rt06a-20261011/full-verified.xml`. 증거는 같은 디렉터리의 `full-verified.txt/json/xml`이다. JSON/JUnit은 `scripts/check_mysql_test_report.py`로 별도 재검증했다.
- `scripts/check_boundaries.py`: PASS, 경계·계약 정합성 위반 0건. `git diff --check`: PASS. 별도 read-only 소스 재리뷰는 P2 수정 후 추가 actionable finding 없음이며, reviewer가 별도 suite를 재실행한 결과는 아니다. 원격 develop SHA도 최종 점검 때 동일했다. 원격 CI 실행은 하지 않았다.
- 후속 두 P2 RED: 실제 MySQL에서 lease 60/7초 × retry/exhausted/cancel 6건·UPDATE 지연·NULL/미래 heartbeat 3건이 잘못된 측정으로 실패했다. 계산의 commit 후 격리 누락도 별도 RED로 확인했다. startup/periodic × SystemExit/KeyboardInterrupt/합성 BaseException 6건은 실제 child process의 stderr 원문/traceback 비노출 assertion에서 실패했다. SystemExit(0/42)의 안전한 종료 코드 테스트도 RED였다. 새 acceptance family 5개 누락 및 parameter 전체 증거 누락이 gate를 통과하는 RED를 확인했다.
- 후속 GREEN/최종 전체 회귀 증거는 `.codex-scratch/rt06a-p2-20261012/`에 별도로 보존한다. 최신 origin/develop `9c2df2f0e962df6fecac2fff4e45e8b5482a4fd2`로 fetch 후 위 네 Runtime 문서가 기존 기준 SHA와 동일함을 확인했다. 현재 HEAD/브랜치는 변경하지 않았다.
- 후속 중간 전체 실행(`full-verified`, TLS-disabled URL)은 기존 `test_explicit_config_url_preserves_percent_encoded_password`의 PyMySQL 인증 오류(`NoneType.is_auth_switch_request`)와 이를 포함한 `test_actual_report_rejects_each_missing_migration_check` 실패로 중단했다. 기존 TLS 사용 URL로 돌려 해당 실제 MySQL 테스트 **1 passed**를 확인하고 전체를 `full-final`로 재실행했다. 제품 source/의존성 수정·skip 대체 없이 테스트 환경 옵션만 복원했으며 중간 결과를 최종 증거로 사용하지 않는다.
- 후속 targeted GREEN: **1,787 passed**. 최종 전체 실행 내부의 실제 MySQL 재실행은 **344 tests, skip=0, xfail=0**, JSON/JUnit gate PASS였다. 실제 parameter 증거 누락 **1,533건 모두 거부**, 새 P2 parameter 증거 누락 **266건** 포함이다. 증거는 `full-final/test_actual_report_rejects_eac0/{mysql.json,mysql.xml,parameter-mutations.json}`이다.
- 재리뷰의 P3(테스트가 Runtime 로그를 event 이름으로만 요약)는 child의 실제 Runtime 로그 본문 비노출 검사로 보완했다. 후속 read-only 재리뷰는 P3 해결·추가 actionable finding 없음이며, reviewer는 별도 suite를 실행하지 않았다.
- 후속 최종 전체 회귀(2026-10-12): **4,312 passed, 26 skipped** (1,565.22s). skip은 비-MySQL 선택 의존성 `typer` 4건·로컬 미디어/opt-in 22건이다. 실제 **MySQL 345 tests, skip=0, xfail=0**, JSON/JUnit gate PASS. startup/periodic × SystemExit/KeyboardInterrupt/합성 BaseException × healthy/logger/filter/handler 24건의 실제 Runtime 로그 본문 검사도 포함한다. boundary 위반 0건·`git diff --check` PASS. 원격 CI는 실행하지 않았다.
- 후속 최종 실행: `DAESINGO_REQUIRE_MYSQL=1`, 실제 disposable MySQL URL, `PYTHONIOENCODING=utf-8` 환경에서 `.venv/Scripts/python.exe -B -m pytest -vv --tb=short -p no:cacheprovider --basetemp=.codex-scratch/rt06a-p2-20261012/full-final --mysql-report=.codex-scratch/rt06a-p2-20261012/full-final.json --junitxml=.codex-scratch/rt06a-p2-20261012/full-final.xml`. `.venv/Scripts/python.exe -B scripts/check_mysql_test_report.py .codex-scratch/rt06a-p2-20261012/full-final.json .codex-scratch/rt06a-p2-20261012/full-final.xml`로 별도 재검증했다. 같은 디렉터리의 `implementation-notes.md`·`review-manifest.json`에 재현 방법·변경 파일/증거 SHA-256을 보존한다.

### RT-06(a) 최종 독립 재리뷰 통과 — 검증 주체 구분

- **사용자 전달 RT-06(a) 최종 판정:** detect latency 의미와 fatal hook 원문 비노출의 두 P2가 해소됐으며 RT-06(a) 독립 재리뷰가 통과했다. 당시 전체 상태는 **IN_PROGRESS**, 연결은 **`Refs #293` (RT-06(a))**, PR 번호·merge SHA는 pending이었다. 이후 **PR #347 / `2f046954`**로 병합됐으며, RT-06(b) 최종 PR이 **`Closes #293`**로 전체 완료를 연결한다.
- **확인된 최종 경계:** detect latency는 durable STALE row의 `ended_at − heartbeat_at`이다. startup/periodic fatal hook은 일반 Exception 격리 경로로 삼키지 않고 stop/join·connection cleanup 후 고정 코드 **1**로 종료한다. 프로세스 경계는 예외 원문·traceback·secret·경로를 stderr나 Runtime 로그에 노출하지 않으며 실패/cleanup logger·filter·handler의 BaseException 재실패도 전파하지 않는다.
- **재리뷰 직접 실행 결과(사용자 전달):** COMMIT 불명 소진, observer 장애, fatal과 cleanup BaseException 동시 발생을 독립 probe로 확인했다. 이 세 probe는 저장소 회귀 테스트에 아직 포함되지 않았다.
- **구현 단계 보존 결과:** 위의 targeted **1,787 passed**, 전체 **4,312 passed / 비-MySQL 26 skipped**, 실제 **MySQL 345 tests / skip=0 / xfail=0**, 내부 MySQL 반복·gate parameter 누락 결과는 구현 단계의 보존 증거다. 이 수치를 독립 재리뷰의 직접 재실행 결과로 기록하지 않는다. 앞선 read-only 재리뷰 기록은 당시 검토 이력으로 유지한다.

### 남은 위험

- RT-06(a) acceptance는 Runtime의 sweep/retry를 증명했다. 당시 후속 범위였던 RT-06(b) T2 재전달·실제 process kill E2E는 아래 구현·독립 재리뷰에서 PASS로 확인됐다. 실제 Case wall timeout/context 적용 여부는 기존 case 소유 판단으로 남긴다(Baseline §3.2).
- **비차단 회귀 보강 후보:** 독립 probe로 확인한 COMMIT 불명 소진·observer 장애·fatal과 cleanup BaseException 동시 발생을 저장소 회귀 테스트로 편입하는 작업은 남아 있다. 독립 probe 확인과 저장소 회귀 커버리지를 구분한다.
- DB stall/B-D8 재시도·느린 hook이 sweep pass를 늦출 수 있고 whole-pass/hook/join의 전체 wall-clock 시간 상한을 보장하지 않는다. fatal 비노출 처리는 강제 kill이나 시간 상한을 추가하지 않는다. 운영 detect latency/false STALE 분포와 Baseline revisit 근거는 실측하지 않았다.
- post-commit 지표는 best effort이며 sink 장애/process 종료/unknown COMMIT 복구가 소진되면 event 유실이 가능하다. durable STALE/retry 원자성은 지표에 의존하지 않는다. 제3자 logger의 전역 masking은 기존 한계다.
- RT-06(a)는 PR #347로 병합됐다. RT-06(b) 최종 PR의 번호·merge SHA는 pending이며 이번 Log 갱신에서 커밋·push·PR 생성은 하지 않는다. 기존 미추적 파일도 수정/staging하지 않는다.

---

### RT-06(b) — terminal T2 redelivery · 실제 Case adapter · process kill (2026-10-12)

**Status: DONE · 최종 PR 연결: Closes #293 · PR 번호 / merge SHA pending.** 사용자 전달 RT-06(b) 독립 재리뷰는 통과했으며 병합 차단 문제 없음으로 판정됐다. 병합된 RT-06(a) PR #347의 sweep/retry에 이어 RT-06(b) 최종 PR이 T2 재전달·실제 Case adapter·process kill 복구를 완성한다. 실제 Issue close는 최종 PR 병합 연결이며, 이번에는 Log만 갱신하고 커밋·푸시·PR 생성은 하지 않는다.

**구현 결과**

- 착수 기준 HEAD/develop `fa5a0fcb`. 사용자 제공 AGENTS.md, Plan §6 RT-06/§12 전체, Tech Spec §6.2/6.3/7.2/7.3/12.2, Baseline B-L3–L5/B-R1–R3/§2.4/3.2/9, Log RT-04/05/06, Issue #293와 병합 PR #342·#343 및 Case 결정/공개 함수·T2 helper·transaction/composition을 확인했다. 저장소 내 AGENTS.md 파일은 발견되지 않았다. #347 merge는 Git history의 `2f046954`로 확인했다.
- `common/jobs/redelivery.py`는 SUCCEEDED/FAILED와 `case_applied_at IS NULL`만 잠금 없이 scan한다. connection 반환 후 후보마다 B-D8 transaction을 사용하고 callback replay마다 비잠금 receipt 조회를 다시 한다. CANCELLED/STALE/이미 receipt가 있는 execution은 Case로 넘기지 않는다.
- 기존 `reflect_terminal`과 Case `reflect_execution`을 그대로 재사용한다. Case lock/실행 ID dedup → Runtime terminal facts/receipt lock → 후속 enqueue + receipt 순서다. Case·후속 JobRecord의 Runtime enqueue·receipt는 같은 commit이며 COMMIT 응답 유실은 durable receipt와 Case 처리 기록으로 복구한다. 별도 delivery lease/schema/새 retry 정책은 없다.
- `worker/case_reflector.CaseReflector`는 reader/timeline과 선택적 store factory/budget을 주입받고 Runtime 모델을 Case 모델로 변환한다. 기본 store는 같은 Connection의 MySQLCaseRepository와 `read_executions`다. 다른 Connection의 store는 거부한다. Case 코드/공개 surface는 수정하지 않는다.
- `SweepService`의 startup pass와 각 periodic pass에 독립 redelivery callback을 연결했다. startup scan DB 실패는 B-Q3 admission 재시도로 첫 claim을 막는다. 후보 reflector/DB 오류는 rollback·기존 retry 뒤 격리하여 다음 후보와 다음 주기를 진행한다. scan 실패는 주기 경계로 올라가며 다음 주기에 다시 수행한다. hook은 여전히 transaction/connection 반환 뒤 호출하며 RT-07 import/reconciliation은 없다.
- commit/recovery 이후 best-effort `runtime.reflect.redelivery_count`를 기록한다. scan/replay 중 이미 완료된 receipt에는 재반영하지 않는다. shared post-commit observer는 기존 `attempt >= 2 AND NOT_APPLIED(STOPPED_WAITING)`만 `runtime.retry.after_case_stopped_count`로 집계한다. CANCELLED/SUPERSEDED/ALREADY_APPLIED/rollback/예외는 제외한다. event는 durable exactly-once ledger가 아니다.
- 실제 spawned Worker process에서 IPC로 T1 commit 뒤 T2 진입 전 또는 handler RUNNING 지점에 정지한다. 부모의 별도 MySQL 연결에서 durable 상태를 확인하고 OS kill/join·nonzero exit를 관측한다. gap 복구는 startup receipt 완료를 첫 claim 전에 확인한다. 실행 중 kill은 새 Worker의 실제 lease 만료→STALE→attempt 2→backoff 후 claim→성공→Case 처리 ID/receipt를 확인한다. 후보 중복/Case 후보 1개와 재전달 no-op도 확인한다. child의 engine/heartbeat/sweep를 별도 process가 소유하며 finally에서 child/pipe를 정리한 후 fixture schema를 drop한다.

**Plan 대비 변경 · 새 implementation detail**

- Plan 예상 `sweep.py`에 T2 persistence를 더하는 대신 `redelivery.py`와 Worker-owned adapter로 분리했다. 기존 T2/Case 공개 함수를 소비하는 implementation detail이며 다른 Owner의 새 surface는 필요하지 않았다. 기본 entrypoint의 실제 module reader/timeline/handler 조립은 RT-10에 남긴다.
- [구현 계획/선택 비교](../superpowers/plans/2026-10-12-runtime-t2-redelivery-kill-recovery.md)에 scan 분할, 동시 sweeper, COMMIT 불명, adapter 위치/DI, kill 동기화, 미지원 kind의 대안 2–3개와 장애를 기록했다. 기존 Case lock/receipt를 선택해 cross-process 중복을 해결하며 Runtime 선잠금이나 process-local mutex를 쓰지 않는다.
- MySQL gate에 독립 `redelivery` 9 families / 32 parameters를 추가하고 nested actual-report suite에도 신규 테스트를 포함한다. collection/selection/setup/call/teardown/all/JUnit의 개별 누락은 기존 fail-closed 검사로 확인한다. workflow require/JSON-JUnit gate 경로는 유지한다.

**Contract / Decision / Baseline 영향:** 모두 없음. test 전용 짧은 heartbeat/lease/sweep/backoff는 P-4이며 production 값을 바꾸지 않는다.

**Owner 확인 포인트**

- PR #343의 「미등록 kind는 T2까지 오지 않는다」는 전제를 사용하지 않는다. 실제 KindRegistry는 FAILED/RUNTIME_UNREGISTERED_KIND로 T1 확정 뒤 T2에 전달한다. Case 지원 kind는 현재 HINT_EXTRACT/COARSE_SEARCH다. PLATE_READ의 실제 durable JobRecord로 missing-applier ValueError를 확인하고 receipt를 남기지 않는다. UNKNOWN은 Case vocabulary 밖의 Runtime kind mismatch를 별도로 확인한다. Worker registry와 Case reflector의 호환성/fail-fast 책임은 **RT-10 후속 비차단 경계**이며 새 Case applier나 무음 APPLIED를 만들지 않았다.
- Deferred Audit A: Case→Runtime 잠금, NOT_APPLIED receipt와 unknown COMMIT, 후보 오류 격리, startup 순서, actual kill 증거를 확인한다. ProducedReader의 실제 module persistence/새 applier는 Case 8-6 2단계·RT-10 선행이다.

**Verification — 구현 단계 보존 증거**

- RED: startup/periodic unit 2 failed, 실제 MySQL 신규 32 failed(미구현), gate family 누락 9 failed. 최초 GREEN 시도는 24 passed/8 failed였고 공용 logger.log test 오염을 monkeypatch 복원으로 수정했다.
- 수정 후 unit/gate 2,513 passed. targeted 실제 MySQL/Case/기존 T2/startup 76 passed. 실제 connection kill→B-D8 3회 소진→다음 후보·다음 주기 1 passed. 첫 targeted 실패는 기존 concurrent T2 관측의 performance_schema SELECT 권한 부족이며 최소 읽기 권한 후 재검증했다.
- read-only 구현 리뷰의 P2: 기존 JobRecord.kind를 메모리에서 바꾼 fixture는 MySQL append-only record를 바꾸지 않아 missing-applier 대신 mismatch를 검증했다. durable kind assertion **2 failed RED** 후 실제 Case `issue_plate_read` 발주·정확한 ValueError 원인 assertion으로 수정했다. production 수정은 없었다. 최종 독립 재리뷰와 구분한다.
- 수정 환경의 nested 실제 MySQL require는 **482 passed / skip 0 / xfail 0**, MySQL **8.4.7**이며 별도 JSON/JUnit CLI gate PASS다. 기존·신규 개별 parameter의 7개 증거 계층 누락 **2,317건**을 모두 거부했다. 그중 redelivery 32 parameters의 **224건**이 포함된다.
- 최종 전체 pytest: **5,363 passed / 26 skipped / exit 0**, 1,684.30초. MySQL 선택 **487 tests / skip 0 / xfail 0**, JSON/JUnit CLI gate PASS. 이 통과 baseline에서 신규 32 parameters × 7 계층 누락 **224건**, 9 family 누락 **9건**을 별도로 거부했다. 전체 skip은 search collection의 기존 `typer` 미설치 4개와 로컬 미디어/opt-in이 없는 Case 2·eval 5·recording 15개다. MySQL skip으로 합산하거나 성공 보고서를 조립하지 않았다.
- 최종 boundary checker PASS(위반 0), Contract fixtures PASS(문서 구조 62 / JSON 26 / 의미 104 검사), 전체 5 workflow actionlint+ShellCheck PASS. 실제 host 파일 기준 코드 11개·기존 미추적 보호 파일 1,069개의 SHA-256 유지, 새 Python source 구문 검사와 `git diff --check` PASS, staging 없음. 원격 CI는 실행하지 않았다.
- 첫 전체 require는 기존 `test_sweep_worker_mysql.py` migration fixture의 TLS authentication read에서 장시간 정지했다. read-only py-spy stack 두 번으로 같은 위치를 확인해 `require-hang-stack.txt`를 보존하고 소유 pytest PID만 종료했다. migration API의 timeout 생략은 기존 의도이며 production/migration helper/TLS 설정은 바꾸지 않았다. 정지한 테스트의 disposable schema 1개를 정리하고 test URL에 `connect_timeout=2&read_timeout=10&write_timeout=10`을 명시했다. transport stall의 원인은 미확정이다.
- 재실행 `require-final`은 **485 passed / 1 failed / 비-MySQL collection skip 4**, 656.28초였다. 유일한 실패는 기존 Case `test_waiting_writer_sees_first_writers_commit_under_read_committed`의 `INNODB_TRX` 조회 권한 **1227 / PROCESS** 부족이다. 별도 실행으로 재현한 뒤 전용 서버 test 계정에 PROCESS 관측 권한을 추가해 해당 test **1 passed**를 확인했다. 실패 보고서는 JSON/JUnit gate가 거부했다. 이 보고서를 전체 require PASS 증거로 사용하거나 새 통과 결과와 합쳐 보고서를 만들지 않는다. 수정 환경의 전체 pytest/require 결과는 별도 `full` 보고서로 남긴다.
- 전체 실행 종료 후 fixture schema/account 잔여 **0**, 활성 test connection **0**을 확인했다. 전용 datadir/loopback/port/version을 검증한 뒤 base schema와 test 계정을 제거해 잔여 test schema/account **0**, SQL SHUTDOWN / 서버 session exit **0**을 확인했다. 소유 MySQL PID/socket/pidfile 소멸·port 닫힘·Worker child process **0**을 확인했다. DB data/log는 검증 증거로 남겼다.
- 구현 단계의 읽기 전용 source 재리뷰에서는 P2 fixture 수정 후 새 actionable finding 없음. 당시 reviewer는 테스트를 재실행하지 않았으며 위 실행 검증은 구현자 증거다. 당시 보류했던 최종 독립 재리뷰 판정은 아래 사용자 전달 결과로 구분해 기록한다.
- 검증 산출물은 `.codex-scratch/rt06b-20261012/`에만 보존하며 commit에서 제외한다. 최초 sandbox local socket 10013은 escalation 뒤 해결했다. 임시 서버의 초기 0.0.0.0/% 광범위 권한 요청은 auto-review가 거부했고 loopback/localhost와 test schema 범위 권한으로 제한했다.

**RT-06(b) 최종 독립 재리뷰 통과 — 검증 주체 구분**

- **사용자 전달 최종 판정:** RT-06(b) 독립 재리뷰 통과, 병합 차단 문제 없음. RT-06(a) PR #347과 RT-06(b)를 합친 **RT-06 상태는 DONE**이며, RT-06(b) 최종 PR 연결은 **`Closes #293`**, **PR 번호·merge SHA는 pending**이다.
- **독립 재리뷰 경계 판정(사용자 전달):** redelivery 대상(SUCCEEDED/FAILED·receipt null, CANCELLED/STALE/기존 receipt 제외), Case→Runtime lock 순서, 후보별 짧은 transaction, 동시 sweeper의 execution_id dedup/receipt, Case·후속 enqueue·Runtime receipt의 원자성 **PASS**. COMMIT 결과 불명 복구와 **exactly-once durable effect PASS**. 실제 process-kill **gap/running E2E 모두 PASS**, startup redelivery 완료→첫 claim 순서 및 **Case adapter PASS**. 미지원 kind의 registry↔reflector 호환성/fail-fast는 **RT-10 후속 비차단 경계**다.
- **독립 리뷰 직접 실행 결과(사용자 전달):** 관련 unit/targeted **2,746 passed**; 실제 MySQL **482 passed / 1,446 phases / skip 0 / xfail 0**; 신규 RT-06(b) parameter **32개 모두 통과**, process-kill **gap/running 모두 통과**; JSON/JUnit gate **PASS**; 신규 parameter 누락 **224/224**, family 누락 **9/9**, metadata 일부 누락 **96/96** 거부; 추가 MySQL·kill probe **6개 통과**; boundary·Contract fixture·`git diff --check` **PASS**. 이 수치는 사용자에게서 전달받은 독립 리뷰의 직접 실행 결과이며, 이번 Log 갱신에서 테스트를 재실행하지 않았다.
- **구현 단계와 구분:** 전체 pytest **5,363 passed / 비-MySQL 26 skipped**, 전체/nested MySQL **487/482**, 전체 누락 검사 **2,317건 거부**는 위 구현 단계의 보존 증거다. 독립 리뷰 직접 실행 결과와 합치거나 독립 리뷰가 전체 pytest를 재실행한 것으로 기록하지 않는다.

**비차단 개선 후보**

- 저장소 process-kill 회귀 테스트에 **HINT_EXTRACT → COARSE_SEARCH 후속 enqueue 경로**를 편입한다.
- **ACK 유실 뒤 transaction retry 소진 경계**를 정식 저장소 회귀 테스트로 편입한다. 독립 probe PASS와 저장소 회귀 커버리지를 구분한다.
- 로컬 전체 실행은 약 **28분**이며 원격 CI의 기존 **20분** 시간 예산 확인이 필요하다. 원격 실행 시간이나 CI 통과를 단정하지 않는다.

**남은 위험**

- 미지원 kind는 receipt 없이 매 pass에 반복 재전달될 수 있다. 오류를 숨기거나 APPLIED 처리하지 않으며 **RT-10 registry↔reflector 호환성/fail-fast 검증**이 필요하다. 이 후속 경계는 최종 독립 재리뷰의 비차단 항목이다.
- 실제 **produced reader/timeline durability**는 후속 범위이며 이번 fixture 결과로 증명하지 않는다.
- 후보 수 제한이나 whole-pass deadline은 도입하지 않았다. DB stall/B-D8·느린 Case reader/hook·join은 sweep/startup을 지연할 수 있으며 운영 분포/production tuning은 측정하지 않았다.
- 전체 pass/join의 **wall-clock 상한은 없다**. 기존 retry/timeout 경계를 전체 시간 상한으로 확대 해석하지 않는다.
- `runtime.reflect.redelivery_count`는 **전달 시도 횟수**를 관측하는 best-effort event이며 **durable effect exactly-once 지표가 아니다**. post-commit 지표는 sink 장애·process kill·unknown COMMIT에서 유실 가능하다. exactly-once 보장은 durable Case/후속 enqueue/Runtime receipt 효과이며 event 전달 횟수에 확대하지 않는다.
- 초기 Windows/WSL **TLS 정지**와 사용자 전달 독립 리뷰의 **서버 shutdown 후 close에서 발생한 2013**은 해결된 것으로 단정하지 않는다. 이후 실제 검증 PASS는 이 transport 경계의 원인 규명이나 해소를 뜻하지 않는다. 이번에 workflow timeout이나 migration helper 정책을 바꾸지 않았다.
- 기존 미추적 4개 항목은 수정·삭제·staging하지 않았다. **RT-06 DONE / 최종 PR Closes #293 / PR 번호·merge SHA pending**을 유지하며, 이번에는 RT-06 Log만 갱신한다. 코드·테스트 수정, 테스트 실행, 커밋·푸시는 하지 않는다.

---

## RT-07 — Usage ledger: in-flight · Final UsageRecord · reconciliation

Status: DONE · Issue: #294 · Audit: B

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| [#349](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/349) | `Refs #294 (RT-07(a))` — schema · DECIMAL · caller transaction Final append | `fa5a0fcbd5f88e70e7a4c9ba0a457b42a65a27a1` |
| [#353](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/353) | `Refs #294 (RT-07(b))` — UsageSink · Worker injection · explicit finalize | `95dfff8b3ba11f95b76a168dd18ccc1573c02b39` |
| [#360](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/360) | RT-07(c) — Owner 확인 후 produced 기반 복구·명시적 DIRECT_NO_RUN·P-7·usage_refs 구현. 최종 연결 예정: `Closes #294` | `505e6ad2c95617569faad1b12a45fa48d3e41919` |

### 구현 결과

- 기존 Runtime head `runtime_0002` 뒤에 frozen `0003_usage.py`(`runtime_0003`)를 추가한다. 기존 revision은 변경하지 않는다. `usage_inflight`는 Runtime 내부 호출 identity·context·관측값·run 관계·STARTED/OBSERVED/FINALIZED 상태·관측/확정 시각을 typed column으로 갖는다. Final `usage_record`는 Contract §4~§8의 필드를 typed column으로 보존하고 내부 outcome/state/failure column을 내보내지 않는다.
- 양 table의 `usage_id` 단독 ascii_bin PK로 호출 identity 재사용과 같은 identity의 Final 중복을 차단한다. nullable `execution_ref`에 index를 두며 `case_id`·run·execution·in-flight/Final 사이의 FK는 없다. Final은 tracker lifecycle과 독립된 snapshot이다. in-flight에는 pending run 관계를 허용하며 Final에는 Contract의 두 null 사유 또는 실제 run 참조만 허용한다.
- nullable BIGINT token 세 값의 전체 null/전체 non-null CHECK와 total=input+output CHECK, KRW CHECK, run-kind/reason 관계 CHECK를 양 table에 둔다. SQL UNKNOWN으로 부분 null이 통과하지 않도록 null 여부를 명시한다.
- MySQL ascii_bin의 PAD SPACE 비교로 enum에 공백 접미사가 허용되지 않도록 run_kind/run_ref_reason/state/outcome CHECK는 `CAST(... AS BINARY)`로 비교한다. frozen migration과 live metadata에 같은 제약을 둔다.
- `common/usage/amount.py`와 live `ExactAmount` Core binder는 Decimal/문자열/None만 받는다. float·int·bool·비유한 값·초과 자릿수는 DB 변환 전에 거부한다. Decimal context precision에 의존하는 quantize/normalize를 쓰지 않으며 `amount=null`과 0을 구분한다. 읽기 금액은 문자열 또는 null이다.
- `append_final(conn, record) -> bool`은 열린 caller transaction에서 전체 Contract 입력을 검증한 뒤 INSERT한다. 새 row=True, 동일 identity/typed snapshot replay=False, 다른 snapshot=`UsageIdentityConflict`다. 1062만 locked read/full comparison으로 처리하고 다른 SQL 오류는 전파한다. commit/rollback/retry·ID 발급·provider 호출·in-flight 변경은 하지 않는다. 결과는 caller commit 전까지 잠정적이다.
- `read_final(conn, usage_id)`는 Final Contract 필드만 projection하며 UTC timestamp·decimal string을 반환한다. JobExecution `usage_refs` read port는 이번 범위에서 연결하지 않는다.

### Plan 대비 변경

- Plan의 예상 migration `0002_usage.py` 대신 이미 존재하는 claim receipt revision 다음의 `0003_usage.py`를 사용한다. 순번/파일 배치만 달라지는 implementation detail이다.
- RT-07(a)에 한정했다. UsageSink begin/finish·Worker injection·Run finalize 배선은 (b), reconciliation·늦은 관측(P-7)·sweep hook은 (c), Search 배선은 SRCH-1에 남긴다. pricing/FX·retention/purge·budget guard·기존 SearchLedger는 변경하지 않는다.
- 새 테스트 파일은 기존 jobs 테스트와 Python module 이름이 충돌하지 않도록 `test_usage_repository_mysql.py`로 둔다. 기존 migration acceptance의 head/table inventory와 future-revision parent만 새 head에 맞춘다. `.github/workflows/`·Case 소유 테스트/fixture는 변경하지 않는다.

### 새 implementation detail

- **DECIMAL(65,30) 근거(P-10):** Contract 예시는 `184.20`과 `0`이고 기존 `search/usage.py:ProviderUsage.cost_with_rates`는 Decimal(str(rate)) × 정수 token / 1,000,000이며 quantization 없이 Decimal을 반환한다. Accepted #244 U-2는 KRW 정규화 책임과 unknown=null을 정했으나 미래 KRW 출력의 숫자 상한/scale을 고정하지 않았다. (20,6)은 작은 소수, (38,18)은 더 긴 계산 결과를 수용하지 못한다. MySQL 지원 최대 65/30을 사용해 별도 가격 반올림 정책을 만들지 않고 35자리 정수와 30자리 소수를 허용한다. 모든 미래 값이 들어간다는 보장은 하지 않는다. 더 긴 fractional suffix(0 포함)도 거부한다. [MySQL DECIMAL](https://dev.mysql.com/doc/refman/8.4/en/precision-math-decimal-characteristics.html).
- **Identity 대안:** composite `(execution_ref, usage_id)` UNIQUE는 서로 다른 execution에 같은 usage_id를 재사용할 수 있고 nullable execution에도 부적합하다. surrogate PK만으로는 Final 중복을 차단하지 못한다. usage_id 단독 PK를 선택하며 별도 중복 UNIQUE는 추가하지 않는다.
- **참조 대안:** Final→in-flight FK는 ledger를 tracking lifecycle에 종속시키고 cascade는 원장 삭제 위험이 있다. 동일 PK의 논리 참조 + 독립 snapshot을 선택한다. 향후 tracker 정리는 삭제 대신 finalize 표시(P-7)이며 이번 primitive는 이를 구현하지 않는다. 내부 context 정합 확인은 후속 tracker/finalize 책임이다.
- **Idempotency/COMMIT 불명:** 새 ID 재발급은 중복 청구, unconditional upsert/ignore는 원장 덮어쓰기/충돌 은폐 위험이다. caller가 identity와 전체 snapshot을 유지하여 replay한다. INSERT는 경쟁 transaction의 commit/rollback을 기다리고 1062 뒤 locked read가 동일 snapshot을 확인한다. 처음 writer가 rollback하면 새 INSERT가 성공한다. 기존 Worker DB callback retry와 조합할 수 있으나 caller transaction의 다른 효과도 각각 replay-safe여야 한다. 단일 Final receipt를 전체 다른 transaction 효과의 commit 증거로 확대하지 않는다.
- 설계 비교·TDD/검증 계획은 [RT-07(a) 구현 계획](../superpowers/plans/2026-10-12-runtime-usage-ledger-schema.md)에 보존한다. 새 Decision·Contract·Baseline 값을 정하지 않는다.

### Contract / Decision / Baseline 영향

- 모두 변경 없음. 다른 Owner의 새 surface/의무, SoT 모순이나 외부 의미가 달라지는 ambiguity는 발견하지 않았다. supplied AGENTS.md를 적용하며 저장소 내 AGENTS.md 파일은 검색에서 확인되지 않았다.

### Owner 확인 포인트

- Deferred Audit B: amount의 명시적 물리 범위, unknown=null/0 구분, pending in-flight/Final run 연결 경계, fixed identity의 snapshot conflict와 caller transaction/COMMIT 불명 경계를 확인한다. §12.3에 따른 사전 Owner 확인 사항은 없다.

### Verification

- **RT-07(a) 독립 재리뷰 최종 판정 — PASS(사용자 전달 결과):** 병합 차단 문제 없음. schema·DECIMAL·caller transaction·idempotency의 최종 판정이 모두 통과했다. 아래 구현 단계의 보존 증거와 구분한다.
- **독립 MySQL 재검증:** **445 passed · skip 0 · xfail 0**, JSON/JUnit gate **PASS**. parameter 누락 **2,093/2,093 거부**, usage parameter 증거 누락 **560/560 거부**다. 독립 재리뷰의 전체 pytest 실행 결과로 아래 **5,022 passed / 26 skipped**를 재인용하지 않는다.
- **구현 단계의 보존 증거:** 아래 TDD·read-only 수정 리뷰·nested suite·전체 회귀·재검증 기록은 구현 당시 실행의 증거다.
- TDD RED: 금액 경계 33개·실제 MySQL schema/append 77개·gate 새 usage family 11개와 필수 parameter 동시 collection/selection/phases/JUnit 누락 74개를 미구현 실패로 확인했다. 극단 exponent의 InvalidOperation 분류도 1개 RED 후 수정했다.
- 기존 Runtime migration/queue real MySQL baseline 33 passed. amount 34 passed, gate unit 2,230 passed. CHECK 위반의 실제 MySQL 3819는 PyMySQL OperationalError로 전달되어 테스트에서 코드까지 확인한다. 테스트 파일명 충돌은 collection error 확인 후 신규 파일명 변경으로 해결했다. 첫 baseline unit의 임시 디렉터리 parent 누락과 boundary stdout cp949 인코딩은 실행 환경을 바로잡았으며 제품 source 변경으로 숨기지 않았다.
- 구현 단계의 독립 read-only 리뷰가 발견한 enum 공백 접미사 P2를 실제 MySQL INSERT **6 failed** RED로 재현하고 수정했다. six suffix + frozen/live DDL **7 passed** GREEN, 새 필수 parameter 누락 **6 failed** gate RED를 확인했다. 당시 수정 재리뷰의 독립 SELECT probe와 기존 GREEN JSON/JUnit 확인에서 P2 해결 및 추가 actionable finding 없음으로 보고됐다. 해당 read-only reviewer는 새 pytest를 실행하지 않았으며, 위 최종 독립 MySQL 재검증과 별개다.
- 중간 전체 실행 `full-verified`는 리뷰 수정 전 증거이므로 중단했다. 최종 source로 `full-final`을 다시 실행하며 필수 usage inventory는 11 families / 80 parameters다.
- 구현 단계 최종 실행의 nested 실제 MySQL suite **445 tests · skip 0 · xfail 0**, JSON/JUnit gate PASS를 별도 CLI로 확인했다. 실제 보고서 parameter 증거 누락 **2,093/2,093 거부**, 신규 usage **80 parameters × 7 layers = 560/560 거부**다. `full-final/test_actual_report_rejects_eac0/{mysql.json,mysql.xml,parameter-mutations.json}`에 보존한다.
- `full-final` 전체 실행은 **5,022 passed / 1 failed / 26 skipped**, 1,515.89초였다. 기존 API kill 테스트의 blocker `lock.rollback()`에서 MySQL 2013 / Windows 10053 연결 중단이 발생했다. 같은 test는 nested suite와 별도 진단 **1 passed**였으며 해당 기존 test/transaction source는 변경하지 않았다. 실패 보고서를 통과 증거로 사용하지 않는다.
- 구현 단계의 코드 변경 없는 `full-recheck`는 **5,022 passed / 26 skipped**, **928.39초 · exit 0**이다. 이 전체 수치는 구현 단계의 보존 증거이며 이번 독립 재검증에서 전체 suite를 다시 실행했다는 의미가 아니다. 이미 통과한 실제 보고서 mutation test 하나(`test_migration_gate.py`)만 중첩 반복에서 제외하며 그 PASS와 실제 nested JSON/JUnit/누락 2,093건 거부 증거를 보존한다. skip 26개는 비-MySQL의 typer 의존성/로컬 미디어 opt-in 항목이며 MySQL skip으로 대체하지 않았다.
- 구현 단계 최종 재검증 JSON/JUnit을 별도 CLI와 evidence 집계 script로 검사했다. 실제 MySQL **445 tests · skip 0 · xfail 0 · 1,335 phases passed**, 신규 usage MySQL **101 passed**다. amount unit **34 passed**, gate unit **2,272 passed**를 포함한다. evidence는 `.codex-scratch/rt07a-20261012/{full-recheck.txt,json,xml,exit,final-evidence-summary.json}`이며 실패한 `full-final` 보고서는 gate가 실제로 거부하는 것도 확인했다.
- 실행: `DAESINGO_REQUIRE_MYSQL=1`, 실제 disposable MySQL URL, `PYTHONIOENCODING=utf-8`에서 `.venv/Scripts/python.exe -B -X utf8 -m pytest -vv --tb=short -p no:cacheprovider --ignore=tests/common/db/integration/test_migration_gate.py --basetemp=.codex-scratch/rt07a-20261012/full-recheck --mysql-report=.codex-scratch/rt07a-20261012/full-recheck.json --junitxml=.codex-scratch/rt07a-20261012/full-recheck.xml`. 보고서는 `scripts/check_mysql_test_report.py`로 검증했다. boundary checker PASS, `git diff --check` PASS. 테스트 서버는 검증 후 PID/datadir 확인 스크립트로 종료했다. 원격 CI 실행은 하지 않았다.

### 남은 위험

- 독립 재리뷰에서 cancel timing 테스트의 단발 경계 초과가 보고됐다. 원인은 미확정이며 timing 안정성 위험을 유지한다. 이를 해소됐다고 기록하지 않으며, 병합 차단 문제 없음이라는 최종 판정과 별도로 보존한다.
- RT-07(b)는 PR #353으로 병합됐다. RT-07(c)는 아래 독립 재리뷰 PASS로 RT-07 전체 DONE이며, 최종 PR 번호는 #360, merge SHA는 `505e6ad2c95617569faad1b12a45fa48d3e41919`이다. SRCH-1 실제 배선은 미구현이다. 실제 recovery·늦은 관측 보존을 RT-07(a)의 schema/append 결과로 검증했다고 주장하지 않는다. B-G1의 terminal 기반 recovery와 P-7 의미는 그대로다.
- raw textual SQL/외부 DB writer는 application amount binder를 우회할 수 있다. MySQL은 column 변환에서 소수를 반올림할 수 있어 CHECK로 원래 입력 scale을 복구할 수 없다([MySQL rounding](https://dev.mysql.com/doc/refman/8.4/en/precision-math-rounding.html)). 공식 append/live Core write 경계의 검증을 보장하며 raw SQL writer까지의 보호나 DB UPDATE/DELETE 권한 차단을 구현하지 않았다. repository는 Final을 수정/삭제하지 않는다.
- tracker와 Final의 context 정합은 후속 finalize가 확인해야 한다. 재시도에 영향을 주는 실제 lock timeout/deadlock은 caller의 기존 transaction 정책 대상이다. 새로운 identity로 재시도하거나 provider를 재호출하면 안 된다.
- RT-07(a) 구현 당시에는 사용자 요청에 따라 기존 미추적 파일을 보존하고 커밋·push·PR 없이 로컬 상태로 남겼다. 이후 병합 상태는 위 PR #349 행이 현재 사실이며, 당시 검증 증거와 요청 이력은 보존한다.

---

### RT-07(b) — execution UsageSink · explicit finalize (2026-10-13)

**현재 병합 상태: PR #353 merged · merge SHA `95dfff8b3ba11f95b76a168dd18ccc1573c02b39`.** RT-07(b) 병합 당시 RT-07 전체는 IN_PROGRESS였다. 아래 구현·검증 기록은 RT-07(b) 당시의 이력이며, 현재 RT-07 전체 DONE 판정은 아래 RT-07(c) 독립 재리뷰 기록을 따른다. RT-07(b) 병합 자체를 RT-07 전체 완료나 Issue close로 해석하지 않는다.

**착수 확인**

- branch `feature/runtime-usage-sink-finalize`, HEAD `51683e0b0f3ebd71664ff8771610cab7df8ef476`. 사용자 제공 AGENTS, Plan §6 RT-07/§12, Tech Spec §3.3/4.5/11.1–11.4, Contract §4–8, Baseline B-G1/§2.12, Plan P-7/P-10, Log RT-03–07, 기존 usage/schema/repository/amount와 ExecutionContext/WorkerLoop/composition/transaction helper를 읽었다. 저장소 AGENTS.md 파일은 검색에서 확인되지 않았다.
- GitHub connector로 Issue #293 CLOSED, Issue #294 OPEN, Accepted #244 U-1–U-4와 최종 결정 댓글 `5979576799`, RT-07(a) PR #349 merged와 위 merge SHA를 직접 확인했다. 처음 gh CLI는 네트워크 오류였으며 connector에서 확인된 정보만 사용했다.

**구현 결과**

- `common/usage/port.py`의 stdlib-only `UsageSink` Protocol은 begin/finish/finalize와 provider 오류와 분리된 `UsageError` taxonomy를 소유한다. `ExecutionContext.usage_sink`는 `UsageSink | None`이며 repr/비교에서 제외한다.
- `DurableUsageSink`는 execution/case context와 DB-only transaction runner를 받는다. Worker composition은 claim별 factory를 WorkerLoop에 전달한다. dispatch 전 checkpoint 뒤 실행마다 새 sink를 주입하며 cache/state를 execution 간 공유하지 않는다. heartbeat의 기존 cancel signal/ownership fence는 같은 객체로 유지한다.
- begin은 callback 밖에서 UUID 기반 Runtime ID와 occurred_at/typed STARTED snapshot을 만든다. INSERT/1062 locked read로 replay하며 원래 begin context가 바뀌면 conflict다. 동일 sink가 이미 발급한 ID만 explicit begin replay에 쓸 수 있다. COMMIT 불명/소진의 `UsagePersistenceError.usage_id`에도 그 ID를 유지한다. 이 ID는 예외 문자열/로그에 넣지 않는다. begin 예외 뒤 호출자는 HTTP를 실행하지 않는다.
- finish는 token 전체/합계, finite duration, integer latency, pricing context, exact KRW cost, outcome/failure 관계를 DB 진입 전에 검증·복사한다. row를 잠그고 STARTED 조건부 UPDATE로 OBSERVED를 보존한다. 동일 typed 관측은 timestamps를 바꾸지 않는 no-op, 다른 값은 conflict다. 실제 FAILED invocation·parsing failure의 token/cost null도 보존한다. ownership 상실을 이유로 관측 저장을 차단하지 않는다.
- explicit finalize는 OBSERVED 이후 caller가 확인한 logical Run 관계만 받는다. FAILED Run도 실제 Run ref로 연결하며 이 execution sink의 null 사유는 RUN_NOT_PRODUCED만 허용한다. tracker lock → 기존 append_final → OBSERVED 조건부 FINALIZED 표시 순서가 하나의 transaction이다. 두 단계 사이 실패와 rollback은 모두 되돌리고, 같은 identity/관계 replay는 no-op, 다른 관계는 conflict다. finish는 정상 finalize 이후 같은 관측 replay만 허용한다. recovery finalize/late observation 처리는 구현하지 않는다.
- 모든 method의 DB resource는 runner가 반환 전에 닫는다. provider/fake caller는 transaction 밖에 있고 callback에는 외부 I/O가 없다. callback retry 동안 ID·snapshot·시각을 유지한다. Worker registry는 UsageError를 loop까지 전달하며 loop는 RUNTIME_USAGE_PERSISTENCE/VALIDATION/CONFLICT/STATE FAILED로 처리한다. T1 retry는 결과만 보존하며 handler/HTTP를 다시 부르지 않는다.
- UsageError 문자열은 정적 메시지다. raw input/response, DB exception/SQL, path, tracker identity/state를 structured log나 ValidationError에 전달하지 않는다. Pydantic 입력 모델을 추가하지 않고 기존 Final validator의 typed normalization을 정적 오류 경계로 감싼다.

**Plan 대비 변경 · 새 implementation detail**

- engine 직접 소유 대신 transaction callback injection, 재시도마다 ID 생성 대신 callback 밖 고정 ID/snapshot, unconditional upsert 대신 locked read+조건부 UPDATE, last writer wins 대신 typed snapshot conflict, 별도 commit 대신 append→marker 원자 transaction, process 공용 sink 대신 claim별 factory를 선택했다. 하지 않으면 각각 DB 정책 결합·중복 invocation·관측 덮어쓰기·Final/tracker 불일치·execution 상태 혼선이 생길 수 있다. 상세 비교와 실행 순서는 [RT-07(b) 계획](../superpowers/plans/2026-10-13-runtime-usage-sink-finalize.md)에 기록한다.
- begin explicit replay를 위한 준비 snapshot은 execution-local cache에만 유지한다. 이 surface는 새 invocation 발급과 이미 발급된 begin의 persistence replay를 구분하기 위한 detail이며 restart/recovery read port가 아니다. caller가 이미 수행한 HTTP를 반복할 권한을 뜻하지 않는다.
- 기존 KindRegistry가 모든 handler Exception을 일반 오류로 바꾸는 것을 실제 MySQL RED로 확인해 UsageError 재전파를 추가했다. 공유 registry가 상태를 갖는 변경은 없다.
- RT-07(b) 당시 P2 리뷰 후 execution sink에 DIRECT_NO_RUN 차단 검증을 추가했다. 당시 OBSERVED tracker의 DID NOT RAISE RED와 차단 GREEN 2개, reviewer의 unit 22개는 그 시점의 증거다. 공유 Final validator·Contract·DB CHECK는 DIRECT_NO_RUN을 허용한 채 유지했다. 이후 Issue #294 Owner 확인에서 job 내부에도 no-Run 호출이 유효하고 이 차단의 계약상 근거가 없음을 확인해 RT-07(c)에서 해제한다. 당시 차단을 이미 허용한 구현으로 읽히게 한 기존 Log 문구를 정정한다.
- 새 acceptance `usage_sink` family/parameter는 기존 독립 test inventory와 production gate에 추가한다. nested actual-report suite에 새 Worker MySQL 경로를 명시했다. workflow/require/JSON-JUnit 판정 정책·Case-owned 파일·migration·DECIMAL·DB CHECK·기존 append_final은 변경하지 않는다.
- 첫 전체 MySQL 실행은 529 passed / 6 failed였다. 새 COMMIT fault proxy 테스트가 base URL의 TLS를 상속한 것이 원인이다. helper는 TLS-disabled client를 요구하며 기존 Final proxy 테스트도 명시적으로 끈다. 새 테스트의 proxy URL에 같은 설정을 추가한 뒤 base URL의 TLS가 활성인 조건에서 6 passed를 확인했다. 제품 DB/TLS 설정은 변경하지 않았다. 실패 JSON/JUnit도 gate가 거부하는 증거로 보존한다.

**Contract / Decision / Baseline 영향:** 모두 없음. Runtime port signature/DI/cache/error taxonomy는 Plan §12.3 implementation detail이다. Search interface에 새 값/새 의무를 추가하거나 실제 adapter를 수정하지 않았다.

**Owner 확인 포인트**

- Deferred Audit B: HTTP 직전 begin 및 이미 완료된 HTTP의 재호출 금지, caller-owned Run identity/usage_refs와 explicit finalize 연결, FAILED Run/실제 미산출의 구분, COMMIT 불명 소진 후 고정 ID replay, atomic Final/tracker 상태를 확인한다.
- 실제 Run 존재 확인은 run owner caller 책임이다. Runtime은 run schema를 읽거나 결과를 추정하지 않는다. 사용 예시/fake caller를 SRCH-1이 소비하되 이번에 실제 Search 배선·provider retry를 구현하지 않는다.
- finish 저장 실패 후 실제 관측값의 durable 복구·terminal reconciliation·recovery finalize·P-7 늦은 관측·read projection은 RT-07(c) 후속이다. 이번 범위에서 해당 정책을 미리 정하지 않는다.

**Verification — 이번 구현자 직접 실행**

- 최초 RED: unit 15 failed, Worker unit 6 failed, actual MySQL 27 failed(미구현). 새 gate family/parameter를 기존 gate가 허용하는 RED 45 failed / 2715 passed, validation family 포함 추가 RED 11 failed / 158 passed를 보존한다.
- 초기 GREEN: unit/Worker 21 passed; 기존 Final append·새 sink·Worker 회귀 targeted 181 passed; actual lock timeout/deadlock stage 6 passed. registry 경계 RED 2 failed / 3 passed 후 actual Worker+unit GREEN 27 passed. mutable caller snapshot 복사도 검증했다.
- 새 sink actual MySQL 47 passed는 DIRECT_NO_RUN 수정 전 증거다. ACK 유실 1회 및 3회 retry 소진 뒤 같은 ID/snapshot replay, begin/finish/finalize 1205/1213, 동시 finish/finalize, append/marker 실패 rollback, 관측 검증을 포함한다. P2 RED DID NOT RAISE 후 no-run GREEN 2 passed를 별도 보존한다.
- gate/unit GREEN 2881 passed는 마지막 DIRECT_NO_RUN parameter 추가 전 증거다. 마지막 소스의 전체 pytest 안에서 별도로 실행한 require-MySQL suite는 **535 tests / 1605 phases, skip 0 / xfail 0**, 실제 서버 **8.4.7**, JSON/JUnit gate PASS다.
- 그 actual require JSON/JUnit을 대상으로 필수 parameter **381개 × 7층 = 2667개** 누락을 모두 거부했다. 새 usage_sink **50개 × 7층 = 350개**가 포함된다. 새 parameter metadata(role/scenario/parameter) 개별 삭제 **150개**, 새 family 전체 삭제 **11개**도 모두 거부했다. nested pytest의 자체 parameter-removal 검사도 PASS이며 별도 구현자 검증 결과는 `mysql-require-final-mutations.json`에 보존한다.
- **최종 전체 pytest: 5800 passed / 26 skipped / 실패 0, 2314.29초, exit 0.** nested gate를 제외하지 않은 전체 실행이다. 26 skip은 비-MySQL typer 미설치 4개 및 실제 영상·로컬 미디어/명시적 opt-in 미제공 22개다. 전체 JSON/JUnit의 실제 MySQL은 **540 tests / 1620 phases, skip 0 / xfail 0**, 별도 CLI gate PASS다. 새 unit **23 passed**(sink 17 / Worker 6), 새 MySQL **53 passed**(sink 48 / Worker 5)는 이 최종 실행에 포함된다.
- 실행 조건: `PYTHONIOENCODING=utf-8`, `DAESINGO_REQUIRE_MYSQL=1`, disposable localhost MySQL URL(connect_timeout=2/read_timeout=10/write_timeout=10), `.venv/Scripts/python.exe -u -B -X utf8 -m pytest -vv --tb=short -p no:cacheprovider --basetemp=.codex-scratch/rt07b-20261013/full --mysql-report=.codex-scratch/rt07b-20261013/full.json --junitxml=.codex-scratch/rt07b-20261013/full.xml`. 마지막 product/test 수정은 proxy 테스트 TLS 명시이며 이후 변경은 검증 산출물과 문서뿐이다.
- boundary checker PASS(위반 0), Contract fixtures PASS(구조 62 / JSON 26 / 의미 104), workflow Actionlint 5 files/오류 0·YAML policy·bash -n/ShellCheck 5 run steps PASS. pyflakes는 기존 검사 방식대로 비활성이다. 원격 CI는 실행하지 않았다.
- 증거: `.codex-scratch/rt07b-20261013/`의 RED/GREEN 출력·actual MySQL JSON/JUnit·정적 검사. 테스트 임시 서버는 localhost 전용 MySQL 8.4.7/port 13332/datadir `/tmp/rt07b-20261013/data/`이며 기존 사용자 DB/서비스를 수정하지 않는다.
- 정리: datadir/port/bind/version을 대조하고 활성 테스트 연결 0을 확인했다. fixture schema/계정 잔여 0, base test schema/계정 삭제 후 남은 테스트 schema/계정 0이다. 전용 서버를 종료한 뒤 workspace 테스트 process 0, MySQL process 0, port closed, pid/socket 없음까지 확인했다. RED/실패 보고서와 서버 로그·datadir는 증거로 남기며 기존 미추적 4개 항목은 보존한다.
- 최종 `git diff --check` 및 새 파일 syntax/공백 검사 PASS, staging 0, branch/HEAD 유지. `review.diff`는 새 파일까지 포함하며 `review-manifest.json`에 변경 19개 파일과 SHA256을 기록한다. 이 산출물과 나머지 `.codex-scratch/`는 커밋 제외다. 사용자 독립 재리뷰·Owner Audit·원격 CI는 아직 실행되지 않았다.

**남은 위험**

- process kill·finish 이후 recovery finalize·late observation·terminal reconciliation·usage_refs projection은 이번에 검증하지 않는다. 아직 전체 RT-07의 완결성을 주장하지 않는다.
- DB callback runner와 caller port 순서는 composition의 신뢰 경계다. Python callable에 외부 I/O를 못 넣도록 sandbox하지 않는다. 실제 Search provider retry가 UsageError를 재시도하지 않는 배선은 SRCH-1에서 검증해야 한다.
- begin ACK 불명 후 STARTED가 이미 durable할 수 있다. 예외 뒤 HTTP는 보내지 않고 같은 발급 ID로 persistence를 재확인해야 한다. finish/finalize 소진도 provider를 재호출할 근거가 아니다.
- existing raw SQL binder 우회·MySQL rounding, 제3자 logger의 전역 masking 미보장, 이전 TLS/2013 timing 실패의 원인 미확정 위험은 유지한다. 이번 검증이 그 원인을 해결했다는 의미는 아니다.
- wall-clock 시각은 invocation/관측 기록용이며 lease 판단은 기존 DB 시간이다. 운영 지연·실제 비용/가격/FX·원격 CI 실행 시간을 측정하지 않았다.

---

### RT-07(b) — 독립 확장 MySQL heartbeat/T1 실패 조사 (2026-10-13)

**조사 당시 기록 · 현재 RT-07(b)는 PR #353 merged · merge SHA `95dfff8b3ba11f95b76a168dd18ccc1573c02b39` · RT-07 전체 IN_PROGRESS.** 독립 재리뷰의 최초 실패를 해결됐다고 기록하지 않는다. 사용자 요청의 systematic-debugging 절차로 traceback → 값 생성 경로 → 후보별 실험 → 새 환경 검증을 수행한다. 이 조사에서 제품·test source는 수정하지 않으며 기존 RT-07(b) 변경을 역적용하지 않는다.

**최초 실패의 확인된 증상**

- 원본 `C:/Users/cheol/AppData/Local/Temp/rt07b-independent-require.xml`은 535 tests / failures 1 / skipped 0, 즉 534 passed / 1 failed다. 대상은 `test_heartbeat_db_error_reconnects_without_retry_or_handler_failure[healthy]`다. 원본 XML/JSON을 새 증거 경로에 복사하고 SHA256을 기록했으며, 현재 gate가 실패 보고서를 거부하는 것도 직접 확인했다.
- 호출 경로는 test line 324 → WorkerLoop `_run_claims` → composition `record`/`operation` → `run_worker_transaction`/`_attempt` → jobs.repository `finish` line 213 → `_execution_model` line 105 → JobExecution `state_fields_are_consistent`다. 에러는 assertion이 아닌 Pydantic model validator의 `ended_at < (started_at or queued_at)`다. SUCCEEDED에서 started_at이 필수이므로 이 실패는 started_at 비교이며 heartbeat_at은 validator 입력/하한이 아니다.
- **확인 가능한 실제 ended_at: `2026-10-13T05:56:29.691520Z`. 최초 started_at / heartbeat_at은 확인할 수 없다.** 원본 XML의 row/payload repr가 `...`로 축약됐고 JSON은 node/phase/outcome만 가진다. cleanup 기록의 원래 datadir `/tmp/rt07b-independent-20261013/data/`도 현재 WSL에서 존재하지 않아 원본 binlog/row를 복원하지 못했다. 축약된 무명 숫자를 heartbeat_at이나 started_at으로 추정하지 않는다. 최초 session 설정과 OS/DB 시각 역행 여부도 확인할 수 없다.

| 값 | 생성 주체·clock | 저장/사용 시점 |
| --- | --- | --- |
| queued_at | enqueue의 DB UTC_TIMESTAMP(6) | 초기 QUEUED insert |
| started_at | claim UPDATE의 DB NOW(6) | RUNNING claim transaction, COMMIT 후 dispatch |
| heartbeat_at | 전용 heartbeat connection UPDATE의 DB NOW(6) | 갱신 transaction COMMIT, 실패 시 connection 반환 후 다음 tick 재접속 |
| ended_at | T1 finish의 SELECT DB NOW(6) | RUNNING snapshot 조회 후·model 검증 전 생성, 검증 후 UPDATE·COMMIT; 최초 실패에서는 UPDATE 전에 validator가 거부 |

- 네 column은 DATETIME(6), PyMySQL datetime은 naive, contract projection은 queued/started/ended에 UTC tzinfo를 부착한다. Python wall clock은 위 JobExecution 비교값에 사용되지 않는다. Worker의 monotonic clock은 metrics/scheduling용이며 UsageSink의 Python UTC clock은 usage method용이다. [MySQL 시간 함수](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-functions.html) 및 [소수초 정밀도](https://dev.mysql.com/doc/refman/8.4/en/fractional-seconds.html)의 공식 의미도 실제 SQL 실험과 대조했다.

**RT-07(b) 변경과의 연결**

- diff와 호출 흐름에서 heartbeat start → 기존 started log → 추가 checkpoint/factory → dispatch → 기존 T1 callback/commit_guard → heartbeat join 순서를 확인했다. T1 transaction 경계와 SQL timestamp 생성은 바뀌지 않았다. factory는 engine/connection을 소유하거나 checkout하지 않고 runner closure·execution/case 문자열·빈 cache·Lock을 준비한다. healthy handler는 UsageSink begin/finish/finalize를 호출하지 않는다.
- `dataclasses.replace`는 execution/job/case/kind/attempt/trace와 같은 cancel signal/ownership fence를 유지하고 usage_sink만 바꾼다. constructor 229회에서 SQL 0, 재현 matrix의 healthy 비교 27건에서 claim/factory/T1 identity 일치·attempt 1·각 실행 identity 고유·candidate ended_at이 해당 DB NOW(6) 결과와 일치함을 확인했다.
- **직접적인 timestamp/DB 경계 변경의 인과관계는 확인되지 않았다.** [추론] factory가 dispatch 이전 Python 작업을 추가해 thread scheduling에 영향을 줄 가능성까지 배제한 것은 아니다. repository/model이 미변경이라는 사실만으로 RT-07(b)와 무관하다고 단정하지 않는다.

**후보별 조사 — 제품 수정 전**

| 후보 | 직접 확인/실험 | 현재 판단과 한계 |
| --- | --- | --- |
| Python/DB clock 혼용 | claim/heartbeat/T1의 생성 SQL 역추적, candidate ended_at과 기존 DB NOW 결과 일치 | 이 JobExecution 비교 경로에 Python wall clock은 들어오지 않음; DB wall clock 역행은 별도 후보 |
| DATETIME 정밀도·반올림 | actual column precision 모두 6, 123456/999999/다음 초 000000/000001 roundtrip 동일 | 검사한 경로에서 정밀도 손실 없음; 최초 실측 하한값은 미복원 |
| transaction 시작 전 생성/COMMIT 시각 | 같은 transaction에서 successive statement NOW 갱신, 한 statement의 두 NOW 동일 | transaction 전체에 고정된 NOW가 아니며 ended_at은 COMMIT 시각이 아닌 검증 전 statement 시각 |
| 이전 row/attempt·context 재사용 | 새 fixture schema/engine, UUID execution, healthy 27건 identity/attempt/DB 값 비교 | 조사 실행에서 혼용 없음; 최초 snapshot의 모든 필드는 미복원 |
| session timezone/연결 복원 | application session 관측 1424건 모두 +00:00; pooled 동일 connection +09:00→checkout +00:00, heartbeat 새 connection +00:00 | 현재 factory/fixture 조건의 복원 확인; 최초 session 설정은 미확인 |
| 실행 순서/격리 | 단독 20회, heartbeat file 28개×3회, 최초 직전 8개+healthy 9개×3회, joint 81개 | 27 runs / 212 passed / skip 0 / xfail 0; 자연 발생 오류 재현 없음. 진단 query/I/O가 timing에 미칠 수 있어 최종 전체 inventory는 제품 monkeypatch·추가 SQL 진단 없이 실행 |
| DB wall clock/session timestamp 역행 | 400.94초·3916 sample에서 DB/Python 역행 0; 별도 connection SET timestamp를 1초 역행시키면 동일 validator 거부 | 통제 실험은 실패 기전만 확인한다. 최초 session override 또는 WSL/OS clock step의 발생 증거는 없으며, 과거/샘플 사이 역행을 배제할 수 없음 |

**근본 원인·수정 판단**

- 근본 원인은 **미확정**이다. 자연 발생 오류나 그 원인에 대한 결정적인 최소 RED를 확보하지 못했으므로 제품·test source 수정, sleep 추가, 허용 오차 확대, assertion 제거를 하지 않는다. 인위적인 session clock 역행을 실제 제품 결함 재현이나 수정 RED로 분류하지 않는다.
- 재실행 통과만으로 해결됐다고 판단하지 않는다. 최초 실패와 비교값 미복원, 원래 session/clock 조건 미확인을 별도 위험으로 유지한다. RT-07(b)의 상태 전이·provider 호출 횟수·UsageSink 의미는 그대로다.

**이번 조사 직접 최종 검증**

- 새 검증은 base table 0 / fixture schema 0을 확인한 별도 MySQL 8.4.7 datadir `/tmp/rt07b-debug-final-20261013/data/`, port 13335에서 시작하며 기존 성공 보고서를 사용하지 않았다. 최초 report의 selected 목록에서 파일 순서를 복원하고 실행 후 **535개 selected node의 순서 완전 일치**를 확인했다. 최초 환경 전체는 복원할 수 없으므로 root account/version/확인된 inventory만 대응하며 port/datadir는 새로 분리했다.
- **최종 require: 535 passed / 15 deselected / 실패 0, 722.08초, exit 0.** 실제 MySQL 535 tests / 1605 phases, skip 0 / xfail 0, 새 JSON/JUnit 및 별도 CLI gate PASS다. 최초 실패 healthy도 이 순서에서 PASS다. 실행은 `run-final-require.py`가 최초 selected에서 고유 파일 순서를 복원하여 `-m mysql -vvv --tb=long --showlocals -p clock_failure_only -p no:cacheprovider --basetemp=.../final-require --mysql-report=.../final-require.json --junitxml=.../final-require.xml`로 수행했다. 실패 후 hook 외에 제품 monkeypatch·추가 SQL 진단은 사용하지 않았다.
- **최종 targeted: 104 passed / 실패 0, 91.22초, exit 0.** heartbeat 28 + Worker unit 6/MySQL 5 + UsageSink unit 17/MySQL 48이다. 실제 MySQL 81개 / 243 phases, skip 0 / xfail 0을 별도 보고서로 확인했다. 안전한 timestamp/session 진단도 새 파일에 보존했다.
- 새 actual require 보고서에서 **필수 381 parameters × 7층 = 2667개** 누락을 모두 거부했다. 새 usage_sink parameter 증거 누락 350개가 포함되며 metadata 삭제 150개·family 전체 삭제 11개도 거부했다. 이전 성공 mutation 보고서를 통과 근거로 쓰지 않았다.
- boundary PASS(위반 0), Contract fixture PASS(구조 62 / JSON 26 / 의미 104), Actionlint 5 files/오류 0·YAML policy·bash -n/ShellCheck 5 run steps PASS. pyflakes는 기존 검사 방식대로 비활성이다. 최종 git diff --check PASS다. 제품/test source 무수정이므로 이번에는 전체 pytest를 반복하지 않았으며, 앞 절의 과거 5800 passed 결과를 이번 조사에서 새로 실행한 검증으로 재인용하지 않는다. 원격 CI도 실행하지 않았다.
- 최종 clock monitor는 1225.16초 / 11954 samples에서 DB/Python 역행 0이었다. 100ms 샘플 간 차이 관측이며 더 작은 clock step 또는 과거 발생의 배제 근거로 확대하지 않는다. 원래 OS/DB clock 조정 여부는 미확정이다.
- 조사/최종 서버 모두 활성 테스트 연결 0, fixture schema/계정 잔여 0, base schema 제거 후 남은 테스트 schema/계정 0을 확인하고 종료했다. 알려진 event_scheduler Daemon 1개는 테스트 연결과 구분했다. 두 port(13334/13335) closed, MySQL process·pid·socket 없음, workspace test process 0을 확인했다. 종료 후 Linux tmp의 server.log 경로가 사라져 error log는 보존하지 못했으며 그 소실 이유는 확정하지 않는다. timestamp diagnostics·clock samples·환경/preflight·JSON/JUnit·cleanup 증거는 Windows workspace에 보존됐다.
- 증거는 `.codex-scratch/rt07b-debug-20261013/`의 initial 원본 복사/SHA·traceback·matrix JSON/JUnit/diagnostics·hypotheses·clock samples·final 새 보고서이며 커밋 제외다. 성공 경로의 값 수집은 test-only plugin에 한정하고 제품 structured logging을 추가하지 않았다. 최종 require의 hook는 실패 후에만 안전한 timestamp/identity hash를 추출하며 제품 monkeypatch·추가 SQL·sleep을 수행하지 않는다.
- 이번 조사에서 변경한 저장소 파일은 **이 Log 하나**다. 착수 baseline manifest와 비교해 RT-07(b) 기존 제품·test·gate/다른 문서의 byte hash 유지, HEAD `51683e0b`/branch 유지, staging 0과 기존 제외 파일 보존을 확인했다. 커밋·push·PR는 실행하지 않았다.
- **재리뷰 준비 판단:** 원인 미확정·비교값 미복원·새 검증 범위/한계를 명시하고 독립 재리뷰를 다시 요청할 수 있다. 로컬 검증상 중간 커밋/PR 준비는 가능하나 원인이 해결됐다거나 최종 병합 차단 문제가 없다는 판정은 아니다. 기존 제외 파일을 일괄 staging하지 않으며, 미확정 위험의 수용·병합 판단은 기존 재리뷰/Deferred Owner Audit 절차를 따른다. 새 Owner 사전 승인 gate를 추가하지 않는다. RT-07 전체 상태/Issue 연결은 위 IN_PROGRESS/Refs를 유지한다.

### RT-07(b) — 독립 재리뷰 최종 통과 후속 기록 (2026-10-13)

- **사용자가 전달한 독립 재리뷰 최종 판정: PASS.** 이전 병합 보류가 해제됐으며 남은 병합 차단 문제는 없다. 앞 절의 재리뷰 미실행/준비 판단은 당시의 기록으로 보존하고, 현재 판정은 이 후속 기록으로 갱신한다.
- 최초 heartbeat 시각 실패는 **근본 원인 미확정 비차단 위험**으로 유지한다. 해결된 것으로 판단하지 않으며 RT-07(b)의 직접 원인이나 외부 환경 문제로도 확정하지 않았다. 최초 실패 이력·복원하지 못한 비교값·조사 범위와 한계는 위 기록 그대로 보존한다.
- 재리뷰 근거인 새 MySQL require inventory는 **535 passed / skip 0 / xfail 0**, targeted는 **104 passed**다. 새 JSON/JUnit gate PASS와 함께 누락 parameter **2,667건**, metadata **150건**, family **11건**이 모두 거부됐음을 위 조사에서 직접 실행한 검증 증거로 유지한다. 이번 Log 갱신에서 테스트를 새로 실행한 것은 아니다.
- 전체 pytest **5,800 passed / 26 skipped**는 구현 단계에서 보존한 검증 증거이며, 실패 조사 또는 이번 독립 재리뷰 후속 갱신에서 전체 pytest를 다시 실행한 결과로 취급하지 않는다.

| 항목 | 현재 기록 |
| --- | --- |
| RT-07 상태 | IN_PROGRESS |
| 중간 PR 연결 | Refs #294 (RT-07(b)) |
| PR 번호 | #353 |
| merge SHA | `95dfff8b3ba11f95b76a168dd18ccc1573c02b39` |

---

### RT-07(c) — durable Run 관계 경계 조사 및 구현 전 중단 (2026-10-13)

**Status: IN_PROGRESS · 최종 연결 예정: Closes #294 · PR 번호 pending · merge SHA pending.** 구현 완료 또는 독립 재리뷰 통과 기록이 아니다. 사용자가 명시한 「새 Search 공개 surface/필수 callback이 필요하면 코드를 진행하지 말 것」에 따라 제품·테스트·gate 구현 전에 중단했다.

**이 절은 2026-10-13의 조사·중단 이력이다.** 이후 Issue #294에서 Search의 durable Run 저장소가 없고 최초 영속화 경계가 T1 produced임이 확인되어 아래 2026-10-14 기록으로 중단 조건이 해소됐다. 이 절의 resolver 필요성·미검증 상태를 현재 구현 상태로 읽지 않는다.

**직접 확인한 근거**

- branch `feature/runtime-usage-reconciliation`, HEAD `95dfff8b3ba11f95b76a168dd18ccc1573c02b39`. 로컬 `origin/develop`도 같은 commit이다. GitHub connector로 Issue #294 OPEN, #244의 Accepted 최종 댓글 `5979576799` 및 Search Owner 댓글 `5969821122`, PR #349/#353 merged 및 각각의 merge SHA를 직접 확인했다. 최신 원격 develop tip을 별도로 조회한 결과로 확대 해석하지 않는다.
- Plan §6 RT-07/§12 전체/P-7/P-10, Tech Spec §3.3/§4.5/§11.1–11.4, Final UsageRecord Contract §4–8, Baseline B-G1/§2.12, RT-06 startup/periodic hook 및 현 usage/Worker/read-port 구현·관련 테스트를 대조했다. 저장소 내 AGENTS.md 파일은 검색에서 확인되지 않았으며 사용자 제공 지침을 적용했다.
- `begin()`은 run 관계가 모두 null인 STARTED를 기록한다. `finish()`의 저장 snapshot에는 Run 관계가 없고 관측값만 OBSERVED에 기록한다. `finalize()`는 caller가 확인한 관계로 Final append와 tracker FINALIZED 표시를 한 transaction에 묶는다. 관계만 먼저 durable하게 저장하는 현 port/callback은 없다. 따라서 finish 뒤 finalize 전 process kill의 pending tracker는 Run 미산출과 이미 산출된 Run의 미전달을 구분할 수 없다.
- Runtime의 `JobExecution.produced`는 execution 단위 ContractRef 목록이며 usage별 관계가 아니다. 특히 STALE 전이는 `produced=[]`를 저장하므로 Run 부재의 증거가 아니다. `ExecutionContext`나 begin replay cache도 process restart에서 durable 관계를 복원하지 않는다.
- 현 Search 공개 함수/서비스는 capability 결과를 반환한다. `AnalysisRun.usage_refs`는 파생값이며 현 구현은 Runtime usage identity 배선 전의 `usage:<source_id>`를 사용한다. 현 `SearchLedger`는 process-local list이고 Final 원장도 durable Run resolver도 아니다. 검토한 공개 API와 Accepted #244에서 execution/usage별 복구 조회 surface 및 확정 미산출 증거 callback은 확인되지 않았다. Runtime이 Search 내부 저장소를 직접 import하거나 terminal/조회 실패를 RUN_NOT_PRODUCED로 바꾸지 않는다.

**대안 비교 · 권장 방향(미승인 제안)**

| 안 | 효과 | 한계/Owner 영향 | 판단 |
| --- | --- | --- | --- |
| 현 Runtime durable 데이터만 사용 | 명시적 관계가 durable하게 있는 경우만 복구하고 불충분한 행은 pending 유지 | 현재 sink가 만든 finish→finalize 공백과 실제 Run 미생성 증거를 닫지 못함 | 안전한 보류 동작은 가능하나 RT-07(c) 전체 acceptance를 만족하지 못함 |
| composition이 주입하는 durable Run resolution port | usage별 PRODUCED / NOT_PRODUCED / UNRESOLVED를 구분하고 FAILED Run도 실제 ref로 연결 | Search의 새 공개 조회/미산출 증거 의무 및 false STALE 이후 판정 안정성 합의 필요 | 전체 acceptance를 위한 조건부 권장. Owner 확인 전 구현하지 않음 |
| 기존 sink에 관계 보존 callback 단계 추가 | Final 전에 Runtime tracker에 관계를 durable 보존 | Search가 Run 저장 후 callback 전에 죽는 공백이 남음. 원자성 또는 복구 가능한 전달·미산출 확정 규칙이 추가로 필요 | callback만 추가하는 안은 불충분. 새 의무 확인 필요 |

- 필요한 interface 제안: `resolve_usage_run(*, execution_ref, case_id, usage_id) -> Produced(run_ref, durable_evidence) | NotProduced(durable_evidence) | Unresolved`. 기존 구현/승인된 signature가 아니다. Produced는 해당 execution/case/usage와 실제 durable Run의 연결, NotProduced는 단순 조회 부재가 아닌 최종 미산출 근거를 의미한다. Unresolved는 pending으로 남긴다. payload·provider 응답을 전달하지 않는다.
- resolution은 Runtime transaction 밖에서 실행해야 한다. 전달된 근거는 transaction 전체 replay 및 이후 sweep에서 안정적이어야 하며, NOT_PRODUCED 판정 뒤 늦은 Worker가 다른 Run을 산출하는 공백을 어떻게 막는지 Owner가 확인해야 한다. Runtime transaction은 terminal execution과 tracker를 다시 검증하고 동일 identity/snapshot으로 짧게 finalize하는 방향이다. 이를 현재 보장이라고 기록하지 않는다.

**P-7 및 read-port 판단 — 미구현 설계 방향**

- RT-07(b)의 FINALIZED finish는 동일 관측 replay만 허용하고 상이한 값은 conflict다. 이 동작을 모든 recovery FINALIZED에 그대로 적용하면 아직 관측이 없던 recovery row에 늦은 실제 관측을 보존하지 못한다. P-7에 따라 Final은 그대로 두고 tracker에 첫 늦은 관측을 durable 보존하며 동일 replay는 no-op, 상이 관측/관계는 conflict로 처리하는 방향을 권장한다. Final UPDATE는 Contract §8-1 위반이므로 배제하고 관측 거부/휘발성 로그만 남기기는 P-7을 만족하지 못한다. 구체 상태/marker와 event 재전달 방식은 아직 구현 선택으로 확정하지 않았다.
- 정상 Final 이후 최초 관측 덮어쓰기는 허용하지 않는다. recovery 이후 관측 저장과 event는 transaction/observer 실패로 Final identity·관계가 바뀌지 않도록 분리해야 한다. 원장과 tracker의 late 관측이 달라져도 Final이 authoritative다.
- 현 read port는 여전히 `usage_refs=[]`다. 최종 구현은 `usage_record.execution_ref`별 Final ID만 중복 없이 결정적으로 projection하고 pending tracker는 제외해야 한다. validator/Case 소비 경계 변경은 불필요하다는 설계 방향이며 구현·검증 결과는 아니다.

**Verification · RED→GREEN · 남은 범위**

- 이번 직접 실행은 자료/코드/Git 조회 및 문서 변경 검증이다. RT-07(c)의 TDD RED→GREEN, 실제 MySQL 20개 요구 scenario, JSON/JUnit gate·누락 mutation, 전체 pytest, boundary/fixture/workflow 검사는 실행하지 않았다. 새 MySQL skip/xfail 결과는 미측정이며 0으로 보고하지 않는다. 위 RT-07(a)/(b)의 수치는 과거 보존 증거다.
- 제품·test·migration·CI gate를 수정하지 않았고 외부 provider/테스트 DB/server/thread/process를 생성하지 않았다. 이번 schema/account/connection 정리 acceptance를 검증했다는 뜻은 아니다. 문서 diff 검증 및 보호 파일 hash 비교 결과는 `.codex-scratch/rt07c-20261013/document-verification.json`에 보존한다.
- 상세 조사·필요 interface·대안·완료 보고 12항목은 `.codex-scratch/rt07c-20261013/design-boundary-review.md`에 보존한다. scratch는 Git ignore 대상이며 커밋 제외다.
- Contract/Accepted Decision/Baseline 변경 없음. 제안한 Search surface는 새 의무일 수 있어 Plan §12.3 확인 대상이며 아직 Owner에 메시지를 보내거나 승인받지 않았다. 사용자가 기존 승인 surface를 지정하거나 새 의무에 대한 Owner 확인을 제공한 뒤 구현을 재개해야 한다.
- RT-07(c) 구현의 독립 재리뷰 요청 가능 상태가 아니다. 설계 경계 검토는 가능하다. process-kill·동시성·COMMIT 불명·P-7·usage_refs 전체 acceptance, SRCH-1 실제 배선과 기존 미확정 timing 위험은 남아 있다. 커밋·push·PR 생성·staging은 하지 않는다.

---

### RT-07(c) — Owner 합의 반영 · produced 기반 reconciliation (2026-10-14)

**Status: DONE · 최종 PR 연결: Closes #294 · PR 번호 #360 · merge SHA `505e6ad2c95617569faad1b12a45fa48d3e41919`.** 독립 재리뷰 PASS 및 남은 병합 차단 문제 없음을 사용자 전달 결과로 기록한다. 로컬 구현·검증·테스트 DB 정리 후 재리뷰 요청 상태였던 기존 이력은 아래 보존한다. 이번 갱신은 RT-07 절의 문서 변경만이며 코드·테스트 수정/재실행, staging·커밋·push·PR 생성은 하지 않는다.

**독립 재리뷰 최종 판정 — PASS(사용자 전달 결과)**

- 남은 병합 차단 문제 없음. Owner 합의에 따른 `JobExecution.produced` 기반 복구, 명시적 `DIRECT_NO_RUN`, 별도 Search resolver를 추가하지 않는 경계를 확인했다. 예정 Run ID 자체를 존재 근거로 삼거나 빈 produced에서 DIRECT_NO_RUN을 추론하지 않는다.
- **재리뷰 직접 실행 결과:** targeted **3,475 passed**; 실제 MySQL **590 passed / 1,770 phases**, 신규 reconciliation **51개 포함**. 아래 구현 단계 보존 증거와 별도로 기록하며, 이번 문서 갱신에서 테스트를 다시 실행한 결과가 아니다.
- **누락 거부 검증:** 신규 parameter 증거 누락 **357건**, metadata 누락 **153건**, family 누락 **13건**을 거부했다. P-7 late observation의 durable 관측 보존·immutable Final·replay/conflict 및 `usage_refs`의 Final-only projection 검증도 통과했다.
- **구현 단계 보존 증거:** 전체 pytest **6,374 passed / 26 skipped / 실패 0**, full MySQL **591개 / 1,773 phases**. 이를 독립 재리뷰에서 전체 pytest를 새로 실행한 수치로 재인용하지 않는다. 상세 RED→GREEN·실제 MySQL·gate·cleanup 기록은 아래 보존한다.
- **비차단 개선 후보:** malformed 후보별 오류 격리. 재리뷰의 병합 차단 finding이 아니며 이번 문서 갱신에서 구현하지 않는다.
- **후속 확인:** 원격 CI의 실제 실행 시간과 기존 **900초 nested timeout** 안의 완료 여부는 확인이 필요하다. 로컬 통과를 원격 CI 통과로 확대하지 않으며 timeout을 완화하지 않는다. 최종 PR은 `Closes #294`, PR 번호는 `#360`, merge SHA는 `505e6ad2c95617569faad1b12a45fa48d3e41919`이다.

**설계 경계 및 기존 사실 정정**

- Issue #294의 Runtime 답변 `6145102027`, Search 답변 `6148574716`, 최종 확인 `6150512406`을 connector로 직접 읽었다. Search의 Run은 provider 호출 전 선발급 ID와 호출 후 메모리 객체이며 별도 Run 저장소가 없고, 최초 durable 관계는 T1의 `JobExecution.produced`다. 따라서 앞 절의 「Search 내부 durable Run + T1 전 kill」은 현재 구조의 실제 gap이 아니다. 새 Search resolver/필수 callback/저장소를 추가하지 않는다.
- 대안은 기존 produced 사용 / 새 resolver / begin 전 durable Run 생성이다. Owner 확인에 따라 기존 produced를 선택했다. 나머지 둘은 현재 조회할 Search durable 상태가 없거나 새 저장소 의무를 만들므로 채택하지 않는다. SRCH-1은 예정 ref 전달과 FAILED AnalysisRun의 produced 반환을 배선한다는 Search의 명시적 확인을 따른다.
- DIRECT_NO_RUN은 job 내부에서도 유효한 기존 Contract 의미다. RT-07(b)의 execution sink만 거부했던 사전 검증을 정합화한다. 기존 Log의 「허용했다」와 실제 차단 코드/테스트 불일치는 위 b 기록을 당시 사실로 고쳐 보존했다. 빈 produced를 DIRECT_NO_RUN으로 추론하지 않는다.

**구현 결과**

- frozen `runtime_0004`는 tracker에 `planned_run_kind/ref`, `direct_no_run`, `recovered_at`, `late_observed_at`를 추가한다. 기존 frozen revision과 Final UsageRecord schema는 변경하지 않는다. legacy 행은 예정 관계 없음/explicit no-run false로 유지해 임의 finalization하지 않는다. 실제 MySQL forward migration 보존 및 live metadata DDL 정합을 검사한다.
- 신규 migration의 7개 ALTER를 한 ALTER로 묶어 추가 DDL round trip 6회를 줄였다. SHOW CREATE 정합과 legacy 보존 검사는 통과했다. require-MySQL 실행은 변경 전 968.98초, 변경 후 682.55초였으나 이 환경의 관측값이며 운영 성능이나 시간 상한을 보장하지 않는다. 기존 중첩 실제-report gate의 900초와 workflow timeout 20분은 완화하지 않았다.
- begin은 optional 예정 Run ref 또는 명시적 null + DIRECT_NO_RUN 선언을 durable STARTED에 저장한다. 예정 ID 자체는 실제 Run 존재 근거가 아니다. 기존 b의 intent 생략/발급 ID replay는 유지하고, 같은 ID의 다른 intent는 conflict이며 begin에서 RUN_NOT_PRODUCED를 선결정하지 않는다.
- 자동 normal T1 및 recovery는 terminal execution과 tracker를 짧은 usage별 transaction으로 잠그고 예정 ref를 produced와 대조한다. 일치하면 FAILED 포함 실제 ref, 불일치하면 RUN_NOT_PRODUCED, 명시적 no-Run이면 DIRECT_NO_RUN이다. RUNNING/QUEUED, missing/cross-case execution, intent 불명 행은 변경하지 않는다. malformed/duplicate produced는 검증 오류이며 단순 부재로 다루지 않는다.
- 정상 T1 commit·connection 반환 뒤 별도 usage transaction을 실행한다. STALE/T2 transaction 뒤 기존 startup/periodic hooks에도 연결한다. transaction callback에는 DB I/O만 있고 기존 B-D8를 사용한다. candidate snapshot·finalized_at은 callback 재시도 밖의 고정 준비 상태로 유지하며 unknown COMMIT은 immutable Final과 대조한다. 일반 post-T1 오류는 handler/provider/T1 재실행을 일으키지 않고 sweep에서 다시 복구한다. 기존 fatal/cleanup/thread lifecycle 및 느린 hook/join의 상한 미보장 정책은 유지한다.
- b의 standalone explicit finalize는 caller가 실제 관계를 확인하는 호환 API로 유지한다. 새로운 자동 Worker 경로는 terminal produced를 사용하고 Search의 세 번째 호출을 요구하지 않는다. 이미 FINALIZED인 identity replay는 늦게 보강된 tracker 관측을 Final과 비교해 덮어쓰지 않고 immutable Final의 context/관계를 확인한다.

**P-7 선택**

- b의 FINALIZED 관측 동일성 검사만 유지하면 미관측 recovery Final 뒤 첫 실제 finish를 거부한다. Final UPDATE는 append-only에 어긋나고 휘발성 로그만 남기면 관측 보존을 못 하므로 둘 다 배제했다.
- recovery 표식이 있는 Final tracker에서 최초 늦은 finish는 관측이 없으면 실제 관측을 보존하고, 이미 관측됐다면 동일성 검사 후 late marker만 남긴다. FINALIZED 상태·Final identity·run 관계·Final snapshot은 바꾸지 않는다. 같은 관측 replay는 durable no-op, 다른 관측/관계는 sanitized conflict다.
- 내부 fresh reviewer가 정상 FAILED T1의 미관측 STARTED 확정에서 recovery 표식이 없어 finish persistence replay가 거부되는 Important 1건을 지적했다. 실제 Worker/MySQL RED 1 failed(UsageConflictError) 후 미관측 자동 T1 fallback도 usage recovery로 표시하도록 수정했다. 정상 관측 완료 T1은 recovery로 세지 않는다. 수정 후 신규 actual MySQL 51 passed에서 해당 regression GREEN을 확인했다. reviewer의 재현은 _locked만 대체한 읽기 전용 Python 검사였고 MySQL 검사는 구현자가 실행했다. 사용자 독립 재리뷰와 구분한다.
- `late_observed_at`는 관측과 같은 transaction의 durable event 표식이다. `runtime.usage.late_observation` logger/observer는 commit 및 connection 반환 후 best effort로 호출한다. 로그 전송의 exactly-once/장애 시 외부 전달 보장은 약속하지 않는다. ACK 불명·logger 장애에서도 durable marker와 실제 관측은 남는다.

**read port 및 관측**

- `read_executions`는 `usage_record.execution_ref`별 Final ID만 PK 중복 없이 정렬해 projection한다. pending tracker/private column은 노출하지 않고 없으면 []다. JobExecution validator와 Case의 대표 execution 선택 경계는 유지한다.
- recovered_count는 recovery marker가 있는 committed 행 수, inflight_count는 non-FINALIZED 행 수다. oldest age는 하나의 DB 집계 snapshot에서 DB NOW(6)를 기준으로 계산한다. metric observer는 typed 숫자만 받으며 structured log의 count는 비음수 정수, age event는 기존 duration_ms 표현을 사용한다. 원시 SQL·URL·path·전체 snapshot을 logger/observer/UsageError 문자열에 전달하지 않는다.

**RED→GREEN 및 최종 검증 — 구현 단계 직접 실행의 보존 증거**

- 기존 unit baseline 23 passed. 새로운 relation/P-7/concurrency/metric/projection actual MySQL 29 failed RED 후 기존 usage 회귀 포함 195 passed GREEN. Worker/T1/startup/periodic/OS kill 5 failed RED → 5 passed GREEN.
- COMMIT OK packet 실제 소비·1회 ACK 유실/3회 소진 후 재실행, actual 1205/1213 및 전체 transaction rollback/retry, begin intent/direct explicit finalize, forward legacy 보존: 15 passed. 첫 실행 4 failed/11 passed는 test SQL이 Final에 없는 finalized_at을 조회한 문제였다. traceback으로 1054 원인을 확인해 tracker JOIN으로 고친 뒤 통과했으며 제품 정책은 바꾸지 않았다.
- malformed produced의 부재 오판을 추가 RED 1 failed(DID NOT RAISE)로 확인해 RuntimeContractRef 구조/중복 검증을 추가했다. 이 변경 이후 최종 targeted 재검증 결과는 아래 최종 evidence에 기록한다.
- independent MySQL inventory 추가 후 기존 gate가 새 family 13개와 parameter 전체 삭제 49개를 허용하는 RED 62 failed/3160 passed를 확인했다. parameter metadata 삭제 추가 RED 49 failed/98 passed도 확인했다. production gate에 별도 필수 inventory를 추가하고 기존 Case/Runtime inventory·timeout·skip/xfail 정책은 유지했다.
- 최종 증거는 ignored `.codex-scratch/rt07c-20261014/`에 보존한다. 이전 a/b 수치는 이전 보존 evidence다. 사용량 한도로 중단된 뒤에는 완료된 구현·RED→GREEN·targeted·require/full pytest를 재실행하지 않고 최종 보고서 gate·집계·정리·Git 상태·문서만 마무리했다.
- 수정 후 신규 actual MySQL `targeted-fixed.json/xml`: 51 passed, skip 0/xfail 0. unit/gate/logging/sweep `unit.json/xml`: 3,475 passed, MySQL 194 deselected. 관련 Worker·RT-06·read-port 회귀는 537 passed/2 failed였고, 실패 원인은 두 기존 migration head 기대값이 runtime_0003에 머문 것이었다. runtime_0004로 기대값만 갱신한 후 실제 MySQL 재검증 2 passed이며 최종 full에도 포함됐다.
- 최종 고정 코드 require-MySQL `require.json/xml`: 실제 MySQL 590 tests/1,770 phases, skip 0/xfail 0/failure 0, gate PASS, 682.55초. pytest 요약의 4 skipped는 MySQL이 아닌 typer 미설치 collection skip이다. 독립 inventory 432 parameters × 7 evidence 층의 누락 3,024건, 그중 신규 51 parameters의 누락 357건, 신규 metadata 누락 153건, family 누락 13건과 실패 보고서를 모두 거부했다(`require-mutations.json`, `require-mutations-final.txt`).
- 최종 전체 pytest `full.json/xml/txt`, exit 0: **6,374 passed / 26 skipped / failure 0**, 1,667.89초. 26 skip은 typer 미설치 4건과 로컬 미디어·명시적 opt-in 조건 22건이며 MySQL skip은 0이다. 중첩 실제-report gate도 기존 900초 제한 안에서 통과했다. 최종 full JSON/JUnit에 현재 gate를 실행해 PASS를 확인했다: **MySQL 591 tests / 1,773 phases(setup/call/teardown 각각 591), skip 0 / xfail 0 / failure 0**. require와의 1건 차이는 full에 포함된 `test_actual_report_rejects_each_missing_migration_check`이며 inventory를 줄이지 않았다.
- boundary PASS(위반 0); Contract fixtures 구조 62/JSON 26/의미 104 PASS; workflow 정적 검사 5 files/5 run steps PASS(Actionlint·YAML policy·bash -n·ShellCheck, 기존 pyflakes 비활성 조건 유지). `git diff --check` 및 신규 6개 파일 공백 검사 PASS. 원격 CI/실제 provider 실행 결과로 해석하지 않는다.
- 중간 concurrent 검증 3개는 출력 진행이 멈춰 이 작업의 process임을 확인 후 종료했으며 완료 증거로 사용하지 않는다. 검증 중 소스 변경이 포함된 중간 실행도 최종 증거와 분리했다. 최종 순차 full의 faulthandler 진단에는 중첩 subprocess.communicate 대기가 기록됐으며 실패나 timeout 완화가 아니다. 중간 지연 원인을 확정하거나 해결됐다고 단정하지 않는다.
- 최종 `cleanup-db.py`는 처음에 MySQL 내부 event_scheduler Daemon을 감지해 안전 중단했다. port/bind/datadir로 전용 서버임을 검증한 뒤 scheduler를 종료하고 기존 스크립트를 재실행해 exit 0으로 완료했다. 테스트 schema 3개 제거 후 schema/계정/기타 connection 잔여 0. 서버 종료 뒤 WSL PID 파일/socket/process/listening port와 Windows 테스트 process/13336 port 잔여 0을 확인했다(`cleanup-db.json`, `cleanup-residual.json`).
- 보호 항목 4개의 1,069 파일은 시작 SHA-256과 경로 집합이 동일하며 추가/삭제/변경 0(`protected-final.json`). HEAD `95dfff8b3ba11f95b76a168dd18ccc1573c02b39`, branch `feature/runtime-usage-reconciliation`, staged diff/미병합 index 항목 없음(`git-final.json`). 변경 26파일(기존 20/신규 6)의 전체 diff·SHA-256 manifest·요약을 `review.diff`, `review-manifest.json`, `changed-files.md`, `review-summary.md`에 남긴다. 제품 코드는 최종 검증 이후 변경하지 않는다.

**남은 위험·범위 밖**

- 정상/복구 관계 판정의 근거는 현재 Search 구조에 관한 Owner 확인이다. 이후 별도 durable Run 저장소가 생기면 T1 전 gap을 다시 검토해야 한다. legacy intent 불명 행은 자동 복구로 관계를 꾸며내지 않으며 명시적 관계 확인/이관이 필요하다.
- 실제 Search adapter 배선(SRCH-1), pricing/FX(RD-08), retention/purge(RD-10c/d), Case budget guard, SearchLedger 정리(#153)는 범위 밖이다. 기존 heartbeat/cancel timing 원인 미확정 위험, raw SQL binder 우회/rounding 한계는 유지한다.
- malformed 후보별 오류 격리는 독립 재리뷰에서 제시된 비차단 개선 후보다. 원격 CI 실행 시간과 기존 900초 nested timeout 내 완료 여부는 후속 확인이 필요하다. 로컬 통과 기록과 timeout 미완화 사실은 보존한다.
- Contract/Accepted Decision/Baseline 변경 없음. 독립 재리뷰 PASS 및 남은 병합 차단 문제 없음은 사용자 전달 결과다. 원격 CI 통과는 아직 확인되지 않았으며, 최종 PR은 `Closes #294`, PR 번호는 #360, merge SHA는 `505e6ad2c95617569faad1b12a45fa48d3e41919`이다. 이번 문서 갱신에서는 RT-07을 DONE으로 기록하고 코드·테스트 재실행, staging·커밋·push·PR 생성 없이 멈춘다.

---

## RT-08 — API composition root: `/cases` · `/commands` · `/view` · `/health/*`

Status: IN_PROGRESS · Issue: #295 · Audit: B

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| pending | `Refs #295 (RT-08(a))` — app skeleton · envelope · health · single API process | pending |

### 구현 결과

- RT-01 `Startup`/불변 RuntimeConfig를 재사용하는 `api/app.py:create_app`과 `composition.py:compose_api`를 추가했다. factory에서 설정 검증과 engine 조립을 끝내며 listener 전에 실패한다. DB 접속·migration·provider 호출은 startup에서 하지 않는다. lifespan이 ready helper와 engine을 닫는다.
- 기존 RT-02 API QueuePool과 전용 ready NullPool을 소비한다. `/health/live`는 dependency를 호출하지 않고 Contract §5.7 body를 반환한다. `/health/ready`는 dedicated SELECT 1과 media root metadata만 검사하고 같은 절의 status/body를 반환한다. 실패 dependency는 상수 event에만 남긴다.
- `errors.py`는 Contract §3.3 envelope와 같은 문자열의 code/message_key를 만든다. 기본 404·405·transport validation body/detail을 차단하고 RT-02 BeforeCommitFailure/CommitOutcomeUnknown을 Contract/B-D8의 503/500으로 구분한다. domain validation을 재정의하지 않는다. 아직 command route/transaction은 없다.
- JSON route는 Plan P-9의 sync def다. docs/OpenAPI와 slash redirect는 비활성이다. 각 요청에 서버 trace_id를 발급하고 RT-01 context helper와 allowlist structured logger를 사용한다. request URL/query/body/header, exception 문자열/headers, DB URL, mount path와 Runtime 내부 field를 응답/로그에 담지 않는다.
- `python -m daesingo.api --revision <revision>`이 supported process 경계다. 명시적 workers=1/reload off로 B-W4를 소비하며 WEB_CONCURRENCY를 무시한다. Uvicorn raw access/error/traceback logger는 실행 구간에서 disable하고 원래 상태/handler를 복원하며 application의 안전한 event를 관측 경계로 둔다. composition 예외도 입력/traceback 없이 상수 event와 SystemExit(1)로 처리한다.
- 기존 MySQL JSON/JUnit gate에 api_health ready(normal/pool_exhausted/connection_lost/server_stopped), storage(readonly), process(single_worker)의 독립 필수 identity를 추가했다. nested migration acceptance도 tests/api를 수집하고 동일 identity의 각 evidence layer 누락을 거부한다.

### Plan 대비 변경

- 이번 작업은 RT-08(a) 하나다. Expected files 외에 stdlib metadata-only `storage.py`, bounded telemetry `events.py`, process boundary `__main__.py`를 분리했다. 파일 구조·DI·thread helper 선택은 Plan §12.3의 implementation detail이다.
- 기본 framework validation은 transport 오류 400/http.malformed_request로 차단한다. 이후 commands는 opaque JSON을 Case에 넘기고 Case의 422/응답을 보존해야 한다. generic framework HTTPException의 Contract 밖 status는 internal_error로 끝내며 새 공개 status/code를 만들지 않는다.
- ready에는 media root만 검사한다(Contract §5.7/공유 mount). API temp root·provider·Worker·queue 적체를 새로운 readiness 의무로 추가하지 않는다. B-U2 request limit은 commands가 없는 이 단계에서 전역 middleware로 적용하지 않으며 (c)에서 route별로 연결한다. B-U5의 별도 JSON request timeout은 만들지 않는다.
- 실제 RO mount는 host layout을 가정하지 않고 private namespace에서 RO tmpfs를 생성·검사·unmount한다. 서버 SHUTDOWN은 기존 suite DB와 분리된 독립 MySQL 서버에서 검증한다. mock/skip 대체가 아니다.
- Contract/Accepted Decision/Baseline 의미 변경 및 새 Case/Search 의무: 없음. Runtime Implementation Plan 본문은 바꾸지 않았다.

### 새 implementation detail

- probe별 최대 하나의 in-flight daemon call을 겹치는 요청이 공유한다. 각 caller와 최초 probe의 monotonic deadline 안에서만 성공을 인정한다. 시간 초과한 native call을 강제로 취소하지 않으며, 끝나기 전 새 thread를 누적하지 않는다. 늦게 반환한 연결은 context manager에서 닫는다. 최종 available 판정도 B-H3 deadline을 확인한다.
- `ApiEvents`: app당 daemon consumer 하나, 대기 queue 최대 128 event, 포화 시 새 event drop, correlation은 제출 시 capture, shutdown join 최대 1초. logger exception·지연·thread start failure를 응답으로 전파하지 않는다. 이 수치는 telemetry 내부 자원 상한이며 Baseline 재조정이 아니다. block된 sink를 강제로 중단할 수 없다.
- Windows metadata API에는 statvfs가 없으므로 is_dir/access 검사만 제공한다. 배포 Linux의 read-only flag는 실제 mount acceptance에서 검증한다. 경로를 별도 mountpoint로 강제하는 정책이나 probe file 쓰기는 추가하지 않는다.
- 폐기 가능한 두 번째 MySQL server를 Linux에서는 CI service가 준비한 mysql:8.4 Docker image로, Windows에서는 명시한 WSL 테스트 바이너리/라이브러리 경로로 시작한다. Docker/WSL 또는 mount 기능 부재를 skip으로 숨기지 않는다. 각 helper가 process/port/namespace를 정리한다.
- FastAPI·uvicorn runtime dependency와 HTTP test dependency를 pyproject/uv.lock에 고정했다. 구현 계획과 재현/실행 자료는 `docs/superpowers/plans/2026-10-14-runtime-api-skeleton-health.md`, `.codex-scratch/rt08a-20261014/`에 보존한다.

### Owner 확인 포인트

- 김준영: Contract health 예외 body·default 404/405/validation 차단과 오류 status 표를 확인한다. (b/c/d)의 Case 응답 전달·commit/rollback과 연결할 때 이 transport helper가 domain 응답을 감싸거나 바꾸지 않는지 확인한다.
- 김준영: dedicated probe deadline/in-flight 공유·late close, bounded lossy telemetry와 raw uvicorn diagnostics 억제, shutdown에서 native blocked call을 강제 drain하지 못하는 한계를 Audit B에서 확인한다.
- 김준영: Linux CI의 두 번째 MySQL Docker 서버와 sudo/unshare private RO mount acceptance 실행을 확인한다. workflow source는 바꾸지 않았고 remote CI 결과를 이번 local 검증으로 단정하지 않는다.
- Case/Search 새 공개 capability·의무·Consult 대상 배선 없음. command/view port는 (b/c/d), 실제 Search adapter는 SRCH-1, 전용 metrics 집계는 RT-12에 남는다.

### Verification

- RED: app factory 미구현 ModuleNotFoundError와 신규 evidence 누락 10개 허용을 직접 확인했다. 독립 리뷰 finding의 동시 ready false unavailable, uvicorn raw traceback, slow logger deadline, composition 입력 노출, event thread start failure도 각각 failing test로 보존했다.
- GREEN: 최신 RT-08(a) targeted 49 passed. 실제 MySQL dedicated ready/pool 고갈·transport 단절·독립 server SHUTDOWN·private RO mount·실제 API process를 포함한다. MySQL 대상 skip/xfail 없음. 로그 sink 예외/지연/시작 실패, 유한 queue/context, configuration/composition safe fail-fast와 raw logger 차단을 확인했다.
- 읽기 전용 독립 reviewer가 finding을 제시했고 각 finding은 root 세션에서 RED/GREEN으로 검증했다. reviewer의 sandbox pytest setup 오류와 root의 실행 결과는 구분한다. 아직 외부 Owner acceptance/remote CI PASS를 주장하지 않는다.
- API/common 최종 unit 회귀: `pytest tests/api tests/common -m "not mysql"` → 3,885 passed. MySQL 회귀는 최종 전체 required suite에 포함한다. gate unit 회귀 → 3,449 passed.
- 초회 MySQL 필터 실행은 594 passed/MySQL skip·xfail 0이지만 마지막 process identity 추가 전 수집한 자료여서 현재 gate가 거부한다. 초회 API/common 실행의 3개 실패는 nested MySQL 900초 timeout 및 검증 중 gate inventory 갱신으로 생긴 혼합 snapshot이다. 동시에 실행한 local MySQL 검증을 종료·정리하고, 소스 해시를 고정한 전체 단독 실행으로 재검증한다. 초기 실패 자료는 보존하며 최종 PASS 근거로 사용하지 않는다. 기존 timeout/gate 조건은 완화하지 않았다.
- **최종 단독 전체 pytest:** 6,463 passed · 기존 선택 실행 대상 26 skipped · Starlette/httpx deprecation warning 1. MySQL 대상 skip/xfail은 0이다. 실행 1,748.83초(29분 8초)는 로컬 실측이며 원격 CI의 소요시간을 뜻하지 않는다. 기존 nested 900초 제한을 유지한 채 통과했다.
- **최종 MySQL JSON/JUnit gate:** 596 tests · skip=0 · xfail=0 · failure=0. 전체 JUnit 6,489 testcase · failure/error 0. 별도 nested 실제 acceptance 591개 gate도 PASS이며 기존·신규 parameter mutation 3,066개 중 API 신규 42개가 모두 거부됐다.
- **신규 API evidence 누락:** 최종 full JSON/JUnit을 복사한 6 identity × 10 layer(role/scenario/parameter/collection/selection/setup/call/teardown/all/JUnit) = 60개 삭제 변형을 전부 거부했다. 원본 보고서는 변경하지 않았다.
- **최종 정리:** 소유가 확인된 독립 MySQL 8.4.7 서버에서 테스트 schema 1개를 제거했고, 남은 테스트 schema/계정/연결은 각각 0이다(시스템 daemon은 테스트 연결로 세지 않음). 서버 SHUTDOWN 뒤 PID/process/port 폐쇄, 독립 SHUTDOWN 서버·RO mount 디렉터리 부재, Windows 관련 child process 0을 확인했다. 실제 API process/port와 각 proxy도 fixture 종료 때 정리했다.
- **불변 검증:** 보호된 기존 미추적 4개 항목의 전체 1,069개 파일 inventory/해시 동일. 테스트 대상 소스 18개 해시 동일. HEAD `505e6ad2c95617569faad1b12a45fa48d3e41919` · 현재 feature 브랜치 유지, index empty. staging/commit/push/PR 생성 없음.
- 재리뷰 자료: `.codex-scratch/rt08a-20261014/{review-summary.md,changed-files.md,review.diff,review-manifest.json,full.json,full.xml,full-gate.txt,evidence-mutations.json,full-counts.json,cleanup-db.json,cleanup-wsl.txt,cleanup-processes.json,final-integrity.json}`. 초기 실패 자료도 별도 보존한다.
- boundary checker PASS(위반 0), Contract fixture PASS(문서 구조 62·JSON 26·의미 fixture 104), workflow actionlint/YAML 정책/bash -n/ShellCheck PASS(5 workflow/5 run step, pyflakes disabled), git diff --check PASS를 직접 확인했다. 최종 문서 갱신 후 다시 확인한다.


### 2026-10-14 독립 재리뷰 finding 수정 — 착수 기록

- 이전 RT-08(a) 읽기 전용 reviewer의 추가 finding 없음과 구현자의 전체 6,463 PASS 기록은 당시 검증 범위다. 사용자가 후속 독립 재리뷰에서 전달한 병합 차단 finding은 P1 handler write 정지 시 interpreter logging.shutdown 교착, P2 composition 실패의 동기 sink 종속, P2 CLI 실행 예외 traceback 노출의 세 건이다. 이전 filter 지연 테스트는 handler lock/atexit 경로를 검증하지 않았다. 이 절의 재현·수정·실행 검증 주체는 구현자이며, 수정본 독립 재리뷰 결과와 구분한다.
- P1 구조 선택 사전 검토: (A) daemon + join(timeout) 유지로는 stdlib shutdown이 기다리는 handler lock을 해소하지 못한다. (B) 별도 logging process는 쓰기 강제 중단이 가능하지만 추가 process/IPC/stream 전달 및 B-W4 실행 경계 부담이 생긴다. (C) API 소유 handler의 직렬 I/O lock을 stdlib handler cleanup lock과 분리하고 shutdown에서 sink I/O를 하지 않는 방식을 선택한다. 정상 event emission 자체에서 write/flush를 완료하며, 유한 queue drain은 ApiEvents가 소유한다. 기본 stdout은 unbuffered fd write로 Python buffered stdout의 종료 lock도 잡지 않는다. 제공 TextIO의 close/최종 flush는 caller 소유이며 API가 제3자 handler를 제거하거나 종료하지 않는다. Worker handler, allowlist/formatter, logging 전역 자료구조와 정상 interpreter 종료 정책은 유지한다. 포화·정지 sink 진단 유실 trade-off는 기존 telemetry 정책 안의 implementation detail이다.
- RED/GREEN과 후속 검증 결과는 finding별 실행 후 아래에 추가한다. RT-08 IN_PROGRESS, `Refs #295 (RT-08(a))`, PR/SHA pending, Contract/Accepted Decision/Baseline 의미 및 Case/Search 의무 변경 없음.

| Finding | 수정 근거 및 직접 RED → GREEN | 검증 주체 |
| --- | --- | --- |
| P1 handler write 정지 / interpreter 교착 | 실제 TextIO.write가 release 없이 정지한 subprocess: close 반환 marker 뒤 5초 timeout RED 1. API 소유 handler I/O lock과 stdlib cleanup lock 분리, emission flush / shutdown no sink I/O, 기본 stdout unbuffered fd. 정상 queue drain·포화·context 회귀 포함 P1 GREEN 49 | 구현자 |
| P2 composition fail-fast sink 종속 | composition 예외 + 실제 handler write 정지와 fatal diagnostic 3종 RED 4. 임시 ApiEvents의 유한 drain으로 실패 코드 1을 우선하며 진단 유실 허용. 기존 정상 composition 실패 event 포함 GREEN 5; stderr/traceback/secret/DB URL/경로 비노출 | 구현자 |
| P2 CLI 실행 예외 원문 노출 | 잘못된 port 4종, 서버 Exception/KeyboardInterrupt/SystemExit/BaseException 및 cleanup RED 12. port 0~65535(0은 OS 배정) 선검증, quiet argv 실패 코드 1, 서버 일반/fatal 실패 코드 1·KeyboardInterrupt 코드 0, finally 자원 정리와 signal/서버 logger 복원. API/Worker 회귀 포함 GREEN 67 | 구현자 |

- P1 fatal 정책 보완: 기존 consumer fatal이 thread excepthook으로 끝나 owner에게 전달되지 않는 RED 3, prelaunch fatal 시 미완료 queue task RED 3을 확인했다. 일반 Exception은 best-effort, fatal은 원문을 thread stderr에 출력하지 않고 close에서 owner에게 전달한다. common log_event_best_effort의 strict BaseException 전달 및 Worker handler 정책은 유지한다.
- 이번 읽기 전용 reviewer의 추가 P1: stdout 실패의 고정 fallback이 buffered stderr에서 정지하면 종료가 다시 교착된다. reviewer가 close_returned 뒤 7초 timeout을 직접 재현했고 구현자도 unread stderr subprocess RED 1(9초 timeout) 후 동일 API 소유 unbuffered fd 경계를 적용했다. 고정 JSON fallback/Worker 동작 유지, unread stdout/실제 write 포함 GREEN 4. reviewer의 동일 재현도 코드 0 종료를 확인했다.
- 이번 reviewer의 추가 P2: Uvicorn이 lifespan shutdown 예외를 삼킨 뒤 idempotent close가 실패 정보를 잃어 코드 0이 됐다. 실제 LifespanOn 및 partial Readiness 조립 RED 3, 실제 uvicorn.run/socket bind/shutdown subprocess RED 1(코드 0)을 확인했다. dispose는 한 번만 실행하고 cleanup_failed boolean을 process owner까지 보존하며, 조립 중 실패는 모든 할당 engine을 정리한다. 해당 cleanup GREEN 18. 실제 서버 subprocess에서 코드 1, stderr empty, listener 폐쇄/signal 복원을 확인했고 reviewer도 실제 Uvicorn으로 모든 자원의 once-only close와 코드 1을 재검증했다.
- 이번 reviewer의 추가 P2: 실제 Thread.start는 native launch 뒤 interruptible wait를 하므로 callback을 소비한 뒤 start가 실패할 수 있다. unconditional get_nowait의 Empty가 원래 fatal을 덮고 consumer 소유권이 유실되는 RED 3을 실제 Thread로 확인했다. Empty를 구분하고 public ident로 확인한 시작된 consumer를 close owner에 남겨 정리한다. fatal과 시작된 consumer 실패에서는 추가 제출을 중지하며, ordinary prelaunch start 오류 격리는 유지한다. 기존 start 실패 포함 GREEN 7; reviewer도 fatal 2종/Exception 1종과 미완료 queue task 0을 직접 확인했다.
- 최종 읽기 전용 소스 재리뷰: 이번 reviewer는 추가 actionable blocker 없음으로 보고했다. 위 reviewer 직접 subprocess 검증과 구현자의 실행 결과는 구분한다. 외부 독립 재리뷰/Owner acceptance/원격 CI 승인 판정이 아니다. 최종 전체 실행 결과 및 잔여 정리는 아래에 추가한다.


- 최종 신규 회귀 초회는 40 PASS/1 timeout이었다. 실제 서버 종료 뒤 Windows connect_ex의 default 대기가 포함됐으며, 별도 phase marker/faulthandler 진단에서 main 종료 1.344초 후 probe 대기만 2.031초를 확인했다. listener fd 폐쇄 직접 확인과 probe timeout 0.3초를 추가해 검증 경계를 유한하게 만들었다. stderr/handler shutdown의 5초·9초 회귀 제한은 완화하지 않았다. 진행하던 전체 초회 실행은 중단/보존하고 MySQL 보조 서버·연결 잔여 부재를 확인한 뒤 새 final 경로에서 실행한다. 초기 timeout/부분 실행은 최종 PASS 근거로 사용하지 않는다.

- 첫 전체 final 실행은 6,507 PASS / 기존 26 skipped / 1 failure, 2,330.92초였다. 기존 Worker 실제 MySQL `normal_t1`의 단일 final record/provider 호출 검사는 통과했고 `recovered_at is None`만 실패했다. 해당 file은 단독 실제 MySQL 6 PASS(12.32초), nested 591개 acceptance/gate에서는 통과했다. 정상 T1 뒤 recovery=False finalize와 0.05초 주기 recovery=True reconciliation이 경합할 수 있는 기존 코드 경로를 확인했지만 실패 원인을 단정하거나 Worker 의미를 수정하지 않는다. 실패 보고서는 보존하고 gate 성공으로 처리하지 않으며, 소스 불변인 전체 재실행으로 최종 evidence를 확인한다. RT-07 Owner 재현/판단 대상이며 RT-08(a) 수정과의 관련성은 확인되지 않았다.

### 재리뷰 수정본 최종 직접 검증 / 미통과 항목

- 신규 subprocess/종료/정책 41 PASS; RT-08(a) targeted 90 PASS; 실제 MySQL health 5 tests / 필수 identity 6 / phase 15 PASS, MySQL skip/xfail 0. API/common 최종 unit 회귀 3,930 PASS(377 MySQL deselected). 검증 주체는 구현자다.
- 전체 첫 실행: 6,507 PASS / 기존 26 skipped / 1 Worker normal_t1 recovered_at assertion failure(2,330.92초). 같은 Worker file 단독 실제 MySQL 6 PASS. reviewer 소스 검토는 주기 recovery=True hook과 post-T1 recovery=False 경합을 허용하는 기존 경로 및 Worker/usage/test의 HEAD 대비 불변을 확인했다. 실패 trace에 승자 정보가 없으므로 원인/RT-08 관련성을 단정하지 않는다.
- 전체 두 번째 실행: 6,507 PASS / 기존 26 skipped / 1 nested migration gate failure(2,400.88초). 첫 Worker failure는 통과했고, 실제 MySQL child의 기존 900초 제한에서 TimeoutExpired가 발생했다. timeout이나 mandatory collection/skip/xfail 조건을 완화하지 않았다. 두 full report 각각 MySQL 596개 수집 / skip 0 / xfail 0 / call failure 1이며 최종 JSON/JUnit gate는 둘 다 올바르게 거부했다. **전체 pytest 및 전체 MySQL gate PASS는 미달이다.**
- 첫 전체에 포함된 최신 nested 실제 MySQL 보고서는 591 tests / skip 0 / xfail 0 / failure 0로 JSON/JUnit gate PASS. 필수 parameter 누락 mutation 3,066개(API 42 포함) 모두 거부. 이 유효 보고서로 별도 API 6 identity × 10 layer = 60 evidence 누락 mutation을 모두 거부했으며 실패 full report를 변조하거나 합성하지 않았다.
- boundary PASS(위반 0), Contract fixture PASS(문서 62/JSON 26/의미 104), workflow actionlint/YAML/bash -n/ShellCheck PASS(5 workflow/5 run step, pyflakes disabled), git diff --check 및 신규 파일 whitespace 검사를 최종 확인한다.
- 최종 DB 정리: 검증된 작업 소유 MySQL 8.4.7 / port 13339 / datadir `/tmp/rt08a-rereview-fixes-20261014/data/`에서 남은 schema 3개를 제거하고 계정/connection(시스템 daemon 제외)/schema 각각 0을 확인했다. SHUTDOWN의 process 소멸은 pid 파일 삭제보다 늦어 첫 확인은 실패했고, 종료 완료 후 재검사에서 Linux process/port 및 보조 서버/RO mount 디렉터리 잔여 0, Windows 관련 process 0 / test port 폐쇄를 확인했다. 테스트 thread/handler는 종료한 소유 process와 정상 drain/once-only cleanup 회귀 범위에서 정리됐다.
- 보호된 기존 파일 1,069개와 테스트 소스 21개 해시, HEAD/branch/index 불변을 최종 확인한다. staging/commit/push/PR 생성 없음. RT-08 IN_PROGRESS / `Refs #295 (RT-08(a))` / PR/SHA pending 유지.
- 검증 자료: `.codex-scratch/rt08a-rereview-fixes-20261014/`의 `review-summary.md`, `changed-files.md`, `review.diff`, RED/GREEN별 txt/exit, `subprocess-verified.xml`, `targeted.json/xml`, `api-common-verified.xml`, `full-final.json/xml`, `full-verified.json/xml`, 두 실패 gate 기록, `nested-gate.txt`, `nested-evidence-mutations.json`, `cleanup-db.json`, `cleanup-wsl-final.txt`, `cleanup-processes.json`, `final-integrity.json`. 실패/부분 evidence는 보존하며 성공 근거에서 제외한다.

### Owner 확인 / 선택지와 영향 범위

- 이번 세 finding 및 리뷰 보완 소스의 내부 재리뷰는 actionable blocker 없음이었다. 외부 독립 재리뷰/Owner acceptance/remote CI 승인 또는 전체 검증 PASS를 뜻하지 않는다.
- RT-07 normal-T1 attribution: (A) 현재 의미/검증 assertions를 유지하고 테스트 scheduling을 제어해 normal-T1 경로를 결정적으로 검증하는 별도 test-only 작업, (B) background/normal winner의 recovered_at 의미와 runtime ordering을 Owner가 명시하는 별도 RT-07 작업을 구분한다. (B)는 tracker attribution/metrics 의미와 테스트/문서 영향이 있어 이번 RT-08(a)에서 변경하지 않았다. 재실행 통과가 경합을 해결했다는 의미도 아니다.
- nested 900초 timeout은 현재 환경/성능 원인 재현과 Linux CI 실행 확인이 필요하다. 기존 limit/gate를 유지한 환경 조정과, gate 실행 구조 변경을 검토하는 작업의 영향 범위를 구분해야 한다. 검증 유실·skip/xfail·부분 수집 허용은 선택지로 제시하지 않는다.
- 남은 검증 실패를 해결한 전체/전체 gate 재검증 전 merge 가능 판정을 하지 않는다. 수정본은 원 요청대로 독립 재리뷰 가능한 unstaged 상태이며 native I/O 강제 취소와 포화 시 telemetry 유실, RT-08(b/c/d)/RT-11/auth/CORS/TLS 후속 범위는 유지한다.

### 남은 위험

- Python native filesystem/socket 또는 logger code는 강제 취소할 수 없다. shutdown 뒤에도 최장 probe/sink call이 daemon에서 늦게 반환할 수 있고 Engine.dispose는 checked-out 연결을 강제로 닫지 않는다. 정상/장애 acceptance의 schema·계정·connection·process·port 정리 결과와 구분한다.
- 포화/blocked sink에서 일부 event는 유실된다. full metrics exporter와 과부하 운영 관측은 RT-12 이후이며 새 availability/budget 정책을 이 작업에서 정하지 않는다.
- 설치된 Starlette TestClient가 httpx 호환 경로의 deprecation warning을 내지만 테스트 실패가 아니다. Linux remote CI 실행 시간 및 Docker/sudo namespace 권한은 local PASS로 확정하지 않는다.
- RT-08은 (b) cases/view, (c) commands/enqueue, (d) 중단 배선이 남아 IN_PROGRESS다. media/auth/CORS/TLS, 새 Case/Search surface는 이번 범위 밖이다. staging·commit·push·PR 생성 없이 pending 상태로 남긴다.

---

## 2026-10-15 RT-08(a) 실패 조사 및 중단 검증 재개

RT-08은 `IN_PROGRESS`, 연결은 `Refs #295 (RT-08(a))`, PR 번호와 merge SHA는 `pending`이다. 이전 절의 실패/부분 실행 및 독립 리뷰 기록은 당시 증거로 보존한다. 아래는 구현자의 추가 조사와 직접 실행이며, Owner 승인·외부 독립 재리뷰·원격 CI 판정과 구분한다.

### 이전 Worker / nested 조사 — 최초 사건과 새 재현 구분

- 첫 Worker 실패 node는 `tests/worker/test_usage_reconciliation_worker_mysql.py::test_normal_t1_finalizes_from_committed_produced_without_third_search_call`, 직전은 sweep의 `test_ordinary_hook_exception_isolated_in_startup_and_next_periodic_pass`였다. `recovered_at is None` 기대에 실제 `2026-10-14 12:21:23.090831`이 나왔다. 당시 started_at/heartbeat_at/ended_at/NOW(6)/session timezone/schema UUID/transaction·connection 상태는 원본 stdout/JSON/JUnit에 없고 삭제된 schema에서 복원할 수 없다. **최초 사건의 정확한 winning transaction과 근본 원인은 미확정이다.**
- 단독, 직전 순서, fresh MySQL/schema 반복 이후 별도 실제 DB Event 순서 재현으로 periodic recovery=True가 post-T1 recovery=False보다 먼저 finalize하는 `recovered_at` assertion RED를 확인했다. HEAD Worker/logging 코드 대조도 같은 RED다. 자연 반복에서는 handler의 전역 pool checkedout==0 assertion이 concurrent sweep connection 때문에 실패하고, Worker가 이를 terminal failure로 처리한 뒤 stop에 도달하지 않아 idle을 계속하는 별도 결함을 관측했다. live row/stack/후속 exception trace를 보존했다.
- 확인된 테스트 결함만 수정했다: normal-T1 테스트는 실제 startup/DB/T1/기존 assertions를 유지하며 periodic wait를 cleanup까지 대기시키고 handler stop을 finally에 둔다. 직전+전체 reconciliation file 7 PASS, 별도 fresh instance/schema 10회 PASS다. Worker/usage/jobs 제품 코드는 HEAD 대비 불변이고 handler/formatter/context/event helper 7개 AST도 같다. 이 RED→GREEN은 정상 T1 경로의 결정적 검증이며, 최초 자연 사건을 소급 확정하거나 recovery attribution 의미를 바꾼 것이 아니다.
- 최초 nested timeout은 child 마지막 node/stack/실행 개수/완성 JSON·JUnit/당시 migration 횟수가 미확보다. parent의 60초 faulthandler는 900초 순간 stack으로 취급하지 않는다. 기존 child fatal-hook cleanup 파일은 첫 성공에서 약678초, 두 번째에서 약854초 뒤 작성됐고 thread/connection/dispose 정리를 기록한다. 이 filesystem 단서는 모든 node의 마지막 완료 기록이 아니다. **최초 timeout의 정확한 부하·근본 원인은 미확정이다.**
- 새 disk MySQL 대조는 같은591개 수집 중518개 call을 완료한 채900초에 실패했다. 다음 sweep fatal-hook setup/migration을 진행했고 완료 upgrade_all480회/480.727초를 기록했다. 해당 새 실행은 interpreter shutdown 단계가 아니었다. 실제 MySQL8.4.7의 별도 tmpfs 대조에서는 child591 PASS/약650초, parent gate/누락 검사 PASS/820.47초였다. flush_commit1/sync_binlog1은 유지했고 실제 flush_method disk O_DIRECT vs tmpfs fsync, port/datadir/새 instance 및 idle disk instance 차이를 명시했다. migration5회 평균0.995초 vs0.458초, 공통300번째 node 완료455.722초 vs305.754초는 로컬 환경/storage 비용 기여를 지지하며 최초 사건의 부하를 증명하지 않는다. 900초·workflow20분·필수 inventory를 변경하지 않았다.
- 검증 주체: 위 직접 재현/실행은 구현자. 읽기 전용 내부 reviewer는 test-only isolation/cleanup과 인과 한계를 검토해 source blocker를 발견하지 못했으나 최종 full/gate/cleanup 승인 또는 Owner 판정이 아니다. 자료는 `.codex-scratch/rt08a-failure-investigation-20261014/`의 original-evidence/timeline, investigation.md, RED/GREEN별 txt/XML/JSON, PID별 trace/stack, migration/checkpoint 대조다.

### 남은 clean API/common 실패 조사

- 원본 api-common-clean은3928 PASS/2 failure/377 MySQL deselected,15819.10초였다. BaseException server-failure subprocess call7395.117초, 다음 once-only composition cleanup teardown8102.51초, 후속 KeyboardInterrupt cleanup subprocess call5.044초를 보존했다. 두 killed child stdout/stderr는 비어 있었고 당시 내부 phase/child stack은 없다.
- Windows System/Kernel-Power 원문에서23:15:22 Lid 대기 진입→01:18:34 전환의 약7392초 구간과, 이어03:33:45 Lid 복귀까지의 대기 구간을 확보했다. 수시간 call/teardown에는 실제 시스템 대기가 개입했다. 누적 JUnit으로 재구성한 node 시각은 inter-test overhead를 제외한 근사다. 원본 두 child의 정확한 내부 정지 위치와 각각의 timeout 직접 원인은 미확정으로 남기며, 단순 재실행 PASS로 해결 판정을 하지 않는다.
- 원본 직전 순서7개 관측은7 PASS/12.45초, 더 앞선 잔여를 포함한 첫74개 동일 순서는74 PASS/46.21초다. 별도 scratch plugin은 같은5초 제한에서 parent/child file stack, import/main/atexit marker, phase별 thread/handler/clock 및 child PID를 기록했다. 관련 call/teardown 뒤 MainThread만 남았고 관측 child4개/9개 모두 종료했다. 새 handler 누적이나 부모 reader/runtime thread 잔여는 관측되지 않았다. 정상 service/pytest handler의 process 종료 전 존재를 임의로 제거하거나 모두0이라고 취급하지 않는다.
- 두 failing child는 real create_app/uvicorn.run을 가짜로 대체하므로 real DB/readiness/ApiEvents를 생성하지 않으며 server-failure의 foreign handler는 NullHandler다. 기존 thread가 Windows 새 interpreter에 그대로 이어지는 구조가 아니다. 잔여 자원 인과나 제품 cleanup 결함을 재현하지 못해 이번 재개에서 제품·테스트를 수정하지 않았다. 최초 composition stalled-write의 별도5초 timeout도 이전 진단3회 PASS만으로 원인 확정된 것이 아니며 보존한다.
- 검증 controller는 실행 thread의 idle 대기 방지 요청을 finally에서 복원하고 wall/QueryUnbiasedInterruptTime을 함께 기록한다. 전역 전원 정책이나 테스트 deadline을 변경하지 않는다. QueryUnbiasedInterruptTime은 절전 시간을 제외한다([Microsoft 공식 설명](https://learn.microsoft.com/en-us/windows/win32/sysinfo/interrupt-time)). 실행 요청은 사용자의 lid/power sleep을 차단하는 기능이 아니다([Microsoft 공식 API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate)).
- source22개 frozen hash를 확인해 이미 완료한 process safety41 PASS/targeted90 PASS를 재사용하고 반복하지 않았다. 새 API/common3930 PASS/377 deselected(364.13초), 실제 MySQL health5 PASS/필수6identity·15phase/skip·xfail0(22.16초)다. controller wall/active는 각각369.9438초/369.9438초,26.5862초/26.5862초로 대기 차이가 없다. 기존 유효 nested591JSON/JUnit gate 재검증 및60 API evidence 누락 거부 PASS다.
- 원본/새 직접 실행 자료는 `.codex-scratch/rt08a-resume-validation-20261015/`의 original-clean-evidence, original-power-events 원문, sequence-observation-summary, reused-evidence, 각 txt/XML/JSON/timing, investigation.md에 분리했다. 최초 Worker/nested/child 내부 phase 미확정 위험을 유지하며 병합 가능 판정을 하지 않는다.

### 최종 직접 검증 및 정리 — 2026-10-15

| 검증 | 결과 | 근거/구분 |
| --- | --- | --- |
| process safety / RT-08(a) targeted | 41 / 90 PASS, exit0 | 이전 동일 source의 subprocess-clean/targeted-clean 보고서 재사용; source22 hash 불변으로 반복하지 않음 |
| 최소 순서 / 원본 prefix | 7 / 74 PASS | 새 file stack·child marker·thread/handler/PID 관측, timeout5초 유지 |
| API/common | 3,930 PASS / 377 MySQL deselected | 새 api-common-final,364.13초; 최초 실패 보고서 보존 |
| 실제 MySQL health | 5 tests / 6 mandatory identities / 15 phases PASS | 새 health-final,22.16초; skip/xfail/failure0 |
| 전체 pytest | 6,508 PASS / 기존 영상 opt-in26 skipped / failure·error0 | 새 full-final,2,075.35초; controller wall/active2,084.149843초 일치, 전원 요청 복원 |
| 전체 MySQL JSON/JUnit gate | 596 collected=selected PASS, skip/xfail/failure0 | full-gate/full-counts; mandatory inventory·3phase·JUnit pair 누락 허용 없음 |
| 전체 내 nested child / gate | 591 PASS, skip/xfail/failure0,JUnit670.137초 | 이번 full의 child JSON/JUnit,900초 정책 유지 |
| evidence 누락 | parameter3,066(API42 포함) / 별도 API60 모두 거부 | 이번 full nested의 parameter-mutations 및 full-omissions; 이전 유효 nested 재검증60도 별도 보존 |
| boundary / Contract / workflow | 위반0 / 62·26·104 PASS / 5 workflows·5 run steps PASS | 새 직접 정적 검사; actionlint/YAML/bash-n/ShellCheck,pyflakes disabled; workflow20분 불변 |

- 최종 schema/account/connection 정리는 작업 소유 MySQL8.4.7/port13341/datadir `/dev/shm/rt08a-failure-investigation-memory-20261014/data/`를 확인한 뒤 수행했다. 마지막 test schema1개 제거, 남은 test schema/계정/다른 connection(시스템 daemon 제외)0. SHUTDOWN 뒤 실제 process/port13340·13341/보조 server·RO mount 잔여0을 확인하고 tmpfs를 회수했다. 소유 Windows child/process 잔여0으로 종료 process의 thread/handler도 남지 않았다. source22 hash와 보호 파일1,069개의 전체 inventory/hash, 원본 실패 artifact, HEAD·branch·index 불변 및 diff/신규 Python whitespace PASS를 마지막 integrity 자료로 확인했다. 재개 시간대의 Kernel-Power standby 전환 기록은0이었다.
- 이번 재개는 제품·테스트 수정이 없으며 source를 고정한 채 남은 순차 검증을 완료했다. 기존 Worker test-only scheduling/stop 수정과 세 API review finding 수정은 유지한다. Contract/Accepted Decision/Baseline 의미·HTTP status/body·Case/Search 의무·900초/20분 정책 변화는 없다. RT-08 IN_PROGRESS / `Refs #295 (RT-08(a))` / PR/SHA pending, staging·commit·push·PR 생성 없음.
- Owner 확인: 최초 Worker/nested와 killed child의 내부 phase 증거 공백은 정확한 원인 미확정으로 남긴다. 이번 Windows full34분35초는 Linux remoteCI20분 준수의 증거가 아니며 원격 CI는 미실행이다. 정책 변경 필요성을 단정하거나 limit을 올리지 않았다. 새 전체/gate PASS와 독립 재리뷰 가능한 artifact를 제공하지만 병합 가능·Owner acceptance·외부 재리뷰/CI 승인 판정은 하지 않는다. RT-08(b/c/d),RT-11,auth/CORS/TLS 및 새 Case/Search surface는 후속 범위다.

---

## RT-09 — 첫 비동기 E2E (integration acceptance)

Status: NOT_STARTED · Issue: #296 · Audit: B

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## RT-10 — Worker composition root: 실제 kind handler 등록 · cross-process E2E

Status: NOT_STARTED · Issue: #297 · Audit: B

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## RT-11 — Media HTTP: `POST /sources` · frames · assets

Status: NOT_STARTED · Issue: #298 · Audit: B

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## RT-12 — 운영 위생: cleanup · 관측 집계

Status: NOT_STARTED · Issue: #299 · Audit: C

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## RT-13 — Docker / Compose local runtime

Status: NOT_STARTED · Issue: #300 · Audit: C

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## RT-14 — EC2 배포 · 운영 (Issue는 RT-13 착수 때 생성)

Status: NOT_STARTED · Issue: — (RT-13 착수 때 생성) · Audit: C

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## RT-15 — CI 품질 gate · Runtime import 경계

Status: NOT_STARTED · Issue: #301 · Audit: C

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## REC-1 — recording 영속화 · HTTP/Worker용 capability (recording Owner)

Status: NOT_STARTED · Issue: #302 · Audit: B (Runtime이 소비하는 surface만)

recording Owner(정철원) 작업이다. 여기에는 Runtime이 소비하는 surface(RT-10 · RT-11 · RT-12 입력)만 기록하고, recording 내부 결정은 `docs/modules/recording/`이 원문이다.

| PR | 내용 | Merge SHA |
| --- | --- | --- |
| — | — | — |

### 구현 결과

—

### Plan 대비 변경

—

### 새 implementation detail

—

### Owner 확인 포인트

—

### Verification

—

### 남은 위험

—

---

## Change log

| 날짜 | 변경 | 기준 |
| --- | --- | --- |
| 2026-10-06 | 생성 — Plan §12 Single Implementer + Deferred Owner Review 실행 모델의 기록 문서. RT-01 ~ RT-15 · REC-1 절 · implementation detail 색인 · Baseline revisit · Owner 확인 · Milestone audit 표 | PR #305 |
| 2026-10-06 | 사용 규칙에 Plan §12.8 체크리스트 pointer · `DONE` = Issue close 연결 | PR #307 |

## 2026-10-15 RT-08(a) 두 번째 독립 재리뷰 후속 조사

- 상태는 `IN_PROGRESS`, 연결은 `Refs #295 (RT-08(a))`, PR 번호·merge SHA는 `pending`이다. 기존 GREEN 이력은 보존한다. 이후 독립 재리뷰에서 composition stalled-write 5초 timeout과 startup KeyboardInterrupt 코드 0이 다시 보고되었으므로 기존 GREEN을 이번 수정의 검증으로 대체 사용하지 않는다.
- 검증 주체: 독립 재리뷰의 재현 횟수·결과는 사용자 제공 증거이며, 아래 직접 관측·RED/GREEN은 현재 implementer가 별도로 실행한다. `receiving-code-review` → `systematic-debugging` → TDD 순서로 진행했다.
- P1 직접 관측: `.codex-scratch/rt08a-second-review-20261015/timed-8.{json,phases,stack}`에서 stdout `write_entered`, stderr 공백의 5초 timeout을 재현했다. 2초 stack은 consumer의 실제 sink `write()` → `Event.wait()`와 main의 `ApiEvents.close()` → `Thread.join(timeout=1)`이다. child 기준 import 완료 1.741796초, close 진입 1.745496초, 반환 2.749820초, 예외 전파 2.750438초, atexit marker 2.751222초를 기록했다. parent Popen 생성 2.039605초와 communicate 약 4.999108초를 별도 측정했다. 두 clock의 원점은 다르며 이 숫자를 직접 빼서 interpreter startup/최종 종료 시간을 확정하지 않는다. 이 재현에서는 close가 반환했고 atexit에도 도달했으므로 무기한 logging shutdown 교착의 증거로 해석하지 않는다. 확인한 불필요한 sink 의존은 확정된 composition 실패에 정상 종료용 1초 drain을 추가하는 경로이다. 독립 재리뷰 실행 자체의 정확한 시간 분해는 확보하지 못했다.
- P1 선택지 검토(제품 수정 전): (a) 5초 테스트 또는 CI 정책 확대는 실패 전파의 불필요한 대기를 남기므로 선택하지 않는다. (b) composition 진단 자체 삭제는 정상 sink의 진단 기회까지 없애므로 선택하지 않는다. (c) API 소유 event queue는 닫되 **확정된 composition 실패에서만 drain을 기다리지 않는 방식**을 선택한다. 정상 lifespan/CLI cleanup의 1초 drain·correlation·fatal handoff는 그대로 둔다. 이 실패 경로의 진단은 유실될 수 있지만 startup 코드 1보다 우선하지 않는다. daemon/join만으로 shutdown 교착을 해결했다고 주장하지 않으며, 기존 API handler의 shutdown-lock 분리와 unbuffered 기본 출력 경계는 유지한다. logging 전역 registry·외부 handler·`os._exit()`는 사용하지 않는다.
- P2 직접 RED: `p2-red.{txt,xml,exit}`에서 실제 bootstrap/composition KeyboardInterrupt 각각 기대 1/실제 0으로 2 FAIL, serving interrupt 기대 0으로 1 PASS를 확인했다. 원인은 startup과 uvicorn 실행을 하나의 `except KeyboardInterrupt`가 성공으로 처리하는 것이다. 실제 API engine의 부분 생성 보상, 전체 composition disposal, signal 및 외부 logger handler 복원을 함께 검사하는 subprocess 회귀를 추가했다. 서버 호출에 진입했는지를 분리한 최소 수정 뒤 `p2-green` 3 PASS를 확인했다.
- 최초 Worker `recovered_at`, 최초 nested 900초 timeout, 수시간 subprocess 지연의 **정확한 근본 원인은 계속 미확정**이다. 이번 P1 시간 관측을 그 사건들의 원인으로 소급하지 않는다. 900초 nested gate, workflow 20분, 필수 evidence inventory, Contract·Accepted Decision·Baseline 의미를 변경하지 않는다.

### 이번 수정의 직접 RED → GREEN

| 대상 | 수정 전 RED | 최소 수정 후 직접 결과 |
| --- | --- | --- |
| P1 composition + 실제 stalled write | `p1-red.{txt,xml,exit}` 1 FAIL: 5초 timeout, stdout `write_entered`, stderr 공백. 실제 write 진입을 Event handshake로 보장했으며 release는 주지 않았다. 진단 관측 `timed-8`도 같은 signature의 timeout이다. | `p1-green` 1 PASS. `p1-repeat.{json,txt,exit}` 같은 5초 제한의 단독 12/12 PASS. composition 실패에서만 `events.close(drain=False)`; 정상 close의 1초 drain은 유지. |
| P2 startup / serving KeyboardInterrupt 구분 | `p2-red` bootstrap·composition 기대 1/실제 0의 2 FAIL, server 기대 0의 1 PASS | `p2-green` 3 PASS. 서버 호출 진입 전 KeyboardInterrupt는 1, 호출 중 KeyboardInterrupt는 기존 0. 실제 부분 생성 engine 보상·전체 disposal·signals·외부 handler 보존·stderr 비노출을 함께 확인. |

- 기존 `run_child` 5초 제한은 바꾸지 않았다. 테스트를 제외하거나 기존 assertion을 제거하지 않았고, P1 실제 sink 진입 보장과 P2 새 subprocess 3개를 추가했다. 수정 전 순서 관측의 첫 실행은 기본 Windows 임시 폴더 접근 거부로 22 PASS/19 fixture ERROR였으므로 GREEN으로 사용하지 않았다. 새 workspace basetemp의 기존 41개 관측 순서는 41 PASS였다. 이것과 별개로 수정 후 기존 41개 + 신규 3개의 **전체 44개 순서**가 44 PASS(60.81초)이다.
- 실행 코드 고정 후 `targeted-final` 93 PASS(89.42초), `api-common-final` 3933 PASS / MySQL 377 deselected(339.76초)이다. targeted의 실제 MySQL 8.4.7 health는 5 tests / 필수 6 identities / 15 phases, skip·xfail·failure 0이다. 제품·테스트·설정 22개의 고정 hash와 각 실행 stdout·JUnit·JSON·전원 요청 복원 timing을 `.codex-scratch/rt08a-second-review-20261015/`에 보존했다. MySQL 전체 gate와 전체 pytest 결과는 아직 대기 중이며 이 단계의 통과를 미리 기록하지 않는다.

### 첫 전체 재검증의 추가 실패와 별도 정리 helper 수정

- 위 대기 기록 이후 `mysql-final`은 실제 MySQL 596 PASS / MySQL 대상 skip·xfail·failure 0, JSON/JUnit gate PASS였다. MySQL 외 선택 의존성 collection skip 4개를 MySQL skip으로 계산하지 않는다. nested child는 591 PASS / 668.539초, 누락 mutation 3066건(API 42건) 모두 거부했다. 그러나 `full-final`은 **6510 PASS / 1 FAIL / 기존 optional 26 SKIP**, 1021.67초였다. 신규 실패 node는 `tests/api/test_health_mysql.py::test_ready_when_actual_mysql_server_is_shutdown`이고 `/health/ready` 503 검사는 통과했으나 `owned_mysql()` 정리의 단일 `connect_ex()!=0` assertion이 실패했다. 전체 JSON/JUnit gate가 이를 거부하는 것도 직접 확인했다. 이 실패를 GREEN으로 기록하지 않으며 `first-full-failure-hashes.json`으로 원본 6개 artifact를 보존했다.
- 원인 조사: 진단 plugin의 같은 health 5개 순서 15회는 모두 PASS였다(`owned-repeats`, 각 `owned-order-*-tcp.json`). 이 반복에서 실패가 자연 재현되지 않았다. 최초 실패 port·local/peer 주소·그 순간 Linux listener/PID는 원본에 없어 그 사건의 정확한 연결 원인을 복원할 수 없다. 종료 시 observer에는 MainThread만 있었고 API event thread 잔여는 없었다. P1/P2 제품 수정이 이 cleanup TCP 검사로 이어지는 직접 data flow는 없으며, 상대 실행 시간 변화의 영향까지 배제했다는 의미는 아니다.
- 별도 **확정된 검사 결함**: 실제 Windows socket을 listener 없이 자기 주소에 bind/connect하면 local=peer, `connect_ex()==0`으로 연결된다. 기존 1회 TCP 성공은 서버 잔존의 충분한 증거가 아니다. 실제 native socket으로 동일한 유효 source-port 후보를 강제한 회귀에서 기존 검사를 그대로 추출한 helper가 `owned MySQL port remains open` assertion RED였다(`port-red-confirmed`: 1 FAIL/1 PASS). 최초 test double의 미바인딩 `getsockname()` WinError10022는 관측 코드 오류로 별도 보존했고 RED 근거로 사용하지 않는다. 새 회귀는 connect 결과를 mock하지 않으며 MySQL acceptance를 대체하지 않는다.
- 최소 수정: `tests/api/owned_mysql.py`의 정리 probe가 source port를 명시적으로 선택하고, destination과 같으면 첫 후보를 reserve한 채 다른 source를 선택한다. **1초 socket 제한과 열린 listener 거부 assertion을 유지**하고 polling·timeout 증가·조건 완화 없이 self-connect 가능성만 제거했다. `tests/api/test_owned_mysql.py`에서 닫힌 port의 source 충돌 및 실제 listener 거부 2 PASS(`port-green`)를 확인했다. 이것은 확인된 test helper 결함의 RED→GREEN이며, 정보가 없는 최초 전체 실패의 정확한 원인을 소급 확정하는 주장이 아니다. 최초 Worker·nested·수시간 지연 3건의 미확정 구분도 유지한다.
- 제품 API source의 두 finding 수정은 유지한다. 테스트 helper 변경 후에는 새 source 고정본(v2)과 별도 `*-clean` 이름으로 검증 순서를 다시 실행한다. 이전 source hash·실패 보고서·GREEN 기록은 덮어쓰지 않는다. 전체 pytest 실패 0을 아직 달성했다고 판정하지 않는다.

### v2 고정본 최종 직접 검증 및 재리뷰 인계

검증 주체는 현재 implementer다. `verification-v2-results.json`의 순차 controller는 각 단계 전 고정 hash를 검사하고 실패 시 다음 단계로 넘어가지 않는다. 변경 source·테스트·설정 **23개**, 전체 검증 tree **445개**를 고정한 뒤 아래를 직접 실행했다. 이전 GREEN 및 첫 `full-final` 실패와 별개인 새 결과다.

| 검증 | v2 직접 실행 결과 |
| --- | --- |
| composition stalled-write 단독 | 동일 5초 제한, 실제 write 진입·release 없음, **12/12 PASS** (`p1-repeat-v2`) |
| process safety 전체 순서 | 기존 41개 + startup 구분 3개, **44 PASS**, 39.95초 |
| RT-08(a) targeted | 기존 90개 + startup 3개 + native TCP 검사 2개, **95 PASS**, 58.34초 |
| API/common·structured logging | **3935 PASS**, MySQL 377 deselected, 211.40초 |
| 실제 MySQL health | MySQL 8.4.7, 5 tests / 필수 6 identities / 15 phases, skip·xfail·failure 0 |
| 실제 MySQL 전체 acceptance | **596 PASS**, MySQL skip·xfail·failure 0, strict JSON/JUnit gate PASS, 906.89초. 별도 optional collection skip 4개는 MySQL 대상이 아니다. |
| 전체 pytest | **6513 PASS / 기존 optional 26 SKIP / failure·error 0**, 1205.34초. 이전 정상 실행과 skip identity 26개가 동일하다. |
| 전체 실행의 MySQL JSON/JUnit | 596 collected = selected, 1788 phases, skip·xfail·failure 0, strict gate PASS |
| 전체 실행 안의 nested child | **591 PASS**, 368.665초, JSON/JUnit PASS, skip·xfail·failure 0. 별도 MySQL acceptance의 child는 591 PASS / 366.440초. 900초 제한 유지. |
| evidence 누락 거부 | 각 nested parameter mutation **3066건(API 42건)** 모두 거부. 최종 전체·nested 실제 보고서에 API 6 identities × 10 layers = **각 60건** 누락도 모두 거부. 필수 inventory 유지. |
| boundary / Contract fixture | 경계 위반 0 / 문서 62·JSON 26·의미 fixture 104 검사 PASS |
| workflow / diff | actionlint·YAML 정책·bash -n·ShellCheck, 5 workflows / 5 run steps PASS (pyflakes 미실행). `git diff --check`의 Log EOF 빈 줄 1건 정리 후 PASS. 제품·테스트 추가 변경 없음. |

- 자원: 전체 pytest session 종료 직전 Python thread는 MainThread뿐이며 API logging/readiness thread 잔여는 없었다. 당시 API handler 1개는 정상 프로세스 logging 소유로 남아 있었고, interpreter 자체가 코드 0으로 종료했다. API가 global/제3자 handler를 임의 제거·종료하지 않았다. 종료 후 Windows 관련 Python process 0, 테스트 Windows listener 0, Linux의 실제 소유 MySQL PID·보조 서버·listener·보조 디렉터리 0을 별도로 확인했다. DB 정리 전 다른 connection 0, 정리 후 테스트 schema·계정 0이며 정확한 port 13342·datadir를 확인한 해당 서버만 SHUTDOWN했다. OS의 다른 서비스·계정은 변경하지 않았다.
- 정리 evidence 한계: SHUTDOWN 후 확인 시 `/dev/shm/rt08a-second-review-20261015`가 이미 소멸해 server/init log 복사는 실패했다(`cleanup-wsl` exit 1). 경로 소멸의 원인은 확인하지 못했다. 이를 숨기지 않고, 별도 `cleanup-wsl-final`에서 실제 PID·listener·경로 잔여 0을 확인해 exit 0으로 기록했다. stdout·JUnit·MySQL JSON·RED/GREEN·원본 실패 자료는 Windows workspace에 그대로 보존했다. Sandbox socket code 10013은 permission denial이므로 port 부재 증거로 쓰지 않았으며 native Windows listener와 Linux PID/ss 검사를 기준으로 삼았다.
- 불변: 보호된 기존 미추적 **1069개 파일의 path 집합·SHA 전부 동일**, 이전 조사 artifact **408개** 및 이번 첫 전체 실패 원본 **6개** SHA 동일, source 23개·검증 tree 445개 고정 hash 동일. `feature/runtime-api-skeleton-health` / HEAD `505e6ad2c95617569faad1b12a45fa48d3e41919`, index 변경 없음. 전체 변경 파일 **28개**와 전체 diff 및 이전 재리뷰 대비 code/test delta를 새 evidence 디렉터리에 제공한다. staging·commit·push·PR 생성은 하지 않았다.
- Plan 대비·새 implementation detail: 범위는 RT-08(a) 유지다. 확정된 composition 실패의 진단만 drain을 기다리지 않으며, 정상 종료 drain·correlation·queue saturation·sink 예외·thread 시작 실패·fatal handoff 정책은 유지한다. CLI는 startup KeyboardInterrupt 1과 server invocation KeyboardInterrupt 0을 구분하고, cleanup 실패·의도적 SystemExit·기타 BaseException의 기존 API 코드 1 정책은 유지한다. 추가 변경은 native TCP source/destination 충돌을 피하는 테스트 정리 helper와 실제 listener 거부 회귀다. HTTP status·envelope·Contract·Accepted Decision·Baseline 의미·Case/Search 의무 및 공개 surface는 변경하지 않았다.
- Owner 확인·남은 위험: terminal 진단 유실을 허용하는 fail-fast 경계, startup/server interrupt 경계, TCP 정리 검사의 실제 listener 거부를 검토할 수 있다. **최초 Worker recovered_at, 최초 nested 900초, 수시간 subprocess 지연의 정확한 근본 원인은 계속 미확정**이고, 이번 첫 전체 cleanup 실패의 실제 연결 원인도 당시 주소 자료가 없어 미확정이다. 확인된 native self-connect 검사 결함의 수정과 새 GREEN을 그 사건들의 원인 확정으로 소급하지 않는다.
- CI 정책: 이번 Windows 전체 실행은 **20분 05초**로 20분을 넘었다. Linux 원격 job의 20분 준수는 이번 로컬 결과로 확인할 수 없다. 선택지는 (1) 현재 20분 유지 후 실제 Linux CI에서 확인, (2) 초과가 확인되면 수집·필수 evidence를 유지하며 fixture/migration 비용을 별도 측정·개선, (3) 정책 변경이 필요한 경우 Owner에게 근거·CI 비용·timeout 영향을 제시한 별도 결정이다. 이번에는 workflow 20분·nested 900초·inventory를 변경하지 않았다.
- 인계: 수정본·전체 검증·원본 실패·불확실성을 갖춘 **독립 재리뷰 가능한 로컬 상태**다. 병합 승인·Owner 수락·원격 CI 통과를 판정하지 않는다. RT-08은 **IN_PROGRESS**, 연결 **Refs #295 (RT-08(a))**, PR 번호·merge SHA **pending**을 유지한다. RT-08(b)의 POST /cases·GET /view, (c)의 command/enqueue, (d)의 중단, RT-11의 sources/frames/assets, 인증·CORS·TLS는 후속 범위다.

## 2026-10-15 RT-08(a) 잔여 5초 timeout 단계 관측 후속 조사

- 독립 리뷰 입력(사용자 제공): stalled-write 단독 **11/12 PASS, 1 timeout**, 실패 child stdout·stderr 모두 공백. 후속 9회·단계 관측 3회·process 44개·targeted 95개 PASS도 함께 전달됐다. 이 수치는 아래 implementer 직접 실행과 구분하며, 이전 GREEN 이력을 삭제하거나 최초 실패가 해소됐다고 소급하지 않는다.
- 절차·범위: `systematic-debugging`으로 제품 변경 전에 source/hash·process 기준 상태를 보존하고 진단용 재현을 실행했다. **이번 조사에서 제품 코드 변경 없음**. `tests/api/process_probe.py`와 기존 stalled-write 회귀의 child source 공유·trigger 검사 1개만 보강했다. 기존 전체 child 5초 검사와 실제 handler write 무한 정지·release 없음·코드 1·stderr 공백·PRIVATE 비노출 assertion을 유지한다. 기존 process 44개/targeted 95개에 새 검사 1개가 추가돼 수집 기준은 **45개/96개**다.
- 관측 경계: child의 첫 실행 marker, 필수 imports 완료, logger/config 완료, ready, composition 직전, 실제 `write_entered`, SystemExit(1) 포착 직후, atexit 직전·callback을 기록한다. 각 marker와 parent spawn/수신/trigger/exit/timeout에 wall clock(ns)·Windows `QueryUnbiasedInterruptTime`(100ns)·PID를 저장한다. 첫 marker에도 최소 stdlib/clock 준비가 필요하므로 Python bootstrap·그 준비 이전의 정지 stack을 관측했다고 주장하지 않는다. Windows venv launcher PID와 실제 interpreter PID가 다름도 별도로 기록했다.
- 새 경계: parent는 child ready를 별도 **setup/import watchdog 5초** 안에 기다린 뒤 stdin GO를 보낸다. 제품 종료 deadline은 **GO write 직전부터 5초**이며, child ack나 관측 수신으로 재설정하지 않는다. setup/import 실패와 `product_exit_5s`를 구분한다. 정상 marker는 stdout 진단 채널, faulthandler stack은 별도 파일에 저장해 stderr 비노출 검사를 유지한다. deadline 후 DUMP/process 관측은 이미 확정된 FAIL을 PASS로 바꾸지 않는다. 실패한 새 child의 launcher/interpreter tree와 parent pipe reader를 정리하며 다른 process/logger를 종료하지 않는다. Windows 외에는 unbiased clock을 null로 표시하고 실제 wall clock을 유지한다.
- 직접 관측(implementer): 초기 진단 total **12/12**, ready/trigger **20/20**, 보강된 새 회귀 trigger **20/20**, 별도로 유지한 원래 total 검사 **12/12 PASS**. 관측된 trigger→exit 최대 **0.1740451초**, write→exit 최대 **0.1710454초**였다. 초기 spawn 시작→첫 marker 최대 **4.3247166초**, imports 구간 최대 **2.2968275초**는 서로 다른 실행에서의 최대값이므로 합산하지 않는다. 초기 실행 wall/active 차이 최대 약 **0.000002초**, 관측 시점까지 Kernel-Power 506/507 이벤트 0이었다. 이는 해당 실행들의 사실이며, 독립 리뷰의 빈 stdout timeout이 launch/import/scheduling 때문이었다는 확정 증거가 아니다.
- 관측 검사 음성 대조군: 테스트 child에만 실제 표준 StreamHandler를 사용해 실제 write에서 handler lock을 잡고 정지시킨 경우 **trigger 이후 5초 거부**를 확인했다. 당시 main `logging.shutdown → handler.acquire`, consumer 실제 write/Event.wait의 faulthandler stack과 process snapshot을 보존했다. 별도 import 전 Event.wait는 **setup watchdog 5초 거부**와 해당 대기 stack을 남겼다. 두 대조군은 관측 경계의 검출 검증이며, 현재 제품에서 자연 발생한 RED 또는 제품 수정 GREEN으로 포장하지 않는다.
- 다른 process: 시작 전부터 별도 독립 리뷰 pytest launcher/interpreter **PID 22152/22184**가 존재했다(시작 17:18:35). 명령·parent·CPU·thread 대기 상태를 읽기 전용으로 보존했다. 이들의 존재·대기와 이번 timeout 사이의 인과관계는 확인하지 못했으며 임의 종료하지 않았다. 현재 조사에서 실행한 child 및 서버와 소유 경계를 구분한다.
- 검증 중 추가 실패: 첫 고정본 process **45 PASS** 뒤 targeted에서 **95 PASS/1 FAIL**. node `tests/api/test_process_safety.py::test_actual_server_cleanup_failure_exit_and_listener_release`가 기존 total 5초 timeout(stdout·stderr 공백)이었다. 원본 stdout·JUnit·MySQL JSON·exit·timing·resource snapshot 6개 SHA를 별도 보존하고 검증을 중단해 조사했다. 종료 직전 parent Python thread는 MainThread뿐이었으나, 그 사실로 실패 child의 5초 시점 상태를 추정하지 않는다.
- 추가 실패의 같은 순서 관측: source나 5초 제한을 바꾸지 않고 외부 진단 plugin으로 **tests/api 전체 원래 순서 96 PASS**. 해당 실제 Uvicorn child의 imports→composition→bind/main loop→cleanup→CLI 반환→SystemExit/atexit, 코드 1·stdout/stderr 공백·signal/listener 검사를 관측했다. 최초 실패에는 당시 marker·stack이 없고 자연 재현하지 못했으므로 **그 추가 timeout의 정확한 원인도 미확정**이다. 단순 재실행 PASS를 해결로 판정하지 않는다.
- 판정: 사용자 제공 최초 1/12 timeout은 write 진입 전/후를 결정할 원본 phase/stack이 없어 **원인 미확정·병합 보류**를 유지한다. 최초 Worker recovered_at, 최초 nested 900초, 수시간 subprocess 지연, 이전 최초 TCP cleanup 사건의 정확한 근본 원인도 계속 미확정이다. timeout 증가·sleep 우회·검사 제외·필수 inventory 완화·제품 추측 수정은 하지 않았다. 후속 고정 소스 검증 결과와 정리는 아래에 추가한다.

### 후속 고정본 직접 검증·정리 결과

검증 주체는 현재 implementer다. 제품·테스트·설정 source **24개**, 전체 검증 tree **446개**를 hash로 고정해 각 실행 전 확인했다(Log 후속 기록 제외). 첫 targeted 실패와 그 원인 미확정 판정을 보존한 상태에서 같은 소스의 아래 최종 검증을 순차 실행했다. 별도 명시한 순서 관측 실행 외에는 phase 주입 plugin 없이 원래 pytest 검사를 실행했으며, 종료 시점 resource observer는 상태를 읽기만 한다.

| 직접 실행 | 결과 |
| --- | --- |
| 새 trigger 이후 stalled-write / 기존 total 검사 | **20/20 / 12/12 PASS**. 앞선 진단용 marker total 12회·trigger 20회와 별도 자료로 보존. |
| process-safety | **45 PASS**, 51.30초. 기존 44개 모두 유지 + 새 trigger 검사 1개. |
| RT-08(a) targeted 최종 | **96 PASS**, 63.78초. 같은 순서 진단 관측 실행도 96 PASS이나 최초 targeted 95 PASS/1 FAIL 원본은 별도 보존. |
| API/common·structured logging | **3936 PASS**, MySQL 377 deselected, 164.25초. |
| 실제 MySQL health | MySQL **8.4.7**, **5 tests / 6 필수 identities / 15 phases**, skip·xfail·failure 0. |
| 실제 MySQL 전체 acceptance | **596 PASS**, 784.79초, MySQL skip·xfail·failure 0, strict JSON/JUnit gate PASS. 별도 optional collection skip 4개는 MySQL 대상이 아니다. |
| 전체 pytest | **6514 PASS / 기존 optional 26 SKIP / failure·error 0**, stdout 기준 984.71초. optional skip identity 26개가 이전 검증과 동일하다. |
| 전체 MySQL / nested gate | **596 collected=selected / 1788 phases** 및 nested **591 collected=selected**, 모두 skip·xfail·failure 0, 두 JSON/JUnit PASS. 전체 안의 child **313.638초**, 별도 MySQL 실행의 child **384.419초**. |
| evidence 누락 거부 | 각 nested의 parameter mutation **3066건(API 42건)** 거부. 최종 전체·nested 실제 보고서에서 API 6 identities × 10 layers = **각 60건** 누락 거부. |
| boundary / Contract | 경계 위반 **0**, 문서 **62**·JSON **26**·의미 fixture **104** PASS. |
| workflow / diff | actionlint·YAML 정책·bash -n·ShellCheck **5 workflows / 5 run steps PASS**. pyflakes 미실행. `git diff --check` 및 추가 파일 whitespace 검사 PASS. |

- 자원 정리: 정확한 localhost **13343**, datadir `/dev/shm/rt08a-phase-boundary-20261015/data/`, 실제 Linux PID **418**을 대조했다. 서버·init log를 SHUTDOWN **전에** 보존한 뒤 다른 connection **0**, 남은 테스트 schema·계정 **0**을 확인하고 해당 서버만 종료했다. Linux PID·서버·listener·datadir·보조 MySQL/readonly 경로 **0**, 이번 실행 소유 Windows Python process·테스트 listener **0**을 독립 확인했다. unrelated MySQL 서비스와 별도 작업 process는 변경하지 않았다.
- thread/handler 관측: 최종 pytest 종료 직전 Python thread는 **MainThread뿐**이었다. API handler 1개는 당시 정상 logging owner 아래 존재했고 interpreter가 코드 0으로 종료했다. 이를 종료 전 handler 0이라고 표현하지 않는다. 종료 후 이번 실행의 process가 없어 그 소유 logging/readiness/probe thread·handler도 남지 않았다. global/제3자 handler를 임의 제거·종료하지 않았다.
- 별도 process 잔여: 시작 전부터 존재한 독립 리뷰 pytest **PID 22152/22184 두 개는 최종에도 그대로 존재**했고 CPU 수치는 기준 snapshot과 같았다. 이들이 현재 조사에서 새로 누출됐다는 증거는 없으며, 강제 종료하지 않았다. 따라서 이번 실행 소유 자원 0과 **호스트 전체 Python process 0은 구분**한다. 이들의 Python stack과 최초 timeout 간 인과관계는 확인하지 못했다.
- clock·관측 한계: 전체 조사 구간의 Kernel-Power **42/107/506/507**, Power-Troubleshooter **1** 이벤트 관측은 **0**이었다. OS scheduler ETW trace는 수집하지 않았으므로 process scheduling 지연을 배제하거나 원인으로 확정할 수 없다. 기존 total 검사는 원래의 `Popen` 반환 뒤 `communicate(timeout=5)` 의미를 유지하며 spawn 호출 시간은 따로 기록한다. 새 검사는 ready 수신 뒤 GO write 직전부터 제품 종료 5초를 측정한다. phase/관측 thread가 실행 timing에 영향을 줄 수 있어 관측 PASS를 무관측 실패의 원인 증명으로 쓰지 않는다.
- 불변·인계: 보호된 기존 미추적 **1069개 파일의 path·SHA 동일**, 이전 재리뷰 top-level artifact **365개**, 그 이전 evidence **408개**, 이전 첫 전체 실패 **6개**, 이번 첫 targeted 실패 **6개**의 SHA를 확인했다. 현재 조사에서 기존 파일 변경은 **테스트·Log 2개**, 추가는 **test helper 1개**뿐이며 모든 제품 source는 조사 시작 때와 같다. 전체 변경 **29개 파일**과 diff·manifest·직접 실행/원본 실패 자료는 `.codex-scratch/rt08a-phase-boundary-20261015/`에 제공한다. branch/HEAD/index는 유지하고 staging·commit·push·PR 생성은 하지 않았다.
- Owner 확인·남은 위험: trigger 이후 5초와 기존 total 경계를 모두 유지한 진단 설계, 실제 stalled write 및 interpreter 종료 검증, 첫 marker 이전의 blind window, 별도 리뷰 process 보존 범위를 확인할 수 있다. **최초 1/12 timeout과 이번 첫 targeted Uvicorn timeout의 정지 위치·근본 원인은 여전히 미확정이며 병합 보류**다. 이전 Worker recovered_at·nested 900초·수시간 지연·TCP cleanup 사건의 정확한 원인도 새 GREEN으로 소급 확정하지 않는다. 재리뷰 자료는 준비됐지만 병합 가능 판정은 하지 않는다.
- 정책·범위: 새 implementation detail은 테스트용 phase clock·ready/trigger·stack/process 관측과 소유 child 정리뿐이다. **제품 수정, Contract·Accepted Decision·Baseline 의미·HTTP status/envelope·Case/Search 의무 변경 없음**. 이번 Windows 전체는 약 **16분 25초**지만 원격 Linux CI의 20분 준수는 미검증이다. nested **900초**, workflow **20분**, 필수 inventory를 유지한다. **RT-08 IN_PROGRESS / Refs #295 (RT-08(a)) / PR·merge SHA pending** 유지. RT-08(b)의 cases/view, (c)의 command/enqueue, (d)의 중단, RT-11의 sources/frames/assets, 인증·CORS·TLS는 후속 범위다.

## 2026-10-16 RT-08(a) 독립 재리뷰 최종 후속 기록

- 독립 재리뷰 판정: **PASS / 현재 재현 가능한 병합 차단 문제 없음**. 사용자가 전달한 독립 재리뷰 결과를 반영해 앞선 병합 보류 이후의 판정을 추가한다. 기존 실패·조사·GREEN 이력과 원본 증거는 유지한다.
- 검증 주체·증거 구분: 아래 직접 통과는 독립 재리뷰에서 직접 실행한 결과이며, 전체 pytest·MySQL 전체·nested 결과는 보존 증거 대조다. **이번 Log 갱신 작업에서는 테스트를 재실행하지 않았다.**

| 증거 구분 | 검증 | 결과 |
| --- | --- | --- |
| 독립 재리뷰 직접 실행 | ready/trigger 이후 stalled-write | **20/20 PASS** |
| 독립 재리뷰 직접 실행 | 기존 total-process | **12/12 PASS** |
| 독립 재리뷰 직접 실행 | RT-08(a) targeted | **96 PASS** |
| 독립 재리뷰 직접 실행 | process-safety | **45 PASS** |
| 독립 재리뷰 직접 실행 | 실제 MySQL health | **5 tests · 6 identities · 15 phases PASS** |
| 보존 증거 대조 | 전체 pytest | **6514 PASS / 기존 optional 26 SKIP / 실패 0** |
| 보존 증거 대조 | 실제 MySQL 전체 / nested | **596 / 591 PASS**, MySQL skip·xfail·failure 0 |

- 비차단 위험: 최초 **1/12 timeout**과 추가 **Uvicorn timeout**은 정확한 정지 위치·근본 원인이 계속 **미확정**이다. 해결됐다고 단정하지 않고 비차단 위험으로 유지한다. 과거 실패 원본과 앞선 원인 미확정 기록도 그대로 보존한다.
- 관측·CI 한계: **첫 marker 이전 blind window**, phase/관측 thread의 **timing 영향 가능성**, **원격 CI 20분 실행시간 미확인**을 유지한다. 현재 재리뷰 PASS로 이 한계나 과거 사건의 원인을 소급 확정하지 않는다.
- 정책·상태: **timeout·gate·필수 inventory 정책 변경 없음**. 제품 종료 5초, nested 900초, workflow 20분을 유지한다. RT-08 상태는 **IN_PROGRESS**, 연결은 **Refs #295 (RT-08(a))**, PR 번호와 merge SHA는 각각 **pending**이다.
- 이번 수정 범위는 이 Log의 후속 기록 추가뿐이다. Log 외 파일 수정, 테스트 재실행, staging·commit·push·PR 생성은 하지 않았다.
