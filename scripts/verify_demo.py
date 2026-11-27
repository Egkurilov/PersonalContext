import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen


def verify_demo(root: Path) -> None:
    database = root / "localdata/PersonalContext/demo/context.db"
    with closing(sqlite3.connect(database)) as connection:
        if connection.execute("SELECT count(*) FROM jobs").fetchone()[0] != 0:
            raise RuntimeError("Fresh database contains unexpected jobs")
        events_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone()
        if events_table and connection.execute("SELECT count(*) FROM events").fetchone()[0] != 0:
            raise RuntimeError("Fresh database contains unexpected events")
    with urlopen("http://127.0.0.1:17890/api/v1/demo", timeout=2) as response:
        body = json.loads(response.read())
        if not body.get("demo") or len(body.get("items", [])) != 2:
            raise RuntimeError("Synthetic demo dataset unavailable")
    if (root / "localdata/PersonalContext/data/context.db").exists():
        raise RuntimeError("Demo created a production database")
