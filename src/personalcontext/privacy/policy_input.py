"""Validate a bounded owner-provided capture policy document."""

from personalcontext.privacy.policy_validation import PolicyDraft, valid_draft


def parse_policy(value: dict[str, object] | None) -> tuple[int, PolicyDraft] | None:
    fields = {"version", "paused", "ttl", "allowed", "denied", "grants"}
    if value is None or value.keys() != fields:
        return None
    version, paused, ttl = value["version"], value["paused"], value["ttl"]
    allowed, denied, grants = value["allowed"], value["denied"], value["grants"]
    if type(version) is not int or type(paused) is not bool or type(ttl) is not int:
        return None
    if not all(isinstance(item, list) for item in (allowed, denied, grants)):
        return None
    assert isinstance(allowed, list) and isinstance(denied, list) and isinstance(grants, list)
    if len(allowed) > 64 or len(denied) > 64 or len(grants) > 192:
        return None
    if not all(isinstance(item, str) for item in allowed + denied):
        return None
    if len(set(allowed)) != len(allowed) or len(set(denied)) != len(denied):
        return None
    pairs: list[tuple[str, str]] = []
    for item in grants:
        if (not isinstance(item, dict) or item.keys() != {"source", "scope"}
                or not isinstance(item["source"], str) or not isinstance(item["scope"], str)):
            return None
        pairs.append((item["source"], item["scope"]))
    if len(set(pairs)) != len(pairs):
        return None
    draft = PolicyDraft(paused, ttl, frozenset(allowed), frozenset(denied), frozenset(pairs))
    return (version, draft) if valid_draft(draft) else None
