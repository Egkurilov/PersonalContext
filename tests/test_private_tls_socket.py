import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import test_tls_identity as tls_fixture
import uvicorn

from personalcontext.app import create_app
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.tls_vault import seal_passphrase
from personalcontext.network.uvicorn_config import private_server_config


@unittest.skipUnless(tls_fixture.openssl_path(), "OpenSSL executable required for synthetic TLS certificates")
class PrivateTlsSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_tls_socket_rejects_loopback_peer_spoofing_and_plaintext(self):
        fixture = tls_fixture.TlsIdentityTests
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(fixture.cert, fixture.key)
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(10)
            port = listener.getsockname()[1]
            app = create_app(Path(directory) / "context.db")
            with (patch("personalcontext.network.uvicorn_config.validated_tls_material",
                        return_value=nullcontext((fixture.cert, fixture.key))),
                  patch("personalcontext.network.uvicorn_config.vault_server_context", return_value=context) as verify):
                config = private_server_config(app, boundary, fixture.cert, fixture.key, b"synthetic")
            verify.assert_called_once_with(fixture.cert, fixture.key, boundary.hostname, b"synthetic")
            server = uvicorn.Server(config)
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(server.started)
                client = ssl.create_default_context(cafile=str(fixture.cert))
                with (socket.create_connection(("127.0.0.1", port), timeout=3) as raw,
                      client.wrap_socket(raw, server_hostname="pc.example.test") as secured):
                    secured.sendall(b"GET /healthz HTTP/1.1\r\nHost: pc.example.test:18443\r\n"
                                    b"X-Forwarded-For: 192.168.7.9\r\nConnection: close\r\n\r\n")
                    self.assertIn(b" 403 ", secured.recv(1024))
                with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
                    raw.sendall(b"GET /healthz HTTP/1.1\r\nHost: pc.example.test:18443\r\n\r\n")
                    try:
                        response = raw.recv(1024)
                    except ConnectionResetError:
                        response = b""
                    self.assertNotIn(b"HTTP/1.1 200", response)
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())

    def test_client_only_context_cannot_configure_server(self):
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with (tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError),
              patch("personalcontext.network.uvicorn_config.validated_tls_material",
                    return_value=nullcontext((Path("synthetic-cert"), Path("synthetic-key")))),
              patch("personalcontext.network.uvicorn_config.vault_server_context", return_value=context)):
            private_server_config(create_app(Path(directory) / "context.db"), boundary,
                                  Path("synthetic-cert"), Path("synthetic-key"), b"synthetic")

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI is required")
    def test_config_uses_dpapi_key_and_trust_check(self):
        fixture = tls_fixture.TlsIdentityTests
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        protected = seal_passphrase(b"synthetic-test-passphrase")
        create_default = ssl.create_default_context
        with (tempfile.TemporaryDirectory() as directory,
              patch("personalcontext.network.uvicorn_config.validated_tls_material",
                    return_value=nullcontext((fixture.cert, fixture.encrypted))),
              patch("personalcontext.network.tls.ssl.create_default_context",
                    side_effect=lambda: create_default(cafile=str(fixture.cert)))):
            config = private_server_config(create_app(Path(directory) / "context.db"), boundary,
                                           fixture.cert, fixture.encrypted, protected)
            config.load()
            self.assertTrue(config.is_ssl)
            self.assertFalse(config.proxy_headers)
            self.assertFalse(config.access_log)
            self.assertEqual(config.ssl.minimum_version, ssl.TLSVersion.TLSv1_2)
