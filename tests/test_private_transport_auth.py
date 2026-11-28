import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.transport import ScopedTransport
from personalcontext.storage.initialize import initialize_database

LOCAL = "http://127.0.0.1:17890"
REMOTE = "https://pc.example.test:18443"
CANDIDATE = "synthetic remote owner"


class PrivateTransportAuthTests(unittest.TestCase):
    def test_default_https_port_uses_canonical_browser_host_and_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            app = create_app(path)
            with TestClient(app, base_url=LOCAL, client=("127.0.0.1", 1)) as local:
                self.assertEqual(local.post("/api/v1/auth/bootstrap", headers={"Origin": LOCAL},
                                            json={"code": code, "password": CANDIDATE}).status_code, 204)
            boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 443, ["192.168.7.0/24"])
            with TestClient(ScopedTransport(app, boundary), base_url="https://pc.example.test", client=("192.168.7.9", 1)) as remote:
                result = remote.post("/api/v1/auth/login", headers={"Origin": "https://pc.example.test"},
                                     json={"password": CANDIDATE})
                self.assertEqual(result.status_code, 200)
                self.assertIn("Secure", result.headers["set-cookie"])

    def test_remote_auth_requires_private_boundary_and_secure_cookie(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            app = create_app(path)
            with TestClient(app, base_url=LOCAL, client=("127.0.0.1", 1)) as local:
                response = local.post("/api/v1/auth/bootstrap", headers={"Origin": LOCAL},
                                      json={"code": code, "password": CANDIDATE})
                self.assertEqual(response.status_code, 204)
            boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
            transport = ScopedTransport(app, boundary)
            with TestClient(transport, base_url=REMOTE, client=("192.168.7.9", 1)) as remote:
                self.assertEqual(remote.get("/api/v1/auth/me").status_code, 401)
                response = remote.post("/api/v1/auth/login", headers={"Origin": REMOTE}, json={"password": CANDIDATE})
                self.assertEqual(response.status_code, 200)
                self.assertIn("Secure", response.headers["set-cookie"])
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn("SameSite=strict", response.headers["set-cookie"])
                csrf = response.json()["csrf"]
                self.assertEqual(remote.get("/api/v1/auth/me").status_code, 200)
                self.assertEqual(remote.get("/api/v1/network/private/config").status_code, 403)
                self.assertEqual(remote.post("/api/v1/network/private/config",
                                             headers={"Origin": REMOTE, "X-CSRF-Token": csrf}, json={}).status_code, 403)
                self.assertEqual(remote.post("/api/v1/network/private/firewall/check",
                                             headers={"Origin": REMOTE, "X-CSRF-Token": csrf}).status_code, 403)
                self.assertEqual(remote.post("/api/v1/network/private/start", headers={"Origin": REMOTE, "X-CSRF-Token": csrf},
                                             json={"revision": 1}).status_code, 403)
                self.assertEqual(remote.post("/api/v1/network/private/stop", headers={"Origin": REMOTE, "X-CSRF-Token": csrf}).status_code, 403)
                self.assertEqual(remote.get("/api/v1/mcp/status").status_code, 403)
                self.assertEqual(remote.post("/api/v1/mcp/credentials", headers={"Origin": REMOTE, "X-CSRF-Token": csrf},
                                             json={"scope": "status:read"}).status_code, 403)
                self.assertEqual(remote.post("/api/v1/auth/rotate", headers={"Origin": LOCAL, "X-CSRF-Token": csrf}).status_code, 403)
                response = remote.post("/api/v1/auth/rotate", headers={"Origin": REMOTE, "X-CSRF-Token": csrf})
                self.assertEqual(response.status_code, 200)
                self.assertIn("Secure", response.headers["set-cookie"])
                self.assertNotIn("access-control-allow-origin", response.headers)
                csrf = response.json()["csrf"]
                self.assertEqual(remote.post("/api/v1/auth/bootstrap", headers={"Origin": REMOTE}, json={}).status_code, 403)
                response = remote.post("/api/v1/auth/logout", headers={"Origin": REMOTE, "X-CSRF-Token": csrf})
                self.assertEqual(response.status_code, 204)
                self.assertIn("Secure", response.headers["set-cookie"])
            with TestClient(transport, base_url=REMOTE, client=("192.168.8.9", 1)) as remote:
                self.assertEqual(remote.get("/healthz").status_code, 403)
            with TestClient(transport, base_url="http://pc.example.test:18443", client=("192.168.7.9", 1)) as remote:
                self.assertEqual(remote.get("/healthz").status_code, 403)
