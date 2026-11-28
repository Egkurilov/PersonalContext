"""The frozen network smoke must tolerate transient socket read timeouts."""

import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from scripts.smoke_frozen_network import wait_ready


class FrozenNetworkWaitTests(unittest.TestCase):
    def test_timeout_then_ready(self):
        process = Mock()
        process.poll.return_value = None
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status = 200
        with (patch("scripts.smoke_frozen_network.urlopen", side_effect=[TimeoutError(), URLError("offline"), response]),
              patch("scripts.smoke_frozen_network.time.sleep")):
            wait_ready(process)

    def test_exited_process_is_not_ready(self):
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            wait_ready(process)

    def test_repeated_timeout_still_hits_deadline(self):
        process = Mock()
        process.poll.return_value = None
        with (patch("scripts.smoke_frozen_network.urlopen", side_effect=TimeoutError),
              patch("scripts.smoke_frozen_network.time.monotonic", side_effect=[0, 0, 31]),
              patch("scripts.smoke_frozen_network.time.sleep"),
              self.assertRaisesRegex(RuntimeError, "did not become ready")):
            wait_ready(process)
