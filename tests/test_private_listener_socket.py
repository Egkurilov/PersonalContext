"""Real local TLS socket driven by the private listener lifecycle."""

import socket
import ssl
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import test_private_listener_http as fixture
import test_tls_identity as tls_fixture


@unittest.skipUnless(tls_fixture.openssl_path(), "Synthetic TLS certificate needs OpenSSL")
class PrivateListenerSocketTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown
    configured = fixture.PrivateListenerHttpTests.configured

    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_real_tls_rejects_unlisted_peer_and_stops(self):
        owner, _ = self.configured()
        fixture_tls = tls_fixture.TlsIdentityTests
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(fixture_tls.cert, fixture_tls.key)
        ports = []

        def bind_loopback(_boundary):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.setblocking(False)
            ports.append(listener.getsockname()[1])
            return listener

        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.bind_listener", side_effect=bind_loopback),
              patch("personalcontext.network.uvicorn_config.validated_tls_material",
                    return_value=nullcontext((fixture_tls.cert, fixture_tls.key))),
              patch("personalcontext.network.uvicorn_config.vault_server_context", return_value=context)):
            response = self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1})
            self.assertEqual(response.status_code, 200)
            client = ssl.create_default_context(cafile=str(fixture_tls.cert))
            with (socket.create_connection(("127.0.0.1", ports[0]), timeout=3) as raw,
                  client.wrap_socket(raw, server_hostname="pc.example.test") as secured):
                secured.sendall(b"GET /healthz HTTP/1.1\r\nHost: pc.example.test:18443\r\nConnection: close\r\n\r\n")
                self.assertIn(b" 403 ", secured.recv(1024))
            with socket.create_connection(("127.0.0.1", ports[0]), timeout=3) as raw:
                raw.sendall(b"GET /healthz HTTP/1.1\r\nHost: pc.example.test:18443\r\n\r\n")
                try:
                    plaintext = raw.recv(1024)
                except ConnectionResetError:
                    plaintext = b""
                self.assertNotIn(b"HTTP/1.1 200", plaintext)
            self.assertEqual(self.client.post(fixture.ROOT + "/stop", headers=owner).status_code, 204)
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", ports[0])), 0)
