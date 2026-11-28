"""Stop private access when the server or firewall assessment fails."""

import asyncio
import contextlib
import sqlite3
import sys
from typing import TYPE_CHECKING

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.status import firewall_status
from personalcontext.network.listener.read import audit_stop

if TYPE_CHECKING:
    from personalcontext.network.listener.manager import PrivateListener

CHECK_INTERVAL = 15


async def monitor_listener(manager: "PrivateListener", boundary: PrivateBoundary) -> None:
    try:
        while manager.task is not None:
            done, _ = await asyncio.wait({manager.task}, timeout=CHECK_INTERVAL)
            if done or not manager.healthy() or await asyncio.to_thread(firewall_status, boundary, sys.executable) != "restricted":
                break
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001,S110 - fail closed without logging network details
        pass
    await manager.stop()
    with contextlib.suppress(sqlite3.Error, RuntimeError):
        await manager.writer.submit(lambda c: audit_stop(c, "system"))
