"""Persisted owner filters cannot be silently lost through downgrade."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore_security import reset_restored_access


class FilterMigrationTests(unittest.TestCase):
    def test_downgrade_refuses_to_discard_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("INSERT INTO privacy_filter_rules VALUES ('allowed_domains', 'example.org')")
                connection.commit()
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            with self.assertRaises(RuntimeError):
                command.downgrade(config, "0015")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0017")
                self.assertEqual(connection.execute("SELECT value FROM privacy_filter_rules").fetchone()[0], "example.org")

    def test_restoring_rules_does_not_restore_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("INSERT INTO privacy_filter_rules VALUES ('allowed_domains', 'example.org')")
                reset_restored_access(connection)
                connection.commit()
                self.assertEqual(connection.execute("SELECT value FROM privacy_filter_rules").fetchone()[0], "example.org")
                self.assertEqual(connection.execute("SELECT paused FROM capture_policy").fetchone()[0], 1)
