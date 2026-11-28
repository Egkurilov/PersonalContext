"""Bounded internal batches; caller must supply a trusted classification context."""

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from personalcontext.ingest.active.model import WebActive
from personalcontext.ingest.browser.ledger.record import VisitResult
from personalcontext.ingest.browser.ledger.record import _record_browser as _record
from personalcontext.ingest.visit.model import WebVisit
from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.runtime.authorization import device_policy_allows
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext, valid_context

_MAX_BYTES = 1024 * 1024
_MAX_ITEMS = 100


class InvalidBatch(ValueError):
    """The envelope is malformed or exceeds a transport-independent limit."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidBatch("Invalid batch")
        result[key] = value
    return result


def _constant(_value: str) -> object:
    raise InvalidBatch("Invalid batch")


def _parse(raw: object) -> list[object]:
    if type(raw) is not bytes or len(raw) > _MAX_BYTES:
        raise InvalidBatch("Invalid batch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidBatch("Invalid batch") from error
    if type(value) is not list or len(value) > _MAX_ITEMS:
        raise InvalidBatch("Invalid batch")
    return value


async def submit_visit_batch(writer: Writer, latch: CaptureLatch, token: object, device_id: object, raw: object,
                             context: SanitizerContext, *, origin: object = None,
                             clock: Callable[[], datetime] | None = None) -> list[VisitResult]:
    """Commit the batch atomically; no result is returned before durable commit."""
    values = _parse(raw)
    if not values:
        return []
    events: list[WebVisit | WebActive | None] = []
    for value in values:
        event: WebVisit | WebActive | None
        try:
            if type(value) is not dict:
                event = None
            elif value.get("kind") == "web_active":
                event = WebActive.model_validate(value)
            else:
                event = WebVisit.model_validate(value)
        except (ValidationError, ValueError, TypeError):
            event = None
        events.append(event if event is not None and event.device_id == device_id else None)
    if not valid_context(context):
        return ["rejected"] * len(events)
    now = clock or (lambda: datetime.now(UTC))
    authorized: list[CaptureRequest] = []

    def allowed(connection: sqlite3.Connection, request: CaptureRequest) -> bool:
        return device_policy_allows(connection, token=token, device_id=device_id, request=request,
                                    latch=latch, origin=origin, clock=now)

    def execute(connection: sqlite3.Connection) -> list[VisitResult]:
        results: list[VisitResult] = []
        for event in events:
            if event is None:
                results.append("rejected")
                continue
            request = CaptureRequest(event.source_id, event.consent_scope, event.policy_version,
                                     context.private, context.sensitivity)
            outcome = _record(connection, event, request, context, latch, now) if allowed(connection, request) else None
            results.append(outcome if outcome is not None else "rejected")
            if outcome is not None:
                authorized.append(request)
        return results

    result = await submit_capture(writer, latch, execute, lambda c: all(allowed(c, item) for item in authorized))
    return result if result is not None else ["rejected"] * len(events)
