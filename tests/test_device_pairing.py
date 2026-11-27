import asyncio
import tempfile
import unittest
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing, revoke_device
from personalcontext.devices.scopes import authorize_device
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class DevicePairingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()
        code = await self.writer.submit(partial(issue_bootstrap, now=1000))
        encoded = hash_password("synthetic pairing owner")
        await self.writer.submit(partial(consume_bootstrap, candidate=code, encoded=encoded, now=1001))
        self.owner = await self.writer.submit(partial(create_session, expected_hash=encoded, now=1002))

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def issue(self, mask=3, csrf=None, now=1010):
        return await self.writer.submit(partial(issue_pairing, token=self.owner.token,
                                                 csrf=csrf or self.owner.csrf, mask=mask, now=now))

    async def test_one_time_pairing_binding_scope_and_revocation(self):
        code = await self.issue()
        device = await self.writer.submit(partial(enroll, code=code, now=1011))
        self.assertIsNotNone(device)
        self.assertIsNone(await self.writer.submit(partial(enroll, code=code, now=1011)))
        for scope, allowed in ((1, True), (2, True), (4, False)):
            decision = await self.writer.submit(partial(authorize_device, token=device.token,
                                                         device_id=device.device_id, scope=scope))
            self.assertEqual(decision, allowed)
        self.assertFalse(await self.writer.submit(partial(authorize_device, token=device.token,
                                                           device_id="00000000-0000-4000-8000-000000000000", scope=1)))
        self.assertFalse(await self.writer.submit(partial(revoke_device, token=self.owner.token,
                                                          csrf="invalid", device_id=device.device_id, now=1012)))
        self.assertTrue(await self.writer.submit(partial(revoke_device, token=self.owner.token,
                                                         csrf=self.owner.csrf, device_id=device.device_id, now=1012)))
        self.assertFalse(await self.writer.submit(partial(authorize_device, token=device.token,
                                                           device_id=device.device_id, scope=1)))

    async def test_expiry_invalid_permission_and_concurrent_replay(self):
        self.assertIsNone(await self.issue(mask=8))
        self.assertIsNone(await self.issue(csrf="invalid"))
        expired = await self.issue(now=1100)
        self.assertIsNone(await self.writer.submit(partial(enroll, code=expired, now=1400)))
        code = await self.issue(now=1500)
        results = await asyncio.gather(*(self.writer.submit(partial(enroll, code=code, now=1501)) for _ in range(5)))
        self.assertEqual(sum(value is not None for value in results), 1)

    async def test_secrets_are_not_stored_and_survive_writer_restart(self):
        code = await self.issue()
        device = await self.writer.submit(partial(enroll, code=code, now=1011))
        await self.writer.close()
        self.writer = Writer(self.path)
        await self.writer.start()
        self.assertTrue(await self.writer.submit(partial(authorize_device, token=device.token,
                                                         device_id=device.device_id, scope=1)))
        if device.token in repr(device):
            self.fail("Device token exposed by representation")
        for path in (self.path, self.path.with_name(self.path.name + "-wal")):
            if path.exists() and any(value.encode("ascii") in path.read_bytes() for value in (code, device.token)):
                self.fail("Pairing secret persisted in SQLite files")

    async def test_owner_change_invalidates_unconsumed_code(self):
        code = await self.issue()
        replacement = hash_password("synthetic replacement owner")

        def change_owner(connection):
            connection.execute("UPDATE owner_credentials SET password_hash=? WHERE singleton=1", (replacement,))

        await self.writer.submit(change_owner)
        self.assertIsNone(await self.writer.submit(partial(enroll, code=code, now=1011)))

    async def test_invalid_scope_types_are_rejected(self):
        for value in (0, 8, -1, True, "1"):
            self.assertIsNone(await self.issue(mask=value))
