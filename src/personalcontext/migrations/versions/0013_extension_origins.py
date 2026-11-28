"""Bind browser origins to one-time codes and device credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("extension_pairings",
                    sa.Column("code_hash", sa.LargeBinary(), sa.ForeignKey("pairing_codes.code_hash", ondelete="CASCADE"), primary_key=True),
                    sa.Column("origin", sa.Text(), nullable=False),
                    sa.CheckConstraint("length(origin)=51"))
    op.create_table("extension_devices",
                    sa.Column("device_id", sa.Text(), sa.ForeignKey("devices.device_id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("origin", sa.Text(), nullable=False),
                    sa.CheckConstraint("length(origin)=51"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM extension_pairings LIMIT 1")).first() or bind.execute(
        sa.text("SELECT 1 FROM extension_devices LIMIT 1"),
    ).first():
        raise RuntimeError("Cannot discard origin bindings; restore backup instead")
    op.drop_table("extension_devices")
    op.drop_table("extension_pairings")
