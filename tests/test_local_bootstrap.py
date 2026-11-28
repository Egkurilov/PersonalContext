import tempfile
import unittest
from pathlib import Path

from personalcontext.auth.local_bootstrap import setup_local_owner
from personalcontext.auth.owner_bootstrap import OwnerBootstrap
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.password_hash import verify_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class LocalBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        self.writer = Writer(path)
        await self.writer.start()
        self.executor = PasswordExecutor()
        self.bootstrap = OwnerBootstrap(self.writer, self.executor, clock=lambda: 1001)

    async def asyncTearDown(self):
        await self.executor.close()
        await self.writer.close()
        self.directory.cleanup()

    async def test_local_setup_creates_owner_and_cannot_replace_it(self):
        candidate = "synthetic local owner"
        result = await setup_local_owner(self.writer, self.bootstrap, candidate, clock=lambda: 1000)
        self.assertEqual(result.status, "ok")
        encoded = await self.writer.submit(find_owner_hash)
        self.assertTrue(verify_password(encoded, candidate))
        again = await setup_local_owner(self.writer, self.bootstrap, "synthetic replacement", clock=lambda: 1002)
        self.assertEqual(again.status, "unavailable")
        self.assertEqual(await self.writer.submit(find_owner_hash), encoded)

    async def test_failed_setup_does_not_create_owner(self):
        result = await setup_local_owner(self.writer, self.bootstrap, "short", clock=lambda: 1000)
        self.assertEqual(result.status, "invalid")
        self.assertIsNone(await self.writer.submit(find_owner_hash))
