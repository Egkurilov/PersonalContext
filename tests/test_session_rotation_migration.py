import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.audit.record import record_audit
from personalcontext.storage.initialize import initialize_database


class RotationMigrationTests(unittest.TestCase):
    def test_existing_history_survives_and_downgrade_refuses_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            command.downgrade(config, "0010")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                record_audit(connection, "source_create", "owner", 1000)
                connection.commit()
            command.upgrade(config, "head")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                record_audit(connection, "owner_session_rotate", "owner", 1001)
                connection.commit()
            with self.assertRaisesRegex(RuntimeError, "rotation audit history"):
                command.downgrade(config, "0010")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone(), ("0011",))
                rows = connection.execute("SELECT event_type FROM security_audit ORDER BY id").fetchall()
                self.assertEqual(rows, [("source_create",), ("owner_session_rotate",)])
