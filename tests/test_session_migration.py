import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_hash import hash_password, verify_password
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class SessionMigrationTests(unittest.TestCase):
    def test_upgrade_and_backup_preserve_existing_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
            config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
            command.downgrade(config, "0004")
            candidate = "synthetic session migration"
            digest = hash_password(candidate)
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, now=1000)
                connection.commit()
                self.assertTrue(consume_bootstrap(connection, candidate=code, encoded=digest, now=1001))
                connection.commit()
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0007")
                self.assertTrue(verify_password(find_owner_hash(connection), candidate))
                self.assertEqual(connection.execute("SELECT count(*) FROM owner_sessions").fetchone()[0], 0)
            backups = list(path.parent.glob("context.db.*.dpapi"))
            self.assertEqual(len(backups), 1)
            restored = path.parent / "restored.db"
            restore_backup(backups[0], restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0004")
                self.assertTrue(verify_password(find_owner_hash(connection), candidate))
