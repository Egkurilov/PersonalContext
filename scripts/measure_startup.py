import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


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
                        if response.read() == b'{"status":"ready"}':
                            elapsed = time.monotonic() - started
                            print(f"Fresh API readiness in {elapsed:.3f}s on {platform.platform()}, logical CPUs={os.cpu_count()}")
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
                            if browser_marker.read_text(encoding="utf-8") != "http://127.0.0.1:17890/":
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
                except OSError:
                    time.sleep(0.1)
            raise RuntimeError("Fresh application did not become ready")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
