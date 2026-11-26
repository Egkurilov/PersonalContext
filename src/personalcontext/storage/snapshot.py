import sqlite3
import time


def copy_snapshot(source: sqlite3.Connection, target: sqlite3.Connection, *, busy_timeout: float = 5.0) -> None:
    last_progress = time.monotonic()

    def progress(status: int, _remaining: int, _total: int) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if status & 0xff in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            if now - last_progress >= busy_timeout:
                raise sqlite3.OperationalError("SQLite backup remained busy")
        else:
            last_progress = now

    source.backup(target, pages=128, progress=progress, sleep=0.05)
