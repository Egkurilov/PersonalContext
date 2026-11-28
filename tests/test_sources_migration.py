import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.audit.record import record_audit
from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing
from personalcontext.sources.registry import (
    create_source,
    owns_source,
    set_source_pause,
)
from personalcontext.storage.backup import backup_database
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup


def config_for(path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
    url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class SourcesMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_prior_audit_and_backup_restores_old_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            command.downgrade(config_for(path), "0009")
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                record_audit(connection, "owner_login", "owner", int(time.time()))
                connection.commit()
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0015")
                self.assertEqual(connection.execute("SELECT count(*) FROM security_audit WHERE event_type='owner_login'").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM sources").fetchone()[0], 0)
            backup, = path.parent.glob("context.db.*.dpapi")
            restored = path.parent / "restored.db"
            restore_backup(backup, restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0009")
                self.assertEqual(connection.execute("SELECT count(*) FROM security_audit WHERE event_type='owner_login'").fetchone()[0], 1)

    def test_restore_pauses_source_and_revokes_its_device(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            now = int(time.time()) - 10
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic source backup owner")
                code = issue_bootstrap(connection, now)
                connection.commit()
                consume_bootstrap(connection, code, encoded, now + 1)
                connection.commit()
                owner = create_session(connection, encoded, now + 2)
                connection.commit()
                code = issue_pairing(connection, owner.token, owner.csrf, 7, now + 3)
                connection.commit()
                device = enroll(connection, code, now + 4)
                connection.commit()
                source = create_source(connection, owner.token, owner.csrf, device.device_id, "browser", now + 5)
                connection.commit()
                set_source_pause(connection, owner.token, owner.csrf, source.source_id, 1, False, now + 6)
                connection.commit()
                backup = backup_database(connection, path)
            with self.assertRaisesRegex(RuntimeError, "Cannot downgrade"):
                command.downgrade(config_for(path), "0009")
            restored = path.parent / "restored.db"
            restore_backup(backup, restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute("SELECT paused,revision FROM sources").fetchone(), (1, 3))
                self.assertFalse(owns_source(connection, device.token, device.device_id, source.source_id))
                self.assertEqual(connection.execute("SELECT count(*) FROM owner_credentials").fetchone()[0], 0)
