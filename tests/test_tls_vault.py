import sys
import unittest

from personalcontext.network.tls_vault import open_passphrase, seal_passphrase


@unittest.skipUnless(sys.platform == "win32", "Windows DPAPI is required")
class TlsVaultTests(unittest.TestCase):
    def test_user_bound_round_trip_and_tamper_rejection(self):
        secret = b"synthetic private key passphrase"
        sealed = seal_passphrase(secret)
        self.assertNotIn(secret, sealed)
        self.assertEqual(open_passphrase(sealed), secret)
        altered = bytearray(sealed)
        altered[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "TLS secret unavailable"):
            open_passphrase(bytes(altered))

    def test_invalid_secret_and_other_dpapi_purpose_are_rejected(self):
        import win32crypt

        for value in (b"", b"x" * 1025, "synthetic", None):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                seal_passphrase(value)
        other = win32crypt.CryptProtectData(b"synthetic", "other purpose", None, None, None, 1)
        with self.assertRaisesRegex(ValueError, "TLS secret unavailable"):
            open_passphrase(other)
        for blob in (b"", b"invalid", b"x" * 8193, "synthetic", None):
            with self.subTest(kind=type(blob).__name__), self.assertRaises(ValueError):
                open_passphrase(blob)
