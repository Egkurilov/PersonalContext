import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path

from personalcontext.jobs import repository
from personalcontext.jobs.writer import Writer


class Scheduler:
    def __init__(self, path: Path, handlers: dict[str, Callable[[str], Awaitable[None]]], poll_interval: float = 1.0,
                 *, on_storage_failure: Callable[[], None] | None = None) -> None:
        self.writer = Writer(path, on_storage_failure=on_storage_failure)
        self.on_storage_failure = on_storage_failure
        self.handlers = dict(handlers)
        self.poll_interval = poll_interval
        self.stopping = asyncio.Event()
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.writer.start()
        self.task = asyncio.create_task(self._run(), name="job-scheduler")

    async def enqueue(self, kind: str, key: str) -> bool:
        if not kind or not key or len(kind) > 128 or len(key) > 256:
            raise ValueError("Invalid job identity")
        return await self.writer.submit(partial(repository.enqueue, kind=kind, key=key))

    async def _run(self) -> None:
        try:
            await self._run_jobs()
        finally:
            if self.on_storage_failure is not None:
                self.on_storage_failure()

    async def _run_jobs(self) -> None:
        while not self.stopping.is_set():
            job = await self.writer.submit(partial(repository.claim, kinds=tuple(self.handlers), lease_seconds=60))
            if job is None:
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass
                continue
            key, kind, attempts, token = job
            succeeded = False
            try:
                await asyncio.wait_for(self.handlers[kind](key), timeout=30)
                succeeded = True
            except Exception:  # noqa: BLE001 - persist failure without logging job content
                succeeded = False
            await self.writer.submit(partial(repository.finish, key=key, token=token, attempts=attempts, succeeded=succeeded))

    async def stop(self) -> None:
        self.stopping.set()
        if self.task is not None:
            try:
                await asyncio.wait_for(self.task, timeout=5)
            except TimeoutError:
                self.task.cancel()
            finally:
                await self.writer.close()
        else:
            await self.writer.close()
