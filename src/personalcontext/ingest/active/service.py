"""Internal active-tab writer; classifier and transport must be trusted."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from personalcontext.ingest.active.model import WebActive
from personalcontext.ingest.browser.ledger.record import VisitResult, _record_browser
from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.runtime.authorization import device_policy_allows
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext, valid_context


async def submit_web_active(writer: Writer, latch: CaptureLatch, token: object, device_id: object, value: object,
                            context: SanitizerContext, *, origin: object = None,
                            clock: Callable[[], datetime] | None = None) -> VisitResult:
    """Foreground, private status and sensitivity must originate in a verified adapter."""
    if type(value) is not dict:
        return "rejected"
    try:
        event = WebActive.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        return "rejected"
    if event.device_id != device_id or not valid_context(context):
        return "rejected"
    now = clock or (lambda: datetime.now(UTC))
    request = CaptureRequest(event.source_id, event.consent_scope, event.policy_version, context.private, context.sensitivity)

    def authorize(connection: sqlite3.Connection) -> bool:
        return device_policy_allows(connection, token=token, device_id=device_id, request=request,
                                    latch=latch, origin=origin, clock=now)

    result: VisitResult | None = await submit_capture(writer, latch, lambda c: _record_browser(c, event, request, context, latch, now), authorize)
    return result if result is not None else "rejected"
