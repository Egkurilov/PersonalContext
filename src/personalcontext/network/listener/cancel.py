"""Cancel a slow preflight without letting its worker open a socket."""

import asyncio
from collections.abc import Callable
from typing import Any


class StartCancelled(Exception):
    pass


async def preflight(cancel: asyncio.Event, function: Callable[..., Any], *args: object) -> Any:
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    stopped = asyncio.create_task(cancel.wait())
    try:
        await asyncio.wait({worker, stopped}, return_when=asyncio.FIRST_COMPLETED)
        if cancel.is_set():
            raise StartCancelled
        return await worker
    finally:
        stopped.cancel()
        if not worker.done():
            worker.cancel()
        elif not worker.cancelled():
            worker.exception()
