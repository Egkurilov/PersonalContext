import os
import subprocess
from pathlib import Path


def listener_addresses(output: str, pid: int) -> set[str]:
    addresses = set()
    for line in output.splitlines():
        columns = line.split()
        if (len(columns) == 5 and columns[0] == "TCP" and columns[3] == "LISTENING"
                and columns[4] == str(pid)):
            addresses.add(columns[1])
    return addresses


def verify_listeners(pid: int) -> None:
    executable = Path(os.environ["SYSTEMROOT"]) / "System32/netstat.exe"
    addresses = set()
    for protocol in ("tcp", "tcpv6"):
        result = subprocess.run([str(executable), "-ano", "-p", protocol],
                                capture_output=True, text=True, check=True, timeout=15)
        addresses.update(listener_addresses(result.stdout, pid))
    if addresses != {"127.0.0.1:17890"}:
        raise RuntimeError("Application listeners differ from the expected loopback endpoint")
