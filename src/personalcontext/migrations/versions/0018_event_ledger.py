"""Add a bounded event ledger; no collector or ingress is enabled."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ux_sources_identity", "sources", ["source_id", "device_id"], unique=True)
    op.create_table(
        "events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("device_id", sa.Text(), sa.ForeignKey("devices.device_id"), nullable=False),
        sa.Column("source_id", sa.Text(), sa.ForeignKey("sources.source_id"), nullable=False),
        sa.Column("source_event_key", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.LargeBinary(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("ended_at", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("granularity", sa.Text(), nullable=False),
        sa.Column("quality", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("consent_scope", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("received_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("job_key", sa.Text(), sa.ForeignKey("jobs.idempotency_key"), nullable=False, unique=True),
        sa.ForeignKeyConstraint(["source_id", "device_id"], ["sources.source_id", "sources.device_id"]),
        sa.UniqueConstraint("source_id", "source_event_key"),
        sa.CheckConstraint("length(event_id)=36 AND length(device_id)=36 AND length(source_id)=36"),
        sa.CheckConstraint("length(source_event_key) BETWEEN 1 AND 256"),
        sa.CheckConstraint("typeof(body_hash)='blob' AND length(body_hash)=32"),
        sa.CheckConstraint("schema_version=1"),
        sa.CheckConstraint("kind IN ('app_active','idle','lock','web_visit','web_active','media_play',"
                           "'shared_item','document_reference','imported_visit','note','ocr_text')"),
        sa.CheckConstraint("length(started_at) BETWEEN 1 AND 128 AND length(observed_at) BETWEEN 1 AND 128 "
                           "AND (ended_at IS NULL OR length(ended_at) BETWEEN 1 AND 128)"),
        sa.CheckConstraint("length(timezone) BETWEEN 1 AND 128"),
        sa.CheckConstraint("granularity IN ('point','interval') AND (granularity!='point' OR duration_ms IS NULL)"),
        sa.CheckConstraint("duration_ms IS NULL OR (typeof(duration_ms)='integer' AND duration_ms BETWEEN 0 AND 900000)"),
        sa.CheckConstraint("quality IN ('measured','imported','estimated','unknown')"),
        sa.CheckConstraint("typeof(policy_version)='integer' AND policy_version>=1"),
        sa.CheckConstraint("consent_scope IN ('metadata','text','ocr')"),
        sa.CheckConstraint("length(CAST(payload_json AS BLOB))<=1048576 AND "
                           "length(CAST(provenance_json AS BLOB))<=16384 AND "
                           "json_valid(payload_json) AND json_valid(provenance_json)"),
        sa.CheckConstraint("typeof(received_at)='integer' AND received_at>=0 AND "
                           "typeof(expires_at)='integer' AND expires_at>received_at"),
    )
    op.create_index("ix_events_source_time", "events", ["source_id", "started_at", "event_id"])


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM events LIMIT 1")).first():
        raise RuntimeError("Cannot discard event ledger; restore a verified backup")
    op.drop_index("ix_events_source_time", table_name="events")
    op.drop_table("events")
    op.drop_index("ux_sources_identity", table_name="sources")
