import asyncio
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from personalcontext.jobs.scheduler import Scheduler
from personalcontext.storage.initialize import initialize_database


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "jobs.db"
        initialize_database(self.path)
        self.scheduler = None

    async def asyncTearDown(self):
        if self.scheduler is not None:
            await self.scheduler.stop()
        self.directory.cleanup()

    async def test_committed_job_and_duplicate_run_once(self):
        called = []
        finished = asyncio.Event()

        async def handler(key):
            called.append(key)
            finished.set()

        self.scheduler = Scheduler(self.path, {"synthetic": handler}, poll_interval=0.01)
        await self.scheduler.start()
        self.assertTrue(await self.scheduler.enqueue("synthetic", "fixture-1"))
        self.assertFalse(await self.scheduler.enqueue("synthetic", "fixture-1"))
        await asyncio.wait_for(finished.wait(), 2)
        await asyncio.sleep(0.1)
        self.assertEqual(called, ["fixture-1"])

    async def test_pending_job_survives_restart(self):
        called = asyncio.Event()
        async def handler(_key):
            called.set()
        self.scheduler = Scheduler(self.path, {}, poll_interval=0.01)
        await self.scheduler.start()
        await self.scheduler.enqueue("synthetic", "fixture-2")
        await self.scheduler.stop()
        self.scheduler = Scheduler(self.path, {"synthetic": handler}, poll_interval=0.01)
        await self.scheduler.start()
        await asyncio.wait_for(called.wait(), 2)

    async def test_duplicate_key_with_different_kind_is_rejected(self):
        self.scheduler = Scheduler(self.path, {}, poll_interval=0.01)
        await self.scheduler.start()
        await self.scheduler.enqueue("one", "fixture-3")
        with self.assertRaises(ValueError):
            await self.scheduler.enqueue("two", "fixture-3")

    async def test_claimed_job_recovers_after_process_kill(self):
        code = """
import sqlite3, sys, time
from personalcontext.jobs import repository
connection = sqlite3.connect(sys.argv[1])
repository.enqueue(connection, 'synthetic', 'crash-fixture')
connection.commit()
repository.claim(connection, ('synthetic',), 60)
connection.commit()
print('claimed', flush=True)
time.sleep(30)
"""
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, str(self.path), stdout=asyncio.subprocess.PIPE)
        try:
            line = await asyncio.wait_for(process.stdout.readline(), 5)
            self.assertEqual(line.strip(), b"claimed")
        finally:
            process.kill()
            await asyncio.wait_for(process.wait(), 5)
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE jobs SET lease_until=0 WHERE idempotency_key='crash-fixture'")
        connection.close()
        completed = asyncio.Event()

        async def handler(_key):
            completed.set()

        self.scheduler = Scheduler(self.path, {"synthetic": handler}, poll_interval=0.01)
        await self.scheduler.start()
        await asyncio.wait_for(completed.wait(), 3)
