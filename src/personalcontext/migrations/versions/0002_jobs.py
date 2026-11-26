"""Create the durable job queue."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("idempotency_key", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_at", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lease_until", sa.Float(), nullable=True),
        sa.Column("lease_token", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'running', 'done', 'failed')"),
    )
    op.create_index("ix_jobs_due", "jobs", ["status", "retry_at", "lease_until"])


def downgrade():
    op.drop_index("ix_jobs_due", table_name="jobs")
    op.drop_table("jobs")
