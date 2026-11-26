import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from measure_startup import measure_fresh_start


def main():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/PersonalContext/PersonalContext.exe").resolve()
    for name in ("health.v1.schema.json", "readiness.v1.schema.json", "event-id.v1.schema.json", "event-kind.v1.schema.json", "event-quality.v1.schema.json", "event-timing.v1.schema.json"):
        assert (executable.parent / "_internal" / "schemas" / name).read_bytes() == (Path("schemas") / name).read_bytes()
    measure_fresh_start(executable)
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "PersonalContext" / "data"
        data_dir.mkdir(parents=True)
        database = data_dir / "context.db"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE synthetic (value TEXT)")
            connection.execute("INSERT INTO synthetic VALUES ('before migration')")
        connection.close()
        env = os.environ.copy()
        env["LOCALAPPDATA"] = directory
        process = subprocess.Popen([str(executable)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as response:
                        assert response.read() == b'{"status":"ready"}'
                    with urlopen("http://127.0.0.1:17890/", timeout=1) as response:
                        assert b"PersonalContext" in response.read()
                    with urlopen("http://127.0.0.1:17890/settings/privacy", timeout=1) as response:
                        assert b"PersonalContext" in response.read()
                    backups = list(data_dir.glob("context.db.*.dpapi"))
                    assert len(backups) == 1
                    restored = data_dir / "restored.db"
                    subprocess.run(
                        [str(executable), "--restore", str(backups[0]), str(restored)],
                        env=env, capture_output=True, timeout=20, check=True,
                    )
                    with sqlite3.connect(restored) as connection:
                        assert connection.execute("SELECT value FROM synthetic").fetchone()[0] == "before migration"
                    connection.close()
                    print("Frozen API, UI and SQLite smoke passed")
                    return
                except OSError:
                    time.sleep(0.25)
            raise RuntimeError("Frozen application did not become ready")
        finally:
            process.terminate()
            _stdout, stderr = process.communicate(timeout=10)
            if process.returncode not in (0, 1, 15):
                print(stderr.decode(errors="replace"))


if __name__ == "__main__":
    main()
