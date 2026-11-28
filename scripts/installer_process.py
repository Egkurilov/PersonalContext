"""Bound installer calls without holding inherited output pipes open."""

import os
import subprocess
from pathlib import Path


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            taskkill = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"], check=True, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except (KeyError, OSError, subprocess.SubprocessError) as error:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            raise RuntimeError("Unable to stop installer process tree") from error
    else:
        process.kill()
    process.wait(timeout=10)


def run_installer(command: list[str], *, check: bool, timeout: float = 120,
                  env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env) as process:
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            _stop_process(process)
            raise
    if check and code:
        raise subprocess.CalledProcessError(code, command)
    return subprocess.CompletedProcess(command, code)
