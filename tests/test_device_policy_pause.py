"""A device authorization decision must fail closed on a local pause."""

import unittest
from datetime import UTC, datetime
from functools import partial

import test_device_capture_guard as fixture

from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.privacy.runtime.authorization import device_policy_allows
from personalcontext.sources.registry import set_source_pause


class DevicePolicyPauseTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.DeviceCaptureGuardTests.asyncSetUp
    asyncTearDown = fixture.DeviceCaptureGuardTests.asyncTearDown

    async def test_local_pause_before_or_during_decision_denies(self):
        device = self.devices[0]
        grant = PolicyDraft(False, 600, frozenset({self.source}), frozenset(), frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=1, draft=grant, now=1012))
        await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                         source_id=self.source, expected_revision=1, paused=False, now=1014))
        request = CaptureRequest(self.source, "metadata", 2, False, "ordinary")

        async def check(clock):
            def decision(connection):
                connection.execute("BEGIN IMMEDIATE")
                return device_policy_allows(connection, token=device.token, device_id=device.device_id,
                                            request=request, latch=self.latch, clock=clock)
            return await self.writer.submit(decision)

        def now():
            return datetime.fromtimestamp(1015, UTC)
        self.assertTrue(await check(now))
        self.latch.pause()
        self.assertFalse(await check(now))
        self.assertTrue(self.latch.drain())
        self.assertTrue(self.latch.resume_if_unchanged(self.latch.generation()))

        def pause_during_check():
            self.latch.pause()
            return now()

        self.assertFalse(await check(pause_during_check))
