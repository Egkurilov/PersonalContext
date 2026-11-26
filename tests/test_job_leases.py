import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.jobs import repository
from personalcontext.storage.initialize import initialize_database


class LeaseTests(unittest.TestCase):
    def test_expired_lease_recovers_and_stale_completion_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                repository.enqueue(connection, "fixture", "one")
                connection.commit()
                first = repository.claim(connection, ("fixture",), -1)
                connection.commit()
                second = repository.claim(connection, ("fixture",), 60)
                connection.commit()
                self.assertEqual(second[2], 2)
                repository.finish(connection, "one", first[3], 1, True)
                connection.commit()
                self.assertEqual(connection.execute("SELECT status FROM jobs").fetchone()[0], "running")
                repository.finish(connection, "one", second[3], 2, True)
                connection.commit()
                self.assertEqual(connection.execute("SELECT status FROM jobs").fetchone()[0], "done")

    def test_failures_retry_and_fifth_attempt_is_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            initialize_database(path)
            with closing(sqlite3.connect(path)) as connection:
                repository.enqueue(connection, "fixture", "two")
                connection.commit()
                for attempt in range(1, 6):
                    job = repository.claim(connection, ("fixture",), 60)
                    connection.commit()
                    self.assertEqual(job[2], attempt)
                    repository.finish(connection, "two", job[3], attempt, False)
                    connection.commit()
                    status, retry_at = connection.execute("SELECT status,retry_at FROM jobs").fetchone()
                    self.assertEqual(status, "failed" if attempt == 5 else "pending")
                    self.assertGreater(retry_at, time.time())
                    connection.execute("UPDATE jobs SET retry_at=0")
                    connection.commit()
                self.assertIsNone(repository.claim(connection, ("fixture",), 60))
                connection.commit()
