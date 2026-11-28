"""Windows private-listener integration with synthetic certificates and real DPAPI/ACLs."""

import os
import shutil
import socket
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_private_listener_http as fixture
import test_private_owner_socket as socket_fixture
import test_tls_file_acl as acl_fixture
import test_tls_identity as tls_fixture


@unittest.skipUnless(sys.platform == "win32" and tls_fixture.openssl_path(), "Windows and OpenSSL required")
class WindowsPrivateListenerMaterialTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown

    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_start_revalidates_material_and_serves_real_tls(self):
        import win32con
        import win32security

        address = socket_fixture.private_address()
        if address is None:
            self.skipTest("No eligible private IPv4 interface")
        with socket.socket() as probe:
            try:
                probe.bind((address, 0))
            except OSError:
                self.skipTest("Private IPv4 interface cannot be bound")
            port = probe.getsockname()[1]
        identity = tls_fixture.TlsIdentityTests
        client_tls = ssl.create_default_context(cafile=str(identity.cert))
        create_default = ssl.create_default_context
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        with tempfile.TemporaryDirectory(dir=os.environ["LOCALAPPDATA"]) as directory:
            parent = Path(directory)
            root = parent / "tls"
            root.mkdir()
            cert, key = root / "cert.pem", root / "key.pem"
            shutil.copyfile(identity.cert, cert)
            shutil.copyfile(identity.encrypted, key)
            acl_fixture.protect_fixture(parent, root, cert, key)
            self.client.app.state.private_tls_dir = root
            self.client.app.state.private_listener.tls_dir = root
            settings = {"revision": 0, "address": address, "hostname": "pc.example.test", "port": port,
                        "peers": [address + "/32"], "cert": "cert.pem", "key": "key.pem",
                        "passphrase": "synthetic-test-passphrase"}
            with (patch("personalcontext.network.tls.ssl.create_default_context",
                        side_effect=lambda: create_default(cafile=str(identity.cert))),
                  patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
                  patch("personalcontext.network.listener.monitor.firewall_status", return_value="restricted")):
                self.assertEqual(self.client.post(fixture.ROOT + "/config", headers=owner, json=settings).status_code, 200)
                descriptor = win32security.GetNamedSecurityInfo(str(key), win32security.SE_FILE_OBJECT,
                                                                win32security.DACL_SECURITY_INFORMATION)
                acl = descriptor.GetSecurityDescriptorDacl()
                everyone = win32security.CreateWellKnownSid(win32security.WinWorldSid, None)
                acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_READ, everyone)
                win32security.SetNamedSecurityInfo(str(key), win32security.SE_FILE_OBJECT,
                    win32security.DACL_SECURITY_INFORMATION, None, None, acl, None)
                try:
                    self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 503)
                finally:
                    acl_fixture.protect_fixture(key)
                self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)
                try:
                    untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        socket_fixture.request(address, port, untrusted, "GET", "/healthz")
                    status, _, _ = socket_fixture.request(address, port, client_tls, "GET", "/healthz")
                    self.assertEqual(status, 200)
                    origin = {"Origin": f"https://pc.example.test:{port}"}
                    status, headers, _ = socket_fixture.request(address, port, client_tls, "POST", "/api/v1/auth/login",
                                                                origin, {"password": fixture.fixture.CANDIDATE})
                    self.assertEqual(status, 200)
                    self.assertIn("Secure", headers["set-cookie"])
                finally:
                    self.assertEqual(self.client.post(fixture.ROOT + "/stop", headers=owner).status_code, 204)
