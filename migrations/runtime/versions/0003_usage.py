"""Typed in-flight tracking and immutable Final UsageRecord snapshots.

Frozen revision: do not import live metadata or application validators.
DECIMAL(65,30) rationale: Runtime Implementation Log RT-07(a), Plan P-10.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "runtime_0003"
down_revision = "runtime_0002"
branch_labels = None
depends_on = None


def _id(length=128):
    return sa.String(length, collation="ascii_bin")


def _columns():
    return [
        sa.Column("usage_id", _id(), primary_key=True),
        sa.Column("execution_ref", _id()),
        sa.Column("case_id", _id()),
        sa.Column("occurred_at", DATETIME(fsp=6), nullable=False),
        sa.Column("provider_label", sa.String(191), nullable=False),
        sa.Column("operation", sa.String(191), nullable=False),
        sa.Column("run_kind", _id(16)),
        sa.Column("run_ref", _id()),
        sa.Column("run_ref_reason", _id(32)),
        sa.Column("input_tokens", sa.BigInteger),
        sa.Column("output_tokens", sa.BigInteger),
        sa.Column("total_tokens", sa.BigInteger),
        sa.Column("processed_duration_sec", sa.Double),
        sa.Column("latency_ms", sa.BigInteger),
        sa.Column("pricing_id", sa.String(191), nullable=False),
        sa.Column("unit", sa.String(191), nullable=False),
        sa.Column("amount", sa.DECIMAL(65, 30)),
        sa.Column("currency", _id(3), nullable=False),
    ]


def _checks(name, pending=False):
    # ascii_bin is PAD SPACE; enum membership must compare the exact bytes.
    run = (
        "(run_kind IS NOT NULL AND run_ref IS NOT NULL "
        "AND CAST(run_kind AS BINARY) IN ('analysis_run','readout_run') AND run_ref_reason IS NULL) OR "
        "(run_kind IS NULL AND run_ref IS NULL AND run_ref_reason IS NOT NULL "
        "AND CAST(run_ref_reason AS BINARY) IN ('DIRECT_NO_RUN','RUN_NOT_PRODUCED'))"
    )
    if pending:
        run += " OR (run_kind IS NULL AND run_ref IS NULL AND run_ref_reason IS NULL)"
    return [
        sa.CheckConstraint(
            "(input_tokens IS NULL AND output_tokens IS NULL AND total_tokens IS NULL) OR "
            "(input_tokens IS NOT NULL AND output_tokens IS NOT NULL AND total_tokens IS NOT NULL)",
            name=f"ck_{name}_token_complete"),
        sa.CheckConstraint("input_tokens IS NULL OR total_tokens = input_tokens + output_tokens",
                           name=f"ck_{name}_token_total"),
        sa.CheckConstraint("currency = 'KRW'", name=f"ck_{name}_currency"),
        sa.CheckConstraint(run, name=f"ck_{name}_run"),
    ]


def upgrade() -> None:
    op.create_table(
        "usage_inflight", *_columns(),
        sa.Column("state", _id(16), nullable=False),
        sa.Column("outcome", _id(16)),
        sa.Column("failure_kind", sa.String(191)),
        sa.Column("observed_at", DATETIME(fsp=6)),
        sa.Column("finalized_at", DATETIME(fsp=6)),
        *_checks("usage_inflight", pending=True),
        sa.CheckConstraint("CAST(state AS BINARY) IN ('STARTED','OBSERVED','FINALIZED')", name="ck_usage_inflight_state"),
        sa.CheckConstraint("outcome IS NULL OR CAST(outcome AS BINARY) IN ('SUCCEEDED','FAILED')", name="ck_usage_inflight_outcome"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_usage_inflight_execution_ref", "usage_inflight", ["execution_ref"])
    op.create_table("usage_record", *_columns(), *_checks("usage_record"),
                    mysql_engine="InnoDB", mysql_charset="utf8mb4")
    op.create_index("ix_usage_record_execution_ref", "usage_record", ["execution_ref"])


def downgrade() -> None:
    raise NotImplementedError("forward-only (runtime-tech-spec §4.4)")
