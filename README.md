# 대신고 (Daesingo)

**블랙박스 영상에서 교통위반 신고 자료를 준비해 주는 제품.**

위험한 위반을 목격했고 신고할 마음도 생겼지만, 운전 중이라 **정확한 시각과 장소를 적어두지 못한 운전자**가 타깃이다. 몇 시간짜리 영상을 손으로 훑는 대신, 기억나는 단서를 자연어로 말하면(대충 언제 · 어떤 차 · 무슨 일 · 어디쯤) 제품이 사건 구간 후보와 그 전후 증거를 찾아온다. **사용자는 확인하고 고치기만 한다.**

목표는 신고할 마음이 없던 사람을 유도하는 게 아니라, **이미 생긴 신고 의향이 준비 과정의 마찰 때문에 사라지지 않게 하는 것**이다.

> **현재 상태 (2026-09-18 갱신):** 설계 단계를 지나 모듈별 구현이 진행 중이다. `apps/prototype`은 여전히 백엔드·영상 파이프라인·AI 호출이 없는 흐름 프로토타입(목데이터)이지만, `apps/web`은 실제 구현이 시작됐다(`CaseView` 소비 화면·컴포넌트). `src/daesingo/`는 `case`·`search`·`readout`·`recording`·`evidence`·`common` 6개가 실제 코드와 테스트를 갖고 있고(`tests/` 기준 445개 통과), `api`·`worker`는 아직 README만 있는 골격이다. `eval/`도 채점 도구(정규화·scorer·runner)가 실제로 동작한다. 모듈 간 실제 AI 호출·엔드투엔드 연결은 아직 없다.

## 무엇을 하고, 무엇을 하지 않는가

제품이 약속하는 것과 명시적으로 하지 않는 것은 **[`docs/product/product-spec.md`](docs/product/product-spec.md) §5**가 소유한다. 요약하면:

**한다** — 자연어 기억 단서를 시간·차량·상황 정보로 구조화 · 1차 탐색(Coarse)으로 상위 후보 생성 후 정밀 검증 · Top-3 구조화 카드와 사용자 보정 · 사건 전후 증거 구간 구성(**영상 파일 경계에 걸친 사건 포함**) · 번호판 best frame과 OCR · 시각을 **출처와 함께**(화면 표시 / 파일명 / 메타데이터 / 사용자 / Unknown) 관리 · GPS가 있으면 위치 보강, 없으면 사용자 단서 유지 · 신고요건 점검과 안전신문고 handoff

**하지 않는다** — AI가 법적 위반 여부를 최종 확정 · 사용자 승인 없는 무인 자동신고 · 신뢰 가능한 출처 없는 시각을 임의 생성 · 자체 지도 UI · 모든 도로교통법 위반 유형 지원

### 초기 지원 사건 4종

신호위반 · 중앙선 침범 · 진로변경(백색 실선 침범) · 이륜차 안전모 미착용

4종으로 좁힌 이유는 시간 순서 판단(신호 → 정지선 → 통과)과 객체 속성 판단(안전모)처럼 **서로 다른 인식 능력을 함께 검증**할 수 있기 때문이다. 자세한 근거는 product-spec §6.

### 넘지 않는 선

[`product-spec.md`](docs/product/product-spec.md) **§7**이 제품 수준 불변 경계를 소유한다. 그중 셋만 옮기면:

- **원본 영상을 덮어쓰지 않는다.**
- 번호판·시각·위치가 불확실하면 **값을 만들어내지 않고** 출처와 `확인 필요`/`UNKNOWN` 상태를 보여준다.
- **실제 안전신문고 제출은 사용자가 직접 한다.**

## 사용자 흐름

영상 업로드 → 영상에서 읽은 정보 확인(촬영 시간 · 화면 시각 유무 · GPS 유무) → 사용자가 기억을 말함 → 단서 구조화와 탐색 범위 확인 → 분석 → 사건 후보 비교·검증 → 사용자 보정 → 번호판·시각·위치 확정 → 신고요건 점검 → 안전신문고로 handoff.

화면 단위 흐름과 **실패했을 때 무엇을 보여주는지**는 [`docs/product/core-user-flow.md`](docs/product/core-user-flow.md)가 소유한다. 채팅 인터페이스가 아니라 **단계형 화면**이고, 자연어 입력은 단서 입력 한 곳에만 있다.

## 구조

모듈 7개로 나눈다. 기준은 팀원 수가 아니라 **서로 다른 변경 이유**다 — 무엇이 바뀌면 어디를 고치게 되는가.

| 모듈 | 다루는 사실 |
| --- | --- |
| `recording` | 블랙박스 파일·stream이라는 현실. Source가 말해주는 것과 픽셀 접근 경계 |
| `search` | 넓은 영상 범위의 픽셀이 말해주는 것 — 사건 구간 후보 탐색 |
| `readout` | 좁은 화면 영역의 값 — 번호판·화면 시각이 어떻게 보이는지 |
| `evidence` | 확정 Evidence + 신고 규정 + Package 정책 |
| `case` | 진행 상태·사용자 선택·부분 재실행·작업 발주 의도 |
| `web` | 도메인 상태를 갖지 않고 `CaseView`를 표현하는 작업공간 |
| `eval` | 제품 런타임과 분리된 채점 도구 |

