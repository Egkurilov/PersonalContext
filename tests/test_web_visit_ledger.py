"""Synthetic web event through device, policy, sanitizer and durable writer."""

import json
import unittest
import uuid
from datetime import UTC, datetime
from functools import partial

import test_device_capture_guard as fixture

from personalcontext.devices.pairing import revoke_device
from personalcontext.ingest.visit.model import WebVisit
from personalcontext.ingest.visit.service import submit_web_visit
from personalcontext.privacy.filters.rules import FilterRules
from personalcontext.privacy.filters.store import save_filters
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.sources.registry import set_source_pause


def synthetic_event(device, source):
    return {"schema_version": 1, "event_id": str(uuid.uuid4()), "device_id": device,
            "source_id": source, "source_event_key": "seq-1", "kind": "web_visit",
            "started_at": "1970-01-01T00:16:55Z", "ended_at": None,
            "duration_ms": None, "observed_at": "1970-01-01T00:16:55Z",
            "timezone": "UTC", "granularity": "point", "quality": "measured", "policy_version": 3,
            "consent_scope": "metadata", "payload": {"domain": "example.org",
            "url": "https://example.org/article?tracking=synthetic", "title": "Synthetic article"},
            "provenance": {"collector": "browser", "collector_version": "1.0.0", "import_id": None}}


class WebVisitLedgerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.DeviceCaptureGuardTests.asyncSetUp
    asyncTearDown = fixture.DeviceCaptureGuardTests.asyncTearDown

    async def test_consent_sanitization_duplicate_conflict_binding_and_revoke(self):
        a, b = self.devices
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        event = synthetic_event(a.device_id, self.source)
        now = lambda: datetime.fromtimestamp(1016, UTC)

        async def submit(value, token=a.token, device=a.device_id, clock=now):
            return await submit_web_visit(self.writer, self.latch, token, device, value, context, clock=clock)

        await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                         source_id=self.source, expected_revision=1, paused=False, now=1011))
        self.assertEqual(await submit({**event, "policy_version": 1}), "rejected")
        await self.writer.submit(partial(save_filters, token=self.owner.token, csrf=self.owner.csrf, expected=1,
                                         rules=FilterRules(allowed_domains=frozenset({"example.org"})), now=1012))
        grant = PolicyDraft(False, 600, frozenset({self.source}), frozenset(), frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=2, draft=grant, now=1013))
        self.assertEqual(await submit(event, token=b.token, device=b.device_id), "rejected")
        forged = {**event, "device_id": b.device_id}
        self.assertEqual(await submit(forged, token=a.token, device=b.device_id), "rejected")
        self.assertEqual(await submit(forged, token=b.token, device=b.device_id), "rejected")
        self.assertEqual(await submit(WebVisit.model_construct(**event)), "rejected")
        self.assertEqual(await submit(event), "accepted")
        self.assertEqual(await submit(event), "duplicate")
        without_query = {**event, "payload": {**event["payload"], "url": "https://example.org/article"}}
        self.assertEqual(await submit(without_query), "duplicate")
        upper_domain = {**event, "payload": {**event["payload"], "domain": "EXAMPLE.ORG",
                                           "url": "https://EXAMPLE.ORG/article"}}
        self.assertEqual(await submit(upper_domain), "duplicate")
        changed = {**event, "payload": {**event["payload"], "url": "https://example.org/other"}}
        self.assertEqual(await submit(changed), "conflict")
        self.assertEqual(await submit({**event, "event_id": str(uuid.uuid4())}), "conflict")
        for bad in ({**event, "timezone": "Invalid/Unknown"}, {**event, "schema_version": True},
                    {**event, "started_at": "1970-01-01T00:22:00Z"},
                    {**event, "payload": {**event["payload"], "form": "synthetic"}},
                    {**event, "payload": {**event["payload"], "domain": "user@example.org"}},
                    {**event, "device_id": b.device_id}):
            self.assertEqual(await submit(bad), "rejected")
        rows = await self.writer.submit(lambda c: c.execute("SELECT payload_json FROM events").fetchall())
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["url"], "https://example.org/article")
        self.assertNotIn("tracking", rows[0][0])
        jobs = await self.writer.submit(lambda c: c.execute("SELECT count(*) FROM jobs").fetchone()[0])
        self.assertEqual(jobs, 1)
        expiry = await self.writer.submit(lambda c: c.execute("SELECT received_at,expires_at FROM events").fetchone())
        self.assertEqual(expiry, (1016, 1016 + 90 * 86400))
        self.latch.pause()
        self.assertEqual(await submit({**event, "event_id": str(uuid.uuid4()), "source_event_key": "seq-2"}), "rejected")
        self.assertTrue(self.latch.drain())
        self.assertTrue(self.latch.resume_if_unchanged(self.latch.generation()))
        await self.writer.submit(partial(revoke_device, token=self.owner.token, csrf=self.owner.csrf,
                                         device_id=a.device_id, now=1017))
        self.assertEqual(await submit({**event, "event_id": str(uuid.uuid4()), "source_event_key": "seq-2"}), "rejected")
        self.assertEqual(await self.writer.submit(lambda c: c.execute("SELECT count(*) FROM events").fetchone()[0]), 1)
