import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DemoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    demo: Literal[True]
    items: tuple[str, ...]


DEMO_ITEMS = (
    "Синтетический материал о локальном поиске",
    "Synthetic article about vector indexes",
)


def seed_demo(path: Path) -> DemoResponse:
    encoded = json.dumps(DEMO_ITEMS, ensure_ascii=False, separators=(",", ":"))
    with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO app_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING",
            ("demo.seed.v1", encoded),
        )
        row = connection.execute("SELECT value FROM app_metadata WHERE key=?", ("demo.seed.v1",)).fetchone()
        if row is None or row[0] != encoded:
            raise ValueError("Invalid demo seed")
        return DemoResponse(demo=True, items=tuple(json.loads(row[0])))
