# case

**Owner:** 유소연

이 폴더는 `case` 모듈의 세부 문서 작업공간이다. authoritative 경계는 `docs/architecture/module-architecture.md`, 역할은 `docs/management/ownership.md`를 따른다.

## 다루는 범위

- Case State와 사용자 선택
- 자연어 intent를 작업으로 매핑
- 작업 발주/재실행 정책
- 진행 상태와 E2E orchestration

## 다루지 않는 범위

- 신고요건 계산
- 시각 출처 우선순위
- 프롬프트/OCR 파라미터
- 확정 Evidence 값을 복제 소유
## 문서 운영

- `research/`: 조사·비교·Spike
- `experiments/`: 실제 설정/입력/결과/learning
- `decisions/`: 조사·실험 후 확정한 module 내부 결정
- `contracts/`: 이 모듈이 생산/소비하는 계약의 초안·검토 메모. cross-module 최종 계약은 `architecture/contracts/`로 승격
- `case-edge-cases.md`: case가 만나는 경계 상황(반복 행동 · 동시성 · 실패 · 빈 입력 · LLM) 목록 — 현재 동작 · 근거 · 다음 할 일

빈 spec을 미리 만들지 않는다. 필요해질 때 Owner가 생성한다.

### MySQL 통합 테스트 (opt-in)

case 저장소의 MySQL 구현은 `DAESINGO_MYSQL_URL`이 있을 때만 테스트한다(로컬은 opt-in). CI는 `python-tests.yml`이 MySQL 8.4 service와 `DAESINGO_REQUIRE_MYSQL=1`로 돌려 skip을 실패로 본다(RT-02a #319).

    docker run -d --rm --name daesingo-mysql -e MYSQL_ROOT_PASSWORD=devpw -e MYSQL_DATABASE=daesingo_test -p 3306:3306 mysql:8.4
    DAESINGO_MYSQL_URL="mysql+pymysql://root:devpw@127.0.0.1:3306/daesingo_test" python -m pytest tests/case -q

3306이 이미 쓰이고 있으면 `-p 3307:3306`처럼 다른 포트를 쓰고 URL의 포트를 맞춘다.

**격리 요건:** MySQL 저장소를 쓰는 transaction은 READ COMMITTED여야 한다(`create_engine(url, isolation_level="READ COMMITTED")`, #250 01b). 아니면 `load(lock="update")`가 첫 읽기여야 한다 — REPEATABLE READ에서는 잠금 없는 record 테이블 읽기가 낡을 수 있다(`store_mysql.py` docstring).

테스트 fixture가 시작할 때 case 테이블을 지우고 migration을 다시 올린다 — **테스트 전용 DB만** 가리킨다. migration(잠정 배치): `PYTHONPATH=src DAESINGO_MYSQL_URL=... alembic -c migrations/case/alembic.ini upgrade head`.
