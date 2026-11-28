"""An automatic safety stop invalidates a start already waiting on the lock."""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_private_listener_http as fixture


class PrivateListenerRaceTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown
    configured = fixture.PrivateListenerHttpTests.configured

    def test_firewall_stop_invalidates_an_earlier_queued_start(self):
        owner, _ = self.configured()
        fake_socket = fixture.FakeSocket()
        entered, release = threading.Event(), threading.Event()

        def changed_firewall(_boundary, _executable):
            entered.set()
            release.wait(timeout=5)
            return "not_restricted"

        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.monitor.firewall_status", side_effect=changed_firewall),
              patch("personalcontext.network.listener.monitor.CHECK_INTERVAL", 0.01),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket) as bind,
              patch("personalcontext.network.listener.manager.PrivateServer", fixture.FakeServer),
              ThreadPoolExecutor(max_workers=1) as executor):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)
            self.assertTrue(entered.wait(timeout=2))
            manager = self.client.app.state.private_listener
            self.client.portal.call(manager.lock.acquire)
            try:
                future = executor.submit(self.client.post, fixture.ROOT + "/start", headers=owner, json={"revision": 1})
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if self.client.portal.call(lambda: bool(manager.lock._waiters)):
                        break
                    time.sleep(0.01)
                self.assertTrue(self.client.portal.call(lambda: bool(manager.lock._waiters)))
                release.set()
                deadline = time.monotonic() + 2
                while manager.generation == 0 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertGreater(manager.generation, 0)
            finally:
                release.set()
                self.client.portal.call(manager.lock.release)
            self.assertEqual(future.result(timeout=2).status_code, 409)
            self.assertEqual(bind.call_count, 1)
            self.assertTrue(fake_socket.closed)
