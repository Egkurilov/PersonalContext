"""Explicit-app metadata filtering; executable paths are not accepted."""

from dataclasses import dataclass, field

from personalcontext.privacy.sanitizer.rules import (
    SanitizerContext,
    app_allowed,
    valid_context,
)
from personalcontext.privacy.sanitizer.text import sanitize_text


@dataclass(frozen=True)
class SanitizedApp:
    app: str = field(repr=False)
    title: str | None = field(repr=False)


def sanitize_app(value: object, context: object) -> SanitizedApp | None:
    if not valid_context(context) or not isinstance(context, SanitizerContext) or type(value) is not dict:
        return None
    if not {"app"} <= value.keys() or not value.keys() <= {"app", "title"} or not isinstance(value["app"], str):
        return None
    app = value["app"].lower()
    if not app_allowed(app, context):
        return None
    title = value.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 512
                              or sanitize_text(title, 2048, allow_multiline=False) is None):
        return None
    return SanitizedApp(app, sanitize_text(title, 2048, allow_multiline=False) if title is not None else None)
