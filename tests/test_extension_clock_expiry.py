"""An expired pairing code must not survive an observed CORS expiry."""

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_extension_pairing_http as fixture
from fastapi.testclient import TestClient

from personalcontext.app import create_app


class ExtensionClockExpiryTests(unittest.TestCase):
    setUp = fixture.ExtensionPairingTests.setUp
    tearDown = fixture.ExtensionPairingTests.tearDown
    issue = fixture.ExtensionPairingTests.issue
    preflight = fixture.ExtensionPairingTests.preflight

    def test_expired_preflight_cannot_revive_after_clock_rewind(self):
        code = self.issue().json()["code"]
        self.assertEqual(self.preflight(fixture.ENROLL).status_code, 200)
        with patch("personalcontext.devices.extension_cors.time.time", return_value=4_000_000_000):
            self.assertEqual(self.preflight(fixture.ENROLL).status_code, 403)
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.path), base_url=fixture.fixture.ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.assertEqual(self.preflight(fixture.ENROLL).status_code, 403)
        result = self.client.post(fixture.ENROLL, json={"code": code}, headers={"Origin": fixture.EXTENSION})
        self.assertNotEqual(result.status_code, 200)

    def test_expiry_observed_by_one_origin_cannot_revive_other_pending_codes(self):
        self.issue()
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        other = self.client.post(fixture.ISSUE, json={"scopes": "config", "origin": fixture.OTHER}, headers=owner)
        self.assertEqual(other.status_code, 200)
        with patch("personalcontext.devices.extension_cors.time.time", return_value=4_000_000_000):
            self.assertEqual(self.preflight(fixture.ENROLL).status_code, 403)
        self.assertEqual(self.preflight(fixture.ENROLL, origin=fixture.OTHER).status_code, 403)

    def test_time_before_issuance_invalidates_pending_code(self):
        self.issue()
        with patch("personalcontext.devices.extension_cors.time.time", return_value=0):
            self.assertEqual(self.preflight(fixture.ENROLL).status_code, 403)
        self.assertEqual(self.preflight(fixture.ENROLL).status_code, 403)

    def test_corrupt_negative_issuance_is_never_approved(self):
        self.issue()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE pairing_codes SET issued_at=-1,expires_at=299")
            connection.commit()
        with patch("personalcontext.devices.extension_cors.time.time", return_value=0):
            self.assertEqual(self.preflight(fixture.ENROLL).status_code, 403)

    def test_expired_pending_code_does_not_revoke_an_active_device(self):
        initial = self.issue().json()["code"]
        device = self.client.post(fixture.ENROLL, json={"code": initial}, headers={"Origin": fixture.EXTENSION}).json()
        expired = self.issue().json()["code"]
        with patch("personalcontext.devices.extension_cors.time.time", return_value=4_000_000_000):
            self.assertEqual(self.preflight(fixture.ENROLL).status_code, 200)
        result = self.client.post(fixture.ENROLL, json={"code": expired}, headers={"Origin": fixture.EXTENSION})
        self.assertEqual(result.status_code, 401)
        headers = {"Origin": fixture.EXTENSION, "Authorization": "Bearer " + device["token"]}
        heartbeat = self.client.post("/api/v1/device/heartbeat", json={"device_id": device["device_id"]}, headers=headers)
        self.assertEqual(heartbeat.status_code, 204)
