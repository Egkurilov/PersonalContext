import shutil
import sqlite3
import ssl
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import test_tls_identity as tls_fixture
from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.network.settings_prepare import prepare_candidate
from personalcontext.network.tls_vault import open_passphrase
from personalcontext.storage.initialize import initialize_database


@unittest.skipUnless(sys.platform == "win32" and tls_fixture.openssl_path(), "Windows DPAPI and OpenSSL required")
class PrivateSettingsPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_encrypted_key_and_trusted_certificate_are_required(self):
        fixture = tls_fixture.TlsIdentityTests
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tls"
            root.mkdir()
            shutil.copyfile(fixture.cert, root / "cert.pem")
            shutil.copyfile(fixture.encrypted, root / "key.pem")
            shutil.copyfile(fixture.key, root / "plain.pem")
            body = {"revision": 0, "address": "192.168.7.2", "hostname": "pc.example.test", "port": 18443,
                    "peers": ["192.168.7.0/24"], "cert": "cert.pem", "key": "key.pem",
                    "passphrase": "synthetic-test-passphrase"}
            create_default = ssl.create_default_context
            with patch("personalcontext.network.tls.ssl.create_default_context",
                       side_effect=lambda: create_default(cafile=str(fixture.cert))):
                candidate = prepare_candidate(root, body)
                self.assertEqual(open_passphrase(candidate.protected), b"synthetic-test-passphrase")
                self.assertNotIn("synthetic-test-passphrase", repr(candidate))
                for change in ({"key": "plain.pem"}, {"hostname": "other.example.test"}, {"cert": "../cert.pem"},
                               {"passphrase": "short"}):
                    with self.subTest(kind=tuple(change)), self.assertRaisesRegex(ValueError, "Private TLS settings unavailable"):
                        prepare_candidate(root, {**body, **change})

    def test_real_owner_api_protects_secret_and_does_not_enable_listener(self):
        fixture = tls_fixture.TlsIdentityTests
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tls_dir = root / "tls"
            tls_dir.mkdir()
            shutil.copyfile(fixture.cert, tls_dir / "cert.pem")
            shutil.copyfile(fixture.encrypted, tls_dir / "key.pem")
            path = root / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            origin = "http://127.0.0.1:17890"
            body = {"revision": 0, "address": "192.168.7.2", "hostname": "pc.example.test", "port": 18443,
                    "peers": ["192.168.7.0/24"], "cert": "cert.pem", "key": "key.pem",
                    "passphrase": "synthetic-test-passphrase"}
            create_default = ssl.create_default_context
            candidate = "synthetic owner credential"
            with (TestClient(create_app(path), base_url=origin, client=("127.0.0.1", 1)) as client,
                  patch("personalcontext.network.tls.ssl.create_default_context",
                        side_effect=lambda: create_default(cafile=str(fixture.cert)))):
                client.post("/api/v1/auth/bootstrap", headers={"Origin": origin},
                            json={"code": code, "password": candidate})
                csrf = client.post("/api/v1/auth/login", headers={"Origin": origin},
                                   json={"password": candidate}).json()["csrf"]
                response = client.post("/api/v1/network/private/config", headers={"Origin": origin, "X-CSRF-Token": csrf}, json=body)
                self.assertEqual(response.json(), {"revision": 1, "enabled": False})
                self.assertNotIn(body["passphrase"], response.text)
                for file in (path, path.with_name(path.name + "-wal")):
                    if file.exists() and body["passphrase"].encode() in file.read_bytes():
                        self.fail("Passphrase persisted without DPAPI")
