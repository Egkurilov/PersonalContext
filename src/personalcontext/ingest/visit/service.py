"""Internal guarded browser-visit writer; never expose caller-provided trust context."""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from fractions import Fraction
from typing import Literal
from urllib.parse import urlsplit

from pydantic import ValidationError

from personalcontext.contracts.event_temporal import _instant
from personalcontext.ingest.visit.model import WebVisit
from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.runtime.authorization import device_policy_allows
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext, valid_context
from personalcontext.privacy.sanitizer.transaction import prepare_web

VisitResult = Literal["accepted", "duplicate", "conflict", "rejected"]
_RETENTION = 90 * 86400
_EPOCH = _instant("1970-01-01T00:00:00Z")


def _record(connection: sqlite3.Connection, event: WebVisit, request: CaptureRequest, context: SanitizerContext,
            latch: CaptureLatch, clock: Callable[[], datetime]) -> VisitResult | None:
    source = connection.execute("SELECT kind FROM sources WHERE source_id=? AND device_id=?",
                                (event.source_id, event.device_id)).fetchone()
    if source != ("browser",):
        return None
    now = clock()
    try:
        if now.tzinfo is None or now.utcoffset() is None:
            return None
        received = int(now.timestamp())
        if not 0 <= received <= 2**53 - 1 - _RETENTION:
            return None
        latest = _EPOCH + Fraction(received + 300)
        if any(_instant(value) > latest for value in (event.started_at, event.observed_at)):
            return None
        if event.ended_at is not None and _instant(event.ended_at) > latest:
            return None
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    safe = prepare_web(connection, request, context, {"url": event.payload.url, "title": event.payload.title},
                       latch=latch, clock=clock)
    if safe is None or urlsplit(safe.url).hostname != event.payload.domain:
        return None
    payload = {"domain": event.payload.domain, "url": safe.url, "title": safe.title}
    clean = event.model_dump(mode="json", exclude={"payload"}) | {"payload": payload}
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).digest()
    existing = connection.execute("SELECT e.event_id,e.source_id,e.source_event_key,e.body_hash,e.job_key,j.kind "
                                  "FROM events e LEFT JOIN jobs j ON j.idempotency_key=e.job_key "
                                  "WHERE e.event_id=? OR (e.source_id=? AND e.source_event_key=?)",
                                  (event.event_id, event.source_id, event.source_event_key)).fetchall()
    if existing:
        if any(not isinstance(row[0], str) or row[4] != "event:" + row[0] or row[5] != "event.normalize.v1"
               for row in existing):
            raise sqlite3.DatabaseError("Event outbox unavailable")
        expected = (event.event_id, event.source_id, event.source_event_key, digest, "event:" + event.event_id, "event.normalize.v1")
        return "duplicate" if existing == [expected] else "conflict"
    key = "event:" + event.event_id
    connection.execute("INSERT INTO jobs(idempotency_key,kind,status) VALUES (?,?,'pending')", (key, "event.normalize.v1"))
    connection.execute(
        "INSERT INTO events(event_id,device_id,source_id,source_event_key,body_hash,schema_version,kind,"
        "started_at,ended_at,duration_ms,observed_at,timezone,granularity,quality,policy_version,consent_scope,"
        "payload_json,provenance_json,received_at,expires_at,job_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event.event_id, event.device_id, event.source_id, event.source_event_key, digest, event.schema_version,
         event.kind, event.started_at, event.ended_at, event.duration_ms, event.observed_at, event.timezone,
         event.granularity, event.quality, event.policy_version, event.consent_scope,
         json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
         event.provenance.model_dump_json(), received, received + _RETENTION, key),
    )
    return "accepted"


async def submit_web_visit(writer: Writer, latch: CaptureLatch, token: object, device_id: object, value: object,
                           context: SanitizerContext, *, origin: object = None,
                           clock: Callable[[], datetime] | None = None) -> VisitResult:
    """Trust context and Origin must originate in a verified adapter/transport, not the event body."""
    if type(value) is not dict:
        return "rejected"
    try:
        event = WebVisit.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        return "rejected"
    if event.device_id != device_id or not valid_context(context):
        return "rejected"
    now = clock or (lambda: datetime.now(UTC))
    request = CaptureRequest(event.source_id, event.consent_scope, event.policy_version, context.private, context.sensitivity)

    def authorize(connection: sqlite3.Connection) -> bool:
        return device_policy_allows(connection, token=token, device_id=device_id, request=request,
                                    latch=latch, origin=origin, clock=now)

    result: VisitResult | None = await submit_capture(writer, latch, lambda c: _record(c, event, request, context, latch, now), authorize)
    return result if result is not None else "rejected"
