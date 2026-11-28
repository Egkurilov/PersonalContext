"""Global, persistent, identifier-free authentication attempt limits."""

import sqlite3
from dataclasses import dataclass

_WINDOWS = {"owner_login": 60, "owner_bootstrap": 300, "device_enroll": 300}
_LIMIT = 5


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after: int | None = None


def consume_attempt(connection: sqlite3.Connection, action: object, now: object) -> RateDecision:
    """Run through single-writer before expensive or security-sensitive work."""
    if not isinstance(action, str) or action not in _WINDOWS or type(now) is not int or not 0 <= now <= 2**53 - 300:
        return RateDecision(False)
    connection.execute("BEGIN IMMEDIATE")
    clock = connection.execute("SELECT last_seen FROM auth_rate_clocks WHERE action=?", (action,)).fetchone()
    rows = connection.execute(
        "SELECT occurred_at FROM auth_attempts WHERE action=? ORDER BY occurred_at LIMIT ?", (action, _LIMIT + 1),
    ).fetchall()
    if len(rows) > _LIMIT or any(type(row[0]) is not int or row[0] < 0 or row[0] > now for row in rows):
        return RateDecision(False)
    if clock is None:
        if rows:
            return RateDecision(False)
        connection.execute("INSERT INTO auth_rate_clocks(action,last_seen) VALUES (?,?)", (action, now))
    else:
        previous = clock[0]
        if type(previous) is not int or previous < 0 or now < previous or (rows and rows[-1][0] > previous):
            return RateDecision(False)
        connection.execute("UPDATE auth_rate_clocks SET last_seen=? WHERE action=?", (now, action))
    window = _WINDOWS[action]
    connection.execute("DELETE FROM auth_attempts WHERE action=? AND occurred_at <= ?", (action, now - window))
    remaining = [row[0] for row in rows if row[0] > now - window]
    if len(remaining) >= _LIMIT:
        return RateDecision(False, remaining[0] + window - now)
    connection.execute("INSERT INTO auth_attempts(action,occurred_at) VALUES (?,?)", (action, now))
    return RateDecision(True)
