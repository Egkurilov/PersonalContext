import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo

from personalcontext.privacy.capture_policy import (
    CapturePolicy,
    CaptureRequest,
    allows_capture,
)


class CapturePolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, tzinfo=UTC)
        self.policy = CapturePolicy(
            version=7, issued_at=self.now - timedelta(minutes=1),
            expires_at=self.now + timedelta(hours=1), paused=False,
            allowed_sources=frozenset({"synthetic-source"}),
            scopes=frozenset({"metadata"}),
        )
        self.request = CaptureRequest(
            source="synthetic-source", scope="metadata", policy_version=7,
            private=False, sensitivity="ordinary",
        )

    def test_default_deny_and_explicit_valid_grant(self):
        self.assertFalse(allows_capture(CapturePolicy(), self.request, self.now))
        self.assertTrue(allows_capture(self.policy, self.request, self.now))

    def test_expiry_pause_and_deny_override_allow(self):
        variants = (
            replace(self.policy, paused=True),
            replace(self.policy, expires_at=self.now),
            replace(self.policy, issued_at=self.now + timedelta(seconds=1)),
            replace(self.policy, denied_sources=frozenset({"synthetic-source"})),
            replace(self.policy, allowed_sources=frozenset()),
            replace(self.policy, scopes=frozenset()),
        )
        for policy in variants:
            with self.subTest(policy=policy):
                self.assertFalse(allows_capture(policy, self.request, self.now))

    def test_unknown_private_sensitive_scope_and_version_fail_closed(self):
        variants = (
            replace(self.request, private=True), replace(self.request, private=None),
            replace(self.request, sensitivity="unknown"), replace(self.request, sensitivity="financial"),
            replace(self.request, scope="text"), replace(self.request, scope="ocr"),
            replace(self.request, scope="unrecognized"), replace(self.request, policy_version=6),
        )
        for request in variants:
            with self.subTest(request=request):
                self.assertFalse(allows_capture(self.policy, request, self.now))

    def test_bad_types_and_naive_clock_fail_closed(self):
        self.assertFalse(allows_capture(replace(self.policy, paused=0), self.request, self.now))
        self.assertFalse(allows_capture(replace(self.policy, version=True), self.request, self.now))
        self.assertFalse(allows_capture(self.policy, replace(self.request, private=0), self.now))
        self.assertFalse(allows_capture(self.policy, replace(self.request, scope=[]), self.now))
        self.assertFalse(allows_capture(replace(self.policy, allowed_sources=[]), self.request, self.now))
        self.assertFalse(allows_capture(self.policy, self.request, self.now.replace(tzinfo=None)))
        self.assertFalse(allows_capture(replace(self.policy, expires_at=self.now.replace(tzinfo=None)), self.request, self.now))

    def test_expiry_compares_instants_across_repeated_local_hour(self):
        class RepeatedHour(tzinfo):
            def utcoffset(self, value):
                return timedelta(hours=-5 if value.fold else -4)

        zone = RepeatedHour()
        issued = datetime(2026, 11, 1, 1, 0, tzinfo=zone, fold=0)
        expiry = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
        now = datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1)
        self.assertFalse(allows_capture(replace(self.policy, issued_at=issued, expires_at=expiry), self.request, now))
