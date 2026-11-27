import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic device owner"


class DeviceHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        self.path = path
        initialize_database(path)
        with closing(sqlite3.connect(path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.headers = {"Origin": ORIGIN}
        response = self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=self.headers)
        self.assertEqual(response.status_code, 204)
        response = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.headers)
        self.csrf = response.json()["csrf"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_pairing_and_revocation_require_owner_and_csrf(self):
        path = "/api/v1/devices/pairing-codes"
        self.assertEqual(self.client.post(path, json={"scopes": "heartbeat,config"}, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post(path, json={"scopes": "heartbeat,config"},
                                          headers={"X-CSRF-Token": self.csrf}).status_code, 403)
        headers = {**self.headers, "X-CSRF-Token": self.csrf}
        response = self.client.post(path, json={"scopes": "heartbeat,config"}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        code = response.json()["code"]
        response = self.client.post("/api/v1/devices/enroll", json={"code": code})
        self.assertEqual(response.status_code, 200)
        device_id = response.json()["device_id"]
        token = response.json()["token"]
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.post("/api/v1/devices/enroll", json={"code": code}).status_code, 401)
        listing = self.client.get("/api/v1/devices")
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(token, listing.text)
        self.assertEqual(listing.json()["devices"][0]["device_id"], device_id)
        self.assertEqual(self.client.post(f"/api/v1/devices/{device_id}/revoke", headers=self.headers).status_code, 403)
        device_headers = {"Authorization": f"Bearer {token}"}
        heartbeat = "/api/v1/device/heartbeat"
        self.assertEqual(self.client.post(heartbeat, json={"device_id": "00000000-0000-4000-8000-000000000000"},
                                          headers=device_headers).status_code, 401)
        self.assertEqual(self.client.post(heartbeat, json={"device_id": device_id}, headers=device_headers).status_code, 204)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertIsNotNone(connection.execute("SELECT last_seen FROM devices WHERE device_id=?", (device_id,)).fetchone()[0])
        self.assertEqual(self.client.post(f"/api/v1/devices/{device_id}/revoke", headers=headers).status_code, 204)
        self.assertEqual(self.client.post(heartbeat, json={"device_id": device_id}, headers=device_headers).status_code, 401)
        self.assertTrue(self.client.get("/api/v1/devices").json()["devices"][0]["revoked"])

    def test_config_only_token_cannot_send_heartbeat(self):
        headers = {**self.headers, "X-CSRF-Token": self.csrf}
        code = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "config"}, headers=headers).json()["code"]
        device = self.client.post("/api/v1/devices/enroll", json={"code": code}).json()
        response = self.client.post("/api/v1/device/heartbeat", json={"device_id": device["device_id"]},
                                    headers={"Authorization": f"Bearer {device['token']}"})
        self.assertEqual(response.status_code, 401)

    def test_device_token_cannot_heartbeat_another_enrolled_device(self):
        headers = {**self.headers, "X-CSRF-Token": self.csrf}
        devices = []
        for _ in range(2):
            code = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "heartbeat"}, headers=headers).json()["code"]
            devices.append(self.client.post("/api/v1/devices/enroll", json={"code": code}).json())
        response = self.client.post("/api/v1/device/heartbeat", json={"device_id": devices[1]["device_id"]},
                                    headers={"Authorization": f"Bearer {devices[0]['token']}"})
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_and_invalid_scopes_fail_closed(self):
        headers = {**self.headers, "X-CSRF-Token": self.csrf}
        for value in ("", "owner", "ingest,ingest", "ingest,config,unknown"):
            self.assertEqual(self.client.post("/api/v1/devices/pairing-codes", json={"scopes": value},
                                              headers=headers).status_code, 400)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/devices").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "ingest"},
                                          headers={**self.headers, "X-CSRF-Token": self.csrf}).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/devices/enroll", json={"code": "invalid"}).status_code, 401)

    def test_enrollment_rate_limit_is_global(self):
        for _ in range(5):
            self.assertEqual(self.client.post("/api/v1/devices/enroll", json={"code": "invalid"}).status_code, 401)
        response = self.client.post("/api/v1/devices/enroll", json={"code": "invalid"})
        self.assertEqual(response.status_code, 429)
