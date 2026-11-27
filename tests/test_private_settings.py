import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import (
    PrivateCandidate,
    load_candidate,
    save_candidate,
)
from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore_security import reset_restored_access


class PrivateSettingsTests(unittest.TestCase):
    def test_owner_only_revision_atomicity_and_restore_forgets_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic settings owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                self.assertTrue(consume_bootstrap(connection, code, encoded, 1001))
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
                candidate = PrivateCandidate(boundary, "test-cert.pem", "test-key.pem", b"synthetic-protected")
                self.assertIsNone(load_candidate(connection))
                self.assertEqual(save_candidate(connection, owner.token, "invalid", 0, candidate, 1003).status, "forbidden")
                connection.rollback()
                self.assertEqual(save_candidate(connection, owner.token, owner.csrf, 0, candidate, 1004).status, "ok")
                connection.rollback()
                self.assertIsNone(load_candidate(connection))
                result = save_candidate(connection, owner.token, owner.csrf, 0, candidate, 1005)
                connection.commit()
                self.assertEqual(result.revision, 1)
                self.assertEqual(load_candidate(connection).revision, 1)
                self.assertEqual(save_candidate(connection, owner.token, owner.csrf, 0, candidate, 1006).status, "conflict")
                connection.rollback()
                audit = repr(connection.execute("SELECT event_type,actor,status FROM security_audit").fetchall())
                self.assertIn("private_config_update", audit)
                self.assertNotIn("synthetic-protected", audit)
                self.assertNotIn("test-key.pem", audit)
                reset_restored_access(connection)
                connection.commit()
                self.assertIsNone(load_candidate(connection))

    def test_audit_failure_rolls_back_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic settings owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                consume_bootstrap(connection, code, encoded, 1001)
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                connection.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON security_audit BEGIN SELECT RAISE(ABORT,'blocked'); END")
                connection.commit()
                boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
                candidate = PrivateCandidate(boundary, "cert.pem", "key.pem", b"synthetic-protected")
                with self.assertRaises(sqlite3.IntegrityError):
                    save_candidate(connection, owner.token, owner.csrf, 0, candidate, 1003)
                connection.rollback()
                self.assertIsNone(load_candidate(connection))
