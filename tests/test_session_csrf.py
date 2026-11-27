import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import authorize_mutation, create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.auth.session_csrf import rotate_csrf
from personalcontext.storage.initialize import initialize_database


class SessionCsrfTests(unittest.TestCase):
    def test_rotation_rollback_expiry_and_no_plaintext_in_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic csrf owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                self.assertTrue(consume_bootstrap(connection, code, encoded, 1001))
                connection.commit()
                session = create_session(connection, encoded, 1002)
                connection.commit()
                rolled_back = rotate_csrf(connection, session.token, 1003)
                connection.rollback()
                connection.execute("BEGIN IMMEDIATE")
                self.assertTrue(authorize_mutation(connection, session.token, session.csrf, 1004))
                self.assertFalse(authorize_mutation(connection, session.token, rolled_back, 1004))
                connection.rollback()
                current = rotate_csrf(connection, session.token, 1005)
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                self.assertFalse(authorize_mutation(connection, session.token, session.csrf, 1006))
                self.assertTrue(authorize_mutation(connection, session.token, current, 1006))
                connection.rollback()
                self.assertIsNone(rotate_csrf(connection, session.token, 2802))
                connection.rollback()
            for candidate in (session.token, session.csrf, current, rolled_back):
                for file in (path, path.with_name(path.name + "-wal")):
                    if file.exists() and candidate.encode("ascii") in file.read_bytes():
                        self.fail("Session secret appeared in SQLite files")
