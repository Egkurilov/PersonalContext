"""An embedded private server must not replace the primary host's signals."""

import signal
import unittest
from unittest.mock import patch

import uvicorn

from personalcontext.network.listener.manager import PrivateServer


class PrivateListenerSignalTests(unittest.TestCase):
    def test_embedded_server_does_not_register_process_signal_handlers(self):
        async def app(_scope, _receive, _send):
            pass

        server = PrivateServer(uvicorn.Config(app))
        with patch.object(signal, "signal") as register, server.capture_signals():
            register.assert_not_called()
