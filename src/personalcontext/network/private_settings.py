"""Transactional owner-managed private HTTPS candidates; never enables a listener."""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.lan.networks import lan_ranges_allowed

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}\.pem\Z", re.IGNORECASE)
_RESERVED = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})


@dataclass(frozen=True)
class PrivateCandidate:
    boundary: PrivateBoundary = field(repr=False)
    cert_name: str = field(repr=False)
    key_name: str = field(repr=False)
    protected: bytes = field(repr=False)


@dataclass(frozen=True)
class StoredCandidate:
    revision: int
    candidate: PrivateCandidate = field(repr=False)


@dataclass(frozen=True)
class SettingsResult:
    status: Literal["ok", "invalid", "forbidden", "conflict", "unavailable"]
    revision: int | None = None


def _valid_name(value: object) -> bool:
    return (isinstance(value, str) and _NAME.fullmatch(value) is not None
            and value.split(".", 1)[0].lower() not in _RESERVED)


def valid_material_names(cert_name: object, key_name: object) -> bool:
    return (_valid_name(cert_name) and _valid_name(key_name) and isinstance(cert_name, str)
            and isinstance(key_name, str) and cert_name.lower() != key_name.lower())


def valid_candidate(value: object) -> bool:
    return (isinstance(value, PrivateCandidate) and isinstance(value.boundary, PrivateBoundary)
            and valid_material_names(value.cert_name, value.key_name) and type(value.protected) is bytes
            and 1 <= len(value.protected) <= 8192)


def load_candidate(connection: sqlite3.Connection) -> StoredCandidate | None:
    row = connection.execute("SELECT revision,address,hostname,port,peers,cert_name,key_name,protected "
                             "FROM private_network_candidate WHERE singleton=1").fetchone()
    if row is None:
        return None
    revision, address, hostname, port, peers, cert_name, key_name, protected = row
    try:
        if not isinstance(peers, str) or len(peers) > 4096:
            return None
        decoded = json.loads(peers)
        if type(revision) is not int or not 1 <= revision < 2**53 or not isinstance(decoded, list):
            return None
        boundary = PrivateBoundary.create(address, hostname, port, decoded)
        candidate = PrivateCandidate(boundary, cert_name, key_name, protected)
        return StoredCandidate(revision, candidate) if valid_candidate(candidate) else None
    except (ValueError, TypeError, OverflowError):
        return None


def save_candidate(connection: sqlite3.Connection, token: object, csrf: object, expected: object,
                   candidate: object, now: int) -> SettingsResult:
    if (not valid_candidate(candidate) or type(expected) is not int or not 0 <= expected < 2**53 - 1
            or type(now) is not int or not 0 <= now <= 2**53 - 1):
        return SettingsResult("invalid")
    assert isinstance(candidate, PrivateCandidate)
    if not lan_ranges_allowed(candidate.boundary.address, candidate.boundary.peers):
        return SettingsResult("invalid")
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return SettingsResult("forbidden")
    current = load_candidate(connection)
    if current is None and connection.execute("SELECT 1 FROM private_network_candidate LIMIT 1").fetchone() is not None:
        return SettingsResult("unavailable")
    version = current.revision if current is not None else 0
    if expected != version:
        return SettingsResult("conflict")
    boundary = candidate.boundary
    connection.execute("INSERT OR REPLACE INTO private_network_candidate VALUES (1,?,?,?,?,?,?,?,?)",
                       (version + 1, boundary.address, boundary.hostname, boundary.port,
                        json.dumps(boundary.peers, separators=(",", ":")), candidate.cert_name,
                        candidate.key_name, candidate.protected))
    record_audit(connection, "private_config_update", "owner", now)
    return SettingsResult("ok", version + 1)
