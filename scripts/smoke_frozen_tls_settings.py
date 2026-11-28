"""Exercise Windows ACL and DPAPI TLS preparation in a frozen synthetic profile."""

import http.cookiejar
import importlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

ORIGIN = "http://127.0.0.1:17890"
CANDIDATE = "synthetic frozen settings owner"


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    fixture = importlib.import_module("test_tls_identity").TlsIdentityTests
    acl = importlib.import_module("test_tls_file_acl")
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/PersonalContext/PersonalContext.exe").resolve()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    fixture.setUpClass()
    try:
        with tempfile.TemporaryDirectory(dir=os.environ["LOCALAPPDATA"]) as directory:
            root = Path(directory) / "PersonalContext" / "data"
            tls_dir = root / "tls"
            tls_dir.mkdir(parents=True)
            shutil.copyfile(fixture.cert, tls_dir / "cert.pem")
            shutil.copyfile(fixture.encrypted, tls_dir / "key.pem")
            acl.protect_fixture(tls_dir, tls_dir / "cert.pem", tls_dir / "key.pem")
            database = root / "context.db"
            initialize_database(database)
            with closing(sqlite3.connect(database)) as connection:
                code = issue_bootstrap(connection, int(time.time()))
                connection.commit()
            env = os.environ.copy()
            env["LOCALAPPDATA"] = directory
            env["SSL_CERT_FILE"] = str(fixture.cert)
            process = subprocess.Popen([str(executable)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

            def post(path, value, csrf=None):
                headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
                if csrf:
                    headers["X-CSRF-Token"] = csrf
                request = Request(ORIGIN + path, data=json.dumps(value).encode(), headers=headers, method="POST")
                return opener.open(request, timeout=10)

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
                    csrf = json.load(response)["csrf"]
                draft = {"revision": 0, "address": "192.168.7.2", "hostname": "pc.example.test", "port": 18443,
                         "peers": ["192.168.7.0/24"], "cert": "cert.pem", "key": "key.pem",
                         "passphrase": "synthetic-test-passphrase"}
                with post("/api/v1/network/private/config", draft, csrf) as response:
                    assert json.load(response) == {"revision": 1, "enabled": False}
                with opener.open(ORIGIN + "/api/v1/network/private/config", timeout=5) as response:
                    value = json.load(response)
                    assert value["configured"] and value["enabled"] is False
                print("Frozen synthetic TLS settings smoke passed")
            finally:
                process.terminate()
                process.wait(timeout=10)
    finally:
        fixture.tearDownClass()


if __name__ == "__main__":
    main()
