import unittest

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.policy import (
    FirewallProfile,
    FirewallRule,
    firewall_allows_private_only,
)


class FirewallPolicyTests(unittest.TestCase):
    def setUp(self):
        self.boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        self.exe = r"C:\Apps\PersonalContext.exe"
        self.profile = FirewallProfile("Private", True, "Block")
        self.rule = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), ("192.168.7.0/24",), self.exe,
                                 unrestricted=True)

    def test_scoped_rule_and_blocked_default_are_required(self):
        self.assertTrue(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [self.rule]))
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [], [self.rule]))
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [FirewallProfile("Private", False, "Block")], [self.rule]))
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [FirewallProfile("Private", True, "Allow")], [self.rule]))
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], []))

    def test_broad_or_unknown_applicable_allow_rule_fails_closed(self):
        for remote in ("Any", "LocalSubnet", "0.0.0.0/0", "192.168.0.0/16", "invalid"):
            broad = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), (remote,), "Any")
            with self.subTest(remote=remote):
                self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [self.rule, broad]))
        unknown_port = FirewallRule(frozenset({"Private"}), "TCP", ("RPC",), ("Any",), "Any")
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [self.rule, unknown_port]))

    def test_unrelated_rules_do_not_grant_access_and_cannot_expand_scope(self):
        unrelated_app = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), ("Any",), r"C:\Apps\Other.exe")
        unrelated_port = FirewallRule(frozenset({"Private"}), "TCP", ("443",), ("Any",), "Any")
        unrelated_protocol = FirewallRule(frozenset({"Private"}), "UDP", ("18443",), ("Any",), "Any")
        self.assertTrue(firewall_allows_private_only(self.boundary, self.exe, [self.profile],
                                                    [self.rule, unrelated_app, unrelated_port, unrelated_protocol]))
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [unrelated_app]))
        unknown_protocol = FirewallRule(frozenset({"Private"}), "unknown", ("18443",), self.rule.remotes, self.exe)
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [unknown_protocol]))

    def test_all_active_profiles_and_every_peer_range_need_coverage(self):
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443,
                                          ["192.168.7.0/24", "10.0.0.0/8"])
        self.assertFalse(firewall_allows_private_only(boundary, self.exe, [self.profile], [self.rule]))
        full = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), ("192.168.7.0/24", "10.0.0.0/8"), self.exe,
                            unrestricted=True)
        public = FirewallProfile("Public", True, "Block")
        self.assertFalse(firewall_allows_private_only(boundary, self.exe, [self.profile, public], [full]))
        both = FirewallRule(frozenset({"Private", "Public"}), "TCP", ("18443",), full.remotes, self.exe,
                            unrestricted=True)
        self.assertTrue(firewall_allows_private_only(boundary, self.exe, [self.profile, public], [both]))

    def test_edge_traversal_and_unknown_local_scope_never_prove_readiness(self):
        edge = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), self.rule.remotes, self.exe, edge="Allow")
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [edge]))
        unknown = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), self.rule.remotes, self.exe,
                               locals=("LocalSubnet",))
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [unknown]))
        restricted = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), self.rule.remotes, self.exe,
                                  unrestricted=False)
        self.assertFalse(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [restricted]))
        other = FirewallRule(frozenset({"Private"}), "TCP", ("18443",), ("Any",), "Any",
                             locals=("10.9.0.1",))
        self.assertTrue(firewall_allows_private_only(self.boundary, self.exe, [self.profile], [self.rule, other]))
