"""Validate stored owner filters and combine them with trusted adapter context."""

from dataclasses import dataclass, field

from personalcontext.privacy.sanitizer.rules import SanitizerContext, valid_context

FIELDS = ("allowed_domains", "denied_domains", "allowed_apps", "denied_apps")


@dataclass(frozen=True)
class FilterRules:
    allowed_domains: frozenset[str] = field(default_factory=frozenset, repr=False)
    denied_domains: frozenset[str] = field(default_factory=frozenset, repr=False)
    allowed_apps: frozenset[str] = field(default_factory=frozenset, repr=False)
    denied_apps: frozenset[str] = field(default_factory=frozenset, repr=False)


def valid_rules(value: object) -> bool:
    if not isinstance(value, FilterRules):
        return False
    context = SanitizerContext(value.allowed_domains, value.denied_domains, value.allowed_apps, value.denied_apps,
                               private=False, sensitivity="ordinary")
    return valid_context(context)


def intersect(rules: FilterRules, context: SanitizerContext) -> SanitizerContext | None:
    if not valid_rules(rules) or not valid_context(context):
        return None
    result = SanitizerContext(rules.allowed_domains & context.allowed_domains, rules.denied_domains | context.denied_domains,
                              rules.allowed_apps & context.allowed_apps, rules.denied_apps | context.denied_apps,
                              context.private, context.sensitivity, context.ocr_approved)
    return result if valid_context(result) else None
