"""Private receipt for one claim invocation across unknown COMMIT outcomes."""

from alembic import op
import sqlalchemy as sa

revision = "runtime_0002"
down_revision = "runtime_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_execution", sa.Column(
        "claim_token", sa.String(128, collation="ascii_bin"), nullable=True,
    ))


def downgrade() -> None:
    raise NotImplementedError("forward-only (runtime-tech-spec §4.4)")
