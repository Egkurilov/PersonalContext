"""An observed expiry or clock rollback must not silently reactivate consent."""

import time
import unittest
from unittest.mock import patch

import test_source_config_security as fixture


class PolicyClockHttpTests(unittest.TestCase):
    setUp = fixture.SourceConfigSecurityTests.setUp
    tearDown = fixture.SourceConfigSecurityTests.tearDown
    create = fixture.SourceConfigSecurityTests.create

    def active_policy(self):
        source = self.create()
        policy = {"version": 1, "paused": False, "ttl": 600, "allowed": [source], "denied": [],
                  "grants": [{"source": source, "scope": "metadata"}]}
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", json=policy, headers=self.owner).status_code, 200)
        self.assertFalse(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
        return policy

    def test_expiry_followed_by_clock_rewind_stays_paused(self):
        self.active_policy()
        now = int(time.time())
        with patch("personalcontext.sources.config_http.time.time", return_value=now + 601):
            self.assertTrue(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
        self.assertTrue(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
        self.assertTrue(self.client.get("/api/v1/privacy/policy").json()["effective_paused"])

    def test_observed_clock_rollback_pauses_and_cannot_resume_with_stale_clock(self):
        policy = self.active_policy()
        now = int(time.time())
        with patch("personalcontext.sources.config_http.time.time", return_value=now + 100):
            self.assertFalse(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
        self.assertTrue(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
        response = self.client.patch("/api/v1/privacy/policy", json={**policy, "version": 2}, headers=self.owner)
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(self.client.get("/api/v1/privacy/policy").json()["effective_paused"])

    def test_owner_can_issue_new_consent_after_normal_expiry(self):
        policy = self.active_policy()
        now = int(time.time())
        with patch("personalcontext.sources.config_http.time.time", return_value=now + 601):
            self.assertTrue(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
            response = self.client.patch("/api/v1/privacy/policy", json={**policy, "version": 2}, headers=self.owner)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["local_paused"])
            self.assertFalse(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
