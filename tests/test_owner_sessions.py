import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import (
    authorize_mutation,
    create_session,
    revoke_session,
    session_active,
)
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class OwnerSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()
        self.digest = await asyncio.to_thread(hash_password, "synthetic session candidate")
        code = await self.writer.submit(partial(issue_bootstrap, now=1000))
        self.assertTrue(await self.writer.submit(partial(consume_bootstrap, candidate=code, encoded=self.digest, now=1001)))

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def test_session_csrf_expiry_revoke_and_no_plaintext_at_rest(self):
        session = await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100))
        self.assertIsNotNone(session)
        if session.token in repr(session) or session.csrf in repr(session):
            self.fail("Session representation exposed secret")
        self.assertTrue(await self.writer.submit(partial(session_active, token=session.token, now=1101)))
        self.assertFalse(await self.writer.submit(partial(session_active, token="invalid", now=1101)))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=None)))
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.assertTrue(authorize_mutation(connection, session.token, session.csrf, 1101))
            self.assertFalse(authorize_mutation(connection, session.token, "incorrect", 1101))
            self.assertFalse(authorize_mutation(connection, "invalid", session.csrf, 1101))
            self.assertFalse(authorize_mutation(connection, session.token, None, 1101))
            connection.rollback()
            self.assertFalse(authorize_mutation(connection, session.token, session.csrf, 1101))
        for path in (self.path, self.path.with_name(self.path.name + "-wal")):
            if path.exists() and (session.token.encode() in path.read_bytes() or session.csrf.encode() in path.read_bytes()):
                self.fail("Session material was persisted")
        self.assertTrue(await self.writer.submit(partial(revoke_session, token=session.token)))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1101)))

    async def test_session_creation_rejects_absent_or_changed_owner(self):
        other = await asyncio.to_thread(hash_password, "synthetic other candidate")
        self.assertIsNone(await self.writer.submit(partial(create_session, expected_hash=other, now=1100)))
        self.assertIsNone(await self.writer.submit(partial(create_session, expected_hash="invalid", now=1100)))
        def remove_owner(connection):
            connection.execute("DELETE FROM owner_credentials")

        await self.writer.submit(remove_owner)
        self.assertIsNone(await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100)))

    async def test_credential_change_invalidates_existing_session(self):
        session = await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100))
        replacement = await asyncio.to_thread(hash_password, "synthetic replacement candidate")
        def replace_owner(connection):
            connection.execute("UPDATE owner_credentials SET password_hash=? WHERE singleton=1", (replacement,))

        await self.writer.submit(replace_owner)
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1101)))
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.assertFalse(authorize_mutation(connection, session.token, session.csrf, 1101))
            connection.rollback()

    async def test_cap_and_expired_sessions_do_not_evict_active_sessions(self):
        sessions = [await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100)) for _ in range(16)]
        self.assertTrue(all(item is not None for item in sessions))
        self.assertIsNone(await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1101)))
        self.assertTrue(await self.writer.submit(partial(session_active, token=sessions[0].token, now=1101)))
        self.assertIsNotNone(await self.writer.submit(partial(create_session, expected_hash=self.digest, now=2900)))

    async def test_corrupt_verifier_fails_closed(self):
        session = await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE owner_sessions SET csrf_hash=?", ("x" * 32,))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1101)))
