import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

from setup_diagnostics import observe_setup


def main():
    repository = Path(__file__).resolve().parent.parent
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not shell:
        raise RuntimeError("PowerShell is required for the fresh clone smoke")
    uv_cache = subprocess.run(
        [shell, "-NoProfile", "-File", str(repository / "scripts/uv.ps1"), "cache", "dir"],
        cwd=repository, check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    npm_cache = subprocess.run(
        [shell, "-NoProfile", "-Command", "npm config get cache"],
        cwd=repository, check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="personalcontext-fresh-clone-") as directory:
        root = Path(directory)
        clone = root / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(repository), str(clone)],
            check=True, timeout=60,
        )
        subprocess.run(["git", "checkout", "--quiet", "--detach", commit], cwd=clone, check=True, timeout=30)
        actual_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=clone, check=True, capture_output=True, text=True,
        ).stdout.strip()
        if actual_commit != commit:
            raise RuntimeError("Fresh clone did not check out the requested commit")
        original_hooks = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"], cwd=clone, capture_output=True, text=True, check=False,
        ).stdout.strip()
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(root / "localdata")
        environment["UV_CACHE_DIR"] = uv_cache
        environment["UV_OFFLINE"] = "1"
        environment["NPM_CONFIG_CACHE"] = npm_cache
        environment["NPM_CONFIG_OFFLINE"] = "true"
        environment["NPM_CONFIG_AUDIT"] = "false"
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "NODE_PATH"):
            environment.pop(name, None)
        process = subprocess.Popen(
            [shell, "-NoProfile", "-File", str(clone / "scripts/dev.ps1")], cwd=clone, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        state = {"stage": "not started", "reason": "unspecified"}
        observer = threading.Thread(target=observe_setup, args=(process.stdout, state), daemon=True)
        observer.start()
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as response:
                        ready = response.read() == b'{"status":"ready"}'
                    if ready and (root / "localdata/PersonalContext/data/context.db").is_file():
                        break
                except OSError:
                    time.sleep(0.25)
            else:
                observer.join(timeout=2)
                raise RuntimeError(f"Fresh clone failed; stage={state['stage']}; reason={state['reason']}; exit={process.poll()}")
            database = root / "localdata/PersonalContext/data/context.db"
            with closing(sqlite3.connect(database)) as connection:
                if connection.execute("SELECT count(*) FROM jobs").fetchone()[0] != 0:
                    raise RuntimeError("Fresh database contains unexpected jobs")
                events_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
                ).fetchone()
                if events_table and connection.execute("SELECT count(*) FROM events").fetchone()[0] != 0:
                    raise RuntimeError("Fresh database contains unexpected events")
            with urlopen("http://127.0.0.1:17890/", timeout=2) as response:
                if b"PersonalContext" not in response.read():
                    raise RuntimeError("Fresh clone did not serve the portal")
            hooks = subprocess.run(
                ["git", "config", "--get", "core.hooksPath"], cwd=clone, capture_output=True, text=True, check=True,
            ).stdout.strip()
            if hooks != (original_hooks or ".githooks"):
                raise RuntimeError("Git hooks path was not preserved or configured")
            subprocess.run(
                [str(clone / ".venv/Scripts/python.exe"), "-m", "personalcontext", "--shutdown"],
                cwd=clone, env=environment, capture_output=True, check=True, timeout=20,
            )
            if process.wait(timeout=20) != 0:
                raise RuntimeError("Fresh clone did not shut down cleanly")
            print("Fresh local clone: dev setup, API, portal, hooks and shutdown passed")
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False, timeout=15)
                process.wait(timeout=10)
            observer.join(timeout=5)
            process.stdout.close()


if __name__ == "__main__":
    main()
