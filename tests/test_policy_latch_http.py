import asyncio
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing, suppress
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic pause owner"


class PolicyLatchHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        with closing(sqlite3.connect(path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.app = create_app(path)
        self.client = TestClient(self.app, base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.origin = {"Origin": ORIGIN}
        self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=self.origin)
        csrf = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.origin).json()["csrf"]
        self.headers = {**self.origin, "X-CSRF-Token": csrf}
        self.draft = {"version": 1, "paused": False, "ttl": 600, "allowed": ["synthetic-source"],
                      "denied": [], "grants": [{"source": "synthetic-source", "scope": "metadata"}]}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_restart_remains_paused_until_explicit_owner_action(self):
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", json=self.draft, headers=self.headers).status_code, 200)
        self.assertFalse(self.app.state.capture_latch.is_paused())
        self.client.__exit__(None, None, None)
        self.client = TestClient(self.app, base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.origin)
        policy = self.client.get("/api/v1/privacy/policy").json()
        self.assertFalse(policy["paused"])
        self.assertTrue(policy["local_paused"])
        self.assertTrue(policy["effective_paused"])

    def test_unauthenticated_pause_cannot_change_latch(self):
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", json=self.draft, headers=self.headers).status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/v1/privacy/pause", headers=self.headers).status_code, 403)
        self.assertFalse(self.app.state.capture_latch.is_paused())

    def test_paused_policy_update_stops_locally_even_if_database_write_fails(self):
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 200)
        paused = {**self.draft, "version": 2, "paused": True}
        with patch("personalcontext.privacy.policy_store.record_audit", side_effect=sqlite3.OperationalError("synthetic")):
            response = self.client.patch(path, json=paused, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(self.app.state.capture_latch.is_paused())
        self.assertTrue(self.client.get(path).json()["effective_paused"])

    def test_pause_during_request_body_cannot_be_undone_by_inflight_resume(self):
        from personalcontext.auth.http_input import read_json

        async def pause_after_read(request, limit):
            body = await read_json(request, limit)
            self.app.state.capture_latch.pause()
            return body

        with patch("personalcontext.privacy.http_routes.read_json", side_effect=pause_after_read):
            response = self.client.patch("/api/v1/privacy/policy", json=self.draft, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["local_paused"])
        self.assertTrue(self.app.state.capture_latch.is_paused())

    def test_stopped_scheduler_cannot_resume_capture(self):
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 200)

        async def stop_scheduler():
            self.app.state.scheduler.stopping.set()
            await asyncio.wait_for(self.app.state.scheduler.task, timeout=2)

        self.client.portal.call(stop_scheduler)
        self.assertTrue(self.app.state.capture_latch.is_paused())
        result = self.client.patch(path, json={**self.draft, "version": 2}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["local_paused"])
        self.assertEqual(self.client.get("/readyz").status_code, 503)

    def test_stopped_audit_cannot_resume_capture(self):
        path = "/api/v1/privacy/policy"
        self.assertEqual(self.client.patch(path, json=self.draft, headers=self.headers).status_code, 200)

        async def stop_audit():
            task = self.app.state.audit_housekeeping.task
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        self.client.portal.call(stop_audit)
        self.assertTrue(self.app.state.capture_latch.is_paused())
        result = self.client.patch(path, json={**self.draft, "version": 2}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["local_paused"])
        self.assertEqual(self.client.get("/readyz").status_code, 503)
