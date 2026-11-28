"""Store owner-approved sanitizer filters, empty and deny-by-default."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("privacy_filter_rules", sa.Column("kind", sa.Text(), nullable=False),
                    sa.Column("value", sa.Text(), nullable=False), sa.PrimaryKeyConstraint("kind", "value"),
                    sa.CheckConstraint("kind IN ('allowed_domains','denied_domains','allowed_apps','denied_apps')"),
                    sa.CheckConstraint("typeof(value)='text' AND length(value) BETWEEN 1 AND 253"))


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM privacy_filter_rules LIMIT 1")).first():
        raise RuntimeError("Cannot discard privacy filters; restore a verified backup instead")
    op.drop_table("privacy_filter_rules")
