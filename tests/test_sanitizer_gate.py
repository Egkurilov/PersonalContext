import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from personalcontext.privacy.capture_policy import CapturePolicy, CaptureRequest
from personalcontext.privacy.sanitizer.gate import gate_app, gate_text, gate_web
from personalcontext.privacy.sanitizer.rules import SanitizerContext


class SanitizerGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.policy = CapturePolicy(version=2, issued_at=self.now, expires_at=self.now + timedelta(minutes=10),
                                    paused=False, allowed_sources=frozenset({"synthetic-source"}),
                                    grants=frozenset({("synthetic-source", "metadata")}))
        self.request = CaptureRequest("synthetic-source", "metadata", 2, False, "ordinary")
        self.context = SanitizerContext(allowed_domains=frozenset({"example.org"}),
                                        allowed_apps=frozenset({"reader.exe"}), private=False, sensitivity="ordinary")

    def test_web_and_app_require_current_policy_and_safe_data(self):
        web = {"url": "https://example.org/article?tracking=discard", "title": "Синтетическая статья"}
        self.assertIsNotNone(gate_web(self.policy, self.request, self.context, web, self.now))
        self.assertIsNotNone(gate_app(self.policy, self.request, self.context, {"app": "reader.exe"}, self.now))
        for policy in (CapturePolicy(), replace(self.policy, paused=True), replace(self.policy, expires_at=self.now),
                       replace(self.policy, denied_sources=frozenset({"synthetic-source"}))):
            self.assertIsNone(gate_web(policy, self.request, self.context, web, self.now))
        self.assertIsNone(gate_web(self.policy, replace(self.request, policy_version=1), self.context, web, self.now))
        self.assertIsNone(gate_web(self.policy, self.request, replace(self.context, private=True), web, self.now))
        self.assertIsNone(gate_web(self.policy, self.request, self.context, {"url": "https://example.org/login"}, self.now))

    def test_text_and_ocr_need_separate_grants_and_trusted_origin(self):
        request = replace(self.request, scope="text")
        self.assertIsNone(gate_text(self.policy, request, self.context, "example.org", "synthetic content", self.now))
        policy = replace(self.policy, grants=frozenset({("synthetic-source", "text"), ("synthetic-source", "ocr")}))
        self.assertEqual(gate_text(policy, request, self.context, "example.org", "synthetic content", self.now),
                         "synthetic content")
        self.assertIsNone(gate_text(policy, request, self.context, "unknown.example", "synthetic content", self.now))
        ocr = replace(request, scope="ocr")
        self.assertIsNone(gate_text(policy, ocr, self.context, "example.org", "synthetic content", self.now))
        approved = replace(self.context, ocr_approved=True)
        self.assertEqual(gate_text(policy, ocr, approved, "example.org", "synthetic content", self.now),
                         "synthetic content")
        self.assertIsNone(gate_text(policy, request, self.context, "example.org", "api" + "_key=value", self.now))
