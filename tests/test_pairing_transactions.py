import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing
from personalcontext.devices.scopes import authorize_device
from personalcontext.storage.initialize import initialize_database


class PairingTransactionTests(unittest.TestCase):
    def test_enrollment_rollback_restores_code_and_does_not_create_device(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic transaction owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                self.assertTrue(consume_bootstrap(connection, code, encoded, 1001))
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                pairing = issue_pairing(connection, owner.token, owner.csrf, 1, 1003)
                connection.commit()
                device = enroll(connection, pairing, 1004)
                connection.rollback()
                self.assertFalse(authorize_device(connection, device.token, device.device_id, 1))
                replacement = enroll(connection, pairing, 1005)
                connection.commit()
                self.assertTrue(authorize_device(connection, replacement.token, replacement.device_id, 1))

    def test_corrupt_device_scope_or_timestamp_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                encoded = hash_password("synthetic corrupt device owner")
                code = issue_bootstrap(connection, 1000)
                connection.commit()
                consume_bootstrap(connection, code, encoded, 1001)
                connection.commit()
                owner = create_session(connection, encoded, 1002)
                connection.commit()
                pairing = issue_pairing(connection, owner.token, owner.csrf, 1, 1003)
                connection.commit()
                device = enroll(connection, pairing, 1004)
                connection.commit()
                connection.execute("PRAGMA ignore_check_constraints=ON")
                for column, value in (("scope_mask", 15), ("created_at", "bad")):
                    connection.execute(f"UPDATE devices SET {column}=?", (value,))
                    self.assertFalse(authorize_device(connection, device.token, device.device_id, 1))
                    connection.rollback()
