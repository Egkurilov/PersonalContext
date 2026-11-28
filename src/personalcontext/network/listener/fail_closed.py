"""Pause capture and schedule private network shutdown on security failures."""

import asyncio
from collections.abc import Callable
from contextlib import suppress

from fastapi import FastAPI

from personalcontext.privacy.runtime.latch import CaptureLatch


def failure_callback(app: FastAPI, latch: CaptureLatch) -> Callable[[], None]:
    loop = asyncio.get_running_loop()

    def fail() -> None:
        latch.pause()
        manager = getattr(app.state, "private_listener", None)
        if manager is None:
            return

        def stop() -> None:
            asyncio.create_task(manager.stop())

        with suppress(RuntimeError):
            loop.call_soon_threadsafe(stop)

    return fail
