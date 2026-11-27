import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session, session_active
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing
from personalcontext.devices.scopes import authorize_device
from personalcontext.privacy.policy_store import PolicyDraft, load_policy, save_policy
from personalcontext.storage.backup import backup_database
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore import restore_backup
from personalcontext.storage.restore_security import _REVISIONS


class RestoreSchemaCoverageTests(unittest.TestCase):
    def test_every_migration_requires_an_explicit_restore_rule(self):
        versions = Path(__file__).resolve().parent.parent / "src/personalcontext/migrations/versions"
        migrations = {path.name[:4] for path in versions.glob("[0-9][0-9][0-9][0-9]_*.py")}
        self.assertEqual(migrations, set(_REVISIONS))


@unittest.skipUnless(sys.platform == "win32", "DPAPI backup requires Windows")
class RestoreSecurityTests(unittest.TestCase):
    def test_restore_invalidates_access_and_requires_owner_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            candidate = "synthetic restore owner"
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password(candidate)
                bootstrap = issue_bootstrap(connection, 1000)
                connection.commit()
                consume_bootstrap(connection, bootstrap, encoded, 1001)
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                code = issue_pairing(connection, owner.token, owner.csrf, 1, 1003)
                connection.commit()
                device = enroll(connection, code, 1004)
                connection.commit()
                pending = issue_pairing(connection, owner.token, owner.csrf, 1, 1005)
                connection.commit()
                draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                                    frozenset({("synthetic-source", "metadata")}))
                self.assertEqual(save_policy(connection, owner.token, owner.csrf, 1, draft, 1006).status, "ok")
                connection.commit()
                backup = backup_database(connection, path)
            restored = path.parent / "restored.db"
            restore_backup(backup, restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertIsNone(find_owner_hash(connection))
                self.assertFalse(session_active(connection, owner.token, 1007))
                self.assertFalse(authorize_device(connection, device.token, device.device_id, 1))
                self.assertIsNone(enroll(connection, pending, 1007))
                connection.rollback()
                self.assertTrue(load_policy(connection).paused)
                self.assertEqual(connection.execute("SELECT count(*) FROM security_audit WHERE event_type='restore'").fetchone()[0], 1)
                replacement_code = issue_bootstrap(connection, 1010)
                connection.commit()
                replacement_hash = hash_password("synthetic replacement owner")
                self.assertTrue(consume_bootstrap(connection, replacement_code, replacement_hash, 1011))
                connection.commit()
                replacement = create_session(connection, replacement_hash, 1012)
                connection.commit()
                self.assertIsNotNone(replacement)
                self.assertTrue(load_policy(connection).paused)

    def test_unknown_or_inconsistent_schema_never_creates_destination(self):
        for corruption in ("UPDATE alembic_version SET version_num='9999'", "DROP TABLE devices",
                           "DROP TABLE alembic_version", "UPDATE alembic_version SET version_num='0002'"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "context.db"
                initialize_database(path)
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(corruption)
                    connection.commit()
                    backup = backup_database(connection, path)
                destination = path.parent / "restored.db"
                with self.assertRaises(sqlite3.DatabaseError):
                    restore_backup(backup, destination)
                self.assertFalse(destination.exists())
