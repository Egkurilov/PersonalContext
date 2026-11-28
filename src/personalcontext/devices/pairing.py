"""Atomic owner-authorized one-time device enrollment and revocation."""

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from dataclasses import dataclass, field

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_hash import is_supported_hash
from personalcontext.devices.extension_origin import pairing_origin, valid_origin
from personalcontext.devices.scopes import digest_token, valid_device_id


@dataclass(frozen=True)
class DeviceCredential:
    device_id: str
    token: str = field(repr=False)


def _valid_time(now: object) -> bool:
    return type(now) is int and 0 <= now <= 2**53 - 300


def issue_pairing(connection: sqlite3.Connection, token: object, csrf: object, mask: object, now: int,
                  origin: object = None) -> str | None:
    if (type(mask) is not int or not 1 <= mask <= 7 or not _valid_time(now)
            or (origin is not None and not valid_origin(origin))):
        return None
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return None
    owner = find_owner_hash(connection)
    assert owner is not None
    connection.execute("DELETE FROM pairing_codes WHERE expires_at <= ? OR issued_at > ?", (now, now))
    if connection.execute("SELECT count(*) FROM pairing_codes").fetchone()[0] >= 8:
        return None
    code = secrets.token_urlsafe(32)
    connection.execute("INSERT INTO pairing_codes VALUES (?,?,?,?,?)", (
        digest_token(code), hashlib.sha256(owner.encode("ascii")).digest(), mask, now, now + 300,
    ))
    if origin is not None:
        connection.execute("INSERT INTO extension_pairings VALUES (?,?)", (digest_token(code), origin))
    record_audit(connection, "pairing_issue", "owner", now)
    return code


def enroll(connection: sqlite3.Connection, code: object, now: int, origin: object = None) -> DeviceCredential | None:
    digest = digest_token(code)
    if digest is None or not _valid_time(now):
        return None
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute(
        "SELECT owner_hash,scope_mask,issued_at,expires_at FROM pairing_codes WHERE code_hash=?", (digest,),
    ).fetchone()
    owner = find_owner_hash(connection)
    if row is None:
        return None
    binding = pairing_origin(connection, digest)
    if (binding is None and origin is not None) or (binding is not None and
            (not valid_origin(binding[0]) or binding[0] != origin)):
        return None
    owner_hash, mask, issued, expires = row
    if (not isinstance(owner_hash, bytes) or len(owner_hash) != 32 or type(mask) is not int or not 1 <= mask <= 7
            or not is_supported_hash(owner) or type(issued) is not int or type(expires) is not int or not _valid_time(issued)
            or expires != issued + 300 or not issued <= now < expires
            or owner is None or not hmac.compare_digest(owner_hash, hashlib.sha256(owner.encode("ascii")).digest())):
        connection.execute("DELETE FROM pairing_codes WHERE code_hash=?", (digest,))
        return None
    device_id, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
    connection.execute("INSERT INTO devices(device_id,token_hash,scope_mask,created_at) VALUES (?,?,?,?)",
                       (device_id, digest_token(token), mask, now))
    if binding is not None:
        connection.execute("INSERT INTO extension_devices VALUES (?,?)", (device_id, binding[0]))
        connection.execute("DELETE FROM extension_pairings WHERE code_hash=?", (digest,))
    connection.execute("DELETE FROM pairing_codes WHERE code_hash=?", (digest,))
    record_audit(connection, "device_enroll", "device", now)
    return DeviceCredential(device_id, token)


def revoke_device(connection: sqlite3.Connection, token: object, csrf: object, device_id: object, now: int) -> bool:
    if not _valid_time(now) or not valid_device_id(device_id):
        return False
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return False
    revoked = connection.execute(
        "UPDATE devices SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL AND created_at <= ?",
        (now, device_id, now),
    ).rowcount == 1
    if revoked:
        record_audit(connection, "device_revoke", "owner", now)
    return revoked
