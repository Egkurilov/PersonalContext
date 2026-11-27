import unittest

from personalcontext.network.boundary import (
    LocalBoundary,
    PrivateBoundary,
    check_request,
)


class NetworkBoundaryTests(unittest.TestCase):
    def test_local_exact_peer_host_scheme_origin_and_no_forwarding(self):
        boundary = LocalBoundary()
        self.assertIsNone(check_request(boundary, "127.0.0.1", "http", ["127.0.0.1:17890"], [], []))
        self.assertIsNone(check_request(boundary, "127.0.0.1", "http", ["127.0.0.1"], ["http://127.0.0.1:17890"], []))
        cases = [("192.0.2.10", "http", ["127.0.0.1"], [], [], 403),
                 ("127.0.0.1", "https", ["127.0.0.1"], [], [], 403),
                 ("127.0.0.1", "http", ["evil.example"], [], [], 400),
                 ("127.0.0.1", "http", ["127.0.0.1", "127.0.0.1"], [], [], 400),
                 ("127.0.0.1", "http", ["127.0.0.1"], ["null"], [], 403),
                 ("127.0.0.1", "http", ["127.0.0.1"], [], ["anything"], 400)]
        for peer, scheme, hosts, origins, forwarding, status in cases:
            with self.subTest(status=status, hosts=hosts):
                self.assertEqual(check_request(boundary, peer, scheme, hosts, origins, forwarding)[0], status)

    def test_private_boundary_rejects_spoofed_peer_host_origin_and_plaintext(self):
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        self.assertIsNone(check_request(boundary, "192.168.7.9", "https", ["pc.example.test:18443"],
                                        ["https://pc.example.test:18443"], []))
        cases = [("192.168.8.9", "https", ["pc.example.test:18443"], [], [], 403),
                 ("192.168.7.9", "http", ["pc.example.test:18443"], [], [], 403),
                 ("192.168.7.9", "https", ["attacker.test:18443"], [], [], 400),
                 ("192.168.7.9", "https", ["pc.example.test:18443"], ["https://attacker.test"], [], 403),
                 ("192.168.7.9", "https", ["pc.example.test:18443"], [], ["127.0.0.1"], 400)]
        for peer, scheme, hosts, origins, forwarding, status in cases:
            with self.subTest(status=status, peer=peer):
                self.assertEqual(check_request(boundary, peer, scheme, hosts, origins, forwarding)[0], status)

    def test_private_configuration_rejects_public_wildcard_and_ambiguous_addresses(self):
        for address, hostname, networks in [("0.0.0.0", "pc.example.test", ["10.0.0.0/8"]),
                                            ("8.8.8.8", "pc.example.test", ["10.0.0.0/8"]),
                                            ("192.168.1.2", "pc.example.test", ["0.0.0.0/0"]),
                                            ("192.168.1.2", "PC.example.test", ["192.168.1.0/24"]),
                                            ("192.168.1.2", "pc.example.test", [])]:
            with self.subTest(address=address, hostname=hostname, networks=networks), self.assertRaises(ValueError):
                PrivateBoundary.create(address, hostname, 18443, networks)
        with self.assertRaises(ValueError):
            PrivateBoundary("192.168.1.2", "pc.example.test", 18443, ["192.168.1.0/24"])

    def test_private_ipv6_and_vpn_ranges_are_explicit_and_family_bound(self):
        boundary = PrivateBoundary.create("fd00::1", "pc.example.test", 18443, ["fd00::/64", "100.64.0.0/10"])
        self.assertIsNone(check_request(boundary, "fd00::2", "https", ["pc.example.test:18443"], [], []))
        self.assertIsNone(check_request(boundary, "100.100.1.2", "https", ["pc.example.test:18443"], [], []))
        for peer in ("fd00:1::2", "::ffff:100.100.1.2", "127.0.0.1", "8.8.8.8", "unknown", None):
            with self.subTest(peer=peer):
                self.assertEqual(check_request(boundary, peer, "https", ["pc.example.test:18443"], [], [])[0], 403)
