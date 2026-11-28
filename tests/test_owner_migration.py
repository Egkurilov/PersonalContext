import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class OwnerMigrationTests(unittest.TestCase):
    def test_upgrade_backs_up_previous_schema_before_adding_owner_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
            config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
            command.downgrade(config, "0002")
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("INSERT INTO app_metadata(key,value) VALUES ('fixture','synthetic')")
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0013")
                self.assertEqual(connection.execute("SELECT value FROM app_metadata WHERE key='fixture'").fetchone()[0], "synthetic")
                self.assertEqual(connection.execute("SELECT count(*) FROM owner_credentials").fetchone()[0], 0)
            backups = list(path.parent.glob("context.db.*.dpapi"))
            self.assertEqual(len(backups), 1)
            restored = path.parent / "restored.db"
            restore_backup(backups[0], restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0002")
                self.assertEqual(connection.execute("SELECT value FROM app_metadata WHERE key='fixture'").fetchone()[0], "synthetic")
