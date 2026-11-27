import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "PowerShell entrypoint requires Windows")
class UvEntrypointTests(unittest.TestCase):
    def test_standalone_uv_is_used_without_python_module(self):
        shell = shutil.which("powershell.exe")
        self.assertIsNotNone(shell)
        script = Path(__file__).resolve().parent.parent / "scripts" / "uv.ps1"
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / "uv.cmd"
            stub.write_bytes(b"@echo off\r\necho UV-CALL %*\r\nexit /b 0\r\n")
            environment = os.environ.copy()
            environment["PATH"] = directory + os.pathsep + str(Path(environment["SYSTEMROOT"]) / "System32")
            result = subprocess.run(
                [shell, "-NoProfile", "-File", str(script), "sync", "--locked"],
                env=environment, capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("UV-CALL sync --locked", result.stdout)

    def test_missing_uv_and_python_returns_failure(self):
        shell = shutil.which("powershell.exe")
        self.assertIsNotNone(shell)
        script = Path(__file__).resolve().parent.parent / "scripts" / "uv.ps1"
        environment = os.environ.copy()
        environment["PATH"] = str(Path(environment["SYSTEMROOT"]) / "System32")
        result = subprocess.run(
            [shell, "-NoProfile", "-File", str(script), "sync", "--locked"],
            env=environment, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
