"""Versioned policy stored and changed only through the single writer."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.privacy.capture_policy import CapturePolicy
from personalcontext.privacy.policy_validation import MAX_TIME, PolicyDraft, valid_draft


@dataclass(frozen=True)
class PolicyResult:
    status: Literal["ok", "invalid", "forbidden", "conflict", "unavailable"]
    version: int | None = None


def load_policy(connection: sqlite3.Connection) -> CapturePolicy | None:
    row = connection.execute("SELECT version,issued_at,expires_at,paused FROM capture_policy WHERE singleton=1").fetchone()
    if row is None:
        return None
    version, issued, expires, paused = row
    if (type(version) is not int or not 1 <= version < 2**53 or type(issued) is not int or not 0 <= issued <= MAX_TIME
            or type(expires) is not int or type(paused) is not int or paused not in (0, 1)
            or not ((version == 1 and issued == expires == 0 and paused == 1) or 1 <= expires - issued <= 86400)):
        return None
    sources = connection.execute("SELECT source,disposition FROM capture_policy_sources LIMIT 129").fetchall()
    grants = connection.execute("SELECT source,scope FROM capture_policy_grants LIMIT 193").fetchall()
    allowed = frozenset(source for source, disposition in sources if disposition == "allow")
    denied = frozenset(source for source, disposition in sources if disposition == "deny")
    if any(disposition not in ("allow", "deny") for _, disposition in sources):
        return None
    try:
        draft = PolicyDraft(bool(paused), max(1, expires - issued), allowed, denied, frozenset(grants))
        if not valid_draft(draft):
            return None
        return CapturePolicy(version, datetime.fromtimestamp(issued, UTC), datetime.fromtimestamp(expires, UTC),
                             bool(paused), allowed, denied, draft.grants)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def save_policy(connection: sqlite3.Connection, token: object, csrf: object, expected_version: object,
                draft: object, now: int) -> PolicyResult:
    if (not valid_draft(draft) or type(expected_version) is not int or not 1 <= expected_version < 2**53 - 1
            or type(now) is not int or not 0 <= now <= MAX_TIME):
        return PolicyResult("invalid")
    assert isinstance(draft, PolicyDraft)
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return PolicyResult("forbidden")
    current = load_policy(connection)
    if current is None or current.issued_at is None:
        return PolicyResult("unavailable")
    if current.version != expected_version:
        return PolicyResult("conflict")
    if now < current.issued_at.timestamp():
        return PolicyResult("invalid")
    version = current.version + 1
    connection.execute("UPDATE capture_policy SET version=?,issued_at=?,expires_at=?,paused=? WHERE singleton=1",
                       (version, now, now + draft.ttl, int(draft.paused)))
    connection.execute("DELETE FROM capture_policy_sources")
    connection.execute("DELETE FROM capture_policy_grants")
    connection.executemany("INSERT INTO capture_policy_sources VALUES (?,?)",
                           [(source, disposition) for disposition, values in (("allow", draft.allowed), ("deny", draft.denied))
                            for source in values])
    connection.executemany("INSERT INTO capture_policy_grants VALUES (?,?)", list(draft.grants))
    return PolicyResult("ok", version)
