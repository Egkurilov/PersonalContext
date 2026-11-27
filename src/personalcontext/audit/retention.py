"""Purge expired identifier-free audit events on startup and periodically."""

import asyncio
import math
import sqlite3
import time
from collections.abc import Callable
from contextlib import suppress

from personalcontext.audit.record import RETENTION
from personalcontext.jobs.writer import Writer


def prune_audit(connection: sqlite3.Connection, now: int) -> int:
    if type(now) is not int or not 0 <= now <= 2**53 - 1:
        raise ValueError("Invalid audit clock")
    connection.execute("BEGIN IMMEDIATE")
    return connection.execute("DELETE FROM security_audit WHERE occurred_at < ?", (now - RETENTION,)).rowcount


class AuditHousekeeping:
    def __init__(self, writer: Writer, *, clock: Callable[[], int] | None = None, interval: float = 3600) -> None:
        if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
            raise ValueError("Invalid audit interval")
        self.writer = writer
        self.clock = clock or (lambda: int(time.time()))
        self.interval = interval
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.writer.submit(lambda connection: prune_audit(connection, self.clock()))
        self.task = asyncio.create_task(self._run(), name="audit-retention")

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            await self.writer.submit(lambda connection: prune_audit(connection, self.clock()))

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self.task
