"""Synthetic owner/device/MCP credential separation and revocation."""

import sqlite3
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import test_device_http as fixture
from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.storage.restore_security import reset_restored_access

ISSUE = "/api/v1/mcp/credentials"
STATUS = "/api/v1/mcp/status"


class McpCredentialHttpTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def issue(self):
        return self.client.post(ISSUE, json={"scope": "status:read"},
                                headers={**self.headers, "X-CSRF-Token": self.csrf})

    def test_credential_is_owner_issued_read_only_and_revocable(self):
        self.assertEqual(self.client.post(ISSUE, json={"scope": "status:read"}, headers=self.headers).status_code, 403)
        self.assertEqual(self.client.get(STATUS).status_code, 401)
        issued = self.issue()
        self.assertEqual(issued.status_code, 200)
        credential = issued.json()
        self.assertEqual(credential["scope"], "status:read")
        self.assertEqual(credential["expires_in"], 900)
        self.assertEqual(issued.headers["cache-control"], "no-store")
        token = credential["token"]
        bearer = {"Authorization": "Bearer " + token}
        response = self.client.get(STATUS, headers=bearer)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"scope": "status:read", "status": "ready"})
        self.assertEqual(self.client.get(STATUS + "?extra=1", headers=bearer).status_code, 400)
        self.assertEqual(self.client.post(STATUS, headers=bearer).status_code, 405)
        with closing(sqlite3.connect(self.path)) as connection:
            for row in connection.execute("SELECT * FROM mcp_credentials"):
                self.assertNotIn(token, repr(row))
        for path in (self.path, self.path.with_name(self.path.name + "-wal")):
            if path.exists():
                self.assertNotIn(token.encode(), path.read_bytes())
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        self.assertEqual(self.client.post(ISSUE + "/" + credential["id"] + "/revoke", headers=owner).status_code, 204)
        self.assertEqual(self.client.get(STATUS, headers=bearer).status_code, 401)

    def test_owner_session_and_device_token_are_not_mcp_credentials(self):
        self.assertEqual(self.client.get(STATUS).status_code, 401)
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        pairing = self.client.post("/api/v1/devices/pairing-codes", json={"scopes": "config"}, headers=owner).json()["code"]
        device = self.client.post("/api/v1/devices/enroll", json={"code": pairing}).json()
        self.assertEqual(self.client.get(STATUS, headers={"Authorization": "Bearer " + device["token"]}).status_code, 401)
        token = self.issue().json()["token"]
        response = self.client.get("/api/v1/device/config", headers={"Authorization": "Bearer " + token,
                                                                    "X-Device-Id": device["device_id"]})
        self.assertEqual(response.status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(self.client.post(ISSUE, json={"scope": "status:read"},
                                          headers={**owner, "Authorization": "Bearer " + token}).status_code, 403)

    def test_unknown_scopes_are_denied(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        for scope in ("write", "owner", "read:all", "", "status:read,status:write"):
            self.assertEqual(self.client.post(ISSUE, json={"scope": scope}, headers=owner).status_code, 400)

    def test_expiry_and_clock_rewind_cannot_reactivate_a_token(self):
        token = self.issue().json()["token"]
        bearer = {"Authorization": "Bearer " + token}
        now = int(time.time())
        with patch("personalcontext.mcp_auth.http.time.time", return_value=now + 901):
            self.assertEqual(self.client.get(STATUS, headers=bearer).status_code, 401)
        self.assertEqual(self.client.get(STATUS, headers=bearer).status_code, 401)

    def test_restore_discards_tokens_and_audit_never_contains_them(self):
        token = self.issue().json()["token"]
        audit = self.client.get("/api/v1/audit")
        self.assertIn("mcp_issue", audit.text)
        self.assertNotIn(token, audit.text)
        with closing(sqlite3.connect(self.path)) as connection:
            reset_restored_access(connection)
            self.assertEqual(connection.execute("SELECT count(*) FROM mcp_credentials").fetchone()[0], 0)
            connection.commit()
        self.assertEqual(self.client.get(STATUS, headers={"Authorization": "Bearer " + token}).status_code, 401)

    def test_short_lived_credential_survives_normal_process_restart(self):
        token = self.issue().json()["token"]
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.path), base_url=fixture.ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.assertEqual(self.client.get(STATUS, headers={"Authorization": "Bearer " + token}).status_code, 200)
