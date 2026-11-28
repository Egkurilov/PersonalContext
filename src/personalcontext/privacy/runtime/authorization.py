"""Combine owner consent and device/source binding inside a writer transaction."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from personalcontext.privacy.capture_policy import CaptureRequest, allows_capture
from personalcontext.privacy.policy_store import load_policy
from personalcontext.privacy.runtime.clock import policy_time_valid
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.sources.registry import owns_source


def device_policy_allows(connection: sqlite3.Connection, *, token: object, device_id: object,
                         request: CaptureRequest, latch: CaptureLatch, clock: Callable[[], datetime] | None = None) -> bool:
    """Check consent and identity only; callers must independently verify source capability."""
    if not connection.in_transaction or not isinstance(request, CaptureRequest):
        return False
    if not owns_source(connection, token, device_id, request.source):
        return False
    row = connection.execute(
        "SELECT kind,paused,revision,created_at,updated_at FROM sources WHERE source_id=? AND device_id=?",
        (request.source, device_id),
    ).fetchone()
    if row is None:
        return False
    kind, paused, revision, created, updated = row
    if (kind not in ("browser", "windows") or type(paused) is not int or paused != 0
            or type(revision) is not int or not 1 <= revision < 2**53
            or type(created) is not int or type(updated) is not int or not 0 <= created <= updated <= 2**53 - 1):
        return False
    policy = load_policy(connection)
    now = clock() if clock is not None else datetime.now(UTC)
    if policy is None or not policy_time_valid(latch, policy, now) or not allows_capture(policy, request, now):
        return False
    try:
        return now.timestamp() >= updated
    except (ValueError, TypeError, OverflowError, OSError):
        return False
