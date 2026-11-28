"""Immediate owner-authorized pause, invalidating previously issued revisions."""

import sqlite3

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.privacy.policy_store import PolicyResult, load_policy
from personalcontext.privacy.policy_validation import MAX_TIME


def _pause_in_transaction(connection: sqlite3.Connection, now: int, actor: str) -> PolicyResult:
    current = load_policy(connection)
    if current is None or current.issued_at is None:
        return PolicyResult("unavailable")
    if current.version >= 2**53 - 1 or now < current.issued_at.timestamp():
        return PolicyResult("invalid")
    version = current.version + 1
    connection.execute("UPDATE capture_policy SET version=?,issued_at=?,expires_at=?,paused=1 WHERE singleton=1",
                       (version, now, now + 1))
    record_audit(connection, "policy_pause", actor, now)
    return PolicyResult("ok", version)


def pause_policy(connection: sqlite3.Connection, token: object, csrf: object, now: int) -> PolicyResult:
    if type(now) is not int or not 0 <= now <= MAX_TIME:
        return PolicyResult("invalid")
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return PolicyResult("forbidden")
    return _pause_in_transaction(connection, now, "owner")


def pause_local(connection: sqlite3.Connection, now: int) -> PolicyResult:
    """Native kill switch; callable only in-process, never exposed as an unauthenticated API."""
    if type(now) is not int or not 0 <= now <= MAX_TIME:
        return PolicyResult("invalid")
    connection.execute("BEGIN IMMEDIATE")
    return _pause_in_transaction(connection, now, "local")
