"""Internal bootstrap verifier; issuance must remain local and owner initiated."""

import hashlib
import hmac
import re
import secrets
import sqlite3

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_store import (
    find_owner_hash,
    insert_owner_hash_in_transaction,
)
from personalcontext.auth.password_hash import is_supported_hash

_CODE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_LIFETIME = 300
_MAX_ATTEMPTS = 5


def _time(now: int) -> int:
    if type(now) is not int or not 0 <= now <= 2**53 - _LIFETIME:
        raise ValueError("Invalid time")
    return now


def issue_bootstrap(connection: sqlite3.Connection, now: int) -> str:
    now = _time(now)
    code = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code.encode("ascii")).digest()
    connection.execute("BEGIN IMMEDIATE")
    if find_owner_hash(connection) is not None:
        raise RuntimeError("Bootstrap unavailable")
    connection.execute(
        "INSERT INTO bootstrap_codes(singleton,code_hash,issued_at,expires_at,attempts) VALUES (1,?,?,?,0) "
        "ON CONFLICT(singleton) DO UPDATE SET code_hash=excluded.code_hash,issued_at=excluded.issued_at, "
        "expires_at=excluded.expires_at,attempts=0", (digest, now, now + _LIFETIME),
    )
    return code


def consume_bootstrap(connection: sqlite3.Connection, candidate: object, encoded: str, now: int) -> bool:
    now = _time(now)
    if not is_supported_hash(encoded):
        raise ValueError("Invalid password hash")
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute("SELECT code_hash,issued_at,expires_at,attempts FROM bootstrap_codes WHERE singleton=1").fetchone()
    if row is None:
        return False
    expected, issued, expires, attempts = row
    invalid = (not isinstance(expected, bytes) or len(expected) != 32 or type(issued) is not int
               or type(expires) is not int or type(attempts) is not int or not 0 <= attempts < _MAX_ATTEMPTS
               or expires != issued + _LIFETIME)
    if invalid or find_owner_hash(connection) is not None or now < issued or now >= expires:
        connection.execute("DELETE FROM bootstrap_codes WHERE singleton=1")
        return False
    valid_format = isinstance(candidate, str) and _CODE.fullmatch(candidate) is not None
    digest = hashlib.sha256(candidate.encode("ascii") if valid_format and isinstance(candidate, str) else b"").digest()
    if not (hmac.compare_digest(expected, digest) and valid_format):
        if attempts + 1 >= _MAX_ATTEMPTS:
            connection.execute("DELETE FROM bootstrap_codes WHERE singleton=1")
        else:
            connection.execute("UPDATE bootstrap_codes SET attempts=attempts+1 WHERE singleton=1")
        return False
    created = insert_owner_hash_in_transaction(connection, encoded)
    connection.execute("DELETE FROM bootstrap_codes WHERE singleton=1")
    if created:
        record_audit(connection, "owner_bootstrap", "system", now)
    return created
