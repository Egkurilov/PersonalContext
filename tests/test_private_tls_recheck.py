"""TLS configuration must recheck and lock material while loading keys."""

import ssl
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.uvicorn_config import private_server_config


class PrivateTlsRecheckTests(unittest.TestCase):
    def test_config_holds_validation_lock_during_tls_loading(self):
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        cert, key = Path("synthetic/tls/cert.pem"), Path("synthetic/tls/key.pem")
        events = []

        @contextmanager
        def locked(root, cert_name, key_name):
            self.assertEqual((root, cert_name, key_name), (cert.parent, cert.name, key.name))
            events.append("locked")
            try:
                yield cert, key
            finally:
                events.append("released")

        def load(actual_cert, actual_key, hostname, protected):
            self.assertEqual(events, ["locked"])
            self.assertEqual((actual_cert, actual_key, hostname, protected), (cert, key, boundary.hostname, b"synthetic"))
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            return context

        with (patch("personalcontext.network.uvicorn_config.validated_tls_material", side_effect=locked),
              patch("personalcontext.network.uvicorn_config.vault_server_context", side_effect=load)):
            private_server_config(lambda scope, receive, send: None, boundary, cert, key, b"synthetic")
        self.assertEqual(events, ["locked", "released"])

    def test_different_directories_and_failed_recheck_are_rejected(self):
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        cert, key = Path("synthetic/tls/cert.pem"), Path("synthetic/other/key.pem")
        with self.assertRaises(ValueError):
            private_server_config(lambda scope, receive, send: None, boundary, cert, key, b"synthetic")
        with (patch("personalcontext.network.uvicorn_config.validated_tls_material", side_effect=ValueError("unavailable")),
              patch("personalcontext.network.uvicorn_config.vault_server_context") as load,
              self.assertRaises(ValueError)):
            private_server_config(lambda scope, receive, send: None, boundary, cert, cert.parent / "key.pem", b"synthetic")
        load.assert_not_called()
