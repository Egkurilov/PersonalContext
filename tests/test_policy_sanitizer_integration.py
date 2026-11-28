import tempfile
import unittest
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.policy_pause import pause_local
from personalcontext.privacy.policy_store import PolicyDraft, load_policy, save_policy
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.transaction import prepare_web
from personalcontext.storage.initialize import initialize_database


class PolicySanitizerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_persisted_consent_then_pause_denies_previous_revision_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            try:
                encoded = hash_password("synthetic integration owner")
                bootstrap = await writer.submit(partial(issue_bootstrap, now=1000))
                await writer.submit(partial(consume_bootstrap, candidate=bootstrap, encoded=encoded, now=1001))
                owner = await writer.submit(partial(create_session, expected_hash=encoded, now=1002))
                draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                                    frozenset({("synthetic-source", "metadata")}))
                result = await writer.submit(partial(save_policy, token=owner.token, csrf=owner.csrf,
                                                      expected_version=1, draft=draft, now=1010))
                self.assertEqual(result.status, "ok")
                request = CaptureRequest("synthetic-source", "metadata", 2, False, "ordinary")
                context = SanitizerContext(allowed_domains=frozenset({"example.org"}),
                                           private=False, sensitivity="ordinary")
                latch = CaptureLatch()
                latch.resume_if_unchanged(latch.generation())
                sample = {"url": "https://example.org/article?tracking=discard"}
                result = await writer.submit(partial(prepare_web, request=request, context=context, value=sample,
                                                     latch=latch, clock=lambda: datetime.fromtimestamp(1011, UTC)))
                self.assertIsNotNone(result)
                self.assertEqual(result.url, "https://example.org/article")
                times = iter((datetime.fromtimestamp(1011, UTC), datetime.fromtimestamp(1610, UTC)))
                result = await writer.submit(partial(prepare_web, request=request, context=context, value=sample,
                                                     latch=latch, clock=lambda: next(times)))
                self.assertIsNone(result)
                self.assertTrue(latch.is_paused())
                latch = CaptureLatch()
                latch.resume_if_unchanged(latch.generation())
                calls = [0]

                def pausing_clock():
                    calls[0] += 1
                    if calls[0] == 2:
                        latch.pause()
                    return datetime.fromtimestamp(1011, UTC)

                result = await writer.submit(partial(prepare_web, request=request, context=context, value=sample,
                                                     latch=latch, clock=pausing_clock))
                self.assertIsNone(result)
                await writer.submit(partial(pause_local, now=1012))
                await writer.close()
                writer = Writer(path)
                await writer.start()
                self.assertTrue((await writer.submit(load_policy)).paused)
                result = await writer.submit(partial(prepare_web, request=request, context=context, value=sample,
                                                     latch=latch, clock=lambda: datetime.fromtimestamp(1013, UTC)))
                self.assertIsNone(result)
            finally:
                await writer.close()
