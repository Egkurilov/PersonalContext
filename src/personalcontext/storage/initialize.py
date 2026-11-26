import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL

from personalcontext.storage.backup import backup_database


def initialize_database(path: Path) -> None:
    existed = path.exists()
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent.parent / "migrations"))
    url = URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    target = ScriptDirectory.from_config(config).get_current_head()
    connection = sqlite3.connect(path, timeout=5)
    try:
        version_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        versions = connection.execute("SELECT version_num FROM alembic_version").fetchall() if version_table else []
        if existed and versions != [(target,)]:
            backup_database(connection, path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=FULL")
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        if mode is None or mode[0].lower() != "wal":
            raise sqlite3.OperationalError("SQLite WAL mode unavailable")
        connection.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(content)")
        connection.execute("DROP TABLE temp.fts_probe")
    finally:
        connection.close()
    command.upgrade(config, "head")
