"""Create bounded pairing verifiers and scoped device credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pairing_codes",
        sa.Column("code_hash", sa.LargeBinary(), primary_key=True),
        sa.Column("owner_hash", sa.LargeBinary(), nullable=False),
        sa.Column("scope_mask", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("typeof(code_hash) = 'blob' AND length(code_hash) = 32"),
        sa.CheckConstraint("typeof(owner_hash) = 'blob' AND length(owner_hash) = 32"),
        sa.CheckConstraint("typeof(scope_mask) = 'integer' AND scope_mask BETWEEN 1 AND 7"),
        sa.CheckConstraint("typeof(issued_at) = 'integer' AND issued_at >= 0"),
        sa.CheckConstraint("expires_at = issued_at + 300"),
    )
    op.create_table(
        "devices",
        sa.Column("device_id", sa.Text(), primary_key=True),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("scope_mask", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("length(device_id) = 36"),
        sa.CheckConstraint("typeof(token_hash) = 'blob' AND length(token_hash) = 32"),
        sa.CheckConstraint("typeof(scope_mask) = 'integer' AND scope_mask BETWEEN 1 AND 7"),
        sa.CheckConstraint("typeof(created_at) = 'integer' AND created_at >= 0"),
        sa.CheckConstraint("last_seen IS NULL OR (typeof(last_seen) = 'integer' AND last_seen >= created_at)"),
        sa.CheckConstraint("revoked_at IS NULL OR (typeof(revoked_at) = 'integer' AND revoked_at >= created_at)"),
    )


def downgrade() -> None:
    op.drop_table("devices")
    op.drop_table("pairing_codes")
