"""Create the pending owner bootstrap verifier."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_codes",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("singleton = 1"),
        sa.CheckConstraint("typeof(code_hash) = 'blob' AND length(code_hash) = 32"),
        sa.CheckConstraint("expires_at = issued_at + 300"),
        sa.CheckConstraint("attempts >= 0 AND attempts < 5"),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_codes")
