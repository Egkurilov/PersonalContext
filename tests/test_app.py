import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from personalcontext.app import create_app


class AppTests(unittest.TestCase):
    def test_health_ready_and_empty_portal(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "context.db")
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1234)) as client:
                self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
                self.assertEqual(client.get("/readyz").json(), {"status": "ready"})
                self.assertEqual(client.get("/api/unknown").status_code, 404)
            with closing(sqlite3.connect(Path(directory) / "context.db")) as connection:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_host_and_peer_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "context.db")
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                self.assertEqual(client.get("/healthz", headers={"host": "attacker.example"}).status_code, 400)
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("192.0.2.1", 1)) as client:
                self.assertEqual(client.get("/healthz").status_code, 403)

    def test_database_failure_prevents_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "missing" / "context.db")
            with self.assertRaises(sqlite3.OperationalError), TestClient(app):
                pass

    def test_locked_database_prevents_readiness_then_recovers(self):
        from personalcontext.storage.initialize import initialize_database

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as locker:
                locker.execute("BEGIN IMMEDIATE")
                app = create_app(path)
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"), TestClient(app):
                    pass
                locker.rollback()
            app = create_app(path)
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                self.assertEqual(client.get("/readyz").json(), {"status": "ready"})
