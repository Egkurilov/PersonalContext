"""Security schema downgrade and corruption checks with synthetic bindings."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.devices.extension_origin import device_origin_matches
from personalcontext.storage.initialize import initialize_database


class ExtensionMigrationTests(unittest.TestCase):
    def test_downgrade_refuses_to_drop_a_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("INSERT INTO devices(device_id,token_hash,scope_mask,created_at) VALUES (?,?,?,?)",
                                   ("00000000-0000-4000-8000-000000000001", bytes(32), 1, 1))
                connection.execute("INSERT INTO extension_devices VALUES (?,?)",
                                   ("00000000-0000-4000-8000-000000000001", "chrome-extension://" + "a" * 32))
                connection.commit()
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            with self.assertRaises(RuntimeError):
                command.downgrade(config, "0012")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0017")
                self.assertEqual(connection.execute("SELECT count(*) FROM extension_devices").fetchone()[0], 1)

    def test_missing_binding_table_in_current_schema_is_not_a_native_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("DROP TABLE extension_devices")
                with self.assertRaises(sqlite3.DatabaseError):
                    device_origin_matches(connection, "00000000-0000-4000-8000-000000000001", None)
