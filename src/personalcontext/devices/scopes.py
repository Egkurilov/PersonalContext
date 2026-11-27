"""Validate bearer binding and individual device capability scopes."""

import hashlib
import re
import sqlite3
import uuid

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
INGEST, HEARTBEAT, CONFIG = 1, 2, 4


def digest_token(token: object) -> bytes | None:
    if not isinstance(token, str) or len(token) != 43 or _TOKEN.fullmatch(token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).digest()


def valid_device_id(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        parsed = uuid.UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except ValueError:
        return False


def authorize_device(connection: sqlite3.Connection, token: object, device_id: object, scope: object) -> bool:
    digest = digest_token(token)
    if digest is None or not valid_device_id(device_id) or type(scope) is not int or scope not in (1, 2, 4):
        return False
    row = connection.execute(
        "SELECT scope_mask,revoked_at,created_at,last_seen FROM devices WHERE device_id=? AND token_hash=?", (device_id, digest),
    ).fetchone()
    return bool(row and type(row[0]) is int and 1 <= row[0] <= 7 and row[1] is None
                and type(row[2]) is int and 0 <= row[2] <= 2**53 - 300
                and (row[3] is None or (type(row[3]) is int and row[2] <= row[3] <= 2**53 - 300))
                and row[0] & scope)
