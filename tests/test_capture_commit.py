import asyncio
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.storage.initialize import initialize_database


class CaptureCommitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.latch = CaptureLatch()
        self.latch.resume_if_unchanged(self.latch.generation())
        self.writer = Writer(self.path, on_storage_failure=self.latch.pause)
        await self.writer.start()

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def count(self):
        return await self.writer.submit(lambda connection: connection.execute(
            "SELECT count(*) FROM app_metadata WHERE key='fixture'",
        ).fetchone()[0])

    async def test_paused_or_failed_final_check_rolls_back(self):
        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
            return True

        result = await submit_capture(self.writer, self.latch, operation, lambda _connection: False)
        self.assertIsNone(result)
        self.assertEqual(await self.count(), 0)
        self.latch.pause()
        self.assertIsNone(await submit_capture(self.writer, self.latch, operation, lambda _connection: True))
        self.assertEqual(await self.count(), 0)

    async def test_current_permission_commits_and_returns_only_after_commit(self):
        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
            return True

        result = await submit_capture(self.writer, self.latch, operation, lambda _connection: True)
        self.assertTrue(result)
        self.assertEqual(await self.count(), 1)

    async def test_failed_writer_safety_signal_prevents_commit(self):
        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
            return True

        def validate(_connection):
            self.writer.safety_failed.set()
            return True

        with self.assertRaisesRegex(RuntimeError, "safety"):
            await submit_capture(self.writer, self.latch, operation, validate)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM app_metadata WHERE key='fixture'").fetchone()[0], 0)

    async def test_pause_while_filtering_rolls_back_inflight_write(self):
        entered, release = threading.Event(), threading.Event()

        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
            entered.set()
            release.wait(timeout=3)
            return True

        task = asyncio.create_task(submit_capture(self.writer, self.latch, operation, lambda _connection: True))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.latch.pause()
        finally:
            release.set()
        self.assertIsNone(await task)
        await asyncio.to_thread(self.latch.drain)
        self.assertEqual(await self.count(), 0)

    async def test_pause_during_final_validation_waits_for_rollback(self):
        entered, release = threading.Event(), threading.Event()
        checks = 0

        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
            return True

        def validate(_connection):
            nonlocal checks
            checks += 1
            if checks == 1:
                return True
            entered.set()
            release.wait(timeout=3)
            return True

        task = asyncio.create_task(submit_capture(self.writer, self.latch, operation, validate))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.latch.pause()
            drain = asyncio.create_task(asyncio.to_thread(self.latch.drain))
            await asyncio.sleep(0.03)
            self.assertFalse(drain.done())
        finally:
            release.set()
        self.assertIsNone(await task)
        await drain
        self.assertEqual(await self.count(), 0)
