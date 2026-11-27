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
CANDIDATE = "synthetic rotation password"


class SessionRotationHttpTests(unittest.TestCase):
    def test_rotation_requires_session_origin_and_csrf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            with TestClient(create_app(path), base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
                origin = {"Origin": ORIGIN}
                self.assertEqual(client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=origin).status_code, 204)
                csrf = client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=origin).json()["csrf"]
                old = client.cookies.get("pc_session")
                self.assertEqual(client.post("/api/v1/auth/rotate", headers={"X-CSRF-Token": csrf}).status_code, 403)
                self.assertEqual(client.post("/api/v1/auth/rotate", headers=origin).status_code, 403)
                response = client.post("/api/v1/auth/rotate", headers={**origin, "X-CSRF-Token": csrf})
                self.assertEqual(response.status_code, 200)
                new = client.cookies.get("pc_session")
                self.assertNotEqual(old, new)
                self.assertNotEqual(csrf, response.json()["csrf"])
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn("SameSite=strict", response.headers["set-cookie"])
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(client.get("/api/v1/auth/me").status_code, 200)
                client.cookies.set("pc_session", old, domain="127.0.0.1", path="/")
                self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
