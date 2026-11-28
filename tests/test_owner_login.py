import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path
from unittest.mock import patch

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_login import OwnerLogin
from personalcontext.auth.owner_sessions import (
    revoke_authorized_session,
    session_active,
)
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class OwnerLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        self.path = path
        initialize_database(path)
        self.writer = Writer(path)
        await self.writer.start()
        self.executor = PasswordExecutor(capacity=1)
        self.login = await OwnerLogin.create(self.writer, self.executor)
        self.candidate = "synthetic login candidate"
        encoded = await asyncio.to_thread(hash_password, self.candidate)
        code = await self.writer.submit(partial(issue_bootstrap, now=1000))
        self.assertTrue(await self.writer.submit(partial(consume_bootstrap, candidate=code, encoded=encoded, now=1001)))

    async def asyncTearDown(self):
        await self.executor.close()
        await self.writer.close()
        self.directory.cleanup()

    async def test_login_logout_requires_csrf_and_hides_secret_repr(self):
        self.assertEqual((await self.login.authenticate("wrong synthetic", now=1100)).status, "invalid")
        result = await self.login.authenticate(self.candidate, now=1101)
        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(result.session)
        if result.session.token in repr(result) or result.session.csrf in repr(result):
            self.fail("Login result representation exposed secret")
        self.assertFalse(await self.login.logout(result.session.token, "invalid", now=1102))
        self.assertTrue(await self.writer.submit(partial(session_active, token=result.session.token, now=1102)))
        self.assertTrue(await self.login.logout(result.session.token, result.session.csrf, now=1102))
        self.assertFalse(await self.writer.submit(partial(session_active, token=result.session.token, now=1102)))

    async def test_rate_limit_precedes_password_work_and_survives_restart(self):
        with patch.object(self.executor, "verify", wraps=self.executor.verify) as verifier:
            for _ in range(5):
                self.assertEqual((await self.login.authenticate("wrong synthetic", now=1100)).status, "invalid")
            limited = await self.login.authenticate(self.candidate, now=1101)
            self.assertEqual(limited.status, "limited")
            self.assertEqual(limited.retry_after, 59)
            self.assertEqual(verifier.await_count, 5)
        await self.writer.close()
        self.writer = Writer(Path(self.directory.name) / "context.db")
        await self.writer.start()
        self.login = await OwnerLogin.create(self.writer, self.executor)
        self.assertEqual((await self.login.authenticate(self.candidate, now=1102)).status, "limited")
        self.assertEqual((await self.login.authenticate(self.candidate, now=1160)).status, "ok")

    async def test_missing_owner_still_runs_password_verifier(self):
        def remove_owner(connection):
            connection.execute("DELETE FROM owner_credentials")

        await self.writer.submit(remove_owner)
        with patch.object(self.executor, "verify", wraps=self.executor.verify) as verifier:
            self.assertEqual((await self.login.authenticate(self.candidate, now=1100)).status, "invalid")
            self.assertEqual(verifier.await_count, 1)

    async def test_owner_change_during_verification_cannot_create_session(self):
        replacement = await asyncio.to_thread(hash_password, "synthetic replacement owner")

        async def change_owner(_encoded, _candidate):
            def update(connection):
                connection.execute("UPDATE owner_credentials SET password_hash=? WHERE singleton=1", (replacement,))

            await self.writer.submit(update)
            return True

        with patch.object(self.executor, "verify", side_effect=change_owner):
            result = await self.login.authenticate(self.candidate, now=1100)
        self.assertNotEqual(result.status, "ok")
        self.assertIsNone(result.session)

    async def test_verifier_failure_does_not_create_session_or_echo_error(self):
        with patch.object(self.executor, "verify", side_effect=RuntimeError("synthetic private detail")):
            result = await self.login.authenticate(self.candidate, now=1100)
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.session)
        self.assertNotIn("synthetic private detail", repr(result))

        def count_sessions(connection):
            return connection.execute("SELECT count(*) FROM owner_sessions").fetchone()[0]

        self.assertEqual(await self.writer.submit(count_sessions), 0)

    async def test_invalid_dummy_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid verifier configuration"):
            OwnerLogin(self.writer, self.executor, "invalid")

    async def test_authorized_logout_rollback_keeps_session(self):
        result = await self.login.authenticate(self.candidate, now=1100)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertTrue(revoke_authorized_session(connection, result.session.token, result.session.csrf, 1101))
            connection.rollback()
        self.assertTrue(await self.writer.submit(partial(session_active, token=result.session.token, now=1101)))
