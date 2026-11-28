"""Prevent restored backups from reviving old grants or access credentials."""

import sqlite3
import time

from personalcontext.audit.record import record_audit

_REVISIONS = {f"{number:04d}": number for number in range(1, 17)}
_TABLES = {"owner_credentials": 3, "bootstrap_codes": 4, "owner_sessions": 5,
           "auth_rate_clocks": 6, "auth_attempts": 6, "pairing_codes": 7, "devices": 7,
           "capture_policy": 8, "capture_policy_sources": 8, "capture_policy_grants": 8, "security_audit": 9,
           "sources": 10, "private_network_candidate": 12, "extension_pairings": 13, "extension_devices": 13,
           "mcp_credentials": 14, "privacy_filter_rules": 16}


def reset_restored_access(connection: sqlite3.Connection) -> None:
    """Mutate an in-memory snapshot before any restored file is published."""
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "alembic_version" not in tables:
        if tables.intersection(_TABLES):
            raise sqlite3.DatabaseError("Unversioned backup contains security state")
        return
    rows = connection.execute("SELECT version_num FROM alembic_version LIMIT 2").fetchall()
    if len(rows) != 1 or rows[0][0] not in _REVISIONS:
        raise sqlite3.DatabaseError("Unsupported backup schema for safe restore")
    revision = _REVISIONS[rows[0][0]]
    if any((table in tables) != (revision >= since) for table, since in _TABLES.items()):
        raise sqlite3.DatabaseError("Inconsistent backup security schema")
    if revision >= 4:
        connection.execute("DELETE FROM bootstrap_codes")
    if revision >= 5:
        connection.execute("DELETE FROM owner_sessions")
    if revision >= 14:
        connection.execute("DELETE FROM mcp_credentials")
    if revision >= 13:
        connection.execute("DELETE FROM extension_pairings")
    if revision >= 7:
        connection.execute("DELETE FROM pairing_codes")
        connection.execute("UPDATE devices SET revoked_at=created_at WHERE revoked_at IS NULL")
    if revision >= 3:
        connection.execute("DELETE FROM owner_credentials")
    if revision >= 8:
        connection.execute(
            "UPDATE capture_policy SET paused=1,issued_at=0,expires_at=1, "
            "version=CASE WHEN typeof(version)='integer' AND version BETWEEN 1 AND ? "
            "THEN version+1 ELSE 1 END WHERE singleton=1", (2**53 - 2,),
        )
    if revision >= 10:
        connection.execute("UPDATE sources SET paused=1,revision=CASE WHEN revision BETWEEN 1 AND ? "
                           "THEN revision+1 ELSE 1 END", (2**53 - 2,))
    if revision >= 12:
        connection.execute("DELETE FROM private_network_candidate")
    if revision >= 9:
        record_audit(connection, "restore", "system", int(time.time()))
