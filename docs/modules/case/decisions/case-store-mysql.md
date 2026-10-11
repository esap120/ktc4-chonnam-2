# CaseStore MySQL 영속화 — 1단계 설계

> **상태: 1단계 구현(2026-10-06, `case-store-mysql-plan.md`). §6 진입점은 `store=` 인자를 유지하고 `CaseStore`가 repository · conn · adapters를 묶는다 — 동작은 이 문서 그대로** · 2026-10-05 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-6(`design-refinement-w7-baseline.md`), #245 D-1 · D-2 · D-5, #246 S-4, #250 RD-01
> case schema · 저장소 인터페이스는 case 결정 범위다(#245 D-1 「Case table/schema는 case가 소유」). 다른 Owner와 맞춰야 하는 것은 §9에 따로 둔다.

## 1. 배경

api · worker가 별도 process가 되면서(Ops §2) case의 in-memory 전제가 깨진다. 지금 `CaseStore`(`src/daesingo/case/store.py`)는 process 메모리의 dict라 재시작하면 case가 사라지고, 다른 process는 같은 case를 볼 수 없다.

8-6 문구는 두 가지를 담고 있다.

1. case 상태를 MySQL에 저장한다.
2. case마다 adapter를 들고 CaseView 때마다 adapter에서 다시 읽는 구조를 바꾼다.

2는 search · evidence · readout 결과가 어디에 영속되고 무엇으로 읽히는지(#245 D-6 JobExecution read port, 각 모듈 저장소)가 먼저 정해져야 해서, **이 문서는 1만 다룬다(1단계).** 2는 별도 설계로 한다(2단계).

**1단계가 주는 것:** case 상태(stage · 후보 · 정정 · 발주 기록)가 재시작 뒤에도 남고, 8-7 · 8-8 · 8-9 · 8-11이 올라설 transaction 경계가 생긴다.
**1단계가 주지 않는 것:** api · worker를 다른 process로 띄운 비동기 Real E2E. adapter가 여전히 process 메모리에 있어서다 — 2단계까지 가야 한다.

## 2. 이미 정해진 것 (다시 열지 않음)

- **DB 스택** — MySQL 8.4 하나, PyMySQL(sync) + SQLAlchemy Core 2.x, ORM 없음. Alembic, forward-only, expand → contract. migration은 앱 시작 때 돌리지 않는다(`docs/runtime/runtime-tech-spec.md` §4.4).
- **소유** — case schema는 case가 소유한다. Runtime table과 FK를 두지 않는다(#245 D-1, #250 01a). 각 모듈은 자기 schema · migration만 소유한다(runtime-tech-spec §4.2).
- **transaction 경계는 composition root가 소유한다.** command 처리 · 저장 · enqueue가 한 transaction이고, case repository는 **독자적으로 commit하지 않는다**(runtime-tech-spec §12.1, #245 D-2 · D-3). worker 결과 반영도 T2 한 transaction이다(§12.2, D-5).
- **격리 수준** — READ COMMITTED(#250 01b). provider 호출 동안 DB transaction을 열어 두지 않는다.
- **영속화 대상** — Case aggregate(`Candidate.thumb_ref` 포함) · JobRecord · `scope_ref`가 가리키는 AnalysisScope(#246 S-4) · 처리한 `execution_id`(D-5) · 중단된 `job_id` 집합(C-4).

## 3. 결정

| # | 결정 | 고르지 않은 것 |
| --- | --- | --- |
| D1 | 8-6을 두 단계로 나눈다 — 이 문서는 저장소와 transaction 참여만 | 한 번에 — 다른 모듈 결과 저장 위치를 가정해야 한다 |
| D2 | **하이브리드 schema** — `cases`(조회 칼럼 + aggregate JSON) + append-only 레코드 테이블(§4) | 전부 정규화 — 후보 목록은 탐색마다 통째로 바뀌어 매핑 비용만 늘어난다 / JSON 하나 — append-only를 앱 코드로만 지켜야 한다 |
| D3 | **비관적 잠금** — 쓰기 경로는 `cases` 행을 `SELECT … FOR UPDATE`로 잡고 읽는다. 읽기 경로는 `FOR SHARE` | 낙관적 `row_version` — worker T2에 재시도 루프가 필요하고, 같은 case 동시 쓰기가 드물어 얻는 게 적다 |
| D4 | **opt-in MySQL 통합 테스트 + in-memory 구현** — 두 구현이 같은 계약 테스트를 통과한다 | CI에 MySQL 추가 — 공용 CI라 Runtime과 협의가 먼저다(§9) / sqlite — `FOR UPDATE` · JSON · 잠금 동작이 달라 통과해도 믿을 수 없다 |
| D5 | 처리한 `execution_id` · 중단된 `job_id` 테이블은 **8-8 · 8-9에서** 만든다. **2026-10-06 갱신:** 중단된 `job_id`는 테이블 대신 aggregate 정산 기록으로 둔다(`running-jobs-derivation.md` §결정 5) | 지금 만들기 — 쓰는 코드가 없는 schema가 된다. forward-only라 나중에 더해도 된다 |

D3을 고른 근거 하나 더: 잠금 안에서 `expected_case_rev`를 검사하므로 `case.command.stale_revision` 판정이 정확해진다(검사와 저장 사이 틈이 없다).

## 4. Schema

MySQL 8.4 · InnoDB · utf8mb4. 테이블 이름은 `docs/architecture/erd-draft.md`(L380~392)를 따른다.

```
cases
  case_id        VARCHAR(128) ascii_bin  PK
  case_rev       INT          NOT NULL
  stage          VARCHAR(32)  NOT NULL
  selection_rev  INT          NOT NULL
  state          JSON         NOT NULL
  created_at     DATETIME(6)  NOT NULL   -- UTC
  updated_at     DATETIME(6)  NOT NULL   -- UTC

job_records                                -- append-only
  job_id     VARCHAR(191) ascii_bin  PK
  case_id    VARCHAR(128) ascii_bin  NOT NULL  FK → cases
  seq        INT          NOT NULL             UNIQUE(case_id, seq)
  record     JSON         NOT NULL             -- JobRecord 계약 dict 그대로

correction_records                         -- append-only
  correction_id  VARCHAR(191) ascii_bin  PK
  case_id        VARCHAR(128) ascii_bin  NOT NULL  FK → cases
  seq            INT          NOT NULL             UNIQUE(case_id, seq)
  record         JSON         NOT NULL             -- CorrectionRecord 계약 dict 그대로

analysis_scopes                            -- append-only, scope는 불변
  case_id    VARCHAR(128) ascii_bin  NOT NULL  FK → cases
  scope_id   VARCHAR(128) ascii_bin  NOT NULL
  scope      JSON         NOT NULL
  PRIMARY KEY (case_id, scope_id)
```

- **id 칼럼은 `ascii_bin`이다.** utf8mb4 기본 collation(`utf8mb4_0900_ai_ci`)은 대소문자 · 악센트를 구분하지 않아 `case_A`와 `case_a`가 같은 PK가 된다.
- **`analysis_scopes`는 `(case_id, scope_id)` PK다.** `scope_id`는 case 안에서만 고유하다(테스트에서 `scope_id="s1"`이 여러 case에 쓰인다). `job_id`(`job_{case_id}_{kind}_{uuid8}`) · `correction_id`(`corr_{case_id}_{uuid8}`)는 전역 고유라 단독 PK이고(case_id 128자 + 접두어 · kind · uuid8이 들어가도록 191자), Runtime이 `job_id`로 실행을 식별한다.
- **`seq`** — 테이블에는 순서가 없으므로 aggregate 목록의 index를 `seq`로 둔다. 「같은 kind의 가장 최근 JobRecord」(`jobs.latest_job_record`)가 순서에 기댄다.
- **레코드는 계약 dict를 JSON 그대로** 넣는다. `kind` 등을 칼럼으로 복제하지 않는다 — 조회는 로드 뒤 메모리에서 한다. MySQL JSON은 키 순서를 바꾸지만 dict 비교에는 영향이 없다.
- **`cases`에 뺀 칼럼은 셋**(`case_rev` · `stage` · `selection_rev`) — 운영 조회 · 디버깅용이다. 값의 원본은 aggregate이고, 저장할 때 같이 쓴다.
- FK는 case 소유 테이블끼리만 건다.

### `state` JSON

```json
{
  "state_version": 1,
  "user_reviewed": false,
  "hints": {},
  "manifest_summary": {},
  "candidates": [ { "candidate_id": "...", "thumb_ref": "fr_...", "...": "Candidate dataclass 필드 그대로" } ],
  "situation_response": null,
  "candidate_search_failed": false,
  "candidate_generation": 0
}
```

- `analysis_scopes`는 `state`에 넣지 않는다 — 테이블 하나에만 둔다.
- **모르는 키는 보존한다(round-trip).** 로드할 때 따로 보관했다가 `save()` 때 그대로 다시 쓴다. ops-spec은 single EC2 · 단순 rollback이 전제라(L786), 새 코드가 새 키를 쓴 뒤 옛 코드로 돌아가도 읽히고 데이터가 지워지지 않아야 한다.
- **없는 키는 dataclass 기본값으로 채운다** — expand 단계(필드 먼저 추가)에서도 읽힌다.

### aggregate에 더하는 것

`CaseAggregate.analysis_scopes: dict[str, dict]`(`scope_id` → AnalysisScope). 지금 scope는 만들어서 넘기기만 하고 aggregate에 남지 않는다. `COARSE_SEARCH`를 발주할 때 그 scope를 여기에 남긴다(#246 S-4). CaseView에는 내리지 않는다.

## 5. 저장소 인터페이스

```python
class CaseRepository(Protocol):
    def insert(self, conn: Connection | None, case: CaseAggregate) -> None: ...
    def load(self, conn: Connection | None, case_id: str, *, lock: Literal["share", "update"]) -> CaseAggregate: ...
    def save(self, conn: Connection | None, case: CaseAggregate) -> None: ...
```

- **`conn`은 호출자의 SQLAlchemy `Connection`이고 transaction도 호출자 것이다.** 저장소는 commit · rollback하지 않는다. in-memory 구현은 `conn`을 받지 않아도 된다(`None`).
- **`load()`는 항상 새 객체를 돌려준다.** in-memory 구현도 저장된 객체가 아니라 복사본을 준다 — 같은 객체를 주면 `save()`를 빠뜨려도 in-memory 테스트가 통과하고 MySQL에서만 상태가 사라진다.
- **`lock="update"`는 `cases` 행만 `FOR UPDATE`로, `lock="share"`는 `FOR SHARE`로 잡고** 나머지 세 테이블을 `seq` 순서로 읽는다. READ COMMITTED에서 잠그지 않고 테이블 넷을 따로 읽으면 commit 전후가 섞인 상태를 볼 수 있다.
- **`save()`** — `cases` 행을 갱신하고, 레코드 테이블마다 ① 저장된 id 목록을 `seq` 순서로 읽고 ② 그것이 aggregate 목록의 **앞부분과 정확히 같은지** 확인한 뒤 ③ 뒤에 새로 붙은 것만 INSERT한다. 앞부분이 다르면 `AppendOnlyViolation`이다(기존 레코드가 바뀌거나 지워졌다). 저장소 객체는 상태를 들지 않는다 — 「무엇이 저장됐나」는 매번 DB에서 읽는다. `save()`는 같은 transaction에서 `lock="update"`로 로드한 뒤에만 부른다.

### 잠금 순서 규칙

case 행과 Runtime `job_execution` 행을 함께 잠그는 transaction(api command · worker T2 · 중단 command)은 **항상 case 행을 먼저 잠근다.** 같은 case 안의 쓰기가 줄을 서므로 deadlock이 생기지 않는다. worker T1(terminal 기록)과 heartbeat는 case 행을 건드리지 않는다. Runtime도 지켜야 하는 규칙이라 §9에서 확인받는다.

### adapter

adapter는 저장소에서 빼서 process 메모리의 `AdapterRegistry`(case_id → adapter)에 둔다 — 2단계에서 없앨 대상이라 DB에 넣지 않는다.

`RealAdapter` · `RealVideoAdapter`는 만들 때 받은 `CaseAggregate`를 `self._case`로 들고 후보 · 정정 · `selection_rev`를 거기서 읽는다(`adapters.py:282` · `516`). `load()`가 새 객체를 주면 adapter는 옛 객체를 보게 되므로, adapter에 `bind_case(case)`를 두고 `AdapterRegistry.for_case(case)`가 요청마다 방금 로드한 aggregate를 붙인다. adapter 캐시(evidence 결과 묶음 · 관찰)는 객체 동일성이 아니라 `case_rev` · `candidate_generation` 값으로 판단하므로 그대로 동작한다.

## 6. 호출부

| 진입점 | 바뀌는 것 |
| --- | --- |
| `service.get_view(case_id, *, repository, conn, adapters, …)` | `load(lock="share")` → `adapters.for_case(case)` → 조립 |
| `command.handle_command(request, *, repository, conn, adapters, …)` | `load(lock="update")` → 검사 · 변경 → **성공했을 때만 `save()`**. 실패하면 저장하지 않는다(계약 §6 「실패하면 아무 상태도 바꾸지 않는다」). commit/rollback은 호출자 |
| `demo_happy_001.py` · `scripts/dump_real_caseview.py` · `scripts/dump_real_video_caseview.py` · 테스트 5개 파일 | in-memory 저장소 + `conn=None` |
| `scripts/measure_case_orchestration.py`(PR #234, 미머지) | 먼저 머지되는 쪽에 맞춰 같이 고친다 |
| aggregate를 직접 받는 함수(`receive_search_candidates` 등) | 그대로. 부르는 쪽이 load · save — 실제 경로는 worker 배선(8-8)에서 생긴다 |

「이번 command로 append한 JobRecord 목록」을 돌려주는 것은 8-7이라 넣지 않는다.

## 7. 오류

| 상황 | 동작 |
| --- | --- |
| case 없음 | `CaseNotFound(KeyError)` — `handle_command`가 `KeyError`를 `unknown_target`으로 바꾸는 지금 동작 유지 |
| 같은 `case_id` 재등록 | `CaseAlreadyExists`(DB unique 위반을 변환) |
| 레코드 앞부분 불일치 | `AppendOnlyViolation` — 정상 경로에서는 나지 않는 프로그래밍 오류 |
| `state_version`이 코드가 아는 것보다 큼 | 로드 오류 — 옛 코드가 새 형식을 덮어쓰지 않게 |
| deadlock · lock wait timeout · 연결 오류 | 잡지 않고 올린다. 재시도하지 않는다. rollback은 transaction 소유자(호출자) |

## 8. 테스트

**공통 계약 테스트** — in-memory · MySQL 두 구현을 parametrize한다. MySQL은 `DAESINGO_MYSQL_URL`이 있을 때만 돈다(없으면 skip — recording의 `DAESINGO_RECORDING_VIDEO`와 같은 방식).

- insert → load 왕복(후보 `thumb_ref` · `analysis_scopes` · 모르는 키 보존 포함)
- JobRecord · CorrectionRecord · AnalysisScope append
- 앞부분 불일치 → `AppendOnlyViolation`
- 없는 case · 중복 등록
- `load()`가 새 객체인지 — 고치고 `save()`하지 않으면 다음 `load()`에 없다

**MySQL 전용**

- rollback하면 case · JobRecord가 둘 다 남지 않는다(runtime-tech-spec §16 item 9의 case 쪽)
- 연결 둘에서 `lock="update"`가 서로 기다린다(짧은 `innodb_lock_wait_timeout`로 확인)
- `case_A` · `case_a`가 별개로 저장된다
- 빈 DB에서 migration upgrade

**회귀 기준** — 기존 테스트(develop 기준 1,494 passed)가 in-memory 저장소로 그대로 통과한다.

**이번에 검증하지 못하는 것** — §16 item 9의 나머지 절반(Runtime attempt-1 `QUEUED`가 같은 commit에 들어가는지)은 Runtime enqueue가 없어 Runtime 구현 때 같이 본다.

로컬 실행: `docker run --rm -e MYSQL_ROOT_PASSWORD=… -p 3306:3306 mysql:8.4`(pre-implementation spike와 같은 이미지) → migration upgrade → `DAESINGO_MYSQL_URL=mysql+pymysql://…` 로 pytest.

## 9. 다른 Owner와 맞출 것

이 문서의 결정으로 정하지 않는다. 구현 PR 전에 확인받는다.

> **2026-10-05 확인 결과(#267 리뷰 — @flosure23 PM · api composition root, @cheol1203 Runtime 구현):**
> - `conn` 타입 — **합의.** composition root가 transaction을 소유하고 Case와 Runtime이 같은 SQLAlchemy `Connection`에 참여한다. 별도 UoW 객체는 지금 고정하지 않는다.
> - 잠금 순서 — **합의.** Case와 Runtime 행을 함께 잠그는 경로(api command · worker T2 · 중단)는 `cases` 행을 먼저 잡는다. worker T1 · heartbeat는 case 행을 건드리지 않는다.
> - Alembic 구성 — **잠정(provisional).** 모듈이 자기 migration을 소유한다는 원칙만 합의했다. 아래 `migrations/case/` · `case_alembic_version`은 case의 임시안이고, 정확한 배치는 Runtime Implementation Plan · RD-12f에서 정한다.
> - 의존성 — **합의.** SQLAlchemy · PyMySQL · Alembic은 공용으로 한 버전만 쓴다. 먼저 들어가는 구현 PR이 공용 `pyproject.toml`에 추가하고 다른 쪽이 맞춘다.
> - CI MySQL — 첫 구현 단계에서 통합한다. 세부 구성은 Runtime Implementation Plan에서 정한다.
> - 원칙 재확인 — provider · 외부 모듈 호출 동안 DB transaction · lock을 쥐고 있지 않는다(#250 01b).

| 무엇 | 누구 | case 안 |
| --- | --- | --- |
| `conn` 타입 — Runtime enqueue API도 같은 transaction에 참여하므로 같은 SQLAlchemy `Connection`을 받아야 한다(§12.1 「UoW API 모양은 구현 플래닝」) | common/runtime | 호출자가 `Connection`을 넘기고 각자 commit하지 않는다 |
| 잠금 순서 규칙(§5) | common/runtime | case 행 먼저 |
| Alembic 구성 — 공용 env인지 모듈별인지 미정 **(잠정, 위 확인 결과)** | common/runtime | 임시로 case 전용 env(`migrations/case/`), version table `case_alembic_version`. 공용이 정해지면 옮긴다 |
| `pyproject.toml` 의존성(SQLAlchemy · PyMySQL · Alembic) 버전 | common/runtime (공용 파일) | Runtime과 같은 버전 |
| CI MySQL — runtime-tech-spec §16이 실제 MySQL 통합 테스트를 요구하지만 CI에 없다(`open-decision-register.md` 「MySQL integration CI 없음」) | common/runtime | 요청만 한다. 이 PR에서 CI를 바꾸지 않는다 |

## 10. 범위 밖

- 처리한 `execution_id` · 중단된 `job_id` 테이블과 그 사용(8-8 · 8-9)
- Runtime enqueue · 결과 반영(T2) 배선
- 「이번 command로 append한 JobRecord 목록」 반환(8-7)
- adapter 제거 · CaseView 입력 재구성(2단계)
- CI MySQL
- `case_id` 생성 규칙 · 길이 — HTTP API Contract(#265)가 정한다. 여기서는 128자 이하를 가정하고, 넘으면 insert가 실패한다

## 11. 완료 조건

- §8 계약 테스트가 두 구현 모두 통과(MySQL은 로컬 실행 결과를 PR에 남긴다)
- 기존 테스트 회귀 없음 · `scripts/check_boundaries.py` PASS
- §9 항목 확인 결과를 PR에 남긴다
- ✅ (2026-10-06) `erd-draft.md`의 case 부분(L380~392 · L421 `correction_records` 값 저장 「미정」)을 이 schema로 갱신
- `design-refinement-w7-baseline.md` 8-6에 1단계 완료 · 2단계 남음을 적는다
