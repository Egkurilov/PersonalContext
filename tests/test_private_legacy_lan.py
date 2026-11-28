"""An old VPN candidate remains replaceable but cannot be saved or used anew."""

import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_device_http as fixture

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import PrivateCandidate

PATH = "/api/v1/network/private/config"


class PrivateLegacyLanTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def test_owner_can_replace_legacy_vpn_candidate_but_cannot_save_one(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("INSERT INTO private_network_candidate VALUES (1,1,?,?,?,?,?,?,?)",
                               ("100.100.1.2", "pc.example.test", 18443, json.dumps(["100.100.1.0/24"]),
                                "cert.pem", "key.pem", b"synthetic-protected"))
            connection.commit()
        self.assertEqual(self.client.get(PATH).json()["revision"], 1)
        vpn = PrivateCandidate(PrivateBoundary.create("100.100.1.2", "pc.example.test", 18443, ["100.100.1.0/24"]),
                               "cert.pem", "key.pem", b"synthetic-protected")
        lan = PrivateCandidate(PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"]),
                               "cert.pem", "key.pem", b"synthetic-protected")
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        with patch("personalcontext.network.settings_http.prepare_candidate", return_value=vpn):
            self.assertEqual(self.client.post(PATH, headers=owner, json={"revision": 1}).status_code, 400)
        with patch("personalcontext.network.settings_http.prepare_candidate", return_value=lan):
            self.assertEqual(self.client.post(PATH, headers=owner, json={"revision": 1}).json()["revision"], 2)
