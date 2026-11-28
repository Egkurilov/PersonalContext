"""Synthetic secrets must not escape through sanitizer responses or security audit."""

import unittest

import test_device_http as fixture


class SecurityCanaryTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def test_preview_and_audit_do_not_echo_synthetic_url_secrets(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        canary = "syntheticCanary9472"
        preview = {"kind": "web", "source": "example.org",
                   "data": {"url": f"https://{canary}:{canary}@example.org/article?token={canary}#{canary}"}}
        response = self.client.post("/api/v1/privacy/preview", headers=owner, json=preview)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["url"], "https://example.org/article")
        self.assertNotIn(canary, response.text)
        app = {"kind": "app", "source": "passwordmanager.exe", "data": {"app": "passwordmanager.exe"}}
        self.assertIsNone(self.client.post("/api/v1/privacy/preview", headers=owner, json=app).json()["result"])
        self.assertEqual(self.client.post("/api/v1/auth/login", headers=self.headers,
                                          json={"password": canary}).status_code, 401)
        self.assertNotIn(canary, self.client.get("/api/v1/audit").text)

    def test_loopback_configuration_disables_access_logging(self):
        from personalcontext.network.loopback.config import loopback_server_config

        config = loopback_server_config(self.client.app)
        self.assertFalse(config.access_log)
        self.assertFalse(config.proxy_headers)
        self.assertEqual(config.ws, "none")
