"""Exercise the actual loopback server with an intentionally sensitive request target."""

import http.client
import io
import logging
import socket
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import uvicorn

from personalcontext.app import create_app
from personalcontext.network.loopback.config import loopback_server_config


@contextmanager
def preserve_logging():
    loggers = [logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")]
    previous = [(logger.handlers[:], logger.level, logger.propagate, logger.disabled) for logger in loggers]
    try:
        yield
    finally:
        for logger, (handlers, level, propagate, disabled) in zip(loggers, previous, strict=True):
            logger.handlers, logger.level, logger.propagate, logger.disabled = handlers, level, propagate, disabled


class LoopbackLogCanaryTests(unittest.TestCase):
    def test_query_is_not_access_logged_at_info_level(self):
        canary = "syntheticCanary9472"
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(16)
            port = listener.getsockname()[1]
            with preserve_logging(), redirect_stdout(output), redirect_stderr(output):
                config = loopback_server_config(create_app(Path(directory) / "context.db"))
                logging.getLogger("uvicorn.access").setLevel(logging.INFO)
                logging.getLogger("uvicorn.error").setLevel(logging.INFO)
                server = uvicorn.Server(config)
                thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
                thread.start()
                try:
                    deadline = time.monotonic() + 10
                    while not server.started and thread.is_alive() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(server.started)
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        connection.request("GET", f"/healthz?token={canary}", headers={"Host": "127.0.0.1:17890"})
                        self.assertEqual(connection.getresponse().status, 200)
                    finally:
                        connection.close()
                finally:
                    server.should_exit = True
                    thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
        self.assertIn("Started server process", output.getvalue())
        self.assertNotIn(canary, output.getvalue())
