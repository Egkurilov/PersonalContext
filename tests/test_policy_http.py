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
CANDIDATE = "synthetic policy api owner"


class PolicyHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        with closing(sqlite3.connect(path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.origin = {"Origin": ORIGIN}
        self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=self.origin)
        self.csrf = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.origin).json()["csrf"]
        self.headers = {**self.origin, "X-CSRF-Token": self.csrf}
        self.draft = {"version": 1, "paused": False, "ttl": 600, "allowed": ["synthetic-source"],
                      "denied": [], "grants": [{"source": "synthetic-source", "scope": "metadata"}]}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_owner_policy_update_stale_revision_and_pause(self):
        current = self.client.get("/api/v1/privacy/policy")
        self.assertEqual(current.status_code, 200)
        self.assertTrue(current.json()["paused"])
        self.assertTrue(current.json()["effective_paused"])
        self.assertEqual(current.json()["version"], 1)
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.origin).status_code, 403)
        self.assertEqual(self.client.patch(path, json=self.draft, headers={"X-CSRF-Token": self.csrf}).status_code, 403)
        updated = self.client.patch(path, json=self.draft, headers=self.headers)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["version"], 2)
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/privacy/pause", headers=self.headers).status_code, 204)
        current = self.client.get(path).json()
        self.assertTrue(current["paused"])
        self.assertTrue(current["effective_paused"])
        self.assertEqual(current["version"], 3)

    def test_invalid_and_unauthenticated_requests_fail_closed(self):
        path = "/api/v1/privacy/policy"
        bad = {**self.draft, "ttl": 86401}
        self.assertEqual(self.client.patch(path, json=bad, headers=self.headers).status_code, 400)
        bad = {**self.draft, "grants": [{"source": "synthetic-source", "scope": "unknown"}]}
        self.assertEqual(self.client.patch(path, json=bad, headers=self.headers).status_code, 400)
        response = self.client.patch(path, content='{"version":1,"version":2}',
                                     headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(path, json={**self.draft, "allowed": ["x" * 66000]}, headers=self.headers)
        self.assertEqual(response.status_code, 413)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/privacy/pause", headers=self.headers).status_code, 403)

    def test_local_latch_requires_explicit_owner_resume(self):
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 200)
        self.assertFalse(self.client.get(path).json()["local_paused"])
        self.client.app.state.capture_latch.pause()
        current = self.client.get(path).json()
        self.assertFalse(current["paused"])
        self.assertTrue(current["effective_paused"])
        self.assertTrue(current["local_paused"])
        response = self.client.patch(path, json={**self.draft, "version": 2}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get(path).json()["local_paused"])

    def test_pause_during_policy_commit_cannot_be_undone_by_inflight_resume(self):
        from personalcontext.privacy.policy_store import save_policy

        def pause_during_save(connection, *args, **kwargs):
            result = save_policy(connection, *args, **kwargs)
            self.client.app.state.capture_latch.pause()
            return result

        with patch("personalcontext.privacy.http_routes.save_policy", side_effect=pause_during_save):
            response = self.client.patch("/api/v1/privacy/policy", json=self.draft, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["local_paused"])
        self.assertTrue(self.client.get("/api/v1/privacy/policy").json()["effective_paused"])

    def test_api_pause_stops_locally_when_audit_write_fails(self):
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 200)
        with patch("personalcontext.privacy.policy_pause.record_audit", side_effect=sqlite3.OperationalError("synthetic")):
            result = self.client.post("/api/v1/privacy/pause", headers=self.headers)
        self.assertEqual(result.status_code, 503)
        policy = self.client.get(path).json()
        self.assertFalse(policy["paused"])
        self.assertTrue(policy["local_paused"])
        self.assertTrue(policy["effective_paused"])

    def test_storage_failure_on_active_policy_forces_local_pause(self):
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 200)
        with patch("personalcontext.privacy.policy_store.record_audit", side_effect=sqlite3.OperationalError("synthetic")):
            response = self.client.patch(path, json={**self.draft, "version": 2}, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(self.client.app.state.capture_latch.is_paused())
