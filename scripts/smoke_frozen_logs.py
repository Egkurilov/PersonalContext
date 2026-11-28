"""Check frozen process diagnostics with synthetic request canaries."""

import http.client
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/PersonalContext/PersonalContext.exe").resolve()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    query_canary, body_canary = "syntheticQueryCanary9472", "syntheticBodyCanary8361"
    with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile() as output:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = directory
        process = subprocess.Popen([str(executable)], env=env, stdout=output, stderr=output)
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Frozen application did not become ready")
                try:
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=1) as response:
                        if response.status == 200:
                            break
                except URLError:
                    time.sleep(0.25)
            with socket.create_connection(("127.0.0.1", 17890), timeout=5) as invalid:
                invalid.sendall(b"not an HTTP request\r\n\r\n")
                invalid.recv(1024)
            connection = http.client.HTTPConnection("127.0.0.1", 17890, timeout=5)
            try:
                connection.request("POST", f"/api/v1/auth/login?token={query_canary}",
                                   body=f'{{"password":"{body_canary}"',
                                   headers={"Origin": "http://127.0.0.1:17890", "Content-Type": "application/json"})
                assert connection.getresponse().status == 400
            finally:
                connection.close()
        finally:
            process.terminate()
            process.wait(timeout=10)
        output.seek(0)
        logs = output.read()
        assert b"Invalid HTTP request received" in logs, "Log capture positive control failed"
        assert query_canary.encode() not in logs and body_canary.encode() not in logs
    print("Frozen synthetic diagnostic canary smoke passed")


if __name__ == "__main__":
    main()
