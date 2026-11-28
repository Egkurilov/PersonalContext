import tempfile
import unittest
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing, revoke_device
from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.privacy.runtime.authorization import device_policy_allows
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.sources.registry import create_source, set_source_pause
from personalcontext.storage.initialize import initialize_database


class DeviceCaptureGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.latch = CaptureLatch()
        self.latch.resume_if_unchanged(self.latch.generation())
        self.writer = Writer(self.path, on_storage_failure=self.latch.pause)
        await self.writer.start()
        encoded = hash_password("synthetic capture guard owner")
        code = await self.writer.submit(partial(issue_bootstrap, now=1000))
        await self.writer.submit(partial(consume_bootstrap, candidate=code, encoded=encoded, now=1001))
        self.owner = await self.writer.submit(partial(create_session, expected_hash=encoded, now=1002))
        self.devices = []
        for now in (1003, 1005):
            code = await self.writer.submit(partial(issue_pairing, token=self.owner.token, csrf=self.owner.csrf, mask=7, now=now))
            self.devices.append(await self.writer.submit(partial(enroll, code=code, now=now + 1)))
        source = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                  device_id=self.devices[0].device_id, kind="browser", now=1010))
        self.source = source.source_id

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def attempt(self, token, device_id, version, timestamp, *, private=False, sensitivity="ordinary", final_timestamp=None):
        request = CaptureRequest(self.source, "metadata", version, private, sensitivity)
        instants = iter((timestamp, timestamp if final_timestamp is None else final_timestamp))

        def operation(connection):
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('capture-fixture','synthetic')")
            return True

        validate = partial(device_policy_allows, token=token, device_id=device_id, request=request, latch=self.latch,
                           clock=lambda: datetime.fromtimestamp(next(instants), UTC))
        return await submit_capture(self.writer, self.latch, operation, validate)

    async def count(self):
        return await self.writer.submit(lambda connection: connection.execute(
            "SELECT count(*) FROM app_metadata WHERE key='capture-fixture'",
        ).fetchone()[0])

    async def test_consent_source_binding_expiry_deny_and_revoke(self):
        a, b = self.devices
        self.assertIsNone(await self.attempt(a.token, a.device_id, 1, 1011))
        grant = PolicyDraft(False, 600, frozenset({self.source}), frozenset(), frozenset({(self.source, "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=1, draft=grant, now=1012))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 2, 1013))  # source still paused
        await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                         source_id=self.source, expected_revision=1, paused=False, now=1014))
        self.assertIsNone(await self.attempt(b.token, b.device_id, 2, 1015))
        self.assertIsNone(await self.attempt(a.token, b.device_id, 2, 1015))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 2, 1015, private=None))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 2, 1015, sensitivity="unknown"))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 2, 1612))
        self.assertEqual(await self.count(), 0)
        self.assertTrue(self.latch.is_paused())
        self.assertTrue(self.latch.drain())
        deny = PolicyDraft(False, 600, grant.allowed, grant.allowed, grant.grants)
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=2, draft=deny, now=1613))
        self.assertTrue(self.latch.resume_if_unchanged(self.latch.generation()))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 3, 1614))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=3, draft=grant, now=1615))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 4, 1616, final_timestamp=2215))
        self.assertEqual(await self.count(), 0)
        self.assertTrue(self.latch.is_paused())
        self.assertTrue(self.latch.drain())
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=4, draft=grant, now=2216))
        self.assertTrue(self.latch.resume_if_unchanged(self.latch.generation()))
        self.assertTrue(await self.attempt(a.token, a.device_id, 5, 2217))
        await self.writer.submit(lambda connection: connection.execute("DELETE FROM app_metadata WHERE key='capture-fixture'"))
        await self.writer.submit(partial(revoke_device, token=self.owner.token, csrf=self.owner.csrf,
                                         device_id=a.device_id, now=2218))
        self.assertIsNone(await self.attempt(a.token, a.device_id, 5, 2219))
        self.assertEqual(await self.count(), 0)
