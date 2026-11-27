import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest, allows_capture
from personalcontext.privacy.policy_pause import pause_local
from personalcontext.privacy.policy_store import PolicyDraft, load_policy, save_policy
from personalcontext.storage.initialize import initialize_database


class PolicyStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()
        code = await self.writer.submit(partial(issue_bootstrap, now=1000))
        encoded = await asyncio.to_thread(hash_password, "synthetic policy owner")
        await self.writer.submit(partial(consume_bootstrap, candidate=code, encoded=encoded, now=1001))
        self.owner = await self.writer.submit(partial(create_session, expected_hash=encoded, now=1002))
        self.draft = PolicyDraft(paused=False, ttl=600, allowed=frozenset({"synthetic-source"}),
                                 denied=frozenset(), grants=frozenset({("synthetic-source", "metadata")}))

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def save(self, draft=None, version=1, csrf=None, now=1010):
        return await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=csrf or self.owner.csrf,
                                                 expected_version=version, draft=draft or self.draft, now=now))

    async def test_default_denies_and_owner_grant_expires_after_restart(self):
        request = CaptureRequest("synthetic-source", "metadata", 1, False, "ordinary")
        initial = await self.writer.submit(load_policy)
        self.assertFalse(allows_capture(initial, request, datetime.fromtimestamp(1009, UTC)))
        self.assertEqual((await self.save()).status, "ok")
        await self.writer.close()
        self.writer = Writer(self.path)
        await self.writer.start()
        current = await self.writer.submit(load_policy)
        request = CaptureRequest("synthetic-source", "metadata", 2, False, "ordinary")
        self.assertTrue(allows_capture(current, request, datetime.fromtimestamp(1011, UTC)))
        self.assertFalse(allows_capture(current, request, datetime.fromtimestamp(1610, UTC)))
        self.assertFalse(allows_capture(current, CaptureRequest("synthetic-source", "text", 2, False, "ordinary"),
                                        datetime.fromtimestamp(1011, UTC)))

    async def test_deny_and_pause_override_and_stale_revision_conflicts(self):
        draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset({"synthetic-source"}),
                            frozenset({("synthetic-source", "metadata")}))
        self.assertEqual((await self.save(draft)).status, "ok")
        request = CaptureRequest("synthetic-source", "metadata", 2, False, "ordinary")
        self.assertFalse(allows_capture(await self.writer.submit(load_policy), request, datetime.fromtimestamp(1011, UTC)))
        self.assertEqual((await self.save(version=1, now=1012)).status, "conflict")
        paused = PolicyDraft(True, 600, draft.allowed, frozenset(), draft.grants)
        self.assertEqual((await self.save(paused, version=2, now=1012)).status, "ok")
        request = CaptureRequest("synthetic-source", "metadata", 3, False, "ordinary")
        self.assertFalse(allows_capture(await self.writer.submit(load_policy), request, datetime.fromtimestamp(1013, UTC)))

    async def test_bad_csrf_invalid_drafts_and_clock_rollback_fail_closed(self):
        self.assertEqual((await self.save(csrf="invalid")).status, "forbidden")
        for ttl in (0, 86401, True):
            draft = PolicyDraft(False, ttl, self.draft.allowed, self.draft.denied, self.draft.grants)
            self.assertEqual((await self.save(draft)).status, "invalid")
        self.assertEqual((await self.save()).status, "ok")
        self.assertEqual((await self.save(version=2, now=1009)).status, "invalid")

    async def test_corrupt_policy_is_denied_and_cannot_be_overwritten(self):
        self.assertEqual((await self.save()).status, "ok")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE capture_policy SET paused=2")
        self.assertIsNone(await self.writer.submit(load_policy))
        self.assertEqual((await self.save(version=2, now=1011)).status, "unavailable")

    async def test_write_rollback_keeps_previous_revision(self):
        with closing(sqlite3.connect(self.path)) as connection:
            result = save_policy(connection, self.owner.token, self.owner.csrf, 1, self.draft, 1010)
            self.assertEqual(result.status, "ok")
            connection.rollback()
        policy = await self.writer.submit(load_policy)
        self.assertEqual(policy.version, 1)
        self.assertTrue(policy.paused)

    async def test_native_pause_needs_no_session_and_invalidates_stale_updates(self):
        self.assertEqual((await self.save()).status, "ok")
        paused = await self.writer.submit(partial(pause_local, now=1011))
        self.assertEqual(paused.status, "ok")
        self.assertTrue((await self.writer.submit(load_policy)).paused)
        self.assertEqual((await self.save(version=2, now=1012)).status, "conflict")

    async def test_concurrent_update_and_native_pause_finish_paused(self):
        self.assertEqual((await self.save()).status, "ok")
        results = await asyncio.gather(self.save(version=2, now=1011), self.writer.submit(partial(pause_local, now=1011)))
        self.assertEqual(results[1].status, "ok")
        self.assertTrue((await self.writer.submit(load_policy)).paused)
