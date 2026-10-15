# `api` — FastAPI composition root

**Owner:** 김준영 (공통 기반/운영) · **경계:** `docs/architecture/module-architecture.md` §1-5 · §8-1 · §8-2

- 배포 단위 「API 1」. 긴 작업은 HTTP 요청 안에서 끝내지 않는다 — `case`가 만든 `JobRecord`를 queue에 넣고 `202 Accepted`를 반환한다.
- 즉시 처리하는 것(§8-1): `CaseView` 조회 · hint 수정 · candidate 선택 · pure evidence recompute · requirement recompute · 상태 전이.
- 인증은 MVP 최소 수준이며 방식은 미결(§1-7 A2).
- `web`이 읽는 상태는 `case.get_view()`를 노출하는 CaseView 하나다 (§4-모듈6 ③). 그 밖의 read는 CaseView가 가리키는 FrameRef · 신고용 artifact의 바이너리 조회뿐이다. HTTP surface 결정은 `docs/runtime/runtime-tech-spec.md` §13(RD-05, #247), 경로 · status · body는 HTTP API Contract `docs/architecture/contracts/contract-http-api.md`(`http-api/v1`, Final — Accepted)다. route 구현 전 선행 조건은 그 문서 §9.1이다.

## 상태

RT-01의 `bootstrap.py`를 구현했다. `bootstrap(revision=...)`은 `DAESINGO_ENV_FILE`(미지정 시 cwd `.env`)을 명시적으로 읽고, 불변 API RuntimeConfig와 등록된 모듈 factory/validator를 검증한 뒤 JSON line `process.started`를 기록한다. 실패 시 설정 key 이름만 기록하고 `SystemExit(1)`로 종료한다. `revision`은 호출자가 전달하는 commit SHA 등 안전한 식별자다.

필수 파일 key는 `DAESINGO_RUNTIME_DB_URL` · `DAESINGO_RUNTIME_MEDIA_ROOT` · `DAESINGO_RUNTIME_API_TEMP_ROOT`다. shell에서는 파일 경로만 읽는다. 세부 선택과 검증 결과는 [RT-01 Implementation Log](../../../docs/runtime/runtime-implementation-log.md#rt-01--runtime-config--composition-bootstrap--structured-log-기반)에 기록한다.

RT-08(a)는 `app.create_app` · `composition.compose_api` · API QueuePool / ready NullPool · `errors`의 HTTP envelope · `health`의 `/health/live`와 `/health/ready`를 구현한다. health 성공 body는 Contract §5.7의 `{status: ok}`, 준비 실패는 `{status: unavailable}`이다. 일반 오류는 Contract §3.3의 `ok/error/case_view`이며 프레임워크 `detail`·validation 입력·예외 header를 반환하지 않는다. docs/OpenAPI·slash redirect는 비활성이다.

```bash
uv run --no-sync python -m daesingo.api --revision <revision> --host 127.0.0.1 --port 8000
```

`--revision`은 필수다. port는 0~65535(0은 OS가 배정) 범위를 DB/composition 전에 검증하며 잘못된 argv는 stderr 없이 코드 1이다. 서버 일반 예외·의도적인 SystemExit/기타 BaseException은 코드 1, KeyboardInterrupt는 정상 graceful 코드 0이다. CLI는 lifespan 전 실패에도 resource를 정리하고 signal과 Uvicorn logger 상태를 복원한다. lifespan에서 삼켜진 cleanup 실패도 코드 1로 보존한다. 지원 실행 경계는 명시적 workers=1 · reload off이며 `WEB_CONCURRENCY`로 늘어나지 않는다(B-W4). 설정 검증/engine 조립 실패는 listener 전 안전한 상수 event와 종료 코드로 끝난다. startup에서 migration·DB 접속·provider HTTP는 실행하지 않는다.

ready는 media root의 존재·디렉터리·쓰기 권한과 Linux read-only mount flag를 파일 생성 없이 검사한다. DB는 공용 pool 대기 없이 전용 연결에서 SELECT 1을 실행한다. 두 검사의 제한/전체 budget은 기존 ReadySettings와 B-H1~B-H3를 소비하며, 각 probe는 하나의 in-flight 호출을 동시 요청이 공유한다. 제한을 넘은 native 호출은 강제 종료하지 못하지만 추가 probe를 누적하지 않는다. 늦게 반환한 DB connection은 정상 close된다. Windows에는 statvfs가 없어 디렉터리/access 검사만 적용하며 실제 RO mount acceptance는 Linux private namespace에서 검증한다.

request마다 서버가 발급한 trace_id를 thread/context 경계로 유지한다. request/ready event는 RT-01 allowlist logger를 쓰는 단일 daemon consumer와 유한 queue로 분리하며, sink 장애·지연·thread 시작 실패가 HTTP 응답을 바꾸지 않는다. 로그 포화 시 event를 버리고 shutdown은 유한 대기한다. API 소유 handler는 I/O lock과 stdlib cleanup lock을 분리하고 emission에서 flush하므로 shutdown은 sink I/O를 반복하지 않는다. 기본 stdout과 고정 오류 stderr는 unbuffered fd write로 Python buffered I/O 종료 lock을 잡지 않는다. 제3자 handler를 종료/제거하거나 logging 전역 registry를 수정하지 않는다. fatal sink 예외는 close에서 owner에게 전달하고 composition 실패 진단은 유한 drain 뒤 startup 코드 1보다 우선하지 않는다. raw uvicorn access/error/traceback 출력을 억제한다. 요청 URL·query·body·header·예외 문자열·DB URL·mount 경로는 event/응답에 넣지 않는다.

`POST /cases`·`GET /view`는 RT-08(b), commands/enqueue는 (c), 중단 command는 (d), media HTTP는 RT-11에 남긴다. 이 단계에서 Case/Search 공개 capability를 만들거나 호출하지 않는다. commands body 한도(B-U2) 및 B-D8 transaction 조립은 해당 후속 route에 연결한다.

실제 MySQL acceptance는 기존 disposable 8.4 harness에 참여한다. SHUTDOWN 검사는 suite DB와 분리된 두 번째 서버를 사용한다. Linux CI는 서비스가 준비한 mysql:8.4 image를 Docker로 재사용하고 sudo/unshare/mount로 private RO tmpfs를 생성·해제한다. Windows 로컬 acceptance는 WSL Ubuntu 및 `DAESINGO_MYSQL_TEST_BASEDIR`/`DAESINGO_MYSQL_TEST_LIBDIR`의 테스트 전용 Linux 바이너리/라이브러리 위치가 필요하다. fixture는 기능 부재를 skip으로 대체하지 않는다.
