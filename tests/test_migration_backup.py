import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


@unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows")
class MigrationBackupTests(unittest.TestCase):
    def test_existing_database_is_backed_up_before_first_migration(self):
        import win32crypt

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE sample (value TEXT)")
                connection.execute("INSERT INTO sample VALUES ('synthetic')")
            initialize_database(path)
            backups = list(path.parent.glob("context.db.*.dpapi"))
            self.assertEqual(len(backups), 1)
            description, data = win32crypt.CryptUnprotectData(backups[0].read_bytes(), None, None, None, 1)
            self.assertEqual(description, "PersonalContext SQLite backup")
            restored = sqlite3.connect(":memory:")
            try:
                restored.deserialize(data)
                self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(restored.execute("SELECT value FROM sample").fetchone()[0], "synthetic")
            finally:
                restored.close()
            destination = path.parent / "restored.db"
            restore_backup(backups[0], destination)
            with closing(sqlite3.connect(destination)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM sample").fetchone()[0], "synthetic")
            with self.assertRaises(FileExistsError):
                restore_backup(backups[0], destination)
            initialize_database(path)
            self.assertEqual(len(list(path.parent.glob("context.db.*.dpapi"))), 1)

    def test_failed_backup_prevents_migration(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE sample (value TEXT)")
            with patch("personalcontext.storage.initialize.backup_database", side_effect=OSError("failed")), self.assertRaises(OSError):
                initialize_database(path)
            with closing(sqlite3.connect(path)) as connection, connection:
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                self.assertNotIn(("alembic_version",), tables)
