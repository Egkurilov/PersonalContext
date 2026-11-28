"""Conservative secret and sensitive-text rejection; never logs input."""

import html
import re
import unicodedata
from urllib.parse import unquote

_KEY_VALUE = re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|secret|access[_-]?token|refresh[_-]?token|session[_-]?id|authorization|cookie|пароль|секрет|токен|ключ[_ -]?доступа|код[_ -]?подтверждения)\s*[:=]")
_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]{8,}")
_JWT = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_DIGITS = re.compile(r"(?<!\d)(?:\d[ -]?){8,}(?!\d)")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{1,4}:){2,}[0-9a-f:]{1,}(?![0-9a-z])")
_MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_FORM = re.compile(r"(?i)<\s*/?\s*(?:form|input|script|textarea|select|button|iframe|meta|link)\b")
_LONG = re.compile(r"[A-Za-z0-9_-]{32,}")


def sanitize_text(value: object, max_bytes: object, *, allow_multiline: bool = True) -> str | None:
    if (not isinstance(value, str) or type(max_bytes) is not int or not 1 <= max_bytes <= 16384
            or type(allow_multiline) is not bool):
        return None
    if len(value) > max_bytes:
        return None
    try:
        text = unicodedata.normalize("NFKC", html.unescape(value))
        if len(text.encode("utf-8")) > max_bytes:
            return None
    except (UnicodeError, ValueError):
        return None
    if any(unicodedata.category(char) in ("Cc", "Cf", "Cs") and not (allow_multiline and char in "\n\t") for char in text):
        return None
    try:
        view = text
        for _ in range(2):
            view = unicodedata.normalize("NFKC", html.unescape(unquote(view, encoding="utf-8", errors="strict")))
        if re.search(r"%[0-9a-fA-F]{2}", view) or len(view) > 16384:
            return None
    except (UnicodeError, ValueError):
        return None
    if any(unicodedata.category(char) in ("Cc", "Cf", "Cs") and not (allow_multiline and char in "\n\t") for char in view):
        return None
    if ("@" in view or _KEY_VALUE.search(view) or _BEARER.search(view) or _JWT.search(view)
            or _DIGITS.search(view) or _PHONE.search(view) or _IPV4.search(view) or _IPV6.search(view)
            or _MARKUP.search(view) or _FORM.search(view) or "PRIVATE KEY-----" in view.upper()
            or "http://" in view.lower() or "https://" in view.lower()):
        return None
    if _LONG.search(view):
        return None
    return text
