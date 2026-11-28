"""Assess a complete effective Windows firewall snapshot conservatively."""

import ipaddress
import ntpath
import os

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.model import FirewallProfile, FirewallRule
from personalcontext.network.firewall.ranges import Network, networks, port_match

_PROFILES = frozenset({"Domain", "Private", "Public"})


def _subnet(child: Network, parent: Network) -> bool:
    return child.version == parent.version and child.prefixlen >= parent.prefixlen and child.network_address in parent


def _program(value: str) -> str | None:
    if not isinstance(value, str) or not ntpath.isabs(value) or "%" in value:
        return None
    drive, _ = ntpath.splitdrive(value)
    if len(drive) != 2 or drive[1] != ":":
        return None
    path = os.path.realpath(value) if os.name == "nt" else value
    return ntpath.normcase(ntpath.normpath(path))


def firewall_allows_private_only(boundary: PrivateBoundary, executable: str,
                                 profiles: list[FirewallProfile], rules: list[FirewallRule]) -> bool:
    """Do not use unless the snapshot is complete, current and for the selected interface."""
    if (not isinstance(boundary, PrivateBoundary) or not isinstance(profiles, list) or not 1 <= len(profiles) <= 3
            or not isinstance(rules, list) or len(rules) > 4096):
        return False
    target = _program(executable)
    if target is None:
        return False
    if any(not isinstance(p, FirewallProfile) or p.name not in _PROFILES or p.enabled is not True
           or p.default_inbound != "Block" for p in profiles):
        return False
    active = {profile.name for profile in profiles}
    if len(active) != len(profiles):
        return False
    allowed = networks(boundary.peers)
    if allowed is None:
        return False
    coverage: dict[str, list[Network]] = {name: [] for name in active}
    local = ipaddress.ip_address(boundary.address)
    for rule in rules:
        if (not isinstance(rule, FirewallRule) or not isinstance(rule.profiles, frozenset)
                or not rule.profiles or not rule.profiles <= _PROFILES or not isinstance(rule.protocol, str)):
            return False
        applies = active & rule.profiles
        if not applies or rule.protocol.upper() in ("UDP", "17", "ICMPV4", "ICMPV6", "1", "58"):
            continue
        program = _program(rule.program)
        if program is not None and program != target:
            continue
        matches, known_port = port_match(rule.ports, boundary.port)
        if not matches:
            continue
        local_any = rule.locals == ("Any",) or rule.locals == ("*",)
        local_networks = None if local_any else networks(rule.locals)
        if local_networks is not None and not any(local.version == network.version and local in network for network in local_networks):
            continue
        if rule.edge != "Block":
            return False
        remote = networks(rule.remotes)
        if remote is None or any(not any(_subnet(net, parent) for parent in allowed) for net in remote):
            return False
        known_protocol = rule.protocol.upper() in ("TCP", "6", "ANY", "256")
        if (program == target and known_port and known_protocol and rule.unrestricted is True
                and (local_any or local_networks is not None)):
            for profile in applies:
                coverage[profile].extend(remote)
    return all(all(any(_subnet(peer, net) for net in coverage[name]) for peer in allowed) for name in active)
