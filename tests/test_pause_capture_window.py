import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from personalcontext.jobs.writer import Writer
from personalcontext.privacy.policy_store import load_policy
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.storage.initialize import initialize_database
from personalcontext.windows.pause_capture import PauseCapture


@unittest.skipUnless(sys.platform == "win32", "Windows native pause")
class PauseCaptureWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_action_pauses_without_a_web_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            try:
                def enable(connection):
                    connection.execute("UPDATE capture_policy SET version=2,issued_at=1000,expires_at=1600,paused=0")

                await writer.submit(enable)
                state = SimpleNamespace(scheduler=SimpleNamespace(writer=writer), loop=asyncio.get_running_loop(),
                                        capture_latch=CaptureLatch())
                action = PauseCapture(SimpleNamespace(state=state))
                action._lock.acquire()
                with patch("win32api.MessageBox") as notice:
                    await asyncio.to_thread(action._run)
                self.assertTrue((await writer.submit(load_policy)).paused)
                self.assertEqual(notice.call_count, 1)
            finally:
                await writer.close()

    async def test_local_pause_survives_writer_failure(self):
        class BrokenWriter:
            async def submit(self, _operation):
                raise RuntimeError("synthetic database error")

        latch = CaptureLatch()
        latch.resume_if_unchanged(latch.generation())
        state = SimpleNamespace(scheduler=SimpleNamespace(writer=BrokenWriter()), loop=asyncio.get_running_loop(),
                                capture_latch=latch)
        action = PauseCapture(SimpleNamespace(state=state))
        notified = threading.Event()
        with patch("win32api.MessageBox", side_effect=lambda *_args: notified.set()):
            action.open()
            self.assertTrue(latch.is_paused())
            self.assertTrue(await asyncio.to_thread(notified.wait, 2))
        self.assertTrue(latch.is_paused())
