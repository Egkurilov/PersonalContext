import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from personalcontext.jobs import repository
from personalcontext.jobs.scheduler import Scheduler
from personalcontext.storage.initialize import initialize_database


class SchedulerShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_job_recovers_after_graceful_shutdown_and_lease_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.db"
            initialize_database(path)
            clock = [1_000.0]
            started, cancelled, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()

            async def running(_key):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            async def recovered(_key):
                completed.set()

            with patch.object(repository, "time", SimpleNamespace(time=lambda: clock[0])):
                scheduler = Scheduler(path, {"synthetic": running}, poll_interval=0.01)
                try:
                    await scheduler.start()
                    await scheduler.enqueue("synthetic", "fixture-shutdown")
                    await asyncio.wait_for(started.wait(), 3)
                finally:
                    await scheduler.stop()
                self.assertTrue(cancelled.is_set())
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(connection.execute("SELECT status,attempts FROM jobs").fetchone(), ("running", 1))
                clock[0] += 61
                scheduler = Scheduler(path, {"synthetic": recovered}, poll_interval=0.01)
                try:
                    await scheduler.start()
                    await asyncio.wait_for(completed.wait(), 3)
                finally:
                    await scheduler.stop()
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(connection.execute("SELECT status,attempts FROM jobs").fetchone(), ("done", 2))
