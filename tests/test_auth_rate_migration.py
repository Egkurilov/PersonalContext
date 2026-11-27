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
from personalcontext.auth.owner_sessions import create_session, session_active
from personalcontext.auth.password_hash import hash_password
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class AuthRateMigrationTests(unittest.TestCase):
    def test_previous_session_survives_upgrade_and_backup_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
            config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
            command.downgrade(config, "0005")
            digest = hash_password("synthetic migration candidate")
            with closing(sqlite3.connect(path)) as connection:
                code = issue_bootstrap(connection, now=1000)
                connection.commit()
                self.assertTrue(consume_bootstrap(connection, candidate=code, encoded=digest, now=1001))
                connection.commit()
                session = create_session(connection, expected_hash=digest, now=1100)
                self.assertIsNotNone(session)
                connection.commit()
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0008")
                self.assertTrue(session_active(connection, session.token, now=1101))
                self.assertEqual(connection.execute("SELECT count(*) FROM auth_attempts").fetchone()[0], 0)
            backups = list(path.parent.glob("context.db.*.dpapi"))
            self.assertEqual(len(backups), 1)
            restored = path.parent / "restored.db"
            restore_backup(backups[0], restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0005")
                self.assertFalse(session_active(connection, session.token, now=1101))
