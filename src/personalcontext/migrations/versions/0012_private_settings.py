"""Store disabled private HTTPS candidates and audit owner changes."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_EVENTS = ("'owner_bootstrap','owner_login','owner_logout','pairing_issue','device_enroll','device_revoke',"
           "'policy_update','policy_pause','restore','source_create','source_pause','source_resume','owner_session_rotate'")


def _rebuild(*, settings: bool) -> None:
    op.drop_index("ix_security_audit_time", table_name="security_audit")
    op.rename_table("security_audit", "security_audit_old")
    events = _EVENTS + (",'private_config_update'" if settings else "")
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
    _rebuild(settings=True)
    op.create_table(
        "private_network_candidate",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("peers", sa.Text(), nullable=False),
        sa.Column("cert_name", sa.Text(), nullable=False),
        sa.Column("key_name", sa.Text(), nullable=False),
        sa.Column("protected", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("singleton=1"),
        sa.CheckConstraint("typeof(revision)='integer' AND revision>=1"),
        sa.CheckConstraint("typeof(port)='integer' AND port BETWEEN 1 AND 65535"),
        sa.CheckConstraint("length(protected) BETWEEN 1 AND 8192"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM private_network_candidate LIMIT 1")).first() or bind.execute(
        sa.text("SELECT 1 FROM security_audit WHERE event_type='private_config_update' LIMIT 1"),
    ).first():
        raise RuntimeError("Cannot downgrade with private settings or audit history; restore backup instead")
    op.drop_table("private_network_candidate")
    _rebuild(settings=False)
