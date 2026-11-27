import asyncio
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.storage.initialize import initialize_database


class WriterCapturePauseTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_pause_callback_stops_writer_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)

            def broken_pause():
                raise RuntimeError("synthetic callback failure")

            writer = Writer(path, on_storage_failure=broken_pause)
            await writer.start()
            try:
                def fail(connection):
                    connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
                    raise sqlite3.OperationalError("synthetic database failure")

                with self.assertRaises(sqlite3.OperationalError):
                    await writer.submit(fail)
                with self.assertRaises(RuntimeError):
                    await writer.submit(lambda _connection: True)
            finally:
                await writer.close()
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM app_metadata WHERE key='fixture'").fetchone()[0], 0)

    async def test_database_error_pauses_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            latch = CaptureLatch()
            latch.resume_if_unchanged(latch.generation())
            writer = Writer(path, on_storage_failure=latch.pause)
            await writer.start()
            try:
                def fail(connection):
                    connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
                    raise sqlite3.OperationalError("synthetic failure")

                with self.assertRaises(sqlite3.OperationalError):
                    await writer.submit(fail)
                self.assertTrue(latch.is_paused())
                count = await writer.submit(lambda connection: connection.execute(
                    "SELECT count(*) FROM app_metadata WHERE key='fixture'",
                ).fetchone()[0])
                self.assertEqual(count, 0)
            finally:
                await writer.close()

    async def test_full_or_closed_writer_pauses_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            latch = CaptureLatch()
            latch.resume_if_unchanged(latch.generation())
            writer = Writer(path, capacity=1, on_storage_failure=latch.pause)
            await writer.start()
            started, release = threading.Event(), threading.Event()

            def block(_connection):
                started.set()
                release.wait(timeout=3)
                return True

            first = asyncio.create_task(writer.submit(block))
            second = None
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                second = asyncio.create_task(writer.submit(lambda _connection: True))
                for _ in range(100):
                    if writer.queue.qsize() == 1:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(writer.queue.qsize(), 1)
                with self.assertRaisesRegex(RuntimeError, "full"):
                    await writer.submit(lambda _connection: True)
                self.assertTrue(latch.is_paused())
            finally:
                release.set()
                await first
                if second is not None:
                    await second
                await writer.close()
            self.assertTrue(latch.drain())
            self.assertTrue(latch.resume_if_unchanged(latch.generation()))
            with self.assertRaisesRegex(RuntimeError, "closed"):
                await writer.submit(lambda _connection: True)
            self.assertTrue(latch.is_paused())
