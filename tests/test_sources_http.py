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
CANDIDATE = "synthetic sources owner"


class SourcesHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        with closing(sqlite3.connect(path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        origin = {"Origin": ORIGIN}
        self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=origin)
        csrf = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=origin).json()["csrf"]
        self.owner_headers = {**origin, "X-CSRF-Token": csrf}
        self.devices = []
        for _ in range(2):
            pairing = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "ingest,config"},
                                       headers=self.owner_headers).json()["code"]
            self.devices.append(self.client.post("/api/v1/devices/enroll", json={"code": pairing}).json())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def create(self, device, kind="browser"):
        return self.client.post("/api/v1/sources", json={"device_id": device["device_id"], "kind": kind},
                                headers=self.owner_headers)

    def config(self, device, claimed_id=None):
        return self.client.get("/api/v1/device/config", headers={"Authorization": f"Bearer {device['token']}",
                                                                "X-Device-Id": claimed_id or device["device_id"]})

    def test_device_sees_only_own_unverified_source_and_no_capture_grants(self):
        source_a = self.create(self.devices[0]).json()["source_id"]
        source_b = self.create(self.devices[1], "windows").json()["source_id"]
        path = "/api/v1/sources/" + source_a
        self.assertEqual(self.client.patch(path, json={"revision": 1, "paused": False}, headers=self.owner_headers).status_code, 200)
        policy = {"version": 1, "paused": False, "ttl": 600, "allowed": [source_a, source_b], "denied": [],
                  "grants": [{"source": source_a, "scope": "metadata"}, {"source": source_b, "scope": "metadata"}]}
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", json=policy, headers=self.owner_headers).status_code, 200)
        response = self.config(self.devices[0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(source_b, response.text)
        data = response.json()
        self.assertFalse(data["paused"])
        self.assertFalse(data["collection_enabled"])
        self.assertEqual(len(data["sources"]), 1)
        self.assertEqual(data["sources"][0]["source_id"], source_a)
        self.assertEqual(data["sources"][0]["capability"], "unverified")
        self.assertTrue(data["sources"][0]["paused"])
        self.assertEqual(data["sources"][0]["scopes"], [])
        self.assertEqual(self.config(self.devices[0], self.devices[1]["device_id"]).status_code, 401)

    def test_owner_auth_revisions_and_revocation(self):
        path = "/api/v1/sources"
        body = {"device_id": self.devices[0]["device_id"], "kind": "browser"}
        self.assertEqual(self.client.post(path, json=body, headers={"Origin": ORIGIN}).status_code, 403)
        source = self.create(self.devices[0]).json()["source_id"]
        self.assertEqual(self.client.get(path).json()["sources"][0]["source_id"], source)
        update = {"revision": 1, "paused": False}
        self.assertEqual(self.client.patch(path + "/" + source, json=update, headers=self.owner_headers).status_code, 200)
        self.assertEqual(self.client.patch(path + "/" + source, json=update, headers=self.owner_headers).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/devices/" + self.devices[0]["device_id"] + "/revoke",
                                          headers=self.owner_headers).status_code, 204)
        self.assertEqual(self.config(self.devices[0]).status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_config_requires_its_own_bearer_and_scope(self):
        self.assertEqual(self.client.get("/api/v1/device/config").status_code, 401)
        pairing = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "ingest"},
                                   headers=self.owner_headers).json()["code"]
        device = self.client.post("/api/v1/devices/enroll", json={"code": pairing}).json()
        self.assertEqual(self.config(device).status_code, 401)
        self.assertEqual(self.create(device, "safari").status_code, 400)
