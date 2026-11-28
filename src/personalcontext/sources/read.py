"""Bounded source snapshots, validated before they reach an API response."""

import sqlite3
from dataclasses import dataclass, field

from personalcontext.devices.scopes import valid_device_id


@dataclass(frozen=True)
class Source:
    source_id: str = field(repr=False)
    device_id: str = field(repr=False)
    kind: str
    paused: bool
    revision: int
    created_at: int
    updated_at: int


def read_sources(connection: sqlite3.Connection, *, device_id: str | None = None,
                 cursor: tuple[int, str] | None = None, limit: int = 257) -> list[Source] | None:
    if (device_id is not None and not valid_device_id(device_id)) or not 1 <= limit <= 501:
        return None
    clauses = []
    params: list[object] = []
    if device_id is not None:
        clauses.append("device_id=?")
        params.append(device_id)
    if cursor is not None:
        clauses.append("(created_at>? OR (created_at=? AND source_id>?))")
        params.extend((cursor[0], cursor[0], cursor[1]))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)
    rows = connection.execute("SELECT source_id,device_id,kind,paused,revision,created_at,updated_at FROM sources"
                              + where + " ORDER BY created_at,source_id LIMIT ?", params).fetchall()
    result = []
    for source, device, kind, paused, revision, created, updated in rows:
        if (not valid_device_id(source) or not valid_device_id(device) or kind not in ("browser", "windows")
                or type(paused) is not int or paused not in (0, 1) or type(revision) is not int
                or not 1 <= revision < 2**53 or type(created) is not int or type(updated) is not int
                or not 0 <= created <= updated <= 2**53 - 1):
            return None
        result.append(Source(source, device, kind, bool(paused), revision, created, updated))
    return result
