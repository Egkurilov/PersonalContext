"""Rotate CSRF for an existing session in one single-writer transaction."""

import hashlib
import secrets
import sqlite3

from personalcontext.audit.record import record_audit
from personalcontext.auth.owner_sessions import (
    SessionSecrets,
    authorize_mutation,
    session_active,
)


def rotate_csrf(connection: sqlite3.Connection, token: object, now: int) -> str | None:
    connection.execute("BEGIN IMMEDIATE")
    if not session_active(connection, token, now):
        return None
    assert isinstance(token, str)
    csrf = secrets.token_urlsafe(32)
    connection.execute(
        "UPDATE owner_sessions SET csrf_hash=? WHERE token_hash=?",
        (hashlib.sha256(csrf.encode("ascii")).digest(), hashlib.sha256(token.encode("ascii")).digest()),
    )
    return csrf


def rotate_session(connection: sqlite3.Connection, token: object, csrf: object, now: int) -> SessionSecrets | None:
    """Replace both secrets without extending the existing session expiry."""
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_mutation(connection, token, csrf, now):
        return None
    assert isinstance(token, str) and isinstance(csrf, str)
    replacement = SessionSecrets(token=secrets.token_urlsafe(32), csrf=secrets.token_urlsafe(32))
    if replacement.token in (token, csrf, replacement.csrf) or replacement.csrf in (token, csrf):
        return None
    changed = connection.execute(
        "UPDATE owner_sessions SET token_hash=?,csrf_hash=? WHERE token_hash=?",
        (hashlib.sha256(replacement.token.encode("ascii")).digest(), hashlib.sha256(replacement.csrf.encode("ascii")).digest(),
         hashlib.sha256(token.encode("ascii")).digest()),
    ).rowcount
    if changed != 1:
        return None
    record_audit(connection, "owner_session_rotate", "owner", now)
    return replacement
