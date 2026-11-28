import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path

from personalcontext.auth.rate_limit import consume_attempt
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class AuthRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def attempt(self, action="owner_login", now=1000):
        return await self.writer.submit(partial(consume_attempt, action=action, now=now))

    async def test_sliding_window_and_boundary(self):
        for _ in range(5):
            self.assertTrue((await self.attempt()).allowed)
        denied = await self.attempt(now=1059)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.retry_after, 1)
        self.assertTrue((await self.attempt(now=1060)).allowed)

    async def test_concurrent_attempts_and_restart_do_not_reset_limit(self):
        results = await asyncio.gather(*(self.attempt() for _ in range(20)))
        self.assertEqual(sum(result.allowed for result in results), 5)
        await self.writer.close()
        self.writer = Writer(self.path)
        await self.writer.start()
        self.assertFalse((await self.attempt(now=1001)).allowed)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM auth_attempts").fetchone()[0], 5)

    async def test_clock_rollback_unknown_actions_and_types_fail_closed(self):
        self.assertTrue((await self.attempt()).allowed)
        self.assertFalse((await self.attempt(now=999)).allowed)
        self.assertFalse((await self.attempt(now=True)).allowed)
        self.assertFalse((await self.attempt(action="unknown")).allowed)
        self.assertFalse((await self.attempt(action=[])).allowed)
        self.assertTrue((await self.attempt(action="device_enroll", now=1000)).allowed)

    async def test_bootstrap_has_separate_five_minute_window(self):
        for _ in range(5):
            self.assertTrue((await self.attempt(action="owner_bootstrap")).allowed)
        decision = await self.attempt(action="owner_bootstrap", now=1059)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.retry_after, 241)
        self.assertTrue((await self.attempt(action="owner_login", now=1059)).allowed)
        self.assertTrue((await self.attempt(action="owner_bootstrap", now=1300)).allowed)

    async def test_corrupted_state_does_not_unlock_limit(self):
        self.assertTrue((await self.attempt()).allowed)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE auth_rate_clocks SET last_seen='corrupt' WHERE action='owner_login'")
        self.assertFalse((await self.attempt(now=2000)).allowed)

    async def test_future_attempt_relative_to_clock_is_rejected(self):
        self.assertTrue((await self.attempt()).allowed)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE auth_attempts SET occurred_at=1001 WHERE action='owner_login'")
        self.assertFalse((await self.attempt(now=1001)).allowed)
