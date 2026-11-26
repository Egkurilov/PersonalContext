import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows tray entrypoint required")
class StartupFailureTests(unittest.TestCase):
    def test_demo_shutdown_targets_separate_directory(self):
        from personalcontext.__main__ import main

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}), patch("sys.argv", ["personalcontext", "--demo", "--shutdown"]), patch("personalcontext.__main__.request_shutdown", return_value=0) as shutdown:
                self.assertEqual(main(), 0)
            shutdown.assert_called_once_with(Path(directory) / "PersonalContext" / "demo")

    def test_occupied_port_fails_without_database_or_public_listener(self):
        from personalcontext.__main__ import main

        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 17890))
            occupied.listen()
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}), patch("sys.argv", ["personalcontext"]), patch("win32api.MessageBox") as message:
                self.assertEqual(main(), 1)
            message.assert_called_once()
            self.assertFalse((Path(directory) / "PersonalContext/data/context.db").exists())
