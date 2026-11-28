"""Add separately scoped, short-lived MCP API credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_EVENTS = ("'owner_bootstrap','owner_login','owner_logout','pairing_issue','device_enroll','device_revoke',"
           "'policy_update','policy_pause','restore','source_create','source_pause','source_resume',"
           "'owner_session_rotate','private_config_update'")


def _rebuild(mcp: bool) -> None:
    op.drop_index("ix_security_audit_time", table_name="security_audit")
    op.rename_table("security_audit", "security_audit_old")
    events = _EVENTS + (",'mcp_issue','mcp_revoke'" if mcp else "")
    op.create_table("security_audit", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("event_type", sa.Text(), nullable=False), sa.Column("actor", sa.Text(), nullable=False),
                    sa.Column("status", sa.Text(), nullable=False), sa.Column("occurred_at", sa.Integer(), nullable=False),
                    sa.Column("correlation_id", sa.Text(), nullable=False, unique=True),
                    sa.CheckConstraint(f"event_type IN ({events})"),
                    sa.CheckConstraint("actor IN ('owner','device','local','system','anonymous')"),
                    sa.CheckConstraint("status IN ('success','denied')"),
                    sa.CheckConstraint("typeof(occurred_at) = 'integer' AND occurred_at >= 0"),
                    sa.CheckConstraint("length(correlation_id) = 36"))
    op.execute("INSERT INTO security_audit SELECT id,event_type,actor,status,occurred_at,correlation_id FROM security_audit_old")
    op.drop_table("security_audit_old")
    op.create_index("ix_security_audit_time", "security_audit", ["occurred_at", "id"])


def upgrade() -> None:
    _rebuild(True)
    op.create_table("mcp_credentials", sa.Column("id", sa.Text(), primary_key=True),
                    sa.Column("token_hash", sa.LargeBinary(), nullable=False, unique=True),
                    sa.Column("scope", sa.Text(), nullable=False), sa.Column("issued_at", sa.Integer(), nullable=False),
                    sa.Column("expires_at", sa.Integer(), nullable=False), sa.Column("last_seen", sa.Integer(), nullable=False),
                    sa.Column("revoked_at", sa.Integer()), sa.CheckConstraint("length(id)=36"),
                    sa.CheckConstraint("typeof(token_hash)='blob' AND length(token_hash)=32"),
                    sa.CheckConstraint("scope='status:read'"),
                    sa.CheckConstraint("typeof(issued_at)='integer' AND issued_at>=0"),
                    sa.CheckConstraint("expires_at=issued_at+900"),
                    sa.CheckConstraint("typeof(last_seen)='integer' AND last_seen>=issued_at"),
                    sa.CheckConstraint("revoked_at IS NULL OR (typeof(revoked_at)='integer' AND revoked_at>=issued_at)"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM mcp_credentials LIMIT 1")).first() or bind.execute(
        sa.text("SELECT 1 FROM security_audit WHERE event_type IN ('mcp_issue','mcp_revoke') LIMIT 1"),
    ).first():
        raise RuntimeError("Cannot discard MCP credentials or audit history; restore backup instead")
    op.drop_table("mcp_credentials")
    _rebuild(False)
