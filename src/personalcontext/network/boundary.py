"""Transport request boundaries; private mode is not yet wired to a listener."""

import ipaddress
import re
from dataclasses import dataclass

_PRIVATE = tuple(map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")))
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


@dataclass(frozen=True)
class LocalBoundary:
    """The fixed, local-only default listener policy."""


@dataclass(frozen=True)
class PrivateBoundary:
    address: str
    hostname: str
    port: int
    peers: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            if type(self.peers) is not tuple:
                raise ValueError("Invalid private network boundary")
            address = ipaddress.ip_address(self.address)
            valid_address = str(address) == self.address and any(address.version == net.version and address in net for net in _PRIVATE)
            networks = tuple(ipaddress.ip_network(value, strict=True) for value in self.peers)
            valid_networks = bool(networks) and len(networks) <= 16 and all(
                str(net) == raw and any(net.version == allowed.version and net.network_address in allowed
                                        and net.prefixlen >= allowed.prefixlen for allowed in _PRIVATE)
                for net, raw in zip(networks, self.peers, strict=True)
            )
            labels = self.hostname.split(".")
            valid_name = (len(self.hostname) <= 253 and len(labels) >= 2 and all(_LABEL.fullmatch(label) for label in labels)
                          and not labels[-1].isdigit())
            if not (valid_address and valid_networks and valid_name and type(self.port) is int and 1 <= self.port <= 65535):
                raise ValueError("Invalid private network boundary")
        except (TypeError, AttributeError, ValueError):
            raise ValueError("Invalid private network boundary") from None

    @classmethod
    def create(cls, address: str, hostname: str, port: int, peers: list[str]) -> "PrivateBoundary":
        return cls(address, hostname, port, tuple(peers))


def expected_origin(boundary: LocalBoundary | PrivateBoundary) -> str:
    if isinstance(boundary, PrivateBoundary):
        suffix = "" if boundary.port == 443 else f":{boundary.port}"
        return f"https://{boundary.hostname}{suffix}"
    return "http://127.0.0.1:17890"


def check_request(boundary: LocalBoundary | PrivateBoundary, peer: str | None, scheme: str,
                  hosts: list[str], origins: list[str], forwarding: list[str]) -> tuple[int, str] | None:
    if isinstance(boundary, LocalBoundary):
        valid_peer = peer == "127.0.0.1" and scheme == "http"
        valid_hosts = {"127.0.0.1", "127.0.0.1:17890"}
    elif isinstance(boundary, PrivateBoundary):
        try:
            address = ipaddress.ip_address(peer or "")
            valid_peer = scheme == "https" and any(address in ipaddress.ip_network(net) for net in boundary.peers)
        except ValueError:
            valid_peer = False
        valid_hosts = {f"{boundary.hostname}:{boundary.port}"}
        if boundary.port == 443:
            valid_hosts.add(boundary.hostname)
    else:
        return (403, "Forbidden")
    if not valid_peer:
        return (403, "Forbidden")
    if forwarding:
        return (400, "Invalid forwarding headers")
    if len(hosts) != 1 or hosts[0] not in valid_hosts:
        return (400, "Invalid host")
    if len(origins) > 1 or (origins and origins[0] != expected_origin(boundary)):
        return (403, "Invalid origin")
    return None
