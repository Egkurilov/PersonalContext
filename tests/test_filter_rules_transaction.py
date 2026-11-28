"""Persisted owner filters constrain sanitizer decisions in the writer transaction."""

import unittest
from datetime import UTC, datetime
from functools import partial

import test_device_http as fixture

from personalcontext.privacy.capture_policy import CaptureRequest
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.transaction import (
    prepare_app,
    prepare_text,
    prepare_web,
)


class FilterRulesTransactionTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def test_stored_allowlist_and_deny_override_caller_context(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        policy = {"version": 1, "paused": False, "ttl": 600, "allowed": ["synthetic-source"], "denied": [],
                  "grants": [{"source": "synthetic-source", "scope": "metadata"}]}
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", headers=owner, json=policy).status_code, 200)
        context = SanitizerContext(allowed_domains=frozenset({"example.org", "other.example"}),
                                   private=False, sensitivity="ordinary")

        def prepare(version, url):
            request = CaptureRequest("synthetic-source", "metadata", version, False, "ordinary")
            return self.client.portal.call(self.client.app.state.scheduler.writer.submit,
                partial(prepare_web, request=request, context=context, value={"url": url},
                        latch=self.client.app.state.capture_latch, clock=lambda: datetime.now(UTC)))

        self.assertIsNone(prepare(2, "https://example.org/article"))
        rules = {"version": 2, "allowed_domains": ["example.org"], "denied_domains": [],
                 "allowed_apps": [], "denied_apps": []}
        self.assertEqual(self.client.patch("/api/v1/privacy/filters", headers=owner, json=rules).json()["version"], 3)
        self.assertIsNone(prepare(3, "https://example.org/article"))
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", headers=owner, json={**policy, "version": 3}).status_code, 200)
        self.assertIsNotNone(prepare(4, "https://example.org/article"))
        self.assertIsNone(prepare(4, "https://other.example/article"))
        rules.update({"version": 4, "denied_domains": ["example.org"]})
        self.assertEqual(self.client.patch("/api/v1/privacy/filters", headers=owner, json=rules).json()["version"], 5)
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", headers=owner, json={**policy, "version": 5}).status_code, 200)
        self.assertIsNone(prepare(6, "https://example.org/article"))

    def test_app_and_text_require_owner_and_adapter_allowlists(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        rules = {"version": 1, "allowed_domains": ["example.org"], "denied_domains": [],
                 "allowed_apps": ["reader.exe"], "denied_apps": []}
        self.assertEqual(self.client.patch("/api/v1/privacy/filters", headers=owner, json=rules).status_code, 200)
        policy = {"version": 2, "paused": False, "ttl": 600, "allowed": ["synthetic-source"], "denied": [],
                  "grants": [{"source": "synthetic-source", "scope": scope} for scope in ("metadata", "text", "ocr")]}
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", headers=owner, json=policy).status_code, 200)
        context = SanitizerContext(allowed_domains=frozenset({"example.org", "other.example"}),
                                   allowed_apps=frozenset({"reader.exe", "other.exe"}),
                                   private=False, sensitivity="ordinary", ocr_approved=True)

        def prepare(function, scope, **values):
            request = CaptureRequest("synthetic-source", scope, 3, False, "ordinary")
            return self.client.portal.call(self.client.app.state.scheduler.writer.submit,
                partial(function, request=request, context=context, **values,
                        latch=self.client.app.state.capture_latch, clock=lambda: datetime.now(UTC)))

        self.assertIsNotNone(prepare(prepare_app, "metadata", value={"app": "reader.exe"}))
        self.assertIsNone(prepare(prepare_app, "metadata", value={"app": "other.exe"}))
        for scope in ("text", "ocr"):
            self.assertEqual(prepare(prepare_text, scope, domain="example.org", value="Synthetic text"), "Synthetic text")
            self.assertIsNone(prepare(prepare_text, scope, domain="other.example", value="Synthetic text"))
