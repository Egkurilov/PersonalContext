import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import (
    authorize_mutation,
    create_session,
    session_active,
)
from personalcontext.auth.password_hash import hash_password
from personalcontext.auth.session_csrf import rotate_session
from personalcontext.storage.initialize import initialize_database


class SessionRotationTests(unittest.TestCase):
    def test_rotation_is_atomic_and_does_not_extend_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic session rotation")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                self.assertTrue(consume_bootstrap(connection, code, encoded, 1001))
                connection.commit()
                old = create_session(connection, encoded, 1002)
                connection.commit()
                self.assertIsNone(rotate_session(connection, old.token, "invalid", 1003))
                connection.rollback()
                rolled = rotate_session(connection, old.token, old.csrf, 1004)
                connection.rollback()
                self.assertTrue(session_active(connection, old.token, 1005))
                self.assertFalse(session_active(connection, rolled.token, 1005))
                current = rotate_session(connection, old.token, old.csrf, 1006)
                connection.commit()
                events = connection.execute("SELECT event_type,actor,status FROM security_audit WHERE event_type='owner_session_rotate'").fetchall()
                self.assertEqual(events, [("owner_session_rotate", "owner", "success")])
                self.assertFalse(session_active(connection, old.token, 1007))
                self.assertTrue(session_active(connection, current.token, 1007))
                connection.execute("BEGIN IMMEDIATE")
                self.assertFalse(authorize_mutation(connection, current.token, old.csrf, 1007))
                self.assertTrue(authorize_mutation(connection, current.token, current.csrf, 1007))
                connection.rollback()
                self.assertIsNone(rotate_session(connection, old.token, old.csrf, 1008))
                connection.rollback()
                self.assertFalse(session_active(connection, current.token, 2802))
                self.assertIsNone(rotate_session(connection, current.token, current.csrf, 2802))
                connection.rollback()
            for secret in (old.token, old.csrf, current.token, current.csrf, rolled.token, rolled.csrf):
                for file in (path, path.with_name(path.name + "-wal")):
                    if file.exists() and secret.encode("ascii") in file.read_bytes():
                        self.fail("Session secret appeared in database")
