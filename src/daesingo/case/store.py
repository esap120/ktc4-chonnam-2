"""case 저장소 — repository(in-memory · MySQL) · adapter registry · `CaseStore` facade. `decisions/case-store-mysql.md`."""

from __future__ import annotations

import copy
import dataclasses
import json
from typing import Any, Literal, Protocol

from daesingo.case.adapters import ModuleAdapter
from daesingo.case.domain import CaseAggregate
from daesingo.case.store_state import CaseRow, from_row, to_row

CASE_ID_MAX = 128  # `cases.case_id` VARCHAR(128) ascii_bin


class CaseNotFound(KeyError):
    """등록되지 않은 case_id — `KeyError`라서 기존 `except KeyError`(command의 unknown_target)가 그대로 잡는다."""


class CaseAlreadyExists(ValueError):
    pass


class AppendOnlyViolation(RuntimeError):
    """저장된 레코드의 앞부분이 바뀌거나 지워졌다 — 정상 경로에서는 나지 않는 프로그래밍 오류."""


class InvalidCaseId(ValueError):
    pass


def validate_case_id(case_id: str) -> None:
    if not case_id or len(case_id) > CASE_ID_MAX or not case_id.isascii():
        raise InvalidCaseId(f"case_id는 1~{CASE_ID_MAX}자 ASCII여야 한다: {case_id!r}")


class CaseRepository(Protocol):
    """case 저장소. `conn`은 호출자의 SQLAlchemy `Connection`이고 transaction도 호출자 것이다 —
    저장소는 commit · rollback하지 않는다(#245 D-2). in-memory 구현은 `conn`을 무시한다."""

    def insert(self, conn: Any, case: CaseAggregate) -> None: ...
    def load(self, conn: Any, case_id: str, *, lock: Literal["share", "update"] = "share") -> CaseAggregate: ...
    def save(self, conn: Any, case: CaseAggregate) -> None: ...


def check_append_only(stored_ids: list[str], current_ids: list[str], what: str) -> None:
    if current_ids[: len(stored_ids)] != stored_ids:
        raise AppendOnlyViolation(f"{what}의 저장된 앞부분이 바뀌었다")


def _json_round_trip(row: CaseRow) -> CaseRow:
    """MySQL JSON 칼럼과 같게 — tuple은 list, 키는 str, datetime · set 같은 비JSON 값은 TypeError."""
    return dataclasses.replace(
        row,
        state=json.loads(json.dumps(row.state)),
        job_records=json.loads(json.dumps(row.job_records)),
        correction_records=json.loads(json.dumps(row.correction_records)),
        analysis_scopes=json.loads(json.dumps(row.analysis_scopes)),
    )


class InMemoryCaseRepository:
    """테스트 · 로컬용. load는 늘 새 객체를 준다 — 같은 객체를 주면 save를 빠뜨려도 테스트가 통과해
    MySQL에서만 상태가 사라진다(`decisions/case-store-mysql.md` §5)."""

    def __init__(self) -> None:
        self._rows: dict[str, CaseRow] = {}

    def insert(self, conn: Any, case: CaseAggregate) -> None:
        validate_case_id(case.case_id)
        if case.case_id in self._rows:
            raise CaseAlreadyExists(f"case_id는 재등록할 수 없다: {case.case_id!r}")
        self._rows[case.case_id] = _json_round_trip(to_row(case))

    def load(self, conn: Any, case_id: str, *, lock: Literal["share", "update"] = "share") -> CaseAggregate:
        try:
            row = self._rows[case_id]
        except KeyError:
            raise CaseNotFound(f"등록되지 않은 case_id: {case_id!r}") from None
        return from_row(copy.deepcopy(row))

    def save(self, conn: Any, case: CaseAggregate) -> None:
        stored = self._rows.get(case.case_id)
        if stored is None:
            raise CaseNotFound(f"등록되지 않은 case_id: {case.case_id!r}")
        new = _json_round_trip(to_row(case))
        check_append_only([r["job_id"] for r in stored.job_records], [r["job_id"] for r in new.job_records], "job_records")
        check_append_only(
            [r["correction_id"] for r in stored.correction_records],
            [r["correction_id"] for r in new.correction_records],
            "correction_records",
        )
        for scope_id, scope in stored.analysis_scopes.items():
            if new.analysis_scopes.get(scope_id) != scope:
                raise AppendOnlyViolation(f"analysis_scopes {scope_id!r}가 바뀌거나 지워졌다")
        self._rows[case.case_id] = new


class AdapterRegistry:
    """case_id → adapter(process 메모리). adapter는 2단계에서 없앨 대상이라 DB에 넣지 않는다.

    `RealAdapter` · `RealVideoAdapter`는 생성 때 받은 aggregate를 들고 있다. load가 늘 새 객체를 주므로
    요청마다 방금 로드한 aggregate를 `bind_case`로 다시 붙인다(spec §5)."""

    def __init__(self) -> None:
        self._by_case: dict[str, ModuleAdapter | None] = {}

    def put(self, case_id: str, adapter: ModuleAdapter | None) -> None:
        self._by_case[case_id] = adapter

    def for_case(self, case_id: str, case: CaseAggregate | None = None) -> ModuleAdapter | None:
        adapter = self._by_case.get(case_id)
        if adapter is not None and case is not None and hasattr(adapter, "bind_case"):
            adapter.bind_case(case)
        return adapter


class CaseStore:
    """repository · conn · adapter registry를 묶는다. 진입점(`get_view` · `execute_command` · `create_case` ·
    `record_source_registered`)은 이것 하나를 받는다 — composition root는 요청 transaction마다
    `CaseStore(repository=MySQLCaseRepository(), adapters=registry, conn=connection)`을 만든다.
    기본값은 in-memory(테스트 · 로컬). MySQL transaction은 READ COMMITTED여야 한다 — `MySQLCaseRepository` docstring 참고."""

    def __init__(
        self,
        repository: CaseRepository | None = None,
        adapters: AdapterRegistry | None = None,
        conn: Any = None,
    ) -> None:
        self.repository: CaseRepository = repository if repository is not None else InMemoryCaseRepository()
        self.adapters = adapters if adapters is not None else AdapterRegistry()
        self.conn = conn

    def register(self, case: CaseAggregate, adapter: ModuleAdapter | None = None) -> None:
        """`adapter=None`은 빈 case(`service.create_case()`)다 — 선택 전에는 adapter를 조회하지 않는다."""
        self.repository.insert(self.conn, case)
        self.adapters.put(case.case_id, adapter)

    def get_case(self, case_id: str) -> CaseAggregate:
        return self.repository.load(self.conn, case_id, lock="share")

    def load_for_update(self, case_id: str) -> CaseAggregate:
        return self.repository.load(self.conn, case_id, lock="update")

    def save(self, case: CaseAggregate) -> None:
        self.repository.save(self.conn, case)

    def get_adapter(self, case_id: str, case: CaseAggregate | None = None) -> ModuleAdapter | None:
        return self.adapters.for_case(case_id, case)