두 가지가 이 구조의 핵심이다. **관찰(`search`·`readout`)과 확정(`evidence`)을 분리한다** — "AI가 그렇게 봤다"와 "이 값이 맞다"는 다른 사실이다. 그리고 **`eval`은 제품 런타임이 아니다** — `search`와 `readout`은 `eval`의 존재를 모른다.

경계·계약·각 모듈이 **알면 안 되는 것**은 [`docs/architecture/module-architecture.md`](docs/architecture/module-architecture.md)가 소유한다. 1,900줄이므로 전체를 읽지 않는다 — §1 → §2 → 자기 모듈 §4 → §5 순서로 읽는다.

### 기술 스택 (확정)

Python · FastAPI · **Modular Monolith**(API 1 + Worker 1) · MySQL 8.4 · DB Queue · ffmpeg/ffprobe · AWS · Desktop Web 우선(모바일 반응형은 MVP 제외). 안전신문고 자동 제출 API는 연동하지 않는다.

## 레포 구성

`apps/`에 실행 코드, `docs/`에 living document, `src/`·`eval/`에 Python 구현이 있다. 모듈별 진행 상태는 다르다 — 코드가 들어온 곳도 있고, 아직 README만 있는 골격도 있다. 정확한 현황은 각 폴더의 README와 `docs/management/ownership.md`가 소유한다.

| 경로 | 내용 |
| --- | --- |
| `apps/prototype/` | 흐름 프로토타입 (React 19 + Vite 6, 목데이터). **제품 코드 아님** |
| `apps/web/` | 실제 웹 앱. `CaseView` 소비 화면·컴포넌트 구현 진행 중 (Owner: 신유민) — 자세한 현황은 `apps/web/README.md` |
| `src/daesingo/` | Python 모듈형 모놀리스 — `case`·`search`·`readout`·`recording`·`evidence`·`common`은 실제 구현+테스트가 있다. `api`는 RT-01 설정·로그 bootstrap, `worker`는 RT-04(a) 진입점·claim/dispatch·T1을 구현했다(HTTP route·T2·실제 Worker handler 미구현) |
| `eval/` | 오프라인 채점 도구 — `datasets` / `manifests` / `runners` / `scorers` / `predictions` / `results` / `locked_test`, 실제로 동작한다 |
| `data/` | 테스트 · 데모용 고정 데이터 — `mock/`(모듈별 계약 fixture · 시나리오), `real/`(실제 영상 E2E 산출 JSON) |
| `examples/` | `recording` · `search` 공개 함수 사용 예제 스크립트 |
| `scripts/` | 경계·계약 검사 등 팀 스크립트 (`check_boundaries.py` 등) |
| `tests/` | 모듈별 pytest 테스트. 루트 `pyproject.toml`(`pythonpath=["src"]`, `testpaths=["tests"]`) 기준으로 레포 루트에서 `pytest` 한 번에 전부 돈다 |
| `docs/product/` | 타깃·문제·제품 약속·지원 범위·사용자 흐름·검증 계획 |
| `docs/architecture/` | 모듈 경계(v4)와 계약 원칙 |
| `docs/runtime/` | 공통 실행 인프라의 Runtime Tech Spec · Ops Spec. `common/runtime`은 도메인 모듈이 아님 |
| `docs/modules/` | 모듈별 조사·실험·결정·계약 |
| `docs/management/` | 역할 배정·운영 계획·cross-cutting 결정·보안 검수 |
| `docs/design/` | 디자인 시스템·1단계 목업·프로토타입 스펙 |
| `docs/archive/` | 지난 제출물과 종료된 안건 — **현재 문서가 아니다** |

문서는 한국어로 쓰고 폴더·파일 이름은 영어로 쓴다.

## 문서를 읽는 순서

**전체를 읽지 않는다.** 자기 작업에 해당하는 것만 연다.

| 하려는 일 | 읽을 것 |
| --- | --- |
| 제품이 무엇을 약속하고 안 하는지 | `docs/product/product-spec.md` §5 · §7 |
| 화면 흐름 · 실패 UX | `docs/product/core-user-flow.md` |
| 내 모듈의 경계 · 계약 · 금지사항 | `docs/architecture/module-architecture.md` §1 → §2 → §4 내 모듈 → §5 |
| 내 모듈의 조사 · 실험 · 결정 | `docs/modules/<module>/` |
| DB Queue · retry · lease/heartbeat · Worker 실행 기반 | `docs/runtime/runtime-tech-spec.md` |
| 배포 · logging · monitoring · storage/retention · capacity | `docs/runtime/ops-spec.md` |
| 누가 무엇을 맡는지 | `docs/management/ownership.md` |
| 운영 결정(승인 경로 · 리뷰 담당) | `docs/management/cross-cutting-decisions.md` |
| 문서 폴더 규칙 · 문서가 서로 다른 말을 할 때 | `docs/README.md` |

