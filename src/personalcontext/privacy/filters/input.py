"""Parse bounded, exact owner filter documents without echoing inputs."""

from personalcontext.privacy.filters.rules import FIELDS, FilterRules, valid_rules


def parse_filters(value: dict[str, object] | None) -> tuple[int, FilterRules] | None:
    if value is None or value.keys() != {*FIELDS, "version"} or type(value["version"]) is not int:
        return None
    groups: dict[str, frozenset[str]] = {}
    for field in FIELDS:
        items = value[field]
        if (not isinstance(items, list) or len(items) > 128 or not all(isinstance(item, str) for item in items)
                or len(set(items)) != len(items)):
            return None
        groups[field] = frozenset(items)
    rules = FilterRules(**groups)
    return (value["version"], rules) if valid_rules(rules) else None
