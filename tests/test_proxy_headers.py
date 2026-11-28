import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app


class ProxyHeaderTests(unittest.TestCase):
    def test_untrusted_forwarding_headers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "context.db")
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1234)) as client:
                self.assertEqual(client.get("/healthz").status_code, 200)
                for header in ("Forwarded", "X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host"):
                    with self.subTest(header=header):
                        self.assertEqual(client.get("/healthz", headers={header: "127.0.0.1"}).status_code, 400)
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("192.0.2.1", 1234)) as client:
                response = client.get("/healthz", headers={"X-Forwarded-For": "127.0.0.1"})
                self.assertEqual(response.status_code, 403)
