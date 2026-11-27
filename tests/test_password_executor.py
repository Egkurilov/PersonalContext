import asyncio
import threading
import unittest
from unittest.mock import patch

from personalcontext.auth.password_executor import PasswordExecutor


class PasswordExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_hash_and_verify(self):
        executor = PasswordExecutor(capacity=1)
        try:
            candidate = "synthetic executor candidate"
            encoded = await executor.hash(candidate)
            self.assertTrue(await executor.verify(encoded, candidate))
            self.assertFalse(await executor.verify(encoded, "wrong synthetic candidate"))
        finally:
            await executor.close()
        with self.assertRaisesRegex(RuntimeError, "Verifier unavailable"):
            await executor.verify("invalid", "synthetic")

    async def test_cancelled_request_does_not_release_running_worker(self):
        started, release = threading.Event(), threading.Event()
        executor = PasswordExecutor(capacity=1)

        def blocked_verify(_encoded, _candidate):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Synthetic worker timeout")
            return False

        try:
            with patch("personalcontext.auth.password_executor.verify_password", side_effect=blocked_verify):
                task = asyncio.create_task(executor.verify("invalid", "synthetic"))
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.assertRaisesRegex(RuntimeError, "Verifier busy"):
                    await executor.verify("invalid", "synthetic")
        finally:
            release.set()
            await executor.close()

    async def test_worker_error_does_not_permanently_consume_capacity(self):
        executor = PasswordExecutor(capacity=1)
        try:
            with patch("personalcontext.auth.password_executor.verify_password", side_effect=[RuntimeError("synthetic"), False]):
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    await executor.verify("invalid", "synthetic")
                self.assertFalse(await executor.verify("invalid", "synthetic"))
        finally:
            await executor.close()

    def test_rejects_unbounded_worker_configuration(self):
        for value in (0, 5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PasswordExecutor(capacity=value)
