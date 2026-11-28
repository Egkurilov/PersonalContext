"""Record observed session time; old sessions lack a trustworthy watermark."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM owner_sessions")
    op.add_column("owner_sessions", sa.Column("last_seen", sa.Integer(),
                  sa.CheckConstraint("typeof(last_seen)='integer' AND last_seen>=issued_at AND last_seen<expires_at"),
                  nullable=False, server_default="0"))


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM owner_sessions LIMIT 1")).first():
        raise RuntimeError("Cannot discard session clock state; revoke sessions or restore a verified backup")
    op.drop_column("owner_sessions", "last_seen")
