import tempfile
import unittest
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.capture_commit import submit_capture
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest, allows_capture
from personalcontext.privacy.filters.rules import FilterRules
from personalcontext.privacy.filters.store import save_filters
from personalcontext.privacy.policy_store import PolicyDraft, load_policy, save_policy
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.transaction import prepare_web
from personalcontext.storage.initialize import initialize_database


class CapturePolicyAtomicTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        self.latch = CaptureLatch()
        self.latch.resume_if_unchanged(self.latch.generation())
        self.writer = Writer(path, on_storage_failure=self.latch.pause)
        await self.writer.start()
        encoded = hash_password("synthetic atomic owner")
        code = await self.writer.submit(partial(issue_bootstrap, now=1000))
        await self.writer.submit(partial(consume_bootstrap, candidate=code, encoded=encoded, now=1001))
        owner = await self.writer.submit(partial(create_session, expected_hash=encoded, now=1002))
        filters = FilterRules(allowed_domains=frozenset({"example.org"}))
        await self.writer.submit(partial(save_filters, token=owner.token, csrf=owner.csrf,
                                         expected=1, rules=filters, now=1003))
        draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                            frozenset({("synthetic-source", "metadata")}))
        await self.writer.submit(partial(save_policy, token=owner.token, csrf=owner.csrf,
                                         expected_version=2, draft=draft, now=1010))
        self.request = CaptureRequest("synthetic-source", "metadata", 3, False, "ordinary")
        self.context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def run_capture(self, final_time, pause=False):
        def operation(connection):
            result = prepare_web(connection, self.request, self.context,
                                 {"url": "https://example.org/article?tracking=synthetic"},
                                 latch=self.latch, clock=lambda: datetime.fromtimestamp(1011, UTC))
            if result is None:
                return None
            connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture',?)", (result.url,))
            return True

        def validate(connection):
            if pause:
                self.latch.pause()
            return allows_capture(load_policy(connection), self.request, datetime.fromtimestamp(final_time, UTC))

        return await submit_capture(self.writer, self.latch, operation, validate)

    async def stored(self):
        return await self.writer.submit(lambda connection: connection.execute(
            "SELECT value FROM app_metadata WHERE key='fixture'",
        ).fetchone())

    async def test_only_sanitized_value_commits_while_consent_current(self):
        self.assertTrue(await self.run_capture(1012))
        self.assertEqual(await self.stored(), ("https://example.org/article",))

    async def test_expiry_before_commit_rolls_back(self):
        self.assertIsNone(await self.run_capture(1610))
        self.assertIsNone(await self.stored())

    async def test_pause_before_commit_rolls_back(self):
        self.assertIsNone(await self.run_capture(1012, pause=True))
        self.assertIsNone(await self.stored())
