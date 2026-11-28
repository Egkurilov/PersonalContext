"""Bounded firewall-policy inputs; values must come from an effective policy snapshot."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FirewallProfile:
    name: str
    enabled: bool
    default_inbound: str


@dataclass(frozen=True)
class FirewallRule:
    profiles: frozenset[str]
    protocol: str
    ports: tuple[str, ...]
    remotes: tuple[str, ...] = field(repr=False)
    program: str = field(repr=False)
    locals: tuple[str, ...] = field(default=("Any",), repr=False)
    edge: str = "Block"
    unrestricted: bool = False
