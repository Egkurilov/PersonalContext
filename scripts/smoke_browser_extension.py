"""Exercise synthetic MV3 extension pairing in installed Edge against the frozen app."""

import base64
import hashlib
import http.cookiejar
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.storage.initialize import initialize_database

BASE = "http://127.0.0.1:17890"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
EXE = Path("dist/PersonalContext/PersonalContext.exe").resolve()
OPENSSL = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
CANDIDATE = "synthetic browser smoke password"


def extension_files(directory: Path, code: str, public_key: bytes) -> str:
    digest = hashlib.sha256(public_key).digest()[:16]
    extension_id = "".join(chr(ord("a") + nibble) for byte in digest for nibble in (byte >> 4, byte & 15))
    manifest = {"manifest_version": 3, "name": "Synthetic pairing smoke", "version": "1.0",
                "key": base64.b64encode(public_key).decode("ascii"), "host_permissions": ["http://127.0.0.1/*"]}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "index.html").write_text('<!doctype html><body>WAIT<script src="test.js"></script></body>', encoding="utf-8")
    script = """(async () => { try {
      const post = async (path, body, token) => fetch(BASE + path, {
        method: 'POST', headers: {'Content-Type': 'application/json', ...(token ? {'Authorization': 'Bearer ' + token} : {})},
        body: JSON.stringify(body), credentials: 'omit'});
      const enrollment = await post('/api/v1/devices/enroll', {code: CODE});
      if (!enrollment.ok) throw Error('enrollment');
      const device = await enrollment.json();
      const heartbeat = await post('/api/v1/device/heartbeat', {device_id: device.device_id}, device.token);
      if (heartbeat.status !== 204) throw Error('heartbeat');
      const denied = await post('/api/v1/device/heartbeat', {device_id: device.device_id}, 'invalid');
      if (denied.status !== 401) throw Error('authorization');
      let ownerAllowed = false;
      try { ownerAllowed = (await fetch(BASE + '/api/v1/auth/me')).ok; } catch (_) {}
      if (ownerAllowed) throw Error('owner isolation');
      document.body.textContent = 'PASS';
    } catch (_) { document.body.textContent = 'FAIL'; } })();"""
    script = script.replace("BASE", json.dumps(BASE)).replace("CODE", json.dumps(code))
    (directory / "test.js").write_text(script, encoding="utf-8")
    return extension_id


def main() -> None:
    if not EDGE.is_file() or not EXE.is_file() or not OPENSSL.is_file():
        raise RuntimeError("Installed Edge, OpenSSL and packaged application are required")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 17890))
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        database = root / "PersonalContext" / "data" / "context.db"
        database.parent.mkdir(parents=True)
        initialize_database(database)
        with closing(sqlite3.connect(database)) as connection:
            bootstrap = issue_bootstrap(connection, int(time.time()))
            connection.commit()
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(root)
        app = subprocess.Popen([str(EXE)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            deadline = time.monotonic() + 30
            while True:
                if app.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Application did not become ready")
                try:
                    with opener.open(BASE + "/readyz", timeout=1):
                        break
                except URLError:
                    time.sleep(0.2)
            def post(path: str, body: dict[str, str], csrf: str = ""):
                headers = {"Origin": BASE, "Content-Type": "application/json", "X-CSRF-Token": csrf}
                return opener.open(Request(BASE + path, data=json.dumps(body).encode(), headers=headers), timeout=5)
            with post("/api/v1/auth/bootstrap", {"code": bootstrap, "password": CANDIDATE}):
                pass
            with post("/api/v1/auth/login", {"password": CANDIDATE}) as response:
                csrf = json.load(response)["csrf"]
            key = root / "synthetic.pem"
            subprocess.run([str(OPENSSL), "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                            "-out", str(key)], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            public = subprocess.run([str(OPENSSL), "pkey", "-in", str(key), "-pubout", "-outform", "DER"], check=True,
                                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
            ext = root / "extension"
            ext.mkdir()
            extension_id = extension_files(ext, "placeholder", public)
            with post("/api/v1/devices/pairing-codes/extension",
                      {"scopes": "heartbeat", "origin": "chrome-extension://" + extension_id}, csrf) as response:
                code = json.load(response)["code"]
            extension_files(ext, code, public)
            args = [str(EDGE), "--headless=new", "--disable-gpu", "--disable-background-networking", "--no-first-run",
                    "--no-default-browser-check", f"--user-data-dir={root / 'profile'}", f"--load-extension={ext}",
                    "--virtual-time-budget=10000", "--dump-dom", f"chrome-extension://{extension_id}/index.html"]
            result = subprocess.run(args, check=False, capture_output=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != 0 or b"<body>PASS</body>" not in result.stdout:
                raise RuntimeError("Browser extension pairing did not complete")
            print("Installed Edge synthetic extension pairing and heartbeat passed")
        finally:
            app.terminate()
            app.wait(timeout=10)


if __name__ == "__main__":
    main()
