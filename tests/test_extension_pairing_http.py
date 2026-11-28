"""Synthetic acceptance for extension-bound pairing and CORS isolation."""

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_device_http as fixture

from personalcontext.storage.restore_security import reset_restored_access

EXTENSION = "chrome-extension://" + "a" * 32
OTHER = "chrome-extension://" + "b" * 32
ISSUE = "/api/v1/devices/pairing-codes/extension"
ENROLL = "/api/v1/devices/enroll"


class ExtensionPairingTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def issue(self):
        return self.client.post(ISSUE, json={"scopes": "heartbeat,config", "origin": EXTENSION},
                                headers={**self.headers, "X-CSRF-Token": self.csrf})

    def preflight(self, path, origin=EXTENSION, method="POST", headers="content-type"):
        return self.client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method,
                                                  "Access-Control-Request-Headers": headers})

    def test_owner_approval_and_canonical_origin_required(self):
        self.assertEqual(self.client.post(ISSUE, json={"scopes": "config", "origin": EXTENSION},
                                          headers=self.headers).status_code, 403)
        for origin in (OTHER + "/", "chrome-extension://" + "q" * 32, "https://example.test", "null"):
            result = self.client.post(ISSUE, json={"scopes": "config", "origin": origin},
                                      headers={**self.headers, "X-CSRF-Token": self.csrf})
            self.assertEqual(result.status_code, 400)

    def test_pairing_origin_cors_binding_and_revocation(self):
        self.assertNotEqual(self.preflight(ENROLL).status_code, 200)
        issued = self.issue()
        self.assertEqual(issued.status_code, 200)
        code = issued.json()["code"]
        preflight = self.preflight(ENROLL)
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers.get("access-control-allow-origin"), EXTENSION)
        self.assertNotIn("access-control-allow-credentials", preflight.headers)
        self.assertNotEqual(self.preflight(ENROLL, OTHER).status_code, 200)
        self.assertNotEqual(self.preflight("/api/v1/auth/login").status_code, 200)
        self.assertNotEqual(self.client.post(ENROLL, json={"code": code}).status_code, 200)
        self.assertNotEqual(self.client.post(ENROLL, json={"code": code}, headers={"Origin": OTHER}).status_code, 200)
        response = self.client.post(ENROLL, json={"code": code}, headers={"Origin": EXTENSION})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), EXTENSION)
        device = response.json()
        self.assertNotEqual(self.client.post(ENROLL, json={"code": code}, headers={"Origin": EXTENSION}).status_code, 200)
        headers = {"Origin": EXTENSION, "Authorization": "Bearer " + device["token"]}
        path = "/api/v1/device/heartbeat"
        self.assertEqual(self.client.post(path, json={"device_id": device["device_id"]}, headers=headers).status_code, 204)
        self.assertNotEqual(self.client.post(path, json={"device_id": device["device_id"]},
                                             headers={"Authorization": headers["Authorization"]}).status_code, 204)
        self.assertNotEqual(self.client.post(path, json={"device_id": device["device_id"]},
                                             headers={**headers, "Origin": OTHER}).status_code, 204)
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        self.assertEqual(self.client.post(f"/api/v1/devices/{device['device_id']}/revoke", headers=owner).status_code, 204)
        self.assertNotEqual(self.client.post(path, json={"device_id": device["device_id"]}, headers=headers).status_code, 204)

    def test_expiry_and_preflight_are_narrow(self):
        issued = self.issue()
        code = issued.json()["code"]
        self.assertNotEqual(self.preflight(ENROLL, method="GET").status_code, 200)
        self.assertNotEqual(self.preflight(ENROLL, headers="x-csrf-token").status_code, 200)
        with patch("personalcontext.devices.extension_cors.time.time", return_value=4_000_000_000):
            self.assertNotEqual(self.preflight(ENROLL).status_code, 200)
            result = self.client.post(ENROLL, json={"code": code}, headers={"Origin": EXTENSION})
            self.assertNotEqual(result.status_code, 200)

    def test_native_credentials_cannot_be_used_as_extension_credentials(self):
        code = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "heartbeat"},
                                headers={**self.headers, "X-CSRF-Token": self.csrf}).json()["code"]
        native = self.client.post(ENROLL, json={"code": code}).json()
        self.issue()
        headers = {"Origin": EXTENSION, "Authorization": "Bearer " + native["token"]}
        result = self.client.post("/api/v1/device/heartbeat", json={"device_id": native["device_id"]}, headers=headers)
        self.assertEqual(result.status_code, 401)

    def test_restore_invalidates_pending_and_enrolled_access(self):
        code = self.issue().json()["code"]
        device = self.client.post(ENROLL, json={"code": code}, headers={"Origin": EXTENSION}).json()
        pending = self.issue().json()["code"]
        with closing(sqlite3.connect(self.path)) as connection:
            reset_restored_access(connection)
            self.assertEqual(connection.execute("SELECT count(*) FROM extension_pairings").fetchone()[0], 0)
            connection.commit()
        self.assertNotEqual(self.preflight(ENROLL).status_code, 200)
        self.assertNotEqual(self.client.post(ENROLL, json={"code": pending}, headers={"Origin": EXTENSION}).status_code, 200)
        result = self.client.post("/api/v1/device/heartbeat", json={"device_id": device["device_id"]},
                                  headers={"Origin": EXTENSION, "Authorization": "Bearer " + device["token"]})
        self.assertNotEqual(result.status_code, 204)


if __name__ == "__main__":
    unittest.main()
