"""Recheck owner authorization and the exact saved candidate under the writer."""

import sqlite3
import time

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.network.private_settings import StoredCandidate, load_candidate


def authorized_candidate(connection: sqlite3.Connection, token: object, csrf: object,
                         revision: object) -> tuple[str, StoredCandidate | None]:
    if type(revision) is not int or not 1 <= revision < 2**53:
        return "invalid", None
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, int(time.time())):
        return "forbidden", None
    candidate = load_candidate(connection)
    if candidate is None:
        return "unavailable", None
    if candidate.revision != revision:
        return "conflict", None
    return "ok", candidate


def audit_attempt(connection: sqlite3.Connection, token: object, csrf: object, revision: object,
                  expected: StoredCandidate) -> str:
    status, current = authorized_candidate(connection, token, csrf, revision)
    if status != "ok":
        return status
    if current != expected:
        return "conflict"
    record_audit(connection, "private_listener_attempt", "owner", int(time.time()))
    return "ok"


def audit_stop(connection: sqlite3.Connection, actor: str) -> None:
    connection.execute("BEGIN IMMEDIATE")
    record_audit(connection, "private_listener_stop", actor, int(time.time()))
