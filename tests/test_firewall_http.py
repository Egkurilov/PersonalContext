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
CANDIDATE = "synthetic firewall owner"


class FirewallHttpTests(unittest.TestCase):
    def test_local_owner_check_is_bounded_and_never_enables_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            with TestClient(create_app(path), base_url=ORIGIN, client=("127.0.0.1", 1)) as client:
                origin = {"Origin": ORIGIN}
                self.assertEqual(client.post("/api/v1/network/private/firewall/check", headers=origin).status_code, 403)
                client.post("/api/v1/auth/bootstrap", headers=origin, json={"code": code, "password": CANDIDATE})
                csrf = client.post("/api/v1/auth/login", headers=origin, json={"password": CANDIDATE}).json()["csrf"]
                owner = {**origin, "X-CSRF-Token": csrf}
                self.assertEqual(client.post("/api/v1/network/private/firewall/check", headers=owner).status_code, 404)
                boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
                item = PrivateCandidate(boundary, "cert.pem", "key.pem", b"synthetic-protected")
                with patch("personalcontext.network.settings_http.prepare_candidate", return_value=item):
                    self.assertEqual(client.post("/api/v1/network/private/config", headers=owner, json={"revision": 0}).status_code, 200)
                with patch("personalcontext.network.firewall.http.firewall_status", return_value="restricted") as check:
                    self.assertEqual(client.post("/api/v1/network/private/firewall/check", headers=origin).status_code, 403)
                    check.assert_not_called()
                    response = client.post("/api/v1/network/private/firewall/check", headers=owner)
                    self.assertEqual(response.json(), {"firewall": "restricted", "enabled": False})
                    self.assertEqual(response.headers["cache-control"], "no-store")

                def change_during_check(_boundary, _executable):
                    with closing(sqlite3.connect(path)) as connection:
                        connection.execute("UPDATE private_network_candidate SET revision=revision+1")
                        connection.commit()
                    return "restricted"

                with patch("personalcontext.network.firewall.http.firewall_status", side_effect=change_during_check):
                    self.assertEqual(client.post("/api/v1/network/private/firewall/check", headers=owner).status_code, 409)
