"""Runtime-owned queue/ledger table. DATETIME(6) values are stored in UTC.

Keep the frozen migration independent of this live metadata. No cross-module FK,
contract envelope columns or usage_refs mirror are stored here.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

metadata = sa.MetaData()


def _id(length=128):
    return sa.String(length, collation="ascii_bin")


job_execution = sa.Table(
    "job_execution", metadata,
    sa.Column("execution_id", _id(), primary_key=True),
    sa.Column("job_id", _id(191), nullable=False),
    sa.Column("status", _id(16), nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("queued_at", DATETIME(fsp=6), nullable=False),
    sa.Column("started_at", DATETIME(fsp=6)),
    sa.Column("ended_at", DATETIME(fsp=6)),
    sa.Column("produced", sa.JSON, nullable=False),
    sa.Column("failure_kind", sa.String(191)),
    sa.Column("available_at", DATETIME(fsp=6), nullable=False),
    sa.Column("lease_owner", _id()),
    sa.Column("claim_token", _id()),
    sa.Column("lease_expires_at", DATETIME(fsp=6)),
    sa.Column("heartbeat_at", DATETIME(fsp=6)),
    sa.Column("cancel_requested_at", DATETIME(fsp=6)),
    sa.Column("case_applied_at", DATETIME(fsp=6)),
    sa.Column("trace_id", _id(), nullable=False),
    sa.Column("kind", _id(64), nullable=False),
    sa.Column("case_id", _id(), nullable=False),
    sa.CheckConstraint("attempt >= 1", name="ck_job_execution_attempt"),
    sa.CheckConstraint("status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','STALE','CANCELLED')",
                       name="ck_job_execution_status"),
    sa.UniqueConstraint("job_id", "attempt", name="uq_job_execution_job_attempt"),
    sa.Index("ix_job_execution_claim", "status", "available_at", "execution_id"),
    sa.Index("ix_job_execution_job_id", "job_id"),
    mysql_engine="InnoDB", mysql_charset="utf8mb4",
)
