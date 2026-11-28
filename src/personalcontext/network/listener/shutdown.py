"""Cancel startup and close the private listener without stopping loopback."""

import asyncio
import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from personalcontext.network.listener.manager import PrivateListener


def quiesce(manager: "PrivateListener") -> None:
    if manager.server is not None:
        manager.server.should_exit = True
        for item in getattr(manager.server, "servers", []):
            item.close()
        state = getattr(manager.server, "server_state", None)
        for connection in list(getattr(state, "connections", ())):
            with contextlib.suppress(Exception):
                connection.shutdown()
    if manager.socket is not None:
        manager.socket.close()


async def stop_listener(manager: "PrivateListener") -> None:
    manager.generation += 1
    if manager.cancel_start is not None:
        manager.cancel_start.set()
    quiesce(manager)
    async with manager.lock:
        await stop_locked(manager)


async def stop_locked(manager: "PrivateListener") -> None:
    monitor, task = manager.monitor, manager.task
    quiesce(manager)
    manager.monitor, manager.server, manager.task, manager.socket = None, None, None, None
    if monitor is not None and monitor is not asyncio.current_task():
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
    if task is not None:
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
            await asyncio.wait_for(task, 10)
