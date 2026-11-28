"""Exercise the private listener lifecycle on a real same-host TLS socket."""

import http.client
import socket
import ssl
import time
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import test_private_listener_http as fixture
import test_private_owner_socket as socket_fixture
import test_tls_identity as tls_fixture

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import PrivateCandidate


@unittest.skipUnless(tls_fixture.openssl_path(), "Synthetic TLS certificate needs OpenSSL")
class PrivateListenerRealInterfaceTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown

    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_owner_start_and_firewall_failure_close_private_socket(self):
        address = socket_fixture.private_address()
        if address is None:
            self.skipTest("No eligible private IPv4 interface")
        with socket.socket() as probe:
            try:
                probe.bind((address, 0))
            except OSError:
                self.skipTest("Private IPv4 interface cannot be bound")
            port = probe.getsockname()[1]
        boundary = PrivateBoundary.create(address, "pc.example.test", port, [address + "/32"])
        candidate = PrivateCandidate(boundary, "cert.pem", "key.pem", b"synthetic-protected")
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        with patch("personalcontext.network.settings_http.prepare_candidate", return_value=candidate):
            self.assertEqual(self.client.post(fixture.ROOT + "/config", headers=owner, json={"revision": 0}).status_code, 200)
        identity = tls_fixture.TlsIdentityTests
        server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_tls.load_cert_chain(identity.cert, identity.key)
        client_tls = ssl.create_default_context(cafile=str(identity.cert))
        firewall = {"status": "restricted"}
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.monitor.firewall_status", side_effect=lambda *_: firewall["status"]),
              patch("personalcontext.network.listener.monitor.CHECK_INTERVAL", 0.05),
              patch("personalcontext.network.uvicorn_config.validated_tls_material",
                    return_value=nullcontext((identity.cert, identity.key))),
              patch("personalcontext.network.uvicorn_config.vault_server_context", return_value=server_tls)):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)
            try:
                status, _, _ = socket_fixture.request(address, port, client_tls, "GET", "/healthz")
                self.assertEqual(status, 200)
                origin = {"Origin": f"https://pc.example.test:{port}"}
                status, headers, _ = socket_fixture.request(address, port, client_tls, "POST", "/api/v1/auth/login",
                                                            origin, {"password": fixture.fixture.CANDIDATE})
                self.assertEqual(status, 200)
                self.assertIn("Secure", headers["set-cookie"])
                with (socket.create_connection((address, port), timeout=3) as raw,
                      client_tls.wrap_socket(raw, server_hostname="pc.example.test") as secured):
                    secured.sendall(f"GET /healthz HTTP/1.1\r\nHost: pc.example.test:{port}\r\n\r\n".encode())
                    response = http.client.HTTPResponse(secured)
                    response.begin()
                    self.assertEqual(response.status, 200)
                    response.read()
                    firewall["status"] = "not_restricted"
                    deadline = time.monotonic() + 5
                    while self.client.app.state.private_listener.active() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertFalse(self.client.app.state.private_listener.active())
                    secured.settimeout(3)
                    try:
                        remaining = secured.recv(1)
                    except (ConnectionResetError, ssl.SSLError):
                        remaining = b""
                    self.assertEqual(remaining, b"")
                with socket.socket() as probe:
                    probe.settimeout(1)
                    self.assertNotEqual(probe.connect_ex((address, port)), 0)
            finally:
                self.client.post(fixture.ROOT + "/stop", headers=owner)
