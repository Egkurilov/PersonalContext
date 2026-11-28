"""Strict extension origins and origin-bound device authorization."""

import re
import sqlite3

_ORIGIN = re.compile(r"chrome-extension://[a-p]{32}\Z")


def valid_origin(value: object) -> bool:
    return isinstance(value, str) and _ORIGIN.fullmatch(value) is not None


def legacy_schema(connection: sqlite3.Connection, table: str) -> bool:
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return False
    rows = connection.execute("SELECT version_num FROM alembic_version LIMIT 2").fetchall()
    if len(rows) == 1 and rows[0][0] in {f"{number:04d}" for number in range(7, 13)}:
        return True
    raise sqlite3.DatabaseError("Missing extension security table")


def pairing_origin(connection: sqlite3.Connection, digest: bytes) -> tuple[str] | None:
    if legacy_schema(connection, "extension_pairings"):
        return None
    row = connection.execute("SELECT origin FROM extension_pairings WHERE code_hash=?", (digest,)).fetchone()
    if row is None:
        return None
    if not valid_origin(row[0]):
        raise sqlite3.DatabaseError("Invalid extension pairing binding")
    return (str(row[0]),)


def device_origin_matches(connection: sqlite3.Connection, device_id: object, origin: object) -> bool:
    if legacy_schema(connection, "extension_devices"):
        return origin is None
    row = connection.execute("SELECT origin FROM extension_devices WHERE device_id=?", (device_id,)).fetchone()
    if row is None:
        return origin is None
    return valid_origin(row[0]) and origin == row[0]


def origin_approved(connection: sqlite3.Connection, origin: str, now: int) -> bool:
    if not valid_origin(origin) or type(now) is not int or not 0 <= now <= 2**53 - 300:
        return False
    connection.execute(
        "DELETE FROM pairing_codes WHERE typeof(issued_at)!='integer' OR typeof(expires_at)!='integer' "
        "OR issued_at<0 OR issued_at>? OR expires_at!=issued_at+300 OR issued_at>? OR expires_at<=?",
        (2**53 - 300, now, now),
    )
    pending = connection.execute(
        "SELECT 1 FROM extension_pairings e JOIN pairing_codes p ON p.code_hash=e.code_hash "
        "WHERE e.origin=? AND p.issued_at<=? AND p.expires_at>? LIMIT 1", (origin, now, now),
    ).fetchone()
    active = connection.execute(
        "SELECT 1 FROM extension_devices e JOIN devices d ON d.device_id=e.device_id "
        "WHERE e.origin=? AND d.revoked_at IS NULL LIMIT 1", (origin,),
    ).fetchone()
    return bool(pending or active)
