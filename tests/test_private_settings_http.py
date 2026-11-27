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
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import PrivateCandidate
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic settings password"


class PrivateSettingsHttpTests(unittest.TestCase):
    def test_owner_csrf_revision_and_no_secret_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            app = create_app(path)
            with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
                origin = {"Origin": ORIGIN}
                self.assertEqual(client.get("/api/v1/network/private/config").status_code, 401)
                client.post("/api/v1/auth/bootstrap", headers=origin, json={"code": code, "password": CANDIDATE})
                csrf = client.post("/api/v1/auth/login", headers=origin, json={"password": CANDIDATE}).json()["csrf"]
                body = {"revision": 0, "address": "192.168.7.2", "hostname": "pc.example.test", "port": 18443,
                        "peers": ["192.168.7.0/24"], "cert": "cert.pem", "key": "key.pem", "passphrase": "synthetic-pass"}
                boundary = PrivateBoundary.create(body["address"], body["hostname"], body["port"], body["peers"])
                prepared = PrivateCandidate(boundary, "cert.pem", "key.pem", b"synthetic-protected")
                with patch("personalcontext.network.settings_http.prepare_candidate", return_value=prepared) as prepare:
                    self.assertEqual(client.post("/api/v1/network/private/config", headers=origin, json=body).status_code, 403)
                    prepare.assert_not_called()
                    response = client.post("/api/v1/network/private/config", headers={**origin, "X-CSRF-Token": csrf}, json=body)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {"revision": 1, "enabled": False})
                    self.assertNotIn("synthetic-pass", response.text)
                    self.assertEqual(client.post("/api/v1/network/private/config", headers={**origin, "X-CSRF-Token": csrf}, json=body).status_code, 409)
                status = client.get("/api/v1/network/private/config")
                self.assertEqual(status.json(), {"configured": True, "revision": 1, "enabled": False,
                                                 "settings": {key: value for key, value in body.items()
                                                              if key not in ("revision", "passphrase")}})
                self.assertNotIn("synthetic-protected", status.text)

    def test_revoked_session_cannot_commit_after_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            app = create_app(path)
            with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
                origin = {"Origin": ORIGIN}
                client.post("/api/v1/auth/bootstrap", headers=origin, json={"code": code, "password": CANDIDATE})
                csrf = client.post("/api/v1/auth/login", headers=origin, json={"password": CANDIDATE}).json()["csrf"]
                boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
                candidate = PrivateCandidate(boundary, "cert.pem", "key.pem", b"synthetic-protected")

                def revoke_during_preflight(_root, _body):
                    with closing(sqlite3.connect(path)) as connection:
                        connection.execute("DELETE FROM owner_sessions")
                        connection.commit()
                    return candidate

                with patch("personalcontext.network.settings_http.prepare_candidate", side_effect=revoke_during_preflight):
                    response = client.post("/api/v1/network/private/config", headers={**origin, "X-CSRF-Token": csrf},
                                           json={"revision": 0})
                self.assertEqual(response.status_code, 403)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM private_network_candidate").fetchone()[0], 0)
