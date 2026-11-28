"""Owner-controlled private listener lifecycle with synthetic OS dependencies."""

import asyncio
import sqlite3
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import test_device_http as fixture

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import PrivateCandidate

ROOT = "/api/v1/network/private"


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeServer:
    def __init__(self, _config):
        self.started = False
        self.should_exit = False
        self.servers = []

    async def serve(self, sockets):
        self.started = True
        while not self.should_exit:
            await asyncio.sleep(0.01)
        for socket in sockets:
            socket.close()


class PrivateListenerHttpTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def configured(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
        candidate = PrivateCandidate(boundary, "cert.pem", "key.pem", b"synthetic-protected")
        with patch("personalcontext.network.settings_http.prepare_candidate", return_value=candidate):
            self.assertEqual(self.client.post(ROOT + "/config", headers=owner, json={"revision": 0}).status_code, 200)
        return owner, candidate

    def test_owner_start_stop_and_configuration_exclusion(self):
        owner, candidate = self.configured()
        fake_socket = FakeSocket()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket),
              patch("personalcontext.network.listener.manager.PrivateServer", FakeServer)):
            self.assertEqual(self.client.post(ROOT + "/start", headers=self.headers, json={"revision": 1}).status_code, 403)
            started = self.client.post(ROOT + "/start", headers=owner, json={"revision": 1})
            self.assertEqual(started.status_code, 200)
            self.assertEqual(started.json()["firewall_monitoring"], "periodic")
            self.assertTrue(self.client.get(ROOT + "/config").json()["enabled"])
            with patch("personalcontext.network.firewall.http.firewall_status", return_value="restricted"):
                self.assertTrue(self.client.post(ROOT + "/firewall/check", headers=owner).json()["enabled"])
            with patch("personalcontext.network.settings_http.prepare_candidate", return_value=candidate):
                self.assertEqual(self.client.post(ROOT + "/config", headers=owner, json={"revision": 1}).status_code, 409)
            self.assertEqual(self.client.post(ROOT + "/stop", headers=owner).status_code, 204)
            self.assertTrue(fake_socket.closed)
            self.assertFalse(self.client.get(ROOT + "/config").json()["enabled"])
            audit = self.client.get("/api/v1/audit").text
            self.assertIn("private_listener_attempt", audit)
            self.assertIn("private_listener_stop", audit)
            for private in ("192.168.7.2", "pc.example.test", "synthetic-protected"):
                self.assertNotIn(private, audit)

    def test_firewall_failure_and_revoked_owner_never_bind(self):
        owner, _ = self.configured()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="unavailable"),
              patch("personalcontext.network.listener.manager.bind_listener") as bind):
            self.assertEqual(self.client.post(ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 503)
            bind.assert_not_called()

        def revoke_during_preflight(_boundary, _executable):
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute("DELETE FROM owner_sessions")
                connection.commit()
            return "restricted"

        with (patch("personalcontext.network.listener.manager.firewall_status", side_effect=revoke_during_preflight),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener") as bind):
            self.assertEqual(self.client.post(ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 403)
            bind.assert_not_called()

    def test_firewall_change_stops_server_and_closes_socket(self):
        owner, _ = self.configured()
        fake_socket = FakeSocket()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.monitor.firewall_status", return_value="not_restricted"),
              patch("personalcontext.network.listener.monitor.CHECK_INTERVAL", 0.01),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket),
              patch("personalcontext.network.listener.manager.PrivateServer", FakeServer)):
            self.assertEqual(self.client.post(ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)
            deadline = time.monotonic() + 2
            while not fake_socket.closed and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(fake_socket.closed)
            self.assertFalse(self.client.get(ROOT + "/config").json()["enabled"])
