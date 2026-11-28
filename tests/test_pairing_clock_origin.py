"""Expiry is enforced even when an extension presents the wrong Origin."""

import unittest
from functools import partial

import test_device_pairing as fixture

from personalcontext.devices.pairing import enroll, issue_pairing
from personalcontext.jobs.writer import Writer


class PairingClockOriginTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.DevicePairingTests.asyncSetUp
    asyncTearDown = fixture.DevicePairingTests.asyncTearDown

    async def test_expired_code_cannot_revive_after_wrong_origin_attempt(self):
        approved = "chrome-extension://" + "a" * 32
        wrong = "chrome-extension://" + "b" * 32
        code = await self.writer.submit(partial(issue_pairing, token=self.owner.token, csrf=self.owner.csrf,
                                                 mask=2, now=1100, origin=approved))
        self.assertIsNone(await self.writer.submit(partial(enroll, code=code, now=1400, origin=wrong)))
        await self.writer.close()
        self.writer = Writer(self.path)
        await self.writer.start()
        self.assertIsNone(await self.writer.submit(partial(enroll, code=code, now=1101, origin=approved)))
