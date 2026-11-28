"""Short-lived, owner-issued credentials for narrowly scoped local reads."""

import secrets
import sqlite3
import uuid
from dataclasses import dataclass, field

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.devices.scopes import digest_token, valid_device_id

_TTL = 900


@dataclass(frozen=True)
class IssuedCredential:
    id: str
    token: str = field(repr=False)


def _time(now: object) -> bool:
    return type(now) is int and 0 <= now <= 2**53 - _TTL


def issue(connection: sqlite3.Connection, owner: object, csrf: object, scope: object, now: int) -> IssuedCredential | None:
    if scope != "status:read" or not _time(now):
        return None
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, owner, csrf, now):
        return None
    connection.execute("DELETE FROM mcp_credentials WHERE expires_at<=? OR revoked_at IS NOT NULL", (now,))
    if connection.execute("SELECT count(*) FROM mcp_credentials").fetchone()[0] >= 8:
        return None
    identifier, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
    connection.execute("INSERT INTO mcp_credentials VALUES (?,?,?,?,?,?,NULL)",
                       (identifier, digest_token(token), scope, now, now + _TTL, now))
    record_audit(connection, "mcp_issue", "owner", now)
    return IssuedCredential(identifier, token)


def authorize(connection: sqlite3.Connection, token: object, scope: object, now: int) -> bool:
    digest = digest_token(token)
    if digest is None or scope != "status:read" or not _time(now):
        return False
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute("SELECT id,scope,issued_at,expires_at,last_seen,revoked_at "
                             "FROM mcp_credentials WHERE token_hash=?", (digest,)).fetchone()
    if row is None:
        return False
    identifier, actual, issued, expires, last_seen, revoked = row
    if (not valid_device_id(identifier) or actual != scope or not _time(issued) or type(expires) is not int
            or expires != issued + _TTL or type(last_seen) is not int or last_seen < issued
            or revoked is not None):
        return False
    if now < last_seen or not issued <= now < expires:
        connection.execute("DELETE FROM mcp_credentials WHERE token_hash=?", (digest,))
        return False
    connection.execute("UPDATE mcp_credentials SET last_seen=? WHERE id=?", (now, identifier))
    return True


def revoke(connection: sqlite3.Connection, owner: object, csrf: object, identifier: object, now: int) -> bool:
    if not valid_device_id(identifier) or not _time(now):
        return False
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, owner, csrf, now):
        return False
    changed = connection.execute("UPDATE mcp_credentials SET revoked_at=? "
                                 "WHERE id=? AND revoked_at IS NULL AND issued_at<=?", (now, identifier, now)).rowcount == 1
    if changed:
        record_audit(connection, "mcp_revoke", "owner", now)
    return changed
