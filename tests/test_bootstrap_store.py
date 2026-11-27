import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class BootstrapStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()
        self.encoded = hash_password("synthetic bootstrap candidate")

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def issue(self, now=1000):
        return await self.writer.submit(partial(issue_bootstrap, now=now))

    async def consume(self, candidate, now=1001):
        return await self.writer.submit(partial(consume_bootstrap, candidate=candidate, encoded=self.encoded, now=now))

    async def test_one_use_is_atomic_and_never_persists_code(self):
        code = await self.issue()
        results = await asyncio.gather(self.consume(code), self.consume(code))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(await self.writer.submit(find_owner_hash), self.encoded)
        with self.assertRaisesRegex(RuntimeError, "Bootstrap unavailable"):
            await self.issue()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM bootstrap_codes").fetchone()[0], 0)
        for path in (self.path, self.path.with_name(self.path.name + "-wal")):
            if path.exists() and code.encode("ascii") in path.read_bytes():
                self.fail("Bootstrap code was persisted")

    async def test_expiry_attempt_limit_and_reissue_invalidate_old_codes(self):
        old = await self.issue()
        new = await self.issue(now=1001)
        if old == new:
            self.fail("Bootstrap issuance repeated a code")
        self.assertFalse(await self.consume(old, now=1002))
        self.assertFalse(await self.consume(new, now=1301))
        next_code = await self.issue(now=1400)
        for _ in range(5):
            self.assertFalse(await self.consume("invalid", now=1401))
        self.assertFalse(await self.consume(next_code, now=1401))
        self.assertIsNone(await self.writer.submit(find_owner_hash))

    async def test_future_clock_and_rollback_do_not_create_owner(self):
        code = await self.issue(now=1000)
        self.assertFalse(await self.consume(code, now=999))
        self.assertIsNone(await self.writer.submit(find_owner_hash))
        code = await self.issue(now=2000)
        await self.writer.close()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertTrue(consume_bootstrap(connection, candidate=code, encoded=self.encoded, now=2001))
            connection.rollback()
            self.assertIsNone(find_owner_hash(connection))
            self.assertTrue(consume_bootstrap(connection, candidate=code, encoded=self.encoded, now=2001))
            connection.commit()
        self.writer = Writer(self.path)
        await self.writer.start()
        self.assertEqual(await self.writer.submit(find_owner_hash), self.encoded)

    async def test_corrupt_verifier_fails_closed(self):
        code = await self.issue()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE bootstrap_codes SET code_hash=?", ("x" * 32,))
        self.assertFalse(await self.consume(code))
        self.assertIsNone(await self.writer.submit(find_owner_hash))