문서가 충돌하면 우선순위는 **제품 약속 = `product-spec.md`** → **모듈 경계·계약 = `module-architecture.md`(v4)** → **화면 흐름 = `core-user-flow.md`** 이고, 셋이 어긋나면 혼자 고치지 않고 주간 회의 안건으로 올린다. 자세한 규칙은 [`docs/README.md`](docs/README.md).

**미결은 미결로 남긴다.** 업로드 전략 · timeout 수치 · correction 로그 재사용 설계 · overlay 존재 탐지 세부 · 실패 분류 이름 목록은 실측 전이라 `미결`로 표시돼 있다. 문서를 완성도 있게 보이려고 채우지 않는다.

## 실행

Node.js 20 이상. npm workspace라서 **레포 루트에서 한 번만** 설치한다(`apps/*` 안에서 하지 않는다).

```bash
npm install            # 루트에서 한 번
npm run dev:prototype  # Vite가 출력하는 URL 열기 (기본 http://localhost:5173)
```

```bash
npm run build              # build 스크립트가 있는 workspace 전부
npm run preview:prototype  # 프로토타입 프로덕션 빌드 서빙
npm run dev:web            # apps/web 개발 서버
npm run preview:web        # apps/web 프로덕션 빌드 서빙
npm run test:web           # apps/web 테스트 (vitest)
```

### Python (`src/daesingo`, `eval/`)

Python 3.12 이상. 레포 루트에 `pyproject.toml`이 있고 `src/` 레이아웃(`pythonpath=["src"]`)으로 잡혀 있다.

```bash
uv sync --locked --extra test   # daesingo + pytest를 uv.lock 잠금 버전으로 설치 (루트에서 한 번)
# uv 없이: pip install -e ".[test]" — 이 경우 아래 명령의 `uv run`은 빼고 실행한다
uv run pytest               # tests/ 전체 (모듈별 하위 폴더 포함, testpaths=["tests"] 기준)
uv run pytest tests/case/   # 모듈 하나만
uv run python scripts/check_boundaries.py  # 모듈 경계 위반 검사
```

MySQL integration은 `DAESINGO_MYSQL_URL`로 지정한 폐기 가능한 MySQL 8.4 테스트 DB에서 실행한다. 공용 harness는 테스트별 schema를 생성·삭제하므로 해당 권한이 필요하며, 기존 Case fixture는 지정 DB의 Case table을 초기화한다. 권한 실패 시나리오까지 포함한 전체 검증은 테스트 사용자 생성·SELECT 권한 부여·사용자 삭제 권한도 필요하다. CI의 `python-tests.yml`은 MySQL 8.4 service와 `DAESINGO_REQUIRE_MYSQL=1`을 사용하고, MySQL 테스트의 skip/xfail 0·필수 시나리오·기존 Case MySQL 실행을 JSON/JUnit 보고서로 검사한다. URL이 없는 로컬 실행은 MySQL integration을 skip한다.

Migration은 `uv run python -m daesingo.common.db.migrate --database-url-stdin`으로 실행한다. 호출자가 URL 한 개를 비대화형 stdin에 명시적으로 전달하며 credential을 argv·로그에 넣지 않는다. runner는 URL 환경변수·`.env`·RuntimeConfig를 읽지 않는다. 소스 checkout의 env를 frozen registry `case → runtime` 순서로 `head`까지 적용하며, 새 env는 registry와 필수 테스트에 등록해야 한다. 기존 MySQL gate는 RT-02(a)·Case 실행 목록과 새 migration 필수 check를 함께 검사한다.

Migration은 단일 실행 전제다. process 내부 중복 호출만 거부하며 cross-process 동시 실행 안전성을 보장하지 않는다. 첫 실패에서 중단하고 retry·stamp·downgrade·resume/startup migration은 제공하지 않는다. MySQL DDL의 부분 적용은 전체 rollback되지 않으므로 실패 후 상태 검사·복구가 필요하다. 현재 Runtime env는 빈 `runtime_alembic_version`만 만들고 Runtime 업무 schema는 RT-03·RT-07에서 추가한다. 배포 실행 시점·URL 출처·배포 artifact 배치는 후속 범위이며 RT-02(b)는 독립 재리뷰 전이다.

### 프로토타입에 대해

`apps/prototype`은 **흐름 프로토타입**이다. 목데이터로 도는 10화면이고 백엔드·영상 파이프라인·AI 호출이 없다. 결과 없음 · 탐색 실패 · 범위 확장처럼 **실패 상태로 바로 점프하는 `ScenarioBar` 데모 컨트롤**이 들어 있다. 제품 코드가 아니므로 손대지 않는다.

실제 웹 앱은 `apps/web`에서 구현이 진행 중이다(`CaseView` 소비 화면·컴포넌트). 프로토타입을 얼마나 참고했는지·구조가 어떻게 다른지는 `web` Owner가 관리하는 [`apps/web/README.md`](apps/web/README.md)와 `docs/modules/web/`이 소유한다.

## 라이선스

[MIT](LICENSE).
