"""Fail-closed policy decision primitive; not an ingestion or consent API."""

from dataclasses import dataclass
from datetime import UTC, datetime

_SCOPES = frozenset({"metadata", "text", "ocr"})


@dataclass(frozen=True)
class CapturePolicy:
    version: int = 1
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    paused: bool = True
    allowed_sources: frozenset[str] = frozenset()
    denied_sources: frozenset[str] = frozenset()
    scopes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CaptureRequest:
    source: str
    scope: str
    policy_version: int
    private: bool | None
    sensitivity: str | None


def _valid_source(value: object) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 128
            and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value))


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def allows_capture(policy: CapturePolicy, request: CaptureRequest, now: datetime) -> bool:
    """Check a known classification and explicit source/scope grant; unknowns deny."""
    if not isinstance(policy, CapturePolicy) or not isinstance(request, CaptureRequest):
        return False
    if (type(policy.version) is not int or policy.version < 1
            or type(request.policy_version) is not int or request.policy_version != policy.version
            or policy.paused is not False or request.private is not False
            or request.sensitivity != "ordinary" or not _valid_source(request.source)
            or not isinstance(request.scope, str)):
        return False
    if (not isinstance(policy.allowed_sources, frozenset) or not isinstance(policy.denied_sources, frozenset)
            or not isinstance(policy.scopes, frozenset) or not all(map(_valid_source, policy.allowed_sources))
            or not all(map(_valid_source, policy.denied_sources)) or not policy.scopes <= _SCOPES
            or request.scope not in _SCOPES or request.scope not in policy.scopes
            or request.source not in policy.allowed_sources or request.source in policy.denied_sources):
        return False
    try:
        if not (_aware(now) and _aware(policy.issued_at) and _aware(policy.expires_at)):
            return False
        assert policy.issued_at is not None and policy.expires_at is not None
        return policy.issued_at.astimezone(UTC) <= now.astimezone(UTC) < policy.expires_at.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return False
