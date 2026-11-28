"""Upgrading invalidates unverifiable sessions; rollback cannot discard active clocks."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.storage.initialize import initialize_database


def config_for(path):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
    config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
    return config


class SessionClockMigrationTests(unittest.TestCase):
    def test_upgrade_invalidates_old_sessions_and_downgrade_refuses_live_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = config_for(path)
            command.downgrade(config, "0016")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("INSERT INTO owner_sessions VALUES (?,?,?,?,?)", (b"a" * 32, b"b" * 32, b"c" * 32, 1000, 2800))
                connection.commit()
            command.upgrade(config, "head")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM owner_sessions").fetchone()[0], 0)
                connection.execute("INSERT INTO owner_sessions VALUES (?,?,?,?,?,?)", (b"a" * 32, b"b" * 32, b"c" * 32, 1000, 2800, 1001))
                connection.commit()
            with self.assertRaises(RuntimeError):
                command.downgrade(config, "0016")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT last_seen FROM owner_sessions").fetchone()[0], 1001)
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0018")
