"""Live usage metadata, checked against frozen runtime_0003 + runtime_0004.

Shared usage_id is the logical link; no FK couples Final to tracker retention
or other modules. Run linkage may be pending only in the internal tracker.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from .amount import ExactAmount

metadata = sa.MetaData()


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
        sa.Column("amount", ExactAmount()),
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


usage_inflight = sa.Table(
    "usage_inflight", metadata, *_columns(),
    sa.Column("state", _id(16), nullable=False),
    sa.Column("outcome", _id(16)),
    sa.Column("failure_kind", sa.String(191)),
    sa.Column("observed_at", DATETIME(fsp=6)),
    sa.Column("finalized_at", DATETIME(fsp=6)),
    sa.Column("planned_run_kind", _id(16)),
    sa.Column("planned_run_ref", _id()),
    sa.Column("direct_no_run", sa.Boolean, nullable=False, server_default=sa.text("0")),
    sa.Column("recovered_at", DATETIME(fsp=6)),
    sa.Column("late_observed_at", DATETIME(fsp=6)),
    *_checks("usage_inflight", pending=True),
    sa.CheckConstraint("CAST(state AS BINARY) IN ('STARTED','OBSERVED','FINALIZED')", name="ck_usage_inflight_state"),
    sa.CheckConstraint("outcome IS NULL OR CAST(outcome AS BINARY) IN ('SUCCEEDED','FAILED')", name="ck_usage_inflight_outcome"),
    sa.CheckConstraint(
        "(planned_run_kind IS NULL AND planned_run_ref IS NULL) OR "
        "(planned_run_kind IS NOT NULL AND planned_run_ref IS NOT NULL AND "
        "CAST(planned_run_kind AS BINARY) IN ('analysis_run','readout_run') AND direct_no_run = 0)",
        name="ck_usage_inflight_intent"),
    sa.CheckConstraint("direct_no_run IN (0,1)", name="ck_usage_inflight_direct"),
    sa.Index("ix_usage_inflight_execution_ref", "execution_ref"),
    mysql_engine="InnoDB", mysql_charset="utf8mb4",
)

usage_record = sa.Table(
    "usage_record", metadata, *_columns(), *_checks("usage_record"),
    sa.Index("ix_usage_record_execution_ref", "execution_ref"),
    mysql_engine="InnoDB", mysql_charset="utf8mb4",
)
