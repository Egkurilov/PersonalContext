"""Create bounded-content, identifier-free security audit records."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False, unique=True),
        sa.CheckConstraint("event_type IN ('owner_bootstrap','owner_login','owner_logout','pairing_issue',"
                           "'device_enroll','device_revoke','policy_update','policy_pause','restore')"),
        sa.CheckConstraint("actor IN ('owner','device','local','system','anonymous')"),
        sa.CheckConstraint("status IN ('success','denied')"),
        sa.CheckConstraint("typeof(occurred_at) = 'integer' AND occurred_at >= 0"),
        sa.CheckConstraint("length(correlation_id) = 36"),
    )
    op.create_index("ix_security_audit_time", "security_audit", ["occurred_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_security_audit_time", table_name="security_audit")
    op.drop_table("security_audit")
