"""Add an explicit, payload-free session rotation audit event."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_BASE = ("'owner_bootstrap','owner_login','owner_logout','pairing_issue','device_enroll','device_revoke',"
         "'policy_update','policy_pause','restore','source_create','source_pause','source_resume'")


def _rebuild(*, rotation: bool) -> None:
    op.drop_index("ix_security_audit_time", table_name="security_audit")
    op.rename_table("security_audit", "security_audit_old")
    events = _BASE + (",'owner_session_rotate'" if rotation else "")
    op.create_table(
        "security_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False, unique=True),
        sa.CheckConstraint(f"event_type IN ({events})"),
        sa.CheckConstraint("actor IN ('owner','device','local','system','anonymous')"),
        sa.CheckConstraint("status IN ('success','denied')"),
        sa.CheckConstraint("typeof(occurred_at) = 'integer' AND occurred_at >= 0"),
        sa.CheckConstraint("length(correlation_id) = 36"),
    )
    op.execute("INSERT INTO security_audit SELECT id,event_type,actor,status,occurred_at,correlation_id FROM security_audit_old")
    op.drop_table("security_audit_old")
    op.create_index("ix_security_audit_time", "security_audit", ["occurred_at", "id"])


def upgrade() -> None:
    _rebuild(rotation=True)


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM security_audit WHERE event_type='owner_session_rotate' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while rotation audit history exists; restore backup instead")
    _rebuild(rotation=False)
