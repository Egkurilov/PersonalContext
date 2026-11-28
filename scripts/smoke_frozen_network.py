"""Check default listeners for a frozen process using synthetic local data."""

import base64
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

QUERY = r"""
$ErrorActionPreference = 'Stop'
$pcIds = @([int]$env:PC_SMOKE_PID)
for ($pcIndex = 0; $pcIndex -lt $pcIds.Count; $pcIndex++) {
    if ($pcIds.Count -gt 32) { throw 'Unexpected process tree' }
    $pcChildren = @(Get-CimInstance Win32_Process -Filter ('ParentProcessId=' + $pcIds[$pcIndex]))
    foreach ($pcChild in $pcChildren) { $pcIds += [int]$pcChild.ProcessId }
}
$pcTcp = @(); $pcUdp = @()
foreach ($pcId in $pcIds) {
    try { $pcTcp += @(Get-NetTCPConnection -OwningProcess $pcId -State Listen -ErrorAction Stop) }
    catch { if ($_.CategoryInfo.Category -ne 'ObjectNotFound') { throw } }
    try { $pcUdp += @(Get-NetUDPEndpoint -OwningProcess $pcId -ErrorAction Stop) }
    catch { if ($_.CategoryInfo.Category -ne 'ObjectNotFound') { throw } }
}
if ($pcTcp.Count -ne 1 -or $pcTcp[0].LocalAddress -ne '127.0.0.1' -or
    $pcTcp[0].LocalPort -ne 17890 -or $pcUdp.Count -ne 0) {
    throw 'Unexpected listener'
}
exit 0
"""


def wait_ready(process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError("Frozen application did not become ready")


def main():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    executable = Path("dist/PersonalContext/PersonalContext.exe").resolve()
    with tempfile.TemporaryDirectory() as directory:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = directory
        process = subprocess.Popen([str(executable)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            wait_ready(process)
            env["PC_SMOKE_PID"] = str(process.pid)
            shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            encoded = base64.b64encode(QUERY.encode("utf-16le")).decode("ascii")
            for _ in range(2):
                subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, check=True)
                if process.poll() is not None:
                    raise RuntimeError("Frozen application stopped during inspection")
        finally:
            process.terminate()
            process.wait(timeout=10)
    print("Frozen default network listeners verified")


if __name__ == "__main__":
    main()
