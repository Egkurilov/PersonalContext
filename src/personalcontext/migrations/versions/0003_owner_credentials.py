"""Create the single-owner password-hash record."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_credentials",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("singleton = 1"),
        sa.CheckConstraint("length(password_hash) BETWEEN 1 AND 256"),
    )


def downgrade() -> None:
    op.drop_table("owner_credentials")
