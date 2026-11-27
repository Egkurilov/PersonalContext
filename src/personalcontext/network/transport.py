"""Attach a server-selected private boundary to a shared ASGI application."""

from starlette.types import ASGIApp, Receive, Scope, Send

from personalcontext.network.boundary import PrivateBoundary


class ScopedTransport:
    def __init__(self, app: ASGIApp, boundary: PrivateBoundary) -> None:
        if not isinstance(boundary, PrivateBoundary):
            raise TypeError("Private boundary required")
        self._app = app
        self._boundary = boundary

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope = dict(scope)
            scope["personalcontext.boundary"] = self._boundary
        await self._app(scope, receive, send)
