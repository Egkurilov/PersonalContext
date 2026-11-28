"""Synthetic expiry, retry and rollback checks for the internal visit writer."""

import asyncio
import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime
from functools import partial

import test_device_capture_guard as fixture
import test_web_visit_ledger as visit_fixture

from personalcontext.ingest.visit.service import submit_web_visit
from personalcontext.privacy.filters.rules import FilterRules
from personalcontext.privacy.filters.store import save_filters
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.sources.registry import set_source_pause


class WebVisitGuardTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.DeviceCaptureGuardTests.asyncSetUp
    asyncTearDown = fixture.DeviceCaptureGuardTests.asyncTearDown

    async def prepare(self):
        await self.writer.submit(partial(save_filters, token=self.owner.token, csrf=self.owner.csrf, expected=1,
                                         rules=FilterRules(allowed_domains=frozenset({"example.org"})), now=1011))
        draft = PolicyDraft(False, 600, frozenset({self.source}), frozenset(), frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=2, draft=draft, now=1012))
        await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                         source_id=self.source, expected_revision=1, paused=False, now=1014))

    async def submit(self, timestamp=1016):
        device = self.devices[0]
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        return await submit_web_visit(self.writer, self.latch, device.token, device.device_id,
                                      self.event, context, clock=lambda: datetime.fromtimestamp(timestamp, UTC))

    async def counts(self):
        return await self.writer.submit(lambda c: (c.execute("SELECT count(*) FROM events").fetchone()[0],
                                                    c.execute("SELECT count(*) FROM jobs").fetchone()[0]))

    async def test_expired_consent_does_not_write(self):
        await self.prepare()
        self.event = visit_fixture.synthetic_event(self.devices[0].device_id, self.source)
        self.assertEqual(await self.submit(1612), "rejected")
        self.assertEqual(await self.counts(), (0, 0))
        self.assertTrue(self.latch.is_paused())

    async def test_event_predating_current_consent_does_not_write(self):
        await self.prepare()
        event = visit_fixture.synthetic_event(self.devices[0].device_id, self.source)
        self.event = event | {"started_at": "1970-01-01T00:16:51Z",
                              "observed_at": "1970-01-01T00:16:51Z"}
        self.assertEqual(await self.submit(), "rejected")
        self.assertEqual(await self.counts(), (0, 0))
        self.event = event | {"started_at": "1970-01-01T00:16:53Z",
                              "observed_at": "1970-01-01T00:16:53Z"}
        self.assertEqual(await self.submit(), "rejected")
        self.assertEqual(await self.counts(), (0, 0))
        self.event = event | {"started_at": "1970-01-01T00:16:54Z",
                              "observed_at": "1970-01-01T00:16:54Z"}
        self.assertEqual(await self.submit(), "accepted")
        self.assertEqual(await self.counts(), (1, 1))

    async def test_deny_overrides_allow_without_writing(self):
        await self.prepare()
        grant = PolicyDraft(False, 600, frozenset({self.source}), frozenset({self.source}),
                            frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=3, draft=grant, now=1015))
        self.event = {**visit_fixture.synthetic_event(self.devices[0].device_id, self.source), "policy_version": 4}
        self.assertEqual(await self.submit(), "rejected")
        self.assertEqual(await self.counts(), (0, 0))

    async def test_concurrent_retries_commit_one_event_and_one_job(self):
        await self.prepare()
        self.event = visit_fixture.synthetic_event(self.devices[0].device_id, self.source)
        outcomes = await asyncio.gather(*(self.submit() for _ in range(10)))
        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("duplicate"), 9)
        self.assertEqual(await self.counts(), (1, 1))

    async def test_event_failure_rolls_back_its_outbox_job_and_pauses(self):
        await self.prepare()
        self.event = visit_fixture.synthetic_event(self.devices[0].device_id, self.source)
        await self.writer.submit(lambda c: c.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON events "
                                                    "BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"))
        with self.assertRaises(sqlite3.IntegrityError):
            await self.submit()
        self.assertEqual(await self.counts(), (0, 0))
        self.assertTrue(self.latch.is_paused())

    async def test_retry_refuses_missing_outbox_job(self):
        await self.prepare()
        self.event = visit_fixture.synthetic_event(self.devices[0].device_id, self.source)
        self.assertEqual(await self.submit(), "accepted")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("DELETE FROM jobs")
            connection.commit()
        with self.assertRaises(sqlite3.DatabaseError):
            await self.submit()
        self.assertTrue(self.latch.is_paused())
