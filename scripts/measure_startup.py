import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from check_listeners import verify_listeners


def measure_fresh_start(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="personalcontext-cold-start-") as directory:
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = directory
        environment["PATH"] = str(Path(environment["SYSTEMROOT"]) / "System32")
        for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "NODE_PATH"):
            environment.pop(name, None)
        started = time.monotonic()
        process = subprocess.Popen([str(executable)], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = started + 30
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as response:
                        ready = response.read() == b'{"status":"ready"}'
                except OSError:
                    time.sleep(0.1)
                    continue
                if not ready:
                    continue
                elapsed = time.monotonic() - started
                print(f"Fresh API readiness in {elapsed:.3f}s on {platform.platform()}, logical CPUs={os.cpu_count()}")
                verify_listeners(process.pid)
                browser_stub = Path(directory) / "browser_stub.py"
                browser_marker = Path(directory) / "browser_marker.txt"
                browser_stub.write_text(
                    "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text(sys.argv[2])\n",
                    encoding="utf-8",
                )
                second_environment = environment.copy()
                second_environment["BROWSER"] = (
                    f'"{Path(sys.executable).as_posix()}" "{browser_stub.as_posix()}" '
                    f'"{browser_marker.as_posix()}" %s'
                )
                subprocess.run([str(executable)], env=second_environment, check=True, timeout=15, capture_output=True)
                marker_deadline = time.monotonic() + 5
                while not browser_marker.exists() and time.monotonic() < marker_deadline:
                    time.sleep(0.05)
                if not browser_marker.exists() or browser_marker.read_text(encoding="utf-8") != "http://127.0.0.1:17890/":
                    raise RuntimeError("Second instance did not request the local portal")
                if process.poll() is not None:
                    raise RuntimeError("First instance stopped when a second instance started")
                with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as check:
                    if check.read() != b'{"status":"ready"}':
                        raise RuntimeError("First instance is no longer ready")
                print("Second instance exited while the first stayed ready")
                subprocess.run([str(executable), "--shutdown"], env=environment, check=True, timeout=20, capture_output=True)
                if process.wait(timeout=10) != 0:
                    raise RuntimeError("Application did not shut down cleanly")
                return
            raise RuntimeError("Fresh application did not become ready")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
