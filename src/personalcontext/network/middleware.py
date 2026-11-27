"""Enforce a boundary selected by the ASGI server, not by request headers."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from personalcontext.network.boundary import (
    LocalBoundary,
    PrivateBoundary,
    check_request,
)


async def restrict_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    forwarding = [value for name in ("forwarded", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host")
                  for value in request.headers.getlist(name)]
    peer = request.client.host if request.client else None
    boundary = request.scope.get("personalcontext.boundary", LocalBoundary())
    if not isinstance(boundary, (LocalBoundary, PrivateBoundary)):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    failure = check_request(boundary, peer, request.url.scheme, request.headers.getlist("host"),
                            request.headers.getlist("origin"), forwarding)
    if failure is not None:
        return JSONResponse({"detail": failure[1]}, status_code=failure[0])
    return await call_next(request)
