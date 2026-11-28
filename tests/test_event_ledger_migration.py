"""Synthetic schema and transaction checks for the PC-003 ledger."""

import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from personalcontext.storage.initialize import initialize_database
from personalcontext.storage.restore_security import reset_restored_access


class EventLedgerMigrationTests(unittest.TestCase):
    def test_revision_foreign_keys_uniqueness_and_atomic_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0018")
                device, source, event = (str(uuid.uuid4()) for _ in range(3))
                connection.execute("INSERT INTO devices(device_id,token_hash,scope_mask,created_at) VALUES (?,?,1,1)",
                                   (device, b"x" * 32))
                connection.execute("INSERT INTO sources VALUES (?,?,?,0,1,1,1)", (source, device, "browser"))
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("INSERT INTO jobs(idempotency_key,kind,status) VALUES ('synthetic-job','synthetic','pending')")
                statement = ("INSERT INTO events(event_id,device_id,source_id,source_event_key,body_hash,"
                                   "kind,started_at,observed_at,timezone,granularity,quality,policy_version,"
                                   "consent_scope,payload_json,provenance_json,received_at,expires_at,job_key) "
                                   "VALUES (?,?,?,?,?,'web_visit','2026-01-01T00:00:00Z',"
                                   "'2026-01-01T00:00:00Z','UTC','point','measured',1,'metadata',"
                                   "'{}','{}',1,2,'synthetic-job')")
                connection.execute(statement, (event, device, source, "synthetic-key", b"a" * 32))
                connection.rollback()
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT count(*) FROM jobs WHERE idempotency_key='synthetic-job'").fetchone()[0], 0)
                connection.execute("INSERT INTO jobs(idempotency_key,kind,status) VALUES ('synthetic-job','synthetic','pending')")
                connection.execute(statement, (event, device, source, "synthetic-key", b"a" * 32))
                connection.commit()
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement, (event, device, source, "other-key", b"a" * 32))
                connection.rollback()
                connection.execute("INSERT INTO jobs(idempotency_key,kind,status) VALUES ('synthetic-job-2','synthetic','pending')")
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement.replace("synthetic-job", "synthetic-job-2"),
                                       (str(uuid.uuid4()), device, source, "synthetic-key", b"a" * 32))
                connection.rollback()
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("UPDATE events SET job_key='missing-job' WHERE event_id=?", (event,))
                connection.rollback()
                other_device = str(uuid.uuid4())
                connection.execute("INSERT INTO devices(device_id,token_hash,scope_mask,created_at) VALUES (?,?,1,1)",
                                   (other_device, b"y" * 32))
                connection.execute("INSERT INTO jobs(idempotency_key,kind,status) VALUES ('synthetic-job-2','synthetic','pending')")
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement.replace("synthetic-job", "synthetic-job-2"),
                                       (str(uuid.uuid4()), other_device, source, "other-key", b"a" * 32))
                connection.rollback()
                reset_restored_access(connection)
                self.assertEqual(connection.execute("SELECT paused FROM sources WHERE source_id=?", (source,)).fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)
                connection.rollback()
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "src/personalcontext/migrations"))
            config.set_main_option("sqlalchemy.url", URL.create("sqlite", database=str(path)).render_as_string().replace("%", "%%"))
            with self.assertRaisesRegex(RuntimeError, "Cannot discard event ledger"):
                command.downgrade(config, "0017")
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
