"""Synthetic active-tab intervals use the guarded browser ledger."""

import json
import sqlite3
import unittest
import uuid
from contextlib import closing
from datetime import UTC, datetime

import test_web_visit_guards as fixture
from test_web_visit_ledger import synthetic_event

from personalcontext.ingest.active.service import submit_web_active
from personalcontext.ingest.browser.ledger.record import _record_browser
from personalcontext.ingest.visit.batch import submit_visit_batch
from personalcontext.privacy.sanitizer.rules import SanitizerContext


def active_event(device, source):
    event = synthetic_event(device, source)
    return event | {"kind": "web_active", "granularity": "interval", "ended_at": "1970-01-01T00:16:56Z",
                    "observed_at": "1970-01-01T00:16:56Z", "duration_ms": 1000,
                    "payload": event["payload"] | {"foreground": True}}


class WebActiveTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.WebVisitGuardTests.asyncSetUp
    asyncTearDown = fixture.WebVisitGuardTests.asyncTearDown
    prepare = fixture.WebVisitGuardTests.prepare
    counts = fixture.WebVisitGuardTests.counts

    async def submit(self, event):
        device = self.devices[0]
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        return await submit_web_active(self.writer, self.latch, device.token, device.device_id, event, context,
                                       clock=lambda: datetime.fromtimestamp(1016, UTC))

    async def test_consent_redaction_dedup_and_duration(self):
        event = active_event(self.devices[0].device_id, self.source)
        self.assertEqual(await self.submit(event), "rejected")
        await self.prepare()
        for invalid in (event | {"duration_ms": 999}, event | {"ended_at": None},
                        event | {"ended_at": "1970-01-01T00:16:56.000000001Z"},
                        event | {"payload": event["payload"] | {"foreground": False}},
                        event | {"payload": event["payload"] | {"foreground": 1}},
                        event | {"ended_at": "1970-01-01T00:32:00Z"},
                        event | {"device_id": self.devices[1].device_id}):
            self.assertEqual(await self.submit(invalid), "rejected")
        self.assertEqual(await self.submit(event), "accepted")
        self.assertEqual(await self.submit(event), "duplicate")
        self.assertEqual(await self.submit(event | {"duration_ms": None}), "conflict")
        payload = await self.writer.submit(lambda c: c.execute("SELECT payload_json FROM events").fetchone()[0])
        self.assertEqual(json.loads(payload)["url"], "https://example.org/article")
        self.assertIs(json.loads(payload)["foreground"], True)
        self.assertEqual(await self.counts(), (1, 1))

    async def test_mixed_batch_and_unknown_duration(self):
        await self.prepare()
        device = self.devices[0]
        visit = synthetic_event(device.device_id, self.source)
        active = active_event(device.device_id, self.source) | {"event_id": str(uuid.uuid4()),
                                                                "source_event_key": "active-2", "duration_ms": None,
                                                                "ended_at": None}
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        results = await submit_visit_batch(self.writer, self.latch, device.token, device.device_id,
                                           json.dumps([visit, active]).encode(), context,
                                           clock=lambda: datetime.fromtimestamp(1016, UTC))
        self.assertEqual(results, ["accepted", "accepted"])
        self.assertEqual(await self.counts(), (2, 2))
        interval = await self.writer.submit(lambda c: c.execute("SELECT ended_at,duration_ms FROM events WHERE kind='web_active'").fetchone())
        self.assertEqual(interval, (None, None))

    async def test_private_classification_and_unknown_source_are_denied(self):
        await self.prepare()
        device = self.devices[0]
        event = active_event(device.device_id, self.source)
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=True, sensitivity="ordinary")
        result = await submit_web_active(self.writer, self.latch, device.token, device.device_id, event, context,
                                         clock=lambda: datetime.fromtimestamp(1016, UTC))
        self.assertEqual(result, "rejected")
        self.assertEqual(await self.submit(event | {"source_id": str(uuid.uuid4())}), "rejected")
        self.assertEqual(await self.counts(), (0, 0))

    async def test_internal_record_requires_transaction(self):
        with (closing(sqlite3.connect(self.path)) as connection,
              self.assertRaisesRegex(RuntimeError, "Capture transaction required")):
            _record_browser(connection, None, None, None, self.latch, lambda: datetime.now(UTC))
