import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic config owner"


class SourceConfigSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(self.path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        origin = {"Origin": ORIGIN}
        self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=origin)
        csrf = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=origin).json()["csrf"]
        self.owner = {**origin, "X-CSRF-Token": csrf}
        pairing = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "ingest,config"}, headers=self.owner).json()["code"]
        self.device = self.client.post("/api/v1/devices/enroll", json={"code": pairing}).json()
        self.bearer = {"Authorization": f"Bearer {self.device['token']}", "X-Device-Id": self.device["device_id"]}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def create(self):
        return self.client.post("/api/v1/sources", json={"device_id": self.device["device_id"], "kind": "browser"},
                                headers=self.owner).json()["source_id"]

    def test_pagination_is_stable_and_owner_only(self):
        ids = {self.create() for _ in range(3)}
        seen = set()
        cursor = None
        for _ in range(3):
            params = {"limit": "1"}
            if cursor:
                params["cursor"] = cursor
            page = self.client.get("/api/v1/sources", params=params).json()
            seen.add(page["sources"][0]["source_id"])
            cursor = page["next_cursor"]
        self.assertEqual(seen, ids)
        self.assertIsNone(cursor)
        self.assertEqual(self.client.get("/api/v1/sources?limit=501").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/sources?cursor=invalid").status_code, 400)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/sources").status_code, 401)

    def test_pause_expiry_and_corruption_never_open_capture(self):
        source = self.create()
        self.client.patch("/api/v1/sources/" + source, json={"revision": 1, "paused": False}, headers=self.owner)
        policy = {"version": 1, "paused": False, "ttl": 600, "allowed": [source], "denied": [],
                  "grants": [{"source": source, "scope": "metadata"}]}
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", json=policy, headers=self.owner).status_code, 200)
        with patch("personalcontext.sources.config_http.time.time", return_value=int(time.time()) + 601):
            data = self.client.get("/api/v1/device/config", headers=self.bearer).json()
        self.assertTrue(data["paused"])
        self.assertFalse(data["collection_enabled"])
        self.assertEqual(data["sources"][0]["scopes"], [])
        self.client.app.state.capture_latch.pause()
        self.assertTrue(self.client.get("/api/v1/device/config", headers=self.bearer).json()["paused"])
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE sources SET kind='synthetic-private-marker'")
        response = self.client.get("/api/v1/device/config", headers=self.bearer)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("synthetic-private-marker", response.text)
