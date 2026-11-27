import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_login import OwnerLogin
from personalcontext.auth.owner_sessions import session_active
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.password_hash import hash_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class OwnerLoginClockTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_timestamp_is_taken_after_password_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            executor = PasswordExecutor()
            try:
                code = await writer.submit(partial(issue_bootstrap, now=1000))
                encoded = hash_password("synthetic owner password")
                await writer.submit(partial(consume_bootstrap, candidate=code, encoded=encoded, now=1001))
                now = [1100]
                login = await OwnerLogin.create(writer, executor, clock=lambda: now[0])
                original = executor.verify

                async def delayed_verify(encoded, password):
                    matched = await original(encoded, password)
                    now[0] = 1200
                    return matched

                with patch.object(executor, "verify", side_effect=delayed_verify):
                    result = await login.authenticate("synthetic owner password")
                self.assertEqual(result.status, "ok")
                self.assertTrue(await writer.submit(partial(session_active, token=result.session.token, now=1200)))
                self.assertFalse(await writer.submit(partial(session_active, token=result.session.token, now=1100)))
            finally:
                await executor.close()
                await writer.close()
