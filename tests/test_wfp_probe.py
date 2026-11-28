"""A failed WFP permission check must not be treated as an active monitor."""

import ctypes
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_wfp_subscription


class NativeCall:
    def __init__(self, status):
        self.status = status
        self.calls = 0

    def __call__(self, *args):
        self.calls += 1
        return self.status


class WfpProbeTests(unittest.TestCase):
    def test_non_windows_fails_closed(self):
        with patch.object(check_wfp_subscription.sys, "platform", "linux"):
            self.assertFalse(check_wfp_subscription.check_subscription())

    def test_subscription_errors_close_engine_and_never_report_success(self):
        api = type("Api", (), {})()
        api.FwpmEngineOpen0 = NativeCall(0)
        api.FwpmFilterSubscribeChanges0 = NativeCall(5)
        api.FwpmFilterUnsubscribeChanges0 = NativeCall(0)
        api.FwpmEngineClose0 = NativeCall(0)
        with (patch.object(check_wfp_subscription.sys, "platform", "win32"),
              patch.object(ctypes, "WinDLL", return_value=api, create=True),
              patch.object(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, create=True)):
            self.assertFalse(check_wfp_subscription.check_subscription())
        self.assertEqual(api.FwpmEngineClose0.calls, 1)
        self.assertEqual(api.FwpmFilterUnsubscribeChanges0.calls, 0)

    def test_success_requires_subscription_and_unsubscription(self):
        for release, expected in ((0, True), (5, False)):
            api = type("Api", (), {})()
            api.FwpmEngineOpen0 = NativeCall(0)
            api.FwpmFilterSubscribeChanges0 = NativeCall(0)
            api.FwpmFilterUnsubscribeChanges0 = NativeCall(release)
            api.FwpmEngineClose0 = NativeCall(0)
            with (self.subTest(release=release), patch.object(check_wfp_subscription.sys, "platform", "win32"),
                  patch.object(ctypes, "WinDLL", return_value=api, create=True),
                  patch.object(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, create=True)):
                self.assertEqual(check_wfp_subscription.check_subscription(), expected)
                self.assertEqual(api.FwpmFilterUnsubscribeChanges0.calls, 1)
                self.assertEqual(api.FwpmEngineClose0.calls, 1)
