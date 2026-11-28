"""Bound installer calls without holding inherited output pipes open."""

import subprocess


def run_installer(command: list[str], *, check: bool, timeout: float = 120) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=check)
