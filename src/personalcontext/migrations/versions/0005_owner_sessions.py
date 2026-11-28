"""Create hashed owner sessions and CSRF verifiers."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_sessions",
        sa.Column("token_hash", sa.LargeBinary(), primary_key=True),
        sa.Column("csrf_hash", sa.LargeBinary(), nullable=False),
        sa.Column("credential_hash", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("typeof(token_hash) = 'blob' AND length(token_hash) = 32"),
        sa.CheckConstraint("typeof(csrf_hash) = 'blob' AND length(csrf_hash) = 32"),
        sa.CheckConstraint("typeof(credential_hash) = 'blob' AND length(credential_hash) = 32"),
        sa.CheckConstraint("issued_at >= 0"),
        sa.CheckConstraint("expires_at = issued_at + 1800"),
    )


def downgrade() -> None:
    op.drop_table("owner_sessions")
