import importlib.util
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("check_listeners", Path(__file__).resolve().parent.parent / "scripts/check_listeners.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ListenerTests(unittest.TestCase):
    def test_extracts_only_listeners_for_requested_process(self):
        output = """
  TCP    127.0.0.1:17890    0.0.0.0:0    LISTENING    1234
  TCP    0.0.0.0:17890      0.0.0.0:0    LISTENING    1234
  TCP    [::]:9000          [::]:0       LISTENING    1234
  TCP    127.0.0.1:17891    0.0.0.0:0    LISTENING    5678
  TCP    127.0.0.1:17890    127.0.0.1:54321 ESTABLISHED 1234
"""
        self.assertEqual(module.listener_addresses(output, 1234),
                         {"127.0.0.1:17890", "0.0.0.0:17890", "[::]:9000"})
        self.assertEqual(module.listener_addresses(output, 99), set())

    def test_rejects_unexpected_ipv6_listener(self):
        ipv4 = "TCP 127.0.0.1:17890 0.0.0.0:0 LISTENING 1234"
        ipv6 = "TCP [::]:8080 [::]:0 LISTENING 1234"
        with patch.object(module, "os", SimpleNamespace(environ={"SYSTEMROOT": "synthetic"})), patch.object(module.subprocess, "run") as run:
            run.side_effect = [subprocess.CompletedProcess([], 0, ipv4), subprocess.CompletedProcess([], 0, "")]
            module.verify_listeners(1234)
            run.side_effect = [subprocess.CompletedProcess([], 0, ipv4), subprocess.CompletedProcess([], 0, ipv6)]
            with self.assertRaisesRegex(RuntimeError, "listeners"):
                module.verify_listeners(1234)
