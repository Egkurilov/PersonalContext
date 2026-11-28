"""Reject WebSockets until an authenticated protocol contract exists."""

from starlette.types import ASGIApp, Receive, Scope, Send


class RejectWebSockets:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)
