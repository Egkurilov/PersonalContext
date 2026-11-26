import asyncio
from functools import partial

from personalcontext.jobs import repository
from personalcontext.jobs.writer import Writer


class Scheduler:
    def __init__(self, path, handlers, poll_interval=1.0):
        self.writer = Writer(path)
        self.handlers = dict(handlers)
        self.poll_interval = poll_interval
        self.stopping = asyncio.Event()
        self.task = None

    async def start(self):
        await self.writer.start()
        self.task = asyncio.create_task(self._run(), name="job-scheduler")

    async def enqueue(self, kind, key):
        if not kind or not key or len(kind) > 128 or len(key) > 256:
            raise ValueError("Invalid job identity")
        return await self.writer.submit(partial(repository.enqueue, kind=kind, key=key))

    async def _run(self):
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

    async def stop(self):
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
