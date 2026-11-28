"""Bounded policy draft validation; invalid configuration never grants capture."""

from dataclasses import dataclass

from personalcontext.privacy.capture_policy import _valid_source

SCOPES = frozenset({"metadata", "text", "ocr"})
MAX_TIME = 253402214400 - 86400


@dataclass(frozen=True)
class PolicyDraft:
    paused: bool
    ttl: int
    allowed: frozenset[str]
    denied: frozenset[str]
    grants: frozenset[tuple[str, str]]


def valid_draft(value: object) -> bool:
    if not isinstance(value, PolicyDraft) or type(value.paused) is not bool or type(value.ttl) is not int:
        return False
    if not 1 <= value.ttl <= 86400 or not all(isinstance(item, frozenset) for item in (value.allowed, value.denied, value.grants)):
        return False
    if len(value.allowed) > 64 or len(value.denied) > 64 or len(value.grants) > 192:
        return False
    if not all(_valid_source(source) for source in value.allowed | value.denied):
        return False
    return all(isinstance(grant, tuple) and len(grant) == 2 and grant[0] in value.allowed
               and isinstance(grant[1], str) and grant[1] in SCOPES for grant in value.grants)
