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
CANDIDATE = "synthetic owner password"


class AuthHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            self.code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(self.path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def post(self, path, body, **kwargs):
        return self.client.post(path, json=body, headers={"Origin": ORIGIN, **kwargs})

    def bootstrap(self):
        return self.post("/api/v1/auth/bootstrap", {"code": self.code, "password": CANDIDATE})

    def login(self):
        return self.post("/api/v1/auth/login", {"password": CANDIDATE})

    def test_bootstrap_login_me_and_csrf_logout(self):
        self.assertEqual(self.bootstrap().status_code, 204)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertNotIn("Secure", cookie)
        session = self.client.cookies.get("pc_session")
        self.assertNotIn(session, response.text)
        csrf = response.json()["csrf"]
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)
        self.assertEqual(self.post("/api/v1/auth/logout", {}).status_code, 403)
        self.assertEqual(self.post("/api/v1/auth/logout", {}, **{"X-CSRF-Token": csrf}).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.client.cookies.set("pc_session", session, domain="127.0.0.1", path="/")
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

    def test_mutations_require_origin_and_do_not_echo_credentials(self):
        body = {"code": self.code, "password": CANDIDATE}
        self.assertEqual(self.client.post("/api/v1/auth/bootstrap", json=body).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/auth/bootstrap", json=body,
                                          headers={"Origin": "http://attacker.example"}).status_code, 403)
        response = self.post("/api/v1/auth/bootstrap", {"code": self.code, "password": 123})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(self.code, response.text)
        self.assertEqual(self.bootstrap().status_code, 204)
        response = self.post("/api/v1/auth/login", {"password": "synthetic incorrect password"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("synthetic incorrect password", response.text)

    def test_request_limits_and_session_cannot_authenticate_without_cookie(self):
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.post("/api/v1/auth/login", {"password": "x" * 5000}).status_code, 413)
        self.assertEqual(self.client.post("/api/v1/auth/login", content="not json",
                                          headers={"Origin": ORIGIN}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/auth/login", content='{"password":"x","password":"y"}',
                                          headers={"Origin": ORIGIN, "Content-Type": "application/json"}).status_code, 400)

    def test_login_rate_limit_is_applied_before_authentication(self):
        self.assertEqual(self.bootstrap().status_code, 204)
        wrong = "wrong synthetic"
        for _ in range(5):
            self.assertEqual(self.post("/api/v1/auth/login", {"password": wrong}).status_code, 401)
        response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)

    def test_duplicate_origin_and_host_are_rejected(self):
        response = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE},
                                    headers=[("Origin", ORIGIN), ("Origin", ORIGIN)])
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/api/v1/auth/me", headers=[("Host", "127.0.0.1:17890"),
                                                               ("Host", "attacker.example")])
        self.assertEqual(response.status_code, 400)

    def test_csrf_refresh_requires_origin_and_active_session(self):
        self.assertEqual(self.post("/api/v1/auth/csrf", {}).status_code, 401)
        self.assertEqual(self.bootstrap().status_code, 204)
        old = self.login().json()["csrf"]
        self.assertEqual(self.client.post("/api/v1/auth/csrf").status_code, 403)
        refreshed = self.post("/api/v1/auth/csrf", {})
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.headers["cache-control"], "no-store")
        current = refreshed.json()["csrf"]
        if old == current:
            self.fail("CSRF rotation reused a token")
        self.assertEqual(self.post("/api/v1/auth/logout", {}, **{"X-CSRF-Token": old}).status_code, 403)
        self.assertEqual(self.post("/api/v1/auth/logout", {}, **{"X-CSRF-Token": current}).status_code, 204)
        self.assertEqual(self.post("/api/v1/auth/csrf", {}).status_code, 401)
