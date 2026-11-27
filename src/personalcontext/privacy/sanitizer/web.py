"""Explicit-domain metadata filtering; no fetch or raw-payload persistence."""

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import quote, unquote_to_bytes, urlsplit, urlunsplit

from personalcontext.privacy.sanitizer.rules import (
    SanitizerContext,
    domain_allowed,
    valid_context,
)
from personalcontext.privacy.sanitizer.text import sanitize_text
from personalcontext.privacy.url_normalize import normalize_url

_BAD_PERCENT = re.compile(r"%(?![0-9a-fA-F]{2})")
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
_SENSITIVE = re.compile(r"(?i)(?:^|[/_.-])(?:auth|oauth|authorize|login|logout|signin|sign-in|account|profile|credential|credentials|password|passcode|key|apikey|api-key|api_key|token|tokens|secret|session|reset|billing|payment|payments|bank|finance|medical|patient|private|work|messages|chat|вход|авторизация|кабинет|аккаунт|профиль|пароль|ключ|токен|банк|платеж|платёж|платежи|платёжи|финансы|здоровье|медицина|пациент|работа|сообщения|переписка)(?:$|[/_.-])")


@dataclass(frozen=True)
class SanitizedWeb:
    url: str = field(repr=False)
    title: str | None = field(repr=False)


def _safe_path(path: str) -> str | None:
    try:
        decoded = path
        for _ in range(2):
            if _BAD_PERCENT.search(decoded):
                return None
            if not _PERCENT.search(decoded):
                break
            decoded = unquote_to_bytes(decoded).decode("utf-8", errors="strict")
        if _PERCENT.search(decoded) or "\\" in decoded or "//" in decoded:
            return None
        if any(unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in decoded):
            return None
        if any(part in (".", "..") for part in decoded.split("/")):
            return None
        clean = sanitize_text(decoded, 8192)
        if clean is None or _SENSITIVE.search(clean):
            return None
        return quote(clean, safe="/-._~")
    except (UnicodeError, ValueError):
        return None


def sanitize_web(value: object, context: object) -> SanitizedWeb | None:
    if not valid_context(context) or not isinstance(context, SanitizerContext) or type(value) is not dict:
        return None
    if not {"url"} <= value.keys() or not value.keys() <= {"url", "title"}:
        return None
    title = value.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 512
                              or sanitize_text(title, 2048, allow_multiline=False) is None):
        return None
    try:
        parts = urlsplit(normalize_url(value["url"]))
    except (TypeError, ValueError):
        return None
    if parts.hostname is None or not domain_allowed(parts.hostname, context):
        return None
    path = _safe_path(parts.path)
    if path is None:
        return None
    clean_title = sanitize_text(title, 2048, allow_multiline=False) if title is not None else None
    return SanitizedWeb(urlunsplit((parts.scheme, parts.netloc, path, "", "")), clean_title)
