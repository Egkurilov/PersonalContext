"""Storage and bind failures cannot leave a private socket open."""

import sqlite3
import time
import unittest
from unittest.mock import patch

import test_private_listener_http as fixture


class PrivateListenerErrorTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown
    configured = fixture.PrivateListenerHttpTests.configured

    def test_port_conflict_fails_without_starting_server(self):
        owner, _ = self.configured()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", side_effect=OSError("occupied")),
              patch("personalcontext.network.listener.manager.PrivateServer") as server):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 503)
            server.assert_not_called()

    def test_firewall_change_during_tls_preflight_prevents_bind(self):
        owner, _ = self.configured()
        with (patch("personalcontext.network.listener.manager.firewall_status", side_effect=["restricted", "not_restricted"]),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener") as bind):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 503)
            bind.assert_not_called()

    def test_unexpected_preflight_error_is_generic_and_never_binds(self):
        owner, _ = self.configured()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", side_effect=Exception("synthetic private path")),
              patch("personalcontext.network.listener.manager.bind_listener") as bind):
            response = self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("synthetic private path", response.text)
            bind.assert_not_called()

    def test_audit_failure_closes_bound_socket_before_server_starts(self):
        owner, _ = self.configured()
        fake_socket = fixture.FakeSocket()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket),
              patch("personalcontext.network.listener.read.record_audit", side_effect=sqlite3.OperationalError("synthetic")),
              patch("personalcontext.network.listener.manager.PrivateServer") as server):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 503)
            self.assertTrue(fake_socket.closed)
            server.assert_not_called()

    def test_writer_failure_immediately_stops_active_listener(self):
        owner, _ = self.configured()
        fake_socket = fixture.FakeSocket()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket),
              patch("personalcontext.network.listener.manager.PrivateServer", fixture.FakeServer),
              patch("personalcontext.network.listener.monitor.CHECK_INTERVAL", 300)):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)

            def fail(_connection):
                raise sqlite3.OperationalError("synthetic")

            with self.assertRaises(sqlite3.OperationalError):
                self.client.portal.call(self.client.app.state.scheduler.writer.submit, fail)
            deadline = time.monotonic() + 2
            while not fake_socket.closed and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(fake_socket.closed)
            self.assertTrue(self.client.app.state.capture_latch.is_paused())

    def test_stop_closes_socket_even_if_stop_audit_fails(self):
        owner, _ = self.configured()
        fake_socket = fixture.FakeSocket()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket),
              patch("personalcontext.network.listener.manager.PrivateServer", fixture.FakeServer)):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)
            with patch("personalcontext.network.listener.read.record_audit", side_effect=sqlite3.OperationalError("synthetic")):
                self.assertEqual(self.client.post(fixture.ROOT + "/stop", headers=owner).status_code, 503)
            self.assertTrue(fake_socket.closed)
