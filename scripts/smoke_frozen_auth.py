"""Exercise frozen loopback authentication using only a synthetic database."""

import http.cookiejar
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic frozen password"


def main():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/PersonalContext/PersonalContext.exe").resolve()
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "PersonalContext" / "data" / "context.db"
        database.parent.mkdir(parents=True)
        initialize_database(database)
        with closing(sqlite3.connect(database)) as connection:
            code = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        env = os.environ.copy()
        env["LOCALAPPDATA"] = directory
        process = subprocess.Popen([str(executable)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def post(path, value, csrf=None):
            headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
            if csrf:
                headers["X-CSRF-Token"] = csrf
            request = Request(ORIGIN + path, data=json.dumps(value).encode(), headers=headers, method="POST")
            return opener.open(request, timeout=5)

        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Frozen application did not become ready")
                try:
                    with opener.open(ORIGIN + "/readyz", timeout=1) as response:
                        if response.status == 200:
                            break
                except URLError:
                    time.sleep(0.25)
            with post("/api/v1/auth/bootstrap", {"code": code, "password": CANDIDATE}) as response:
                assert response.status == 204
            with post("/api/v1/auth/login", {"password": CANDIDATE}) as response:
                assert response.status == 200
            with opener.open(ORIGIN + "/api/v1/auth/me", timeout=5) as response:
                assert json.load(response) == {"role": "owner"}
            with post("/api/v1/auth/csrf", {}) as response:
                csrf = json.load(response)["csrf"]
            with post("/api/v1/auth/logout", {}, csrf) as response:
                assert response.status == 204
            try:
                opener.open(ORIGIN + "/api/v1/auth/me", timeout=5)
            except HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError("Logged-out session remains authorized")
            print("Frozen synthetic authentication smoke passed")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
