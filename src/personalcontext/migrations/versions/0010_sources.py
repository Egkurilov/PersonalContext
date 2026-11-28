"""Bind owner-approved sources to devices and extend audit categories."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_BASE = "'owner_bootstrap','owner_login','owner_logout','pairing_issue','device_enroll','device_revoke','policy_update','policy_pause','restore'"
_SOURCES = ",'source_create','source_pause','source_resume'"


def _rebuild_audit(*, include_sources: bool) -> None:
    op.drop_index("ix_security_audit_time", table_name="security_audit")
    op.rename_table("security_audit", "security_audit_old")
    categories = _BASE + (_SOURCES if include_sources else "")
    op.create_table(
        "security_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False, unique=True),
        sa.CheckConstraint(f"event_type IN ({categories})"),
        sa.CheckConstraint("actor IN ('owner','device','local','system','anonymous')"),
        sa.CheckConstraint("status IN ('success','denied')"),
        sa.CheckConstraint("typeof(occurred_at) = 'integer' AND occurred_at >= 0"),
        sa.CheckConstraint("length(correlation_id) = 36"),
    )
    op.execute("INSERT INTO security_audit SELECT id,event_type,actor,status,occurred_at,correlation_id FROM security_audit_old")
    op.drop_table("security_audit_old")
    op.create_index("ix_security_audit_time", "security_audit", ["occurred_at", "id"])


def upgrade() -> None:
    _rebuild_audit(include_sources=True)
    op.create_table(
        "sources",
        sa.Column("source_id", sa.Text(), primary_key=True),
        sa.Column("device_id", sa.Text(), sa.ForeignKey("devices.device_id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("paused", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(source_id) = 36"),
        sa.CheckConstraint("kind IN ('browser','windows')"),
        sa.CheckConstraint("typeof(paused) = 'integer' AND paused IN (0,1)"),
        sa.CheckConstraint("typeof(revision) = 'integer' AND revision >= 1"),
        sa.CheckConstraint("typeof(created_at) = 'integer' AND created_at >= 0"),
        sa.CheckConstraint("typeof(updated_at) = 'integer' AND updated_at >= created_at"),
    )
    op.create_index("ix_sources_device", "sources", ["device_id", "source_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM sources LIMIT 1")).first() or bind.execute(
        sa.text("SELECT 1 FROM security_audit WHERE event_type IN ('source_create','source_pause','source_resume') LIMIT 1"),
    ).first():
        raise RuntimeError("Cannot downgrade while source state or audit history exists; restore backup instead")
    op.drop_index("ix_sources_device", table_name="sources")
    op.drop_table("sources")
    _rebuild_audit(include_sources=False)
