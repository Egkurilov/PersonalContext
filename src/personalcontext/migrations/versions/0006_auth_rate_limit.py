"""Create bounded, identifier-free authentication rate state."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_clocks",
        sa.Column("action", sa.Text(), primary_key=True),
        sa.Column("last_seen", sa.Integer(), nullable=False),
        sa.CheckConstraint("action IN ('owner_login', 'owner_bootstrap', 'device_enroll')"),
        sa.CheckConstraint("typeof(last_seen) = 'integer' AND last_seen >= 0"),
    )
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.Text(), sa.ForeignKey("auth_rate_clocks.action", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("typeof(occurred_at) = 'integer' AND occurred_at >= 0"),
    )
    op.create_index("ix_auth_attempts_window", "auth_attempts", ["action", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_window", table_name="auth_attempts")
    op.drop_table("auth_attempts")
    op.drop_table("auth_rate_clocks")
