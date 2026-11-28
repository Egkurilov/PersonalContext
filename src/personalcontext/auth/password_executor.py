"""Bounded off-loop password work; external rate limits remain mandatory."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from personalcontext.auth.password_hash import hash_password, verify_password

T = TypeVar("T")


class PasswordExecutor:
    def __init__(self, capacity: int = 2) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 4:
            raise ValueError("Invalid verifier capacity")
        self._pool = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix="password-hash")
        self._slots: asyncio.Queue[None] = asyncio.Queue(maxsize=capacity)
        for _ in range(capacity):
            self._slots.put_nowait(None)
        self._closed = False

    async def _run(self, operation: Callable[..., T], *args: object) -> T:
        if self._closed:
            raise RuntimeError("Verifier unavailable")
        try:
            self._slots.get_nowait()
        except asyncio.QueueEmpty:
            raise RuntimeError("Verifier busy") from None
        self._slots.task_done()
        try:
            future = asyncio.get_running_loop().run_in_executor(self._pool, operation, *args)
        except BaseException:
            self._slots.put_nowait(None)
            raise

        def finished(result: asyncio.Future[T]) -> None:
            if not result.cancelled():
                result.exception()
            self._slots.put_nowait(None)

        future.add_done_callback(finished)
        return await asyncio.shield(future)

    async def hash(self, password: str) -> str:
        return await self._run(hash_password, password)

    async def verify(self, encoded: str, password: str) -> bool:
        return await self._run(verify_password, encoded, password)

    async def close(self) -> None:
        self._closed = True
        await asyncio.to_thread(self._pool.shutdown, wait=True)
