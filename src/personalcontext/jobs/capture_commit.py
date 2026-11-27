"""Commit a trusted capture operation only while its pause ticket stays current."""

import sqlite3
from collections.abc import Callable

from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch


async def submit_capture[T](writer: Writer, latch: CaptureLatch, operation: Callable[[sqlite3.Connection], T | None],
                         validate: Callable[[sqlite3.Connection], bool]) -> T | None:
    """Run trusted callbacks in an immediate transaction; neither callback may commit."""
    ticket = latch.ticket()
    if ticket is None:
        return None

    def execute(connection: sqlite3.Connection) -> T | None:
        if not latch.allows(ticket):
            return None
        connection.execute("BEGIN IMMEDIATE")
        result = operation(connection)
        if result is None:
            if connection.in_transaction:
                connection.rollback()
            return None
        if not connection.in_transaction:
            raise RuntimeError("Capture transaction required")
        with latch.commit_window(), writer.lock:
            if (writer.closed or writer.safety_failed.is_set() or not latch.allows(ticket)
                    or validate(connection) is not True or writer.safety_failed.is_set() or not latch.allows(ticket)):
                connection.rollback()
                return None
            if not connection.in_transaction:
                raise RuntimeError("Capture transaction required")
            connection.commit()
        return result

    return await writer.submit(execute)
