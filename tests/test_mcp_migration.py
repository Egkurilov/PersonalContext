"""Downgrades must not silently discard MCP access state or audit records."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.storage.initialize import initialize_database


class McpMigrationTests(unittest.TestCase):
    def test_downgrade_rejects_credentials_and_preserves_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("INSERT INTO mcp_credentials VALUES (?,?,?,?,?,?,NULL)",
                                   ("00000000-0000-4000-8000-000000000001", bytes(32), "status:read", 100, 1000, 100))
                connection.commit()
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            with self.assertRaises(RuntimeError):
                command.downgrade(config, "0013")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0015")
                self.assertEqual(connection.execute("SELECT count(*) FROM mcp_credentials").fetchone()[0], 1)
