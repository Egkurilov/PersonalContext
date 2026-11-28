"""Private access must stay on a selected physical LAN interface."""

import unittest
from pathlib import Path
from unittest.mock import patch

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.lan.scope import local_lan_allowed
from personalcontext.network.uvicorn_config import private_server_config


class LocalLanScopeTests(unittest.TestCase):
    def test_only_same_subnet_on_physical_interface(self):
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        self.assertTrue(local_lan_allowed(boundary, 24, True, "Private"))
        self.assertTrue(local_lan_allowed(boundary, 24, True, "Public"))
        self.assertTrue(local_lan_allowed(boundary, 24, True, "Domain"))
        for prefix, physical, category in ((25, True, "Private"), (24, False, "Private"),
                                           (24, True, "Unknown"),
                                           (True, True, "Private"), (0, True, "Private")):
            with self.subTest(prefix=prefix, physical=physical, category=category):
                self.assertFalse(local_lan_allowed(boundary, prefix, physical, category))

    def test_rejects_other_private_subnets_and_other_ip_families(self):
        for peers in (["192.168.8.0/24"], ["10.0.0.0/8"], ["fd00::/64"]):
            boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, peers)
            self.assertFalse(local_lan_allowed(boundary, 24, True, "Private"))

    def test_ipv6_unique_local_subnet_is_supported(self):
        boundary = PrivateBoundary.create("fd00::1", "pc.example.test", 18443, ["fd00::/64"])
        self.assertTrue(local_lan_allowed(boundary, 64, True, "Private"))
        self.assertFalse(local_lan_allowed(boundary, 80, True, "Private"))

    def test_legacy_cgnat_or_vpn_address_never_authorizes_listener(self):
        boundary = PrivateBoundary.create("100.100.1.2", "pc.example.test", 18443, ["100.100.1.0/24"])
        self.assertFalse(local_lan_allowed(boundary, 24, True, "Private"))
        with (patch("personalcontext.network.uvicorn_config.validated_tls_material") as material,
              self.assertRaises(ValueError)):
            private_server_config(lambda *_: None, boundary, Path("cert.pem"), Path("key.pem"), b"synthetic")
        material.assert_not_called()
