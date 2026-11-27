"""Inputs from a trusted local classifier and explicit owner source approvals."""

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from personalcontext.privacy.sanitizer.text import sanitize_text
from personalcontext.privacy.url_normalize import normalize_url

_APP = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_BLOCKED_LABELS = frozenset({"auth", "bank", "banking", "billing", "chat", "finance", "health", "login",
                             "mail", "medical", "messages", "patient", "private", "signin", "work",
                             "банк", "финансы", "медицина", "здоровье", "пациент", "работа", "почта", "сообщения"})
_BLOCKED_APPS = ("password", "keepass", "bitwarden", "1password", "keychain", "authenticator", "vault",
                 "dashlane", "lastpass", "keeper", "enpass", "telegram", "signal", "whatsapp")


@dataclass(frozen=True)
class SanitizerContext:
    allowed_domains: frozenset[str] = field(default_factory=frozenset, repr=False)
    denied_domains: frozenset[str] = field(default_factory=frozenset, repr=False)
    allowed_apps: frozenset[str] = field(default_factory=frozenset, repr=False)
    denied_apps: frozenset[str] = field(default_factory=frozenset, repr=False)
    private: bool | None = None
    sensitivity: str | None = None
    ocr_approved: bool = False


def _domain(value: object) -> bool:
    if (not isinstance(value, str) or not value or len(value) > 253 or value != value.lower()
            or sanitize_text(value, 253, allow_multiline=False) is None):
        return False
    try:
        parts = urlsplit(normalize_url("https://" + value + "/"))
        if parts.hostname != value or parts.netloc != value or "." not in value:
            return False
        try:
            ipaddress.ip_address(value)
            return False
        except ValueError:
            return True
    except ValueError:
        return False


def valid_context(context: object) -> bool:
    if (not isinstance(context, SanitizerContext) or context.private is not False or context.sensitivity != "ordinary"
            or type(context.ocr_approved) is not bool):
        return False
    groups = (context.allowed_domains, context.denied_domains, context.allowed_apps, context.denied_apps)
    if any(not isinstance(group, frozenset) or len(group) > 128 for group in groups):
        return False
    return (all(_domain(value) for value in context.allowed_domains | context.denied_domains)
            and all(isinstance(value, str) and _APP.fullmatch(value) is not None
                    for value in context.allowed_apps | context.denied_apps))


def domain_allowed(host: str, context: SanitizerContext) -> bool:
    if host not in context.allowed_domains or not _domain(host):
        return False
    if any(host == denied or host.endswith("." + denied) for denied in context.denied_domains):
        return False
    try:
        labels = (label.encode("ascii").decode("idna").casefold() for label in host.split("."))
        return not any(label in _BLOCKED_LABELS or label.startswith(("bank", "банк")) for label in labels)
    except UnicodeError:
        return False


def app_allowed(app: str, context: SanitizerContext) -> bool:
    return (_APP.fullmatch(app) is not None and app in context.allowed_apps and app not in context.denied_apps
            and sanitize_text(app, 128, allow_multiline=False) is not None
            and not any(term in app for term in _BLOCKED_APPS))
