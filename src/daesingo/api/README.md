# `api` — FastAPI composition root

**Owner:** 김준영 (공통 기반/운영) · **경계:** `docs/architecture/module-architecture.md` §1-5 · §8-1 · §8-2

- 배포 단위 「API 1」. 긴 작업은 HTTP 요청 안에서 끝내지 않는다 — `case`가 만든 `JobIntent`를 queue에 넣고 `202 Accepted`를 반환한다.
- 즉시 처리하는 것(§8-1): `CaseView` 조회 · hint 수정 · candidate 선택 · pure evidence recompute · requirement recompute · 상태 전이.
- 인증은 MVP 최소 수준이며 방식은 미결(§1-7 A2).
- `web`이 읽는 상태는 `case.get_view()`를 노출하는 CaseView 하나다 (§4-모듈6 ③). 그 밖의 read는 CaseView가 가리키는 FrameRef · 신고용 artifact의 바이너리 조회뿐이다. HTTP surface 결정은 `docs/runtime/runtime-tech-spec.md` §13(RD-05, #247), 경로 · status · body는 HTTP API Contract `docs/architecture/contracts/contract-http-api.md`(`http-api/v1`, Final — Accepted)다. route 구현 전 선행 조건은 그 문서 §9.1이다.

## 상태

RT-01의 `bootstrap.py`를 구현했다. `bootstrap(revision=...)`은 `DAESINGO_ENV_FILE`(미지정 시 cwd `.env`)을 명시적으로 읽고, 불변 API RuntimeConfig와 등록된 모듈 factory/validator를 검증한 뒤 JSON line `process.started`를 기록한다. 실패 시 설정 key 이름만 기록하고 `SystemExit(1)`로 종료한다. `revision`은 호출자가 전달하는 commit SHA 등 안전한 식별자다.

필수 파일 key는 `DAESINGO_RUNTIME_DB_URL` · `DAESINGO_RUNTIME_MEDIA_ROOT` · `DAESINGO_RUNTIME_API_TEMP_ROOT`다. shell에서는 파일 경로만 읽는다. 세부 선택과 검증 결과는 [RT-01 Implementation Log](../../../docs/runtime/runtime-implementation-log.md#rt-01--runtime-config--composition-bootstrap--structured-log-기반)에 기록한다.

HTTP app/route · DB engine · health endpoint는 아직 없다(RT-02 · RT-08 이후). 이후 composition 시 실제 사용하는 모듈의 config factory를 `module_factories`에 등록하고 반환된 설정을 사용한다.
