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
from personalcontext.devices.pairing import enroll, issue_pairing
from personalcontext.devices.scopes import authorize_device
from personalcontext.privacy.policy_store import load_policy
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class PolicyMigrationTests(unittest.TestCase):
    def test_upgrade_is_paused_and_backup_restores_previous_device(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
            config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
            command.downgrade(config, "0007")
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic policy migration owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                consume_bootstrap(connection, code, encoded, 1001)
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                code = issue_pairing(connection, owner.token, owner.csrf, 1, 1003)
                connection.commit()
                device = enroll(connection, code, 1004)
                connection.commit()
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0013")
                self.assertTrue(load_policy(connection).paused)
                self.assertTrue(authorize_device(connection, device.token, device.device_id, 1))
            backups = list(path.parent.glob("context.db.*.dpapi"))
            self.assertEqual(len(backups), 1)
            restored = path.parent / "restored.db"
            restore_backup(backups[0], restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0007")
                self.assertFalse(authorize_device(connection, device.token, device.device_id, 1))
