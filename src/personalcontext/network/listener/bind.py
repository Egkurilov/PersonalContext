"""Bind exactly the owner-selected private interface, without reuse."""

import ipaddress
import socket
import sys

from personalcontext.network.boundary import PrivateBoundary


def bind_listener(boundary: PrivateBoundary) -> socket.socket:
    address = ipaddress.ip_address(boundary.address)
    family = socket.AF_INET if address.version == 4 else socket.AF_INET6
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((boundary.address, boundary.port))
        listener.setblocking(False)
        return listener
    except BaseException:
        listener.close()
        raise
