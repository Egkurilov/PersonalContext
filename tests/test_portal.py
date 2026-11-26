import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app


class PortalTests(unittest.TestCase):
    def test_portal_assets_and_origin_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web = root / "web"
            (web / "assets").mkdir(parents=True)
            (web / "index.html").write_text("synthetic portal", encoding="utf-8")
            (web / "assets" / "app.js").write_text("synthetic", encoding="utf-8")
            app = create_app(root / "context.db", web)
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                self.assertIn("synthetic portal", client.get("/").text)
                self.assertEqual(client.get("/assets/app.js").text, "synthetic")
                self.assertEqual(client.get("/api/missing").status_code, 404)
                self.assertEqual(client.get("/", headers={"origin": "https://attacker.example"}).status_code, 403)
