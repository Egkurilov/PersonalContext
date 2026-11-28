import asyncio
import tempfile
import unittest
from contextlib import suppress
from functools import partial
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.audit.record import RETENTION, record_audit
from personalcontext.audit.retention import AuditHousekeeping
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.storage.initialize import initialize_database


class AuditRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_and_periodic_cleanup_on_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            housekeeping = None
            try:
                def insert(connection, now):
                    connection.execute("BEGIN IMMEDIATE")
                    record_audit(connection, "owner_login", "owner", now)

                await writer.submit(partial(insert, now=1000))
                await writer.submit(partial(insert, now=1001))
                clock = [1001 + RETENTION]
                housekeeping = AuditHousekeeping(writer, clock=lambda: clock[0], interval=0.05)
                await housekeeping.start()
                count = lambda connection: connection.execute("SELECT count(*) FROM security_audit").fetchone()[0]
                self.assertEqual(await writer.submit(count), 1)
                clock[0] += 1
                for _ in range(20):
                    if await writer.submit(count) == 0:
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(await writer.submit(count), 0)
            finally:
                if housekeeping is not None:
                    await housekeeping.stop()
                await writer.close()

    async def test_background_retention_failure_pauses_local_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            latch = CaptureLatch()
            latch.resume_if_unchanged(latch.generation())
            housekeeping = AuditHousekeeping(writer, interval=0.02, on_failure=latch.pause)
            try:
                await housekeeping.start()
                with (patch("personalcontext.audit.retention.prune_audit", side_effect=RuntimeError("synthetic")),
                      self.assertRaises(RuntimeError)):
                    await asyncio.wait_for(housekeeping.task, timeout=2)
                self.assertTrue(latch.is_paused())
            finally:
                await housekeeping.stop()
                await writer.close()


class AuditStartupTests(unittest.TestCase):
    def test_retention_failure_prevents_app_start(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "context.db")
            with (patch("personalcontext.audit.retention.prune_audit", side_effect=RuntimeError("synthetic error")),
                  self.assertRaisesRegex(RuntimeError, "synthetic error"), TestClient(app)):
                pass

    def test_stopped_retention_task_makes_readiness_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "context.db")
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                async def stop_task():
                    task = app.state.audit_housekeeping.task
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

                client.portal.call(stop_task)
                self.assertEqual(client.get("/readyz").status_code, 503)
