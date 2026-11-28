"""Validate a selected listener and peer ranges against a physical LAN."""

import ipaddress

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.lan.networks import LAN_NETWORKS


def _inside(child: ipaddress.IPv4Network | ipaddress.IPv6Network,
            parent: ipaddress.IPv4Network | ipaddress.IPv6Network) -> bool:
    return child.version == parent.version and child.prefixlen >= parent.prefixlen and child.network_address in parent


def local_lan_allowed(boundary: object, prefix: object, physical: object, category: object) -> bool:
    if (not isinstance(boundary, PrivateBoundary) or type(prefix) is not int
            or physical is not True or category not in ("Private", "Public", "Domain")):
        return False
    try:
        network = ipaddress.ip_network(f"{boundary.address}/{prefix}", strict=False)
        if not any(_inside(network, allowed) for allowed in LAN_NETWORKS):
            return False
        peers = (ipaddress.ip_network(value, strict=True) for value in boundary.peers)
        return all(_inside(peer, network) for peer in peers)
    except (ValueError, TypeError):
        return False
