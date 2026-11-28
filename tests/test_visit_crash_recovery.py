"""Abrupt synthetic writer-process termination between commit and delivery."""

import asyncio
import json
import multiprocessing
import unittest
from datetime import UTC, datetime
from pathlib import Path

import test_web_visit_guards as fixture
from test_web_visit_ledger import synthetic_event

from personalcontext.ingest.visit.batch import submit_visit_batch
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext


def _child(path, pipe):
    async def run():
        token, device, raw = pipe.recv()
        latch = CaptureLatch()
        latch.resume_if_unchanged(latch.generation())
        writer = Writer(Path(path), on_storage_failure=latch.pause)
        await writer.start()
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        result = await submit_visit_batch(writer, latch, token, device, raw, context,
                                          clock=lambda: datetime.fromtimestamp(1016, UTC))
        if result != ["accepted"]:
            pipe.send("unexpected-result")
            return
        # Marker confirms commit happened; the actual acknowledgement is withheld.
        pipe.send("committed")
        pipe.recv()

    asyncio.run(run())


class VisitCrashTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.WebVisitGuardTests.asyncSetUp
    asyncTearDown = fixture.WebVisitGuardTests.asyncTearDown
    prepare = fixture.WebVisitGuardTests.prepare
    counts = fixture.WebVisitGuardTests.counts

    async def test_kill_after_commit_before_ack_then_retry(self):
        await self.prepare()
        device = self.devices[0]
        raw = json.dumps([synthetic_event(device.device_id, self.source)]).encode()
        await self.writer.close()
        parent, child = multiprocessing.get_context("spawn").Pipe()
        process = multiprocessing.get_context("spawn").Process(target=_child, args=(str(self.path), child))
        try:
            process.start()
            child.close()
            parent.send((device.token, device.device_id, raw))
            self.assertTrue(await asyncio.to_thread(parent.poll, 30), "child did not commit in time")
            self.assertEqual(parent.recv(), "committed")
            process.kill()
            await asyncio.to_thread(process.join, 10)
            self.assertFalse(process.is_alive())
            self.assertNotEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 10)
            parent.close()
            self.writer = Writer(self.path, on_storage_failure=self.latch.pause)
            await self.writer.start()
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        result = await submit_visit_batch(self.writer, self.latch, device.token, device.device_id, raw, context,
                                          clock=lambda: datetime.fromtimestamp(1016, UTC))
        self.assertEqual(result, ["duplicate"])
        self.assertEqual(await self.counts(), (1, 1))
