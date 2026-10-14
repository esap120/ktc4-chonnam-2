"""Preserve declared Run intent and recovery/late-observation receipts.

Frozen tracker-only revision. Final UsageRecord columns/meaning are unchanged.
"""

from alembic import op

revision = "runtime_0004"
down_revision = "runtime_0003"
branch_labels = None
depends_on = None


def upgrade():
    # One MySQL ALTER avoids six additional DDL round trips. Keep this
    # frozen SQL independent of live metadata; actual SHOW CREATE fidelity is
    # verified against metadata and an upgraded runtime_0003 with retained rows.
    op.execute("""
        ALTER TABLE usage_inflight
        ADD COLUMN planned_run_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NULL,
        ADD COLUMN planned_run_ref VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
        ADD COLUMN direct_no_run BOOL NOT NULL DEFAULT 0,
        ADD COLUMN recovered_at DATETIME(6) NULL,
        ADD COLUMN late_observed_at DATETIME(6) NULL,
        ADD CONSTRAINT ck_usage_inflight_intent CHECK (
            (planned_run_kind IS NULL AND planned_run_ref IS NULL) OR
            (planned_run_kind IS NOT NULL AND planned_run_ref IS NOT NULL AND
             CAST(planned_run_kind AS BINARY) IN ('analysis_run','readout_run') AND direct_no_run = 0)),
        ADD CONSTRAINT ck_usage_inflight_direct CHECK (direct_no_run IN (0,1))
    """)


def downgrade():
    raise NotImplementedError("forward-only runtime migration")
