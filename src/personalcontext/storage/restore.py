import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def restore_backup(backup: Path, destination: Path) -> None:
    import win32crypt

    description, data = win32crypt.CryptUnprotectData(backup.read_bytes(), None, None, None, 1)
    if description != "PersonalContext SQLite backup":
        raise ValueError("Invalid backup description")
    with closing(sqlite3.connect(":memory:")) as snapshot:
        snapshot.deserialize(data)
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Backup integrity check failed")
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        raise
    except OSError:
        if created:
            destination.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a user-bound DPAPI backup to a new file")
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    restore_backup(args.backup, args.destination)


if __name__ == "__main__":
    main()
