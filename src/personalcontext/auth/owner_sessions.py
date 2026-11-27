"""Internal owner-session storage; callers must authenticate and rate-limit first."""

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass, field

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_hash import is_supported_hash

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_LIFETIME = 1800
_LIMIT = 16


@dataclass(frozen=True)
class SessionSecrets:
    token: str = field(repr=False)
    csrf: str = field(repr=False)


def _digest(value: object) -> bytes | None:
    if not isinstance(value, str) or len(value) != 43 or _TOKEN.fullmatch(value) is None:
        return None
    return hashlib.sha256(value.encode("ascii")).digest()


def _valid_time(now: object) -> bool:
    return type(now) is int and 0 <= now <= 2**53 - _LIFETIME


def create_session(connection: sqlite3.Connection, expected_hash: str, now: int) -> SessionSecrets | None:
    """Call only after password verification, outside any database transaction."""
    if not _valid_time(now) or not is_supported_hash(expected_hash):
        return None
    connection.execute("BEGIN IMMEDIATE")
    current = find_owner_hash(connection)
    if current is None or not is_supported_hash(current) or not hmac.compare_digest(current, expected_hash):
        return None
    connection.execute("DELETE FROM owner_sessions WHERE expires_at <= ? OR issued_at > ?", (now, now))
    if connection.execute("SELECT count(*) FROM owner_sessions").fetchone()[0] >= _LIMIT:
        return None
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO owner_sessions(token_hash,csrf_hash,credential_hash,issued_at,expires_at) VALUES (?,?,?,?,?)",
        (_digest(token), _digest(csrf), hashlib.sha256(expected_hash.encode("ascii")).digest(), now, now + _LIFETIME),
    )
    record_audit(connection, "owner_login", "owner", now)
    return SessionSecrets(token=token, csrf=csrf)


def _session(connection: sqlite3.Connection, token: object, now: int) -> bytes | None:
    digest = _digest(token)
    if digest is None or not _valid_time(now):
        return None
    row = connection.execute(
        "SELECT csrf_hash,credential_hash,issued_at,expires_at FROM owner_sessions WHERE token_hash=?", (digest,),
    ).fetchone()
    if row is None:
        return None
    csrf_hash, credential_hash, issued, expires = row
    current = find_owner_hash(connection)
    if (not isinstance(csrf_hash, bytes) or len(csrf_hash) != 32
            or not isinstance(credential_hash, bytes) or len(credential_hash) != 32
            or type(issued) is not int or type(expires) is not int or not _valid_time(issued)
            or expires != issued + _LIFETIME
            or not issued <= now < expires or not is_supported_hash(current)):
        return None
    assert current is not None
    if not hmac.compare_digest(credential_hash, hashlib.sha256(current.encode("ascii")).digest()):
        return None
    return csrf_hash


def session_active(connection: sqlite3.Connection, token: object, now: int) -> bool:
    return _session(connection, token, now) is not None


def authorize_mutation(connection: sqlite3.Connection, token: object, csrf: object, now: int) -> bool:
    if not connection.in_transaction:
        return False
    expected, actual = _session(connection, token, now), _digest(csrf)
    return expected is not None and actual is not None and hmac.compare_digest(expected, actual)


def revoke_session(connection: sqlite3.Connection, token: object) -> bool:
    digest = _digest(token)
    if digest is None:
        return False
    connection.execute("BEGIN IMMEDIATE")
    return connection.execute("DELETE FROM owner_sessions WHERE token_hash=?", (digest,)).rowcount == 1


def revoke_authorized_session(connection: sqlite3.Connection, token: object, csrf: object, now: int) -> bool:
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return False
    digest = _digest(token)
    assert digest is not None
    deleted = connection.execute("DELETE FROM owner_sessions WHERE token_hash=?", (digest,)).rowcount == 1
    if deleted:
        record_audit(connection, "owner_logout", "owner", now)
    return deleted
