import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic preview owner"


class SanitizerPreviewHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        with closing(sqlite3.connect(path)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        self.client = TestClient(create_app(path), base_url=ORIGIN, client=("127.0.0.1", 1000))
        self.client.__enter__()
        self.origin = {"Origin": ORIGIN}
        self.client.post("/api/v1/auth/bootstrap", json={"code": code, "password": CANDIDATE}, headers=self.origin)
        csrf = self.client.post("/api/v1/auth/login", json={"password": CANDIDATE}, headers=self.origin).json()["csrf"]
        self.headers = {**self.origin, "X-CSRF-Token": csrf}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_owner_preview_sanitizes_without_enabling_collection(self):
        sample = {"kind": "web", "source": "example.org",
                  "data": {"url": "https://example.org/article?tracking=synthetic", "title": "Пример"}}
        path = "/api/v1/privacy/preview"
        self.assertEqual(self.client.post(path, json=sample, headers=self.origin).status_code, 403)
        response = self.client.post(path, json=sample, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.json()["preview_only"])
        self.assertEqual(response.json()["result"]["url"], "https://example.org/article")
        self.assertNotIn("tracking=synthetic", response.text)
        self.assertTrue(self.client.get("/api/v1/privacy/policy").json()["effective_paused"])

    def test_rejected_input_never_echoes_secret_or_allows_unauthenticated_preview(self):
        canary = "api" + "_key=" + "synthetic-value"
        sample = {"kind": "web", "source": "example.org", "data": {"url": "https://example.org/article", "title": canary}}
        path = "/api/v1/privacy/preview"
        response = self.client.post(path, json=sample, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["result"])
        self.assertNotIn(canary, response.text)
        self.client.cookies.clear()
        self.assertEqual(self.client.post(path, json=sample, headers=self.headers).status_code, 403)

    def test_application_preview_and_malformed_requests(self):
        path = "/api/v1/privacy/preview"
        sample = {"kind": "app", "source": "reader.exe", "data": {"app": "reader.exe"}}
        response = self.client.post(path, json=sample, headers=self.headers)
        self.assertEqual(response.json()["result"]["app"], "reader.exe")
        sample = {"kind": "app", "source": "password-manager.exe", "data": {"app": "password-manager.exe"}}
        self.assertIsNone(self.client.post(path, json=sample, headers=self.headers).json()["result"])
        self.assertEqual(self.client.post(path, json={**sample, "private": False}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post(path, json={**sample, "data": "x" * 66000}, headers=self.headers).status_code, 413)
