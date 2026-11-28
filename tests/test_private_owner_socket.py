"""Exercise owner authentication over a real local private-interface TLS socket."""

import http.client
import ipaddress
import json
import socket
import ssl
import tempfile
import time
import unittest
from contextlib import nullcontext
from functools import partial
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

import test_device_http as fixture
import test_tls_identity as tls_fixture
import uvicorn
from fastapi.testclient import TestClient

from personalcontext.app import create_app
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.uvicorn_config import private_server_config


def private_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            address = ipaddress.ip_address(probe.getsockname()[0])
        allowed = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        return str(address) if any(address in ipaddress.ip_network(net) for net in allowed) else None
    except OSError:
        return None


def request(address, port, context, method, path, headers=None, data=None):
    body = json.dumps(data).encode() if data is not None else b""
    values = {"Host": f"pc.example.test:{port}", "Connection": "close", **(headers or {})}
    if data is not None:
        values.update({"Content-Type": "application/json", "Content-Length": str(len(body))})
    wire = (f"{method} {path} HTTP/1.1\r\n" + "".join(f"{key}: {value}\r\n" for key, value in values.items())
            + "\r\n").encode() + body
    with (socket.create_connection((address, port), timeout=5) as raw,
          context.wrap_socket(raw, server_hostname="pc.example.test") as secured):
        secured.sendall(wire)
        response = http.client.HTTPResponse(secured)
        response.begin()
        return response.status, dict(response.getheaders()), response.read()


@unittest.skipUnless(tls_fixture.openssl_path(), "OpenSSL is required for synthetic TLS certificates")
class PrivateOwnerSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tls_fixture.TlsIdentityTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tls_fixture.TlsIdentityTests.tearDownClass()

    def test_private_interface_owner_cookie_and_csrf(self):
        address = private_address()
        if address is None:
            self.skipTest("No eligible private IPv4 interface")
        identity = tls_fixture.TlsIdentityTests
        server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_tls.load_cert_chain(identity.cert, identity.key)
        client_tls = ssl.create_default_context(cafile=str(identity.cert))
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            try:
                listener.bind((address, 0))
            except OSError:
                self.skipTest("Private IPv4 interface cannot be bound")
            listener.listen(16)
            port = listener.getsockname()[1]
            boundary = PrivateBoundary.create(address, "pc.example.test", port, [address + "/32"])
            app = create_app(Path(directory) / "context.db")
            with TestClient(app, base_url=fixture.ORIGIN, client=("127.0.0.1", 1000)) as client:
                from personalcontext.auth.bootstrap_store import issue_bootstrap

                def issue(connection):
                    return issue_bootstrap(connection, int(time.time()))

                code = client.portal.call(app.state.scheduler.writer.submit, issue)
                owner = {"Origin": fixture.ORIGIN}
                self.assertEqual(client.post("/api/v1/auth/bootstrap", headers=owner,
                                             json={"code": code, "password": fixture.CANDIDATE}).status_code, 204)
                with (patch("personalcontext.network.uvicorn_config.validated_tls_material",
                            return_value=nullcontext((identity.cert, identity.key))),
                      patch("personalcontext.network.uvicorn_config.vault_server_context", return_value=server_tls)):
                    config = private_server_config(app, boundary, identity.cert, identity.key, b"synthetic")
                server = uvicorn.Server(config)
                running = client.portal.start_task_soon(partial(server.serve, sockets=[listener]))
                try:
                    deadline = time.monotonic() + 10
                    while not server.started and not running.done() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(server.started)
                    origin = {"Origin": f"https://pc.example.test:{port}"}
                    call = partial(request, address, port, client_tls)
                    self.assertEqual(call("GET", "/healthz", {"Host": "evil.example"})[0], 400)
                    self.assertEqual(call("POST", "/api/v1/auth/bootstrap", origin, {"code": "synthetic", "password": fixture.CANDIDATE})[0], 403)
                    status, headers, body = call("POST", "/api/v1/auth/login", origin, {"password": fixture.CANDIDATE})
                    self.assertEqual(status, 200)
                    cookie = SimpleCookie(headers["set-cookie"])["pc_session"]
                    self.assertTrue(cookie["secure"] and cookie["httponly"])
                    self.assertEqual(cookie["samesite"].lower(), "strict")
                    csrf = json.loads(body)["csrf"]
                    auth = {**origin, "Cookie": f"pc_session={cookie.value}"}
                    self.assertEqual(call("GET", "/api/v1/auth/me", auth)[0], 200)
                    self.assertEqual(call("POST", "/api/v1/auth/logout", auth)[0], 403)
                    self.assertEqual(call("POST", "/api/v1/auth/logout", {**auth, "Origin": "https://evil.example", "X-CSRF-Token": csrf})[0], 403)
                    self.assertEqual(call("POST", "/api/v1/auth/logout", {**auth, "X-CSRF-Token": csrf})[0], 204)
                    self.assertEqual(call("GET", "/api/v1/auth/me", auth)[0], 401)
                finally:
                    server.should_exit = True
                    running.result(timeout=10)
