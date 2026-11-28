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
CANDIDATE = "synthetic audit api owner"


class AuditHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(self.path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.origin = {"Origin": ORIGIN}
        self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=self.origin)
        wrong = "wrong synthetic"
        self.client.post("/api/v1/auth/login", json={"password": wrong}, headers=self.origin)
        result = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.origin)
        self.assertEqual(result.status_code, 200)
        self.csrf = result.json()["csrf"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_owner_only_paginated_fixed_fields_and_denied_login(self):
        response = self.client.get("/api/v1/audit?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        first = response.json()
        self.assertEqual(first["events"][0]["event_type"], "owner_login")
        self.assertEqual(first["events"][0]["status"], "success")
        self.assertIsNone(first["events"][0]["target_id"])
        cursor = first["next_cursor"]
        second = self.client.get("/api/v1/audit", params={"limit": "1", "cursor": cursor}).json()
        self.assertEqual(second["events"][0]["status"], "denied")
        self.assertEqual(second["events"][0]["actor"], "anonymous")
        self.assertNotIn(CANDIDATE, response.text)
        self.assertEqual(self.client.get("/api/v1/audit?limit=101").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/audit?cursor=bad").status_code, 400)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/v1/audit").status_code, 401)

    def test_corrupt_row_fails_closed_without_echoing_data(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE security_audit SET event_type='synthetic-sensitive-value'")
        response = self.client.get("/api/v1/audit")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("synthetic-sensitive-value", response.text)

    def test_logout_and_rate_limited_enrollment_failures_are_audited(self):
        self.assertEqual(self.client.post("/api/v1/devices/enroll", json={"code": "invalid"}).status_code, 401)
        events = self.client.get("/api/v1/audit").json()["events"]
        self.assertTrue(any(item["event_type"] == "device_enroll" and item["status"] == "denied" for item in events))
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers={**self.origin, "X-CSRF-Token": self.csrf}).status_code, 204)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.origin).status_code, 200)
        events = self.client.get("/api/v1/audit").json()["events"]
        self.assertTrue(any(item["event_type"] == "owner_logout" and item["status"] == "success" for item in events))
