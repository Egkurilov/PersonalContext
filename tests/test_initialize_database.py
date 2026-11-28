import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.storage.initialize import initialize_database


class DatabaseInitializationTests(unittest.TestCase):
    def test_initializes_wal_and_fts_and_can_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0013")

    def test_invalid_parent_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing" / "context.db"
            with self.assertRaises(sqlite3.OperationalError):
                initialize_database(path)
