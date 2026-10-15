# RT-08(a) API skeleton · health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. 사용자 승인 범위의 native TDD 실행이며 staging/commit/push/PR 생성은 하지 않는다.

**Goal:** Issue #295의 (a)만 구현하며 HTTP Contract · Accepted Decision · Baseline 의미를 유지한다.
**Tech Stack:** Python 3.12 · FastAPI · uvicorn · SQLAlchemy/PyMySQL · 기존 pytest/MySQL 8.4 harness.
**Spec:** runtime-implementation-plan §6 RT-08 · §12, HTTP Contract §2·§3·§5.7·§6·§7, Tech Spec §12.1·§12.4·§12.5·§13·§14, Baseline B-W4·B-U2·B-U5·B-D3·B-D4·B-D8·B-H1~H3.
**Execution:** 사용자 지시대로 현재 브랜치에서 직접 TDD. staging·commit·push·PR 없음. 내부 DI/파일 구조는 위임된 implementation detail.

## Architecture / constraints
- `api/app.py`: `create_app(startup=...)` 또는 bootstrap(revision=...) → composition, lifespan 소유 engine dispose, health 두 route만 등록. OpenAPI/docs 및 slash redirect 비활성.
- `api/composition.py`: RT-01 Startup 재사용, RT-02 API QueuePool와 ready NullPool 조립. Case/Search 새 import/surface 없음.
- `api/errors.py`: HTTP envelope와 RT-02 BeforeCommitFailure/CommitOutcomeUnknown 매핑. 기본 404·405·transport validation body 차단, 예외 detail·headers 비노출.
- `api/health.py`: live 무검사, ready DB SELECT 1과 media_root metadata 검사. 전용 bounded daemon thread별 최대 1 outstanding·동시 요청은 in-flight 결과 공유, deadline 후 unavailable. 파일 쓰기 없음. 실패 dependency는 안전한 상수 event에만 남김.
- `api/events.py`: request/ready event의 유한 queue·daemon consumer·context capture·bounded shutdown. sink 지연/예외/thread 시작 실패 격리.
- `api/__main__.py`: 명시 revision·host·port, uvicorn workers=1·reload off·access log off. 환경 WEB_CONCURRENCY 무시.
- Baseline 값은 기존 config에서 소비. commands JSON limit/transaction은 RT-08(c)에 남김.

## Review Focus
- default validation/detail 또는 unknown error가 응답/로그로 유출되는가
- pool 고갈에도 ready가 전용 연결로 성공하는가
- 느린 metadata/DB가 deadline 후 thread를 누적하는가
- startup 실패가 listener를 열거나 migration/provider를 호출하는가
- 실제 DB 중지 및 Linux mount 읽기 전용 실패를 검증하고 정리하는가

## Tasks
- [x] 테스트 먼저: health/error factory·provider 0·safe logging·startup·workers·deadline 및 MySQL acceptance와 신규 gate evidence 누락.
- [x] RED 실행과 실패 원인 보존.
- [x] 최소 구현 및 GREEN 실행, 필요 시 독립 cycle.
- [x] API/common 회귀, 실제 MySQL acceptance(skip/xfail 0), 전체 pytest, JSON/JUnit와 evidence 누락 mutations, boundary·Contract fixture·workflow 정적 검사·diff check.
- [x] schema/account/connection/process/port 정리 및 기존 미추적 해시 대조.
- [x] Log·README·review evidence에 결과/차이/detail/Owner/위험 기록.
