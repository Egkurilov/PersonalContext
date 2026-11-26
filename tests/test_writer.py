import asyncio
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class WriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_rejects_overload_and_drains_committed_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            initialize_database(path)
            writer = Writer(path, capacity=1)
            await writer.start()
            running = threading.Event()
            release = threading.Event()

            def blocking(connection):
                running.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("fixture timeout")
                connection.execute("INSERT INTO app_metadata VALUES ('fixture', 'committed')")

            first = asyncio.create_task(writer.submit(blocking))
            try:
                self.assertTrue(await asyncio.to_thread(running.wait, 2))
                second = asyncio.create_task(writer.submit(lambda connection: 2))
                await asyncio.sleep(0)
                with self.assertRaisesRegex(RuntimeError, "queue is full"):
                    await writer.submit(lambda connection: 3)
                release.set()
                await first
                self.assertEqual(await second, 2)
            finally:
                release.set()
                await writer.close()

    async def test_failed_connection_rejects_later_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            try:
                with self.assertRaises(sqlite3.ProgrammingError):
                    await asyncio.wait_for(writer.submit(lambda connection: connection.close()), 2)
                with self.assertRaisesRegex(RuntimeError, "closed"):
                    await asyncio.wait_for(writer.submit(lambda connection: 1), 2)
            finally:
                await writer.close()
