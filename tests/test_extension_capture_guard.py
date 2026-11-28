"""Synthetic guarded transactions preserve extension Origin and device binding."""

import unittest
from datetime import UTC, datetime
from functools import partial

import test_device_capture_guard as fixture

from personalcontext.devices.pairing import enroll, issue_pairing, revoke_device
from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.privacy.runtime.authorization import device_policy_allows
from personalcontext.sources.registry import create_source, set_source_pause

ORIGIN = "chrome-extension://" + "a" * 32
OTHER = "chrome-extension://" + "b" * 32


class ExtensionCaptureGuardTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.DeviceCaptureGuardTests.asyncSetUp
    asyncTearDown = fixture.DeviceCaptureGuardTests.asyncTearDown

    async def test_bound_origin_scope_source_and_revocation(self):
        code = await self.writer.submit(partial(issue_pairing, token=self.owner.token, csrf=self.owner.csrf,
                                                mask=7, now=1011, origin=ORIGIN))
        device = await self.writer.submit(partial(enroll, code=code, now=1012, origin=ORIGIN))
        source = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                  device_id=device.device_id, kind="browser", now=1013))
        await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                         source_id=source.source_id, expected_revision=1, paused=False, now=1014))
        request = CaptureRequest(source.source_id, "metadata", 1, False, "ordinary")

        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('extension-fixture','synthetic')")
            return True

        async def attempt(origin, claimed_id=device.device_id):
            validate = partial(device_policy_allows, token=device.token, device_id=claimed_id, request=request,
                               latch=self.latch, origin=origin, clock=lambda: datetime.fromtimestamp(1016, UTC))
            return await submit_capture(self.writer, self.latch, operation, validate)

        self.assertIsNone(await attempt(ORIGIN))  # Default-deny before opt-in.
        before_consent = await self.writer.submit(lambda c: c.execute("SELECT count(*) FROM app_metadata "
                                                                      "WHERE key='extension-fixture'").fetchone()[0])
        self.assertEqual(before_consent, 0)
        draft = PolicyDraft(False, 600, frozenset({source.source_id}), frozenset(),
                            frozenset({(source.source_id, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=1, draft=draft, now=1015))
        request = CaptureRequest(source.source_id, "metadata", 2, False, "ordinary")

        self.assertIsNone(await attempt(None))
        self.assertIsNone(await attempt(OTHER))
        self.assertIsNone(await attempt(ORIGIN, self.devices[0].device_id))
        self.assertTrue(await attempt(ORIGIN))
        await self.writer.submit(lambda connection: connection.execute("DELETE FROM app_metadata WHERE key='extension-fixture'"))
        self.assertTrue(await self.writer.submit(partial(revoke_device, token=self.owner.token, csrf=self.owner.csrf,
                                                         device_id=device.device_id, now=1017)))
        self.assertIsNone(await attempt(ORIGIN))
        remaining = await self.writer.submit(lambda c: c.execute("SELECT count(*) FROM app_metadata "
                                                                 "WHERE key='extension-fixture'").fetchone()[0])
        self.assertEqual(remaining, 0)
