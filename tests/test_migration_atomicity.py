import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from personalcontext.storage.initialize import initialize_database


class MigrationAtomicityTests(unittest.TestCase):
    def test_failed_audit_rebuild_rolls_back_schema_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            root = Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"
            config.set_main_option("script_location", str(root))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            command.downgrade(config, "0009")
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA ignore_check_constraints=ON")
                connection.execute("INSERT INTO security_audit VALUES (1,'invalid','owner','success',1,?)", ("0" * 36,))
            with self.assertRaises(IntegrityError):
                command.upgrade(config, "head")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone(), ("0009",))
                self.assertEqual(connection.execute("SELECT event_type FROM security_audit").fetchall(), [("invalid",)])
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
                self.assertNotIn("security_audit_old", tables)
                self.assertNotIn("sources", tables)
                self.assertIn("ix_security_audit_time", indexes)
