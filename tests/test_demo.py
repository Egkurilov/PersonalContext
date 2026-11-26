import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.storage.initialize import initialize_database


class DemoTests(unittest.TestCase):
    def test_demo_seed_is_isolated_repeatable_and_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            production = root / "data.db"
            demo = root / "demo.db"
            with TestClient(create_app(production), base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                self.assertEqual(client.get("/api/v1/demo").status_code, 404)
            with closing(sqlite3.connect(production)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM app_metadata").fetchone()[0], 0)
            for _ in range(2):
                with TestClient(create_app(demo, demo=True), base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                    response = client.get("/api/v1/demo")
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertTrue(body["demo"])
                    self.assertEqual(len(body["items"]), 2)
                    self.assertTrue(all(item.startswith(("Синтетический", "Synthetic")) for item in body["items"]))
            with closing(sqlite3.connect(demo)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM app_metadata").fetchone()[0], 1)

    def test_unexpected_seed_fails_closed_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("INSERT INTO app_metadata VALUES (?, ?)", ("demo.seed.v1", "synthetic invalid"))
            with self.assertRaisesRegex(ValueError, "demo seed"), TestClient(create_app(path, demo=True)):
                pass
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM app_metadata").fetchone()[0], "synthetic invalid")
