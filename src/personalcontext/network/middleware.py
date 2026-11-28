"""Enforce a boundary selected by the ASGI server, not by request headers."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from personalcontext.devices.extension_cors import cors_headers, extension_request
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
    origins = request.headers.getlist("origin")
    extension = len(origins) == 1 and origins[0].startswith("chrome-extension://")
    failure = check_request(boundary, peer, request.url.scheme, request.headers.getlist("host"),
                            [] if extension else origins, forwarding)
    if failure is not None:
        return JSONResponse({"detail": failure[1]}, status_code=failure[0])
    if extension:
        result = await extension_request(request, origins[0])
        if result is not None:
            return result
        return cors_headers(await call_next(request), origins[0])
    return await call_next(request)
