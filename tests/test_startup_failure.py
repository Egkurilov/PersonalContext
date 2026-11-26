import os
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen


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

    def test_restarts_after_database_lock_is_released(self):
        from personalcontext.__main__ import main
        from personalcontext.storage.initialize import initialize_database

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}), patch("sys.argv", ["personalcontext"]), patch("sys._MEIPASS", directory, create=True), patch("win32api.MessageBox") as message:
            (Path(directory) / "frontend/dist/assets").mkdir(parents=True)
            path = Path(directory) / "PersonalContext/data/context.db"
            path.parent.mkdir(parents=True)
            initialize_database(path)
            with closing(sqlite3.connect(path)) as locker:
                locker.execute("BEGIN IMMEDIATE")
                self.assertEqual(main(), 1)
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 17890))
                locker.rollback()
            with patch("personalcontext.__main__.pystray.Icon") as icon:
                def check_ready(**_kwargs):
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=2) as response:
                        self.assertEqual(response.read(), b'{"status":"ready"}')

                icon.return_value.run.side_effect = check_ready
                self.assertEqual(main(), 0)
            message.assert_called_once()
    def test_restarts_and_becomes_ready_after_port_is_released(self):
        from personalcontext.__main__ import main

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}), patch("sys.argv", ["personalcontext"]), patch("sys._MEIPASS", directory, create=True), patch("win32api.MessageBox") as message:
            (Path(directory) / "frontend/dist/assets").mkdir(parents=True)
            with socket.socket() as occupied:
                occupied.bind(("127.0.0.1", 17890))
                occupied.listen()
                self.assertEqual(main(), 1)
                self.assertFalse((Path(directory) / "PersonalContext/data/context.db").exists())
            with patch("personalcontext.__main__.pystray.Icon") as icon:
                def check_ready(**_kwargs):
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=2) as response:
                        self.assertEqual(response.read(), b'{"status":"ready"}')

                icon.return_value.run.side_effect = check_ready
                self.assertEqual(main(), 0)
            message.assert_called_once()
