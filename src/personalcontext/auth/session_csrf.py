"""Rotate CSRF for an existing session in one single-writer transaction."""

import hashlib
import secrets
import sqlite3

from personalcontext.auth.owner_sessions import session_active


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
