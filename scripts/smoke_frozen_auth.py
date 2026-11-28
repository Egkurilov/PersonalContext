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

from smoke_local_credentials import check_local_credentials

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
        def post(path, value, csrf=None, bearer=None):
            headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
            if csrf:
                headers["X-CSRF-Token"] = csrf
            if bearer:
                headers["Authorization"] = f"Bearer {bearer}"
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
            with post("/api/v1/auth/rotate", {}, csrf) as response:
                csrf = json.load(response)["csrf"]
            check_local_credentials(opener, ORIGIN, csrf)
            preview = {"kind": "web", "source": "example.org",
                       "data": {"url": "https://example.org/article?tracking=synthetic"}}
            with post("/api/v1/privacy/preview", preview, csrf) as response:
                result = json.load(response)
                assert result["preview_only"] is True and result["result"]["url"] == "https://example.org/article"
            draft = {"version": 1, "paused": False, "ttl": 600, "allowed": ["synthetic-source"],
                     "denied": [], "grants": [{"source": "synthetic-source", "scope": "metadata"}]}
            request = Request(ORIGIN + "/api/v1/privacy/policy", data=json.dumps(draft).encode(), method="PATCH",
                              headers={"Origin": ORIGIN, "Content-Type": "application/json", "X-CSRF-Token": csrf})
            with opener.open(request, timeout=5) as response:
                result = json.load(response)
                assert result["version"] == 2 and result["local_paused"] is False
            with post("/api/v1/privacy/pause", {}, csrf) as response:
                assert response.status == 204
            with opener.open(ORIGIN + "/api/v1/privacy/policy", timeout=5) as response:
                result = json.load(response)
                assert result["paused"] is True and result["local_paused"] is True
            with post("/api/v1/devices/pairing-codes", {"scopes": "heartbeat"}, csrf) as response:
                pairing = json.load(response)["code"]
            with post("/api/v1/devices/enroll", {"code": pairing}) as response:
                device = json.load(response)
            with post("/api/v1/device/heartbeat", {"device_id": device["device_id"]}, bearer=device["token"]) as response:
                assert response.status == 204
            with post("/api/v1/devices/" + device["device_id"] + "/revoke", {}, csrf) as response:
                assert response.status == 204
            try:
                post("/api/v1/device/heartbeat", {"device_id": device["device_id"]}, bearer=device["token"])
            except HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError("Revoked device remains authorized")
            with opener.open(ORIGIN + "/api/v1/audit", timeout=5) as response:
                audit = response.read()
                assert b'"device_revoke"' in audit and b'"owner_session_rotate"' in audit and device["token"].encode() not in audit
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
