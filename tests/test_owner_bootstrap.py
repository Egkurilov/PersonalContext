import asyncio
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.auth.owner_bootstrap import OwnerBootstrap
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.password_hash import verify_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class OwnerBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        self.writer = Writer(path)
        await self.writer.start()
        self.executor = PasswordExecutor(capacity=1)
        self.now = 1001
        self.bootstrap = OwnerBootstrap(self.writer, self.executor, clock=lambda: self.now)
        self.code = await self.writer.submit(partial(issue_bootstrap, now=1000))

    async def asyncTearDown(self):
        await self.executor.close()
        await self.writer.close()
        self.directory.cleanup()

    async def test_creates_single_owner_and_rejects_replay(self):
        result = await self.bootstrap.complete(self.code, "synthetic password candidate")
        self.assertEqual(result.status, "ok")
        encoded = await self.writer.submit(find_owner_hash)
        self.assertTrue(verify_password(encoded, "synthetic password candidate"))
        self.assertEqual((await self.bootstrap.complete(self.code, "synthetic password candidate")).status,
                         "invalid")

    async def test_rate_limit_precedes_hashing(self):
        with patch.object(self.executor, "hash", wraps=self.executor.hash) as hasher:
            for _ in range(5):
                self.assertEqual((await self.bootstrap.complete("wrong", "synthetic password candidate")).status,
                                 "invalid")
            self.assertEqual((await self.bootstrap.complete(self.code, "synthetic password candidate")).status,
                             "limited")
            self.assertEqual(hasher.await_count, 5)
        self.assertIsNone(await self.writer.submit(find_owner_hash))

    async def test_concurrent_consumption_creates_only_one_owner(self):
        outcomes = await asyncio.gather(*(
            self.bootstrap.complete(self.code, "synthetic password candidate") for _ in range(2)
        ))
        self.assertEqual(sum(result.status == "ok" for result in outcomes), 1)

    async def test_bad_password_and_hash_failure_are_generic(self):
        self.assertEqual((await self.bootstrap.complete(self.code, "short")).status, "invalid")
        with patch.object(self.executor, "hash", side_effect=RuntimeError("synthetic private detail")):
            result = await self.bootstrap.complete(self.code, "synthetic password candidate")
        self.assertEqual(result.status, "unavailable")
        self.assertNotIn("synthetic private detail", repr(result))
        self.assertIsNone(await self.writer.submit(find_owner_hash))

    async def test_expiry_during_hashing_is_rechecked_at_commit(self):
        original = self.executor.hash

        async def delayed_hash(password):
            encoded = await original(password)
            self.now = 1300
            return encoded

        with patch.object(self.executor, "hash", side_effect=delayed_hash):
            result = await self.bootstrap.complete(self.code, "synthetic password candidate")
        self.assertEqual(result.status, "invalid")
        self.assertIsNone(await self.writer.submit(find_owner_hash))
