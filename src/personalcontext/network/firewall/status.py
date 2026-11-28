"""Bounded, read-only assessment of one firewall snapshot."""

import threading
from typing import Literal

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.policy import firewall_allows_private_only
from personalcontext.network.firewall.windows import read_firewall_snapshot

_GATE = threading.BoundedSemaphore(1)
FirewallStatus = Literal["unavailable", "not_restricted", "restricted"]


def firewall_status(boundary: PrivateBoundary, executable: str) -> FirewallStatus:
    if not _GATE.acquire(blocking=False):
        return "unavailable"
    try:
        snapshot = read_firewall_snapshot(boundary)
        if snapshot is None:
            return "unavailable"
        return "restricted" if firewall_allows_private_only(boundary, executable, *snapshot) else "not_restricted"
    except Exception:  # noqa: BLE001 - policy details must not leak through diagnostics
        return "unavailable"
    finally:
        _GATE.release()
