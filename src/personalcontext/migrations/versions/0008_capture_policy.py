"""Add a default-deny, versioned owner capture policy."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_policy",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Integer(), nullable=False),
        sa.CheckConstraint("singleton = 1"),
        sa.CheckConstraint("typeof(version) = 'integer' AND version >= 1"),
        sa.CheckConstraint("typeof(issued_at) = 'integer' AND issued_at >= 0"),
        sa.CheckConstraint("typeof(expires_at) = 'integer' AND expires_at >= issued_at"),
        sa.CheckConstraint("typeof(paused) = 'integer' AND paused IN (0, 1)"),
    )
    op.create_table(
        "capture_policy_sources",
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("disposition", sa.Text(), primary_key=True),
        sa.CheckConstraint("disposition IN ('allow','deny')"),
    )
    op.create_table(
        "capture_policy_grants",
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.CheckConstraint("scope IN ('metadata','text','ocr')"),
    )
    op.execute("INSERT INTO capture_policy VALUES (1,1,0,0,1)")


def downgrade() -> None:
    op.drop_table("capture_policy_grants")
    op.drop_table("capture_policy_sources")
    op.drop_table("capture_policy")
