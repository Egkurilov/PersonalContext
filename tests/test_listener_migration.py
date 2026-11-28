"""Listener audit history must survive upgrades and block unsafe downgrade."""

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


class ListenerMigrationTests(unittest.TestCase):
    def test_downgrade_refuses_to_drop_listener_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                record_audit(connection, "private_listener_attempt", "owner", 1000)
                connection.commit()
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            with self.assertRaises(RuntimeError):
                command.downgrade(config, "0014")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0015")
                self.assertEqual(connection.execute("SELECT count(*) FROM security_audit WHERE event_type='private_listener_attempt'").fetchone()[0], 1)
