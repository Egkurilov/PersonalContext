"""Private access must not reactivate across a normal host restart."""

import unittest
from unittest.mock import patch

import test_device_http as device_fixture
import test_private_listener_http as fixture
from fastapi.testclient import TestClient

from personalcontext.app import create_app


class PrivateListenerRestartTests(unittest.TestCase):
    setUp = fixture.PrivateListenerHttpTests.setUp
    tearDown = fixture.PrivateListenerHttpTests.tearDown
    configured = fixture.PrivateListenerHttpTests.configured

    def test_restart_stops_listener_and_requires_new_owner_start(self):
        owner, _ = self.configured()
        fake_socket = fixture.FakeSocket()
        with (patch("personalcontext.network.listener.manager.firewall_status", return_value="restricted"),
              patch("personalcontext.network.listener.manager.private_server_config", return_value=object()),
              patch("personalcontext.network.listener.manager.bind_listener", return_value=fake_socket),
              patch("personalcontext.network.listener.manager.PrivateServer", fixture.FakeServer)):
            self.assertEqual(self.client.post(fixture.ROOT + "/start", headers=owner, json={"revision": 1}).status_code, 200)
            self.client.__exit__(None, None, None)
            self.assertTrue(fake_socket.closed)
            self.client = TestClient(create_app(self.path), base_url=device_fixture.ORIGIN, client=("127.0.0.1", 1))
            self.client.__enter__()
            login = self.client.post("/api/v1/auth/login", headers=self.headers,
                                     json={"password": device_fixture.CANDIDATE})
            self.assertEqual(login.status_code, 200)
            config = self.client.get(fixture.ROOT + "/config").json()
            self.assertTrue(config["configured"])
            self.assertFalse(config["enabled"])
