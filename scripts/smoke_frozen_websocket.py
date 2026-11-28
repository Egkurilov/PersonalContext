"""Check that the frozen local host cannot upgrade to WebSocket."""

import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    executable = Path("dist/PersonalContext/PersonalContext.exe").resolve()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    with tempfile.TemporaryDirectory() as directory:
        env = os.environ.copy()
        env["LOCALAPPDATA"] = directory
        process = subprocess.Popen([str(executable)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Frozen application did not become ready")
                try:
                    with urlopen("http://127.0.0.1:17890/readyz", timeout=1):
                        break
                except URLError:
                    time.sleep(0.25)
            with socket.create_connection(("127.0.0.1", 17890), timeout=5) as client:
                client.sendall(b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1:17890\r\n"
                               b"Connection: Upgrade\r\nUpgrade: websocket\r\n"
                               b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n")
                response = client.recv(1024)
                if b" 101 " in response or b"HTTP/1.1 " not in response:
                    raise AssertionError("Unexpected WebSocket upgrade")
            print("Frozen local WebSocket upgrade denied")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
