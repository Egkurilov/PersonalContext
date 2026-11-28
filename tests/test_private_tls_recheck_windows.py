"""Real Windows ACL and encrypted-key recheck using synthetic TLS material."""

import os
import shutil
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_tls_file_acl as acl_fixture
import test_tls_identity as tls_fixture

from personalcontext.app import create_app
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.tls_vault import seal_passphrase
from personalcontext.network.uvicorn_config import private_server_config


@unittest.skipUnless(sys.platform == "win32" and tls_fixture.openssl_path(), "Windows and OpenSSL required")
class WindowsTlsRecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_rejects_acl_change_after_valid_configuration(self):
        import win32con
        import win32security

        fixture = tls_fixture.TlsIdentityTests
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        with tempfile.TemporaryDirectory(dir=os.environ["LOCALAPPDATA"]) as directory:
            root = Path(directory) / "tls"
            root.mkdir()
            cert, key = root / "cert.pem", root / "key.pem"
            shutil.copyfile(fixture.cert, cert)
            shutil.copyfile(fixture.encrypted, key)
            acl_fixture.protect_fixture(root, cert, key)
            protected = seal_passphrase(b"synthetic-test-passphrase")
            create_default = ssl.create_default_context
            with patch("personalcontext.network.tls.ssl.create_default_context",
                       side_effect=lambda: create_default(cafile=str(fixture.cert))):
                app = create_app(Path(directory) / "context.db")
                config = private_server_config(app, boundary, cert, key, protected)
                config.load()
                self.assertEqual(config.ssl.minimum_version, ssl.TLSVersion.TLSv1_2)
                descriptor = win32security.GetNamedSecurityInfo(str(key), win32security.SE_FILE_OBJECT,
                                                                win32security.DACL_SECURITY_INFORMATION)
                acl = descriptor.GetSecurityDescriptorDacl()
                everyone = win32security.CreateWellKnownSid(win32security.WinWorldSid, None)
                acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_READ, everyone)
                try:
                    win32security.SetNamedSecurityInfo(str(key), win32security.SE_FILE_OBJECT,
                        win32security.DACL_SECURITY_INFORMATION, None, None, acl, None)
                    with self.assertRaises(ValueError):
                        private_server_config(app, boundary, cert, key, protected)
                finally:
                    acl_fixture.protect_fixture(root, cert, key)
                cert.write_text("synthetic invalid certificate", encoding="utf-8")
                with self.assertRaises(ValueError):
                    private_server_config(app, boundary, cert, key, protected)
