"""Address ranges eligible for the owner's local-only listener."""

import ipaddress

LAN_NETWORKS = tuple(map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")))


def lan_ranges_allowed(address: str, peers: tuple[str, ...]) -> bool:
    """Reject shared VPN ranges while allowing old configurations to be read."""
    try:
        host = ipaddress.ip_network(address, strict=False)
        networks = [host, *(ipaddress.ip_network(value, strict=True) for value in peers)]
        return bool(peers) and all(any(network.version == allowed.version and
                                       network.prefixlen >= allowed.prefixlen and
                                       network.network_address in allowed for allowed in LAN_NETWORKS)
                                   for network in networks)
    except (TypeError, ValueError):
        return False
