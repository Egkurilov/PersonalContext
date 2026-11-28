"""Fixed-category audit records; never accept payloads or caller identifiers."""

import sqlite3
import uuid

EVENTS = frozenset({"owner_bootstrap", "owner_login", "owner_logout", "pairing_issue", "device_enroll",
                    "device_revoke", "policy_update", "policy_pause", "restore",
                    "source_create", "source_pause", "source_resume", "owner_session_rotate", "private_config_update",
                    "mcp_issue", "mcp_revoke"})
ACTORS = frozenset({"owner", "device", "local", "system", "anonymous"})
RETENTION = 90 * 86400


def record_audit(connection: sqlite3.Connection, event: str, actor: str, now: int, *, status: str = "success") -> None:
    if (not connection.in_transaction or event not in EVENTS or actor not in ACTORS
            or status not in ("success", "denied") or type(now) is not int or not 0 <= now <= 2**53 - 1):
        raise ValueError("Invalid audit event")
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='security_audit'").fetchone()
    if not exists:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is not None and revision[0] in {f"{number:04d}" for number in range(1, 9)}:
            return
        raise sqlite3.DatabaseError("Audit storage unavailable")
    connection.execute("DELETE FROM security_audit WHERE occurred_at < ?", (now - RETENTION,))
    connection.execute("INSERT INTO security_audit(event_type,actor,status,occurred_at,correlation_id) VALUES (?,?,?,?,?)",
                       (event, actor, status, now, str(uuid.uuid4())))


def record_denied(connection: sqlite3.Connection, event: str, actor: str, now: int) -> None:
    """Use only after a bounded attempt; never record IPs, inputs or user identifiers."""
    connection.execute("BEGIN IMMEDIATE")
    record_audit(connection, event, actor, now, status="denied")
