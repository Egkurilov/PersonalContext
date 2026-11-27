import tempfile
import unittest
from pathlib import Path

from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.storage.initialize import initialize_database


class CapturePrecheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_denied_before_operation_and_rechecked_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            latch = CaptureLatch()
            latch.resume_if_unchanged(latch.generation())
            writer = Writer(path, on_storage_failure=latch.pause)
            await writer.start()
            calls = []

            def operation(connection):
                calls.append("operation")
                connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
                return True

            try:
                self.assertIsNone(await submit_capture(writer, latch, operation, lambda _connection: False))
                self.assertEqual(calls, [])
                checks = iter((True, False))
                self.assertIsNone(await submit_capture(writer, latch, operation, lambda _connection: next(checks)))
                self.assertEqual(calls, ["operation"])
                rows = await writer.submit(lambda connection: connection.execute(
                    "SELECT count(*) FROM app_metadata WHERE key='fixture'",
                ).fetchone()[0])
                self.assertEqual(rows, 0)
            finally:
                await writer.close()
