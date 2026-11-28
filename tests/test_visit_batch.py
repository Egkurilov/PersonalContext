"""Synthetic bounded batch acceptance using the same guarded visit writer."""

import asyncio
import json
import sqlite3
import unittest
import uuid
from datetime import UTC, datetime

import test_web_visit_guards as fixture
from test_web_visit_ledger import synthetic_event

from personalcontext.ingest.visit.batch import InvalidBatch, submit_visit_batch
from personalcontext.privacy.sanitizer.rules import SanitizerContext


class VisitBatchTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.WebVisitGuardTests.asyncSetUp
    asyncTearDown = fixture.WebVisitGuardTests.asyncTearDown
    prepare = fixture.WebVisitGuardTests.prepare
    counts = fixture.WebVisitGuardTests.counts

    async def send(self, raw):
        device = self.devices[0]
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        return await submit_visit_batch(self.writer, self.latch, device.token, device.device_id, raw, context,
                                        clock=lambda: datetime.fromtimestamp(1016, UTC))

    async def test_hundred_concurrent_retries_and_per_item_results(self):
        await self.prepare()
        event = synthetic_event(self.devices[0].device_id, self.source)
        values = [{**event, "event_id": str(uuid.uuid4()), "source_event_key": f"batch-{n}"} for n in range(100)]
        raw = json.dumps(values).encode()
        first, second = await asyncio.gather(self.send(raw), self.send(raw))
        self.assertEqual((first + second).count("accepted"), 100)
        self.assertEqual((first + second).count("duplicate"), 100)
        self.assertEqual(await self.counts(), (100, 100))
        changed = {**values[0], "payload": {**event["payload"], "title": "Synthetic change"}}
        results = await self.send(json.dumps([changed, {**event, "forbidden": "synthetic"}, values[1]]).encode())
        self.assertEqual(results, ["conflict", "rejected", "duplicate"])
        self.assertEqual(await self.counts(), (100, 100))

    async def test_invalid_envelopes_do_not_write(self):
        await self.prepare()
        event = synthetic_event(self.devices[0].device_id, self.source)
        bad = [b"\xff", b"{}", b"[NaN]", b'[{"kind":1,"kind":2}]',
               json.dumps([event] * 101).encode(), b" " * (1024 * 1024 + 1)]
        for raw in bad:
            with self.subTest(raw=raw[:20]), self.assertRaises(InvalidBatch):
                await self.send(raw)
        self.assertEqual(await self.counts(), (0, 0))

    async def test_no_consent_and_forged_device_are_rejected_per_item(self):
        event = synthetic_event(self.devices[0].device_id, self.source)
        self.assertEqual(await self.send(json.dumps([event]).encode()), ["rejected"])
        await self.prepare()
        forged = {**event, "device_id": self.devices[1].device_id}
        self.assertEqual(await self.send(json.dumps([forged, event]).encode()), ["rejected", "accepted"])
        self.assertEqual(await self.counts(), (1, 1))

    async def test_partial_commit_retry_after_storage_failure(self):
        await self.prepare()
        event = synthetic_event(self.devices[0].device_id, self.source)
        second = {**event, "event_id": str(uuid.uuid4()), "source_event_key": "fail-once"}
        raw = json.dumps([event, second]).encode()
        await self.writer.submit(lambda c: c.execute(
            "CREATE TRIGGER batch_failure BEFORE INSERT ON events WHEN NEW.source_event_key='fail-once' "
            "BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"))
        with self.assertRaises(sqlite3.IntegrityError):
            await self.send(raw)
        self.assertEqual(await self.counts(), (1, 1))
        self.assertTrue(self.latch.is_paused())
        await self.writer.submit(lambda c: c.execute("DROP TRIGGER batch_failure"))
        self.assertTrue(self.latch.drain())
        self.assertTrue(self.latch.resume_if_unchanged(self.latch.generation()))
        self.assertEqual(await self.send(raw), ["duplicate", "accepted"])
        self.assertEqual(await self.counts(), (2, 2))
