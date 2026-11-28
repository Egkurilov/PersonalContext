"""An observed expired or future session must not revive on wall-clock changes."""

import unittest
from functools import partial

import test_owner_sessions as fixture

from personalcontext.auth.owner_sessions import (
    authorize_mutation,
    create_session,
    session_active,
)
from personalcontext.jobs.writer import Writer


class SessionClockRollbackTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.OwnerSessionTests.asyncSetUp
    asyncTearDown = fixture.OwnerSessionTests.asyncTearDown

    async def test_expired_session_never_revives_after_clock_rollback(self):
        session = await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100))
        self.assertTrue(await self.writer.submit(partial(session_active, token=session.token, now=1101)))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=2900)))
        await self.writer.close()
        self.writer = Writer(self.path)
        await self.writer.start()
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1101)))

    async def test_session_observed_before_issue_never_revives(self):
        session = await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1099)))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1101)))

    async def test_expired_mutation_revokes_session_transactionally(self):
        session = await self.writer.submit(partial(create_session, expected_hash=self.digest, now=1100))

        def mutation(connection):
            connection.execute("BEGIN IMMEDIATE")
            return authorize_mutation(connection, session.token, session.csrf, 2900)

        self.assertFalse(await self.writer.submit(mutation))
        self.assertFalse(await self.writer.submit(partial(session_active, token=session.token, now=1101)))
