"""Compose policy and sanitizer; context must come from a trusted local source."""

from datetime import datetime

from personalcontext.privacy.capture_policy import (
    CapturePolicy,
    CaptureRequest,
    allows_capture,
)
from personalcontext.privacy.sanitizer.app import SanitizedApp, sanitize_app
from personalcontext.privacy.sanitizer.rules import (
    SanitizerContext,
    domain_allowed,
    valid_context,
)
from personalcontext.privacy.sanitizer.text import sanitize_text
from personalcontext.privacy.sanitizer.web import SanitizedWeb, sanitize_web


def _allowed(policy: CapturePolicy, request: CaptureRequest, context: SanitizerContext, now: datetime) -> bool:
    return (isinstance(request, CaptureRequest) and valid_context(context)
            and request.private is context.private and request.sensitivity == context.sensitivity
            and allows_capture(policy, request, now))


def gate_web(policy: CapturePolicy, request: CaptureRequest, context: SanitizerContext,
             value: object, now: datetime) -> SanitizedWeb | None:
    if not _allowed(policy, request, context, now) or request.scope != "metadata":
        return None
    return sanitize_web(value, context)


def gate_app(policy: CapturePolicy, request: CaptureRequest, context: SanitizerContext,
             value: object, now: datetime) -> SanitizedApp | None:
    if not _allowed(policy, request, context, now) or request.scope != "metadata":
        return None
    return sanitize_app(value, context)


def gate_text(policy: CapturePolicy, request: CaptureRequest, context: SanitizerContext,
              domain: object, value: object, now: datetime) -> str | None:
    if (not _allowed(policy, request, context, now) or request.scope not in ("text", "ocr")
            or (request.scope == "ocr" and context.ocr_approved is not True)
            or not isinstance(domain, str) or not domain_allowed(domain, context)):
        return None
    return sanitize_text(value, 16384)
