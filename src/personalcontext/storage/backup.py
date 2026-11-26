import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from personalcontext.storage.snapshot import copy_snapshot


def backup_database(source: sqlite3.Connection, path: Path) -> Path:
    import win32crypt

    with closing(sqlite3.connect(":memory:")) as snapshot:
        copy_snapshot(source, snapshot)
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Backup integrity check failed")
        # A WAL source leaves WAL markers in the serialized database header.
        # The snapshot has no WAL file, so make its standalone format explicit.
        data = bytearray(snapshot.serialize())
        data[18:20] = b"\x01\x01"
    with closing(sqlite3.connect(":memory:")) as verification:
        verification.deserialize(bytes(data))
        if verification.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Serialized backup integrity check failed")
    encrypted = win32crypt.CryptProtectData(
        bytes(data), "PersonalContext SQLite backup", None, None, None, 1
    )
    destination = path.with_name(f"{path.name}.{uuid.uuid4().hex}.dpapi")
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination
