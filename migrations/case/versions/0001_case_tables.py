"""case 테이블 4개 — `decisions/case-store-mysql.md` §4."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "case_0001"
down_revision = None
branch_labels = None
depends_on = None


def _id(length=128):
    return sa.String(length, collation="ascii_bin")


def upgrade() -> None:
    op.create_table(
        "cases",
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
    for name, id_col in (("job_records", "job_id"), ("correction_records", "correction_id")):
        op.create_table(
            name,
            sa.Column(id_col, _id(191), primary_key=True),
            sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), nullable=False),
            sa.Column("seq", sa.Integer, nullable=False),
            sa.Column("record", sa.JSON, nullable=False),
            sa.UniqueConstraint("case_id", "seq", name=f"uq_{name}_case_seq"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
        )
    op.create_table(
        "analysis_scopes",
        sa.Column("case_id", _id(), sa.ForeignKey("cases.case_id"), primary_key=True),
        sa.Column("scope_id", _id(), primary_key=True),
        sa.Column("scope", sa.JSON, nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only (runtime-tech-spec §4.4)")
