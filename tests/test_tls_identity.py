import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personalcontext.network.tls import trusted_server_context, vault_server_context
from personalcontext.network.tls_vault import seal_passphrase


def openssl_path():
    candidate = shutil.which("openssl")
    if candidate:
        return candidate
    return next((str(path) for path in (Path(os.environ.get("ProgramFiles", "")) / "Git/usr/bin/openssl.exe",
                                        Path(os.environ.get("ProgramFiles", "")) / "Git/mingw64/bin/openssl.exe")
                 if path.is_file()), None)


@unittest.skipUnless(openssl_path(), "OpenSSL executable required for synthetic TLS certificates")
class TlsIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        cls.cert, cls.key, cls.other_key = root / "cert.pem", root / "key.pem", root / "other.pem"
        cls.encrypted = root / "encrypted.pem"
        cls.no_san = root / "no-san.pem"
        tool = openssl_path()
        subprocess.run([tool, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=pc.example.test", "-addext", "subjectAltName=DNS:pc.example.test",
                        "-addext", "extendedKeyUsage=serverAuth", "-keyout", str(cls.key), "-out", str(cls.cert)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        subprocess.run([tool, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(cls.other_key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        subprocess.run([tool, "pkey", "-in", str(cls.key), "-aes-256-cbc", "-passout", "pass:synthetic-test-passphrase",
                        "-out", str(cls.encrypted)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        subprocess.run([tool, "req", "-x509", "-new", "-key", str(cls.key), "-days", "1", "-subj",
                        "/CN=pc.example.test", "-out", str(cls.no_san)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_trusted_identity_and_key_work_without_network(self):
        create_default = ssl.create_default_context
        with patch("personalcontext.network.tls.ssl.create_default_context",
                   side_effect=lambda: create_default(cafile=str(self.cert))):
            context = trusted_server_context(self.cert, self.key, "pc.example.test")
            encrypted = trusted_server_context(self.cert, self.encrypted, "pc.example.test", b"synthetic-test-passphrase")
            with self.assertRaisesRegex(ValueError, "TLS configuration unavailable"):
                trusted_server_context(self.cert, self.encrypted, "pc.example.test", b"wrong")
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(encrypted.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_untrusted_wrong_hostname_or_wrong_key_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "TLS configuration unavailable"):
            trusted_server_context(self.cert, self.key, "pc.example.test")
        create_default = ssl.create_default_context
        with patch("personalcontext.network.tls.ssl.create_default_context",
                   side_effect=lambda: create_default(cafile=str(self.cert))):
            with self.assertRaisesRegex(ValueError, "TLS configuration unavailable"):
                trusted_server_context(self.cert, self.key, "other.example.test")
            with self.assertRaisesRegex(ValueError, "TLS configuration unavailable"):
                trusted_server_context(self.cert, self.other_key, "pc.example.test")
        with (patch("personalcontext.network.tls.ssl.create_default_context",
                    side_effect=lambda: create_default(cafile=str(self.no_san))),
              self.assertRaisesRegex(ValueError, "TLS configuration unavailable")):
            trusted_server_context(self.no_san, self.key, "pc.example.test")

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI is required")
    def test_user_bound_passphrase_opens_encrypted_key_for_tls(self):
        sealed = seal_passphrase(b"synthetic-test-passphrase")
        create_default = ssl.create_default_context
        with patch("personalcontext.network.tls.ssl.create_default_context",
                   side_effect=lambda: create_default(cafile=str(self.cert))):
            context = vault_server_context(self.cert, self.encrypted, "pc.example.test", sealed)
            with self.assertRaisesRegex(ValueError, "TLS configuration unavailable"):
                vault_server_context(self.cert, self.key, "pc.example.test", sealed)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
