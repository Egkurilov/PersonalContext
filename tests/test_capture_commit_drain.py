import asyncio
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.storage.initialize import initialize_database


class CaptureCommitDrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_confirmation_waits_for_commit_already_in_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            armed, entered, release = threading.Event(), threading.Event(), threading.Event()
            original_connect = sqlite3.connect

            class DelayedConnection(sqlite3.Connection):
                def commit(self):
                    if armed.is_set():
                        entered.set()
                        if not release.wait(timeout=3):
                            raise RuntimeError("synthetic commit timeout")
                        armed.clear()
                    return super().commit()

            latch = CaptureLatch()
            latch.resume_if_unchanged(latch.generation())
            with patch("personalcontext.jobs.writer.sqlite3.connect",
                       side_effect=lambda *args, **kwargs: original_connect(*args, **kwargs, factory=DelayedConnection)):
                writer = Writer(path, on_storage_failure=latch.pause)
                await writer.start()

            def operation(connection):
                connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
                return True

            armed.set()
            task = asyncio.create_task(submit_capture(writer, latch, operation, lambda _connection: True))
            drain = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                latch.pause()
                drain = asyncio.create_task(asyncio.to_thread(latch.drain))
                await asyncio.sleep(0.03)
                self.assertFalse(drain.done())
                release.set()
                self.assertTrue(await task)
                self.assertTrue(await drain)
                self.assertTrue(latch.is_paused())
                self.assertIsNone(await submit_capture(writer, latch, operation, lambda _connection: True))
            finally:
                release.set()
                await writer.close()
