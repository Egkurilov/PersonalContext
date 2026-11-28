"""Read and atomically replace owner filters, pausing and versioning consent."""

import sqlite3

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.privacy.filters.rules import FIELDS, FilterRules, valid_rules
from personalcontext.privacy.policy_store import PolicyResult, load_policy
from personalcontext.privacy.policy_validation import MAX_TIME


def load_filters(connection: sqlite3.Connection) -> FilterRules | None:
    rows = connection.execute("SELECT kind,value FROM privacy_filter_rules LIMIT 513").fetchall()
    if len(rows) > 512 or any(kind not in FIELDS or not isinstance(value, str) for kind, value in rows):
        return None
    groups = {field: frozenset(value for kind, value in rows if kind == field) for field in FIELDS}
    result = FilterRules(**groups)
    return result if valid_rules(result) else None


def save_filters(connection: sqlite3.Connection, token: object, csrf: object, expected: object,
                 rules: object, now: int) -> PolicyResult:
    if (not valid_rules(rules) or type(expected) is not int or not 1 <= expected < 2**53 - 1
            or type(now) is not int or not 0 <= now <= MAX_TIME):
        return PolicyResult("invalid")
    assert isinstance(rules, FilterRules)
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return PolicyResult("forbidden")
    policy = load_policy(connection)
    if policy is None or policy.issued_at is None or load_filters(connection) is None:
        return PolicyResult("unavailable")
    if policy.version != expected:
        return PolicyResult("conflict")
    if now < policy.issued_at.timestamp():
        return PolicyResult("invalid")
    version = policy.version + 1
    connection.execute("UPDATE capture_policy SET version=?,issued_at=?,expires_at=?,paused=1 WHERE singleton=1",
                       (version, now, now + 1))
    connection.execute("DELETE FROM privacy_filter_rules")
    connection.executemany("INSERT INTO privacy_filter_rules(kind,value) VALUES (?,?)",
                           [(field, item) for field in FIELDS for item in getattr(rules, field)])
    record_audit(connection, "policy_update", "owner", now)
    return PolicyResult("ok", version)
