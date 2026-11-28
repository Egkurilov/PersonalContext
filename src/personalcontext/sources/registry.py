"""Owner-controlled source identities, bound to an enrolled device."""

import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Literal

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.devices.scopes import INGEST, authorize_device, valid_device_id


@dataclass(frozen=True)
class SourceResult:
    status: Literal["ok", "invalid", "forbidden", "conflict", "unavailable"]
    source_id: str | None = field(default=None, repr=False)
    revision: int | None = None


def _valid_time(now: object) -> bool:
    return type(now) is int and 0 <= now <= 2**53 - 1


def create_source(connection: sqlite3.Connection, token: object, csrf: object,
                  device_id: object, kind: object, now: int) -> SourceResult:
    if not _valid_time(now) or not valid_device_id(device_id) or kind not in ("browser", "windows"):
        return SourceResult("invalid")
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return SourceResult("forbidden")
    row = connection.execute("SELECT scope_mask,revoked_at FROM devices WHERE device_id=?", (device_id,)).fetchone()
    if row is None or type(row[0]) is not int or not 1 <= row[0] <= 7 or not row[0] & INGEST or row[1] is not None:
        return SourceResult("forbidden")
    if (connection.execute("SELECT count(*) FROM sources WHERE device_id=?", (device_id,)).fetchone()[0] >= 16
            or connection.execute("SELECT count(*) FROM sources").fetchone()[0] >= 256):
        return SourceResult("unavailable")
    source_id = str(uuid.uuid4())
    connection.execute("INSERT INTO sources VALUES (?,?,?,1,1,?,?)", (source_id, device_id, kind, now, now))
    record_audit(connection, "source_create", "owner", now)
    return SourceResult("ok", source_id, 1)


def owns_source(connection: sqlite3.Connection, token: object, device_id: object, source_id: object,
                origin: object = None) -> bool:
    """Check identity only; this does not authorize capture or verify permissions."""
    if not valid_device_id(source_id) or not authorize_device(connection, token, device_id, INGEST, origin):
        return False
    return connection.execute("SELECT 1 FROM sources WHERE source_id=? AND device_id=?", (source_id, device_id)).fetchone() is not None


def set_source_pause(connection: sqlite3.Connection, token: object, csrf: object, source_id: object,
                     expected_revision: object, paused: object, now: int) -> SourceResult:
    if (not _valid_time(now) or not valid_device_id(source_id) or type(paused) is not bool
            or type(expected_revision) is not int or not 1 <= expected_revision < 2**53 - 1):
        return SourceResult("invalid")
    assert isinstance(source_id, str)
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return SourceResult("forbidden")
    row = connection.execute(
        "SELECT s.paused,s.revision,s.created_at,s.updated_at,d.revoked_at,d.scope_mask FROM sources s "
        "JOIN devices d ON d.device_id=s.device_id WHERE s.source_id=?", (source_id,),
    ).fetchone()
    if row is None:
        return SourceResult("forbidden")
    old_pause, revision, created, updated, revoked, mask = row
    if (type(old_pause) is not int or old_pause not in (0, 1) or type(revision) is not int or not 1 <= revision < 2**53 - 1
            or type(created) is not int or type(updated) is not int or not 0 <= created <= updated <= 2**53 - 1
            or type(mask) is not int or not 1 <= mask <= 7 or not mask & INGEST):
        return SourceResult("unavailable")
    if revision != expected_revision:
        return SourceResult("conflict")
    if not paused and (revoked is not None or now < updated):
        return SourceResult("forbidden")
    revision += 1
    connection.execute("UPDATE sources SET paused=?,revision=?,updated_at=? WHERE source_id=?",
                       (int(paused), revision, max(now, updated), source_id))
    record_audit(connection, "source_pause" if paused else "source_resume", "owner", now)
    return SourceResult("ok", source_id, revision)
