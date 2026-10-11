"""case MySQL 저장소 — `decisions/case-store-mysql.md` §4 · §5. sqlalchemy는 이 파일에서만 import한다
(in-memory만 쓰는 테스트 · 스크립트가 DB 의존성 없이 돌게)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from daesingo.case.domain import CaseAggregate
from daesingo.case.store import (
    AppendOnlyViolation,
    CaseAlreadyExists,
    CaseNotFound,
    check_append_only,
    validate_case_id,
)
from daesingo.case.store_state import CaseRow, from_row, to_row

metadata = sa.MetaData()

_ID = 128  # case_id · scope_id
_RECORD_ID = 191  # job_id · correction_id — `job_{case_id}_{kind}_{uuid8}`가 들어가게


def _id(length: int = _ID) -> sa.String:
    return sa.String(length, collation="ascii_bin")


cases_table = sa.Table(
    "cases",
    metadata,
    sa.Column("case_id", _id(), primary_key=True),
    sa.Column("case_rev", sa.Integer, nullable=False),
    sa.Column("stage", sa.String(32), nullable=False),
    sa.Column("selection_rev", sa.Integer, nullable=False),
    sa.Column("state", sa.JSON, nullable=False),
    sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
    sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

job_records_table = sa.Table(
    "job_records",
    metadata,
    sa.Column("job_id", _id(_RECORD_ID), primary_key=True),
    sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("record", sa.JSON, nullable=False),
    sa.UniqueConstraint("case_id", "seq", name="uq_job_records_case_seq"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

correction_records_table = sa.Table(
    "correction_records",
    metadata,
    sa.Column("correction_id", _id(_RECORD_ID), primary_key=True),
    sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("record", sa.JSON, nullable=False),
    sa.UniqueConstraint("case_id", "seq", name="uq_correction_records_case_seq"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

analysis_scopes_table = sa.Table(
    "analysis_scopes",
    metadata,
    sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), primary_key=True),
    sa.Column("scope_id", _id(), primary_key=True),
    sa.Column("scope", sa.JSON, nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MySQLCaseRepository:
    """호출자의 `Connection`에 참여한다 — commit · rollback하지 않는다(#245 D-2). 상태를 들지 않는다:
    「무엇이 이미 저장됐나」는 매번 DB에서 읽는다(spec §5). 잠금은 `cases` 행에만 건다 — case 행 먼저.

    격리 요건: 호출자의 transaction은 READ COMMITTED여야 한다(예: `create_engine(url, isolation_level="READ COMMITTED")`,
    runtime decision #250 01b). 아니면 `load(lock="update")`가 transaction의 첫 읽기여야 한다 — REPEATABLE READ에서는
    먼저 한 일관 읽기가 행 잠금보다 오래된 snapshot을 고정해 잠금 없는 record 테이블 읽기가 낡을 수 있다."""

    def insert(self, conn: Any, case: CaseAggregate) -> None:
        validate_case_id(case.case_id)
        row = to_row(case)
        now = _now()
        try:
            conn.execute(cases_table.insert().values(
                case_id=row.case_id, case_rev=row.case_rev, stage=row.stage, selection_rev=row.selection_rev,
                state=row.state, created_at=now, updated_at=now,
            ))
        except sa.exc.IntegrityError:
            raise CaseAlreadyExists(f"case_id는 재등록할 수 없다: {case.case_id!r}") from None
        self._append_records(conn, row, job_from=0, correction_from=0, existing_scopes=set())

    def load(self, conn: Any, case_id: str, *, lock: Literal["share", "update"] = "share") -> CaseAggregate:
        query = sa.select(cases_table).where(cases_table.c.case_id == case_id)
        query = query.with_for_update(read=(lock == "share"))
        head = conn.execute(query).mappings().first()
        if head is None:
            raise CaseNotFound(f"등록되지 않은 case_id: {case_id!r}")
        return from_row(CaseRow(
            case_id=head["case_id"], case_rev=head["case_rev"], stage=head["stage"],
            selection_rev=head["selection_rev"], state=head["state"],
            job_records=self._records(conn, job_records_table, case_id),
            correction_records=self._records(conn, correction_records_table, case_id),
            analysis_scopes={
                r["scope_id"]: r["scope"]
                for r in conn.execute(
                    sa.select(analysis_scopes_table).where(analysis_scopes_table.c.case_id == case_id)
                ).mappings()
            },
        ))

    def save(self, conn: Any, case: CaseAggregate) -> None:
        row = to_row(case)
        # 검사를 모든 쓰기보다 먼저 한다 — 저장소는 rollback하지 않으므로, 호출자가 예외를 삼키고 commit해도
        # `cases` 행만 바뀐 반쪽 상태가 남지 않게(#282 Runtime 리뷰).
        stored_jobs = self._ids(conn, job_records_table, "job_id", row.case_id)
        stored_corrections = self._ids(conn, correction_records_table, "correction_id", row.case_id)
        check_append_only(stored_jobs, [r["job_id"] for r in row.job_records], "job_records")
        check_append_only(stored_corrections, [r["correction_id"] for r in row.correction_records], "correction_records")
        stored_scopes = {
            r["scope_id"]: r["scope"]
            for r in conn.execute(
                sa.select(analysis_scopes_table).where(analysis_scopes_table.c.case_id == row.case_id)
            ).mappings()
        }
        for scope_id, scope in stored_scopes.items():
            if row.analysis_scopes.get(scope_id) != scope:
                raise AppendOnlyViolation(f"analysis_scopes {scope_id!r}가 바뀌거나 지워졌다")
        result = conn.execute(
            cases_table.update().where(cases_table.c.case_id == row.case_id).values(
                case_rev=row.case_rev, stage=row.stage, selection_rev=row.selection_rev,
                state=row.state, updated_at=_now(),
            )
        )
        if result.rowcount == 0:
            raise CaseNotFound(f"등록되지 않은 case_id: {row.case_id!r}")
        self._append_records(
            conn, row, job_from=len(stored_jobs), correction_from=len(stored_corrections),
            existing_scopes=set(stored_scopes),
        )

    @staticmethod
    def _records(conn: Any, table: sa.Table, case_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(sa.select(table.c.record).where(table.c.case_id == case_id).order_by(table.c.seq))
        return [r[0] for r in rows]

    @staticmethod
    def _ids(conn: Any, table: sa.Table, id_col: str, case_id: str) -> list[str]:
        rows = conn.execute(sa.select(table.c[id_col]).where(table.c.case_id == case_id).order_by(table.c.seq))
        return [r[0] for r in rows]

    @staticmethod
    def _append_records(conn: Any, row: CaseRow, *, job_from: int, correction_from: int, existing_scopes: set[str]) -> None:
        jobs = [
            {"job_id": r["job_id"], "case_id": row.case_id, "seq": i, "record": r}
            for i, r in enumerate(row.job_records) if i >= job_from
        ]
        corrections = [
            {"correction_id": r["correction_id"], "case_id": row.case_id, "seq": i, "record": r}
            for i, r in enumerate(row.correction_records) if i >= correction_from
        ]
        scopes = [
            {"case_id": row.case_id, "scope_id": sid, "scope": s}
            for sid, s in row.analysis_scopes.items() if sid not in existing_scopes
        ]
        if jobs:
            conn.execute(job_records_table.insert(), jobs)
        if corrections:
            conn.execute(correction_records_table.insert(), corrections)
        if scopes:
            conn.execute(analysis_scopes_table.insert(), scopes)
