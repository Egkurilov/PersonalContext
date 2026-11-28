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
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.privacy.policy_store import PolicyDraft, load_policy, save_policy
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class AuditMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_policy_and_restore_removes_old_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
            config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
            command.downgrade(config, "0008")
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic audit migration owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                consume_bootstrap(connection, code, encoded, 1001)
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                                    frozenset({("synthetic-source", "metadata")}))
                self.assertEqual(save_policy(connection, owner.token, owner.csrf, 1, draft, 1003).status, "ok")
                connection.commit()
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0013")
                self.assertFalse(load_policy(connection).paused)
                self.assertEqual(connection.execute("SELECT count(*) FROM security_audit").fetchone()[0], 0)
            backup, = path.parent.glob("context.db.*.dpapi")
            restored = path.parent / "restored.db"
            restore_backup(backup, restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0008")
                self.assertTrue(load_policy(connection).paused)
                self.assertEqual(connection.execute("SELECT count(*) FROM owner_credentials").fetchone()[0], 0)
