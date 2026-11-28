"""Unimplemented WebSockets must not bypass the HTTP security boundary."""

import tempfile
import unittest
from pathlib import Path

from fastapi import WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from personalcontext.app import create_app
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.transport import ScopedTransport


class WebsocketBoundaryTests(unittest.TestCase):
    def test_no_websocket_can_bypass_local_or_private_request_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "context.db")

            @app.websocket("/synthetic-ws")
            async def synthetic(websocket: WebSocket):
                await websocket.accept()
                await websocket.send_text("unexpected")

            boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
            cases = ((app, "http://127.0.0.1:17890", ("127.0.0.1", 1)),
                     (ScopedTransport(app, boundary), "https://pc.example.test:18443", ("192.168.7.9", 1)))
            for target, base, peer in cases:
                with (self.subTest(base=base), TestClient(target, base_url=base, client=peer) as client,
                      self.assertRaises(WebSocketDisconnect),
                      client.websocket_connect("/synthetic-ws", headers={"Origin": base}) as socket):
                    socket.receive_text()
