"""Prepare privacy decisions while holding the writer's immediate transaction."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from personalcontext.privacy.capture_policy import CaptureRequest, allows_capture
from personalcontext.privacy.policy_store import load_policy
from personalcontext.privacy.runtime.clock import policy_time_valid
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.app import SanitizedApp
from personalcontext.privacy.sanitizer.gate import gate_app, gate_text, gate_web
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.web import SanitizedWeb


def prepare_web(connection: sqlite3.Connection, request: CaptureRequest, context: SanitizerContext,
                value: object, *, latch: CaptureLatch, clock: Callable[[], datetime] | None = None) -> SanitizedWeb | None:
    ticket = latch.ticket()
    if ticket is None:
        return None
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    policy = load_policy(connection)
    get_time = clock or (lambda: datetime.now(UTC))
    first = get_time()
    result = gate_web(policy, request, context, value, first) if policy is not None and policy_time_valid(latch, policy, first) else None
    last = get_time() if result is not None else first
    return result if (policy is not None and result is not None and policy_time_valid(latch, policy, last)
                      and allows_capture(policy, request, last)
                      and latch.allows(ticket)) else None


def prepare_app(connection: sqlite3.Connection, request: CaptureRequest, context: SanitizerContext,
                value: object, *, latch: CaptureLatch, clock: Callable[[], datetime] | None = None) -> SanitizedApp | None:
    ticket = latch.ticket()
    if ticket is None:
        return None
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    policy = load_policy(connection)
    get_time = clock or (lambda: datetime.now(UTC))
    first = get_time()
    result = gate_app(policy, request, context, value, first) if policy is not None and policy_time_valid(latch, policy, first) else None
    last = get_time() if result is not None else first
    return result if (policy is not None and result is not None and policy_time_valid(latch, policy, last)
                      and allows_capture(policy, request, last)
                      and latch.allows(ticket)) else None


def prepare_text(connection: sqlite3.Connection, request: CaptureRequest, context: SanitizerContext,
                 domain: object, value: object, *, latch: CaptureLatch, clock: Callable[[], datetime] | None = None) -> str | None:
    ticket = latch.ticket()
    if ticket is None:
        return None
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    policy = load_policy(connection)
    get_time = clock or (lambda: datetime.now(UTC))
    first = get_time()
    result = gate_text(policy, request, context, domain, value, first) if policy is not None and policy_time_valid(latch, policy, first) else None
    last = get_time() if result is not None else first
    return result if (policy is not None and result is not None and policy_time_valid(latch, policy, last)
                      and allows_capture(policy, request, last)
                      and latch.allows(ticket)) else None
