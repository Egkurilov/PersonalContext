import json
import subprocess
import unittest
from unittest.mock import patch

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.status import _GATE, firewall_status
from personalcontext.network.firewall.windows import inspect_firewall


class FirewallSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        self.exe = r"C:\Apps\PersonalContext.exe"
        self.snapshot = {"profiles": [{"name": "Private", "enabled": True, "inbound": "Block"}],
                         "rules": [{"profiles": ["Private"], "protocol": "TCP", "ports": ["18443"],
                                    "remote": ["192.168.7.0/24"], "local": ["Any"], "program": self.exe,
                                    "edge": "Block", "unrestricted": True}]}

    def call(self, payload):
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload).encode(), stderr=b"")
        with (patch("personalcontext.network.firewall.windows.sys.platform", "win32"),
              patch.dict("personalcontext.network.firewall.windows.os.environ", {"SystemRoot": r"C:\Windows"}),
              patch("personalcontext.network.firewall.windows.subprocess.run", return_value=result)):
            return inspect_firewall(self.boundary, self.exe)

    def test_valid_effective_snapshot_and_broad_rule(self):
        self.assertTrue(self.call(self.snapshot))
        bad = {**self.snapshot, "rules": [{**self.snapshot["rules"][0], "remote": ["Any"]}]}
        self.assertFalse(self.call(bad))

    def test_unknown_malformed_or_missing_values_fail_closed(self):
        for payload in ({}, {"profiles": [], "rules": []}, {**self.snapshot, "extra": True},
                        {**self.snapshot, "rules": [{**self.snapshot["rules"][0], "edge": None}]},
                        {**self.snapshot, "profiles": [{"name": "Private", "enabled": "true", "inbound": "Block"}]}):
            with self.subTest(kind=type(payload).__name__):
                self.assertFalse(self.call(payload))

    def test_command_failure_and_timeout_fail_closed(self):
        for failure in (OSError(), subprocess.TimeoutExpired("synthetic", 1)):
            with (self.subTest(kind=type(failure).__name__),
                  patch("personalcontext.network.firewall.windows.sys.platform", "win32"),
                  patch.dict("personalcontext.network.firewall.windows.os.environ", {"SystemRoot": r"C:\Windows"}),
                  patch("personalcontext.network.firewall.windows.subprocess.run", side_effect=failure)):
                self.assertFalse(inspect_firewall(self.boundary, self.exe))

    def test_busy_or_unexpected_failure_reports_unavailable(self):
        self.assertTrue(_GATE.acquire(blocking=False))
        try:
            self.assertEqual(firewall_status(self.boundary, self.exe), "unavailable")
        finally:
            _GATE.release()
        with patch("personalcontext.network.firewall.status.read_firewall_snapshot", side_effect=RuntimeError("synthetic")):
            self.assertEqual(firewall_status(self.boundary, self.exe), "unavailable")
