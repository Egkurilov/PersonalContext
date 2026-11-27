import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from personalcontext.storage.snapshot import copy_snapshot


class SnapshotBusyTests(unittest.TestCase):
    def test_busy_snapshot_fails_in_bounded_time_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.db"
            with closing(sqlite3.connect(path)) as owner:
                owner.execute("CREATE TABLE sample (value TEXT)")
                owner.execute("INSERT INTO sample VALUES ('synthetic')")
                owner.commit()
                owner.execute("BEGIN EXCLUSIVE")
                with closing(sqlite3.connect(path, timeout=0.05)) as source, closing(sqlite3.connect(":memory:")) as target:
                    started = time.monotonic()
                    with self.assertRaisesRegex(sqlite3.OperationalError, "backup.*busy"):
                        copy_snapshot(source, target, busy_timeout=0.25)
                    self.assertLess(time.monotonic() - started, 3)
                owner.rollback()
                with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(":memory:")) as target:
                    copy_snapshot(source, target, busy_timeout=0.25)
                    self.assertEqual(target.execute("SELECT value FROM sample").fetchone(), ("synthetic",))
