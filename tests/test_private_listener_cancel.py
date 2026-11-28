"""Slow preflight must not delay or undo the owner's stop request."""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_private_listener_http as fixture


class PrivateListenerCancelTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown
    configured = fixture.PrivateListenerHttpTests.configured

    def test_stop_cancels_slow_preflight_before_bind(self):
        owner, _ = self.configured()
        entered, release = threading.Event(), threading.Event()

        def slow_firewall(_boundary, _executable):
            entered.set()
            release.wait(timeout=4)
            return "restricted"

        with (patch("personalcontext.network.listener.manager.firewall_status", side_effect=slow_firewall),
              patch("personalcontext.network.listener.manager.bind_listener") as bind,
              ThreadPoolExecutor(max_workers=1) as executor):
            future = executor.submit(self.client.post, fixture.ROOT + "/start", headers=owner, json={"revision": 1})
            try:
                self.assertTrue(entered.wait(timeout=2))
                start = time.monotonic()
                self.assertEqual(self.client.post(fixture.ROOT + "/stop", headers=owner).status_code, 204)
                self.assertLess(time.monotonic() - start, 2)
                self.assertEqual(future.result(timeout=2).status_code, 409)
                bind.assert_not_called()
            finally:
                release.set()
