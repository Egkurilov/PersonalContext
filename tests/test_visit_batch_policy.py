"""Privacy and device revocation checks for the atomic internal batch."""

import json
import unittest
from datetime import UTC, datetime
from functools import partial
from unittest.mock import patch

import test_web_visit_guards as fixture
from test_web_visit_ledger import synthetic_event

from personalcontext.devices.pairing import revoke_device
from personalcontext.ingest.browser.ledger.record import _record_browser as _record
from personalcontext.ingest.visit.batch import submit_visit_batch
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.privacy.sanitizer.rules import SanitizerContext


class VisitBatchPolicyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.WebVisitGuardTests.asyncSetUp
    asyncTearDown = fixture.WebVisitGuardTests.asyncTearDown
    prepare = fixture.WebVisitGuardTests.prepare
    counts = fixture.WebVisitGuardTests.counts

    async def send(self, event, *, token=None, timestamp=1016):
        device = self.devices[0]
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")
        return await submit_visit_batch(self.writer, self.latch, token or device.token, device.device_id,
                                        json.dumps([event]).encode(), context,
                                        clock=lambda: datetime.fromtimestamp(timestamp, UTC))

    async def test_default_deny_wrong_token_and_revoke(self):
        event = synthetic_event(self.devices[0].device_id, self.source)
        self.assertEqual(await self.send(event), ["rejected"])
        await self.prepare()
        self.assertEqual(await self.send(event, token=self.devices[1].token), ["rejected"])
        await self.writer.submit(partial(revoke_device, token=self.owner.token, csrf=self.owner.csrf,
                                         device_id=self.devices[0].device_id, now=1017))
        self.assertEqual(await self.send(event, timestamp=1018), ["rejected"])
        self.assertEqual(await self.counts(), (0, 0))

    async def test_expired_policy_and_deny_override(self):
        await self.prepare()
        event = synthetic_event(self.devices[0].device_id, self.source)
        deny = PolicyDraft(False, 600, frozenset({self.source}), frozenset({self.source}),
                           frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=3, draft=deny, now=1015))
        event["policy_version"] = 4
        self.assertEqual(await self.send(event), ["rejected"])
        grant = PolicyDraft(False, 600, frozenset({self.source}), frozenset(),
                            frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=4, draft=grant, now=1016))
        event["policy_version"] = 5
        self.assertEqual(await self.send(event, timestamp=1616), ["rejected"])
        self.assertTrue(self.latch.is_paused())
        self.assertEqual(await self.counts(), (0, 0))

    async def test_pause_during_write_rolls_back_batch(self):
        await self.prepare()
        event = synthetic_event(self.devices[0].device_id, self.source)

        def pause_after_record(*args, **kwargs):
            result = _record(*args, **kwargs)
            self.latch.pause()
            return result

        with patch("personalcontext.ingest.visit.batch._record", side_effect=pause_after_record):
            self.assertEqual(await self.send(event), ["rejected"])
        self.assertTrue(self.latch.is_paused())
        self.assertEqual(await self.counts(), (0, 0))
