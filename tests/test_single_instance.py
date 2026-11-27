import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "Windows named objects required")
class SingleInstanceTests(unittest.TestCase):
    def test_second_process_reuses_mutex_without_opening_database(self):
        import win32event

        from personalcontext.windows.lifecycle import mutex_name

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "PersonalContext" / "data"
            data.mkdir(parents=True)
            mutex = win32event.CreateMutex(None, False, mutex_name(data))
            code = """
from unittest.mock import patch
from personalcontext.__main__ import main
with patch('webbrowser.open') as browser:
    result = main()
    browser.assert_called_once_with('http://127.0.0.1:17890/')
    assert result == 0
"""
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = directory
            try:
                subprocess.run([sys.executable, "-c", code], env=environment, check=True, capture_output=True, timeout=15)
                self.assertFalse((data / "context.db").exists())
            finally:
                mutex.Close()
