"""The Windows process probe must reject an extra synthetic listener."""

import base64
import os
import runpy
import socket
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "Windows network APIs are required")
class FrozenNetworkProbeTests(unittest.TestCase):
    def test_rejects_additional_loopback_listener(self):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", 17890))
            except OSError:
                self.skipTest("Loopback port is in use")
        source = ("import socket,sys; "
                  "a=socket.socket(); a.bind(('127.0.0.1',17890)); a.listen(); "
                  "print('ready',flush=True); sys.stdin.read(1); "
                  "b=socket.socket(); b.bind(('127.0.0.1',0)); b.listen(); "
                  "print('extra',flush=True); sys.stdin.read(1)")
        process = subprocess.Popen([sys.executable, "-u", "-c", source], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            script = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts/smoke_frozen_network.py"))["QUERY"]
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            env = os.environ.copy()
            env["PC_SMOKE_PID"] = str(process.pid)
            shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            def inspect():
                return subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                      env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, check=False).returncode

            self.assertEqual(inspect(), 0)
            process.stdin.write("x")
            process.stdin.flush()
            self.assertEqual(process.stdout.readline().strip(), "extra")
            self.assertNotEqual(inspect(), 0)
        finally:
            process.terminate()
            process.communicate(timeout=10)
