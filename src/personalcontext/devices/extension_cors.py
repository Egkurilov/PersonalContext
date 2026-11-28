"""Narrow CORS transport for owner-approved extension origins."""

import sqlite3
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from personalcontext.devices.extension_origin import origin_approved, valid_origin

_PATHS = {"/api/v1/devices/enroll": "POST", "/api/v1/device/heartbeat": "POST", "/api/v1/device/config": "GET"}
_HEADERS = {"authorization", "content-type", "x-device-id"}


async def extension_request(request: Request, origin: str) -> Response | None:
    method = _PATHS.get(request.url.path)
    if method is None or not valid_origin(origin):
        return JSONResponse({"detail": "Invalid origin"}, status_code=403)
    if request.method == "OPTIONS":
        methods = request.headers.getlist("access-control-request-method")
        headers = request.headers.getlist("access-control-request-headers")
        if methods != [method] or len(headers) > 1:
            return JSONResponse({"detail": "Invalid preflight"}, status_code=403)
        names = [part.strip().lower() for part in headers[0].split(",")] if headers else []
        if any(name not in _HEADERS for name in names) or len(names) != len(set(names)):
            return JSONResponse({"detail": "Invalid preflight"}, status_code=403)
    elif request.method != method:
        return JSONResponse({"detail": "Invalid method"}, status_code=403)
    try:
        approved = await request.app.state.scheduler.writer.submit(
            lambda connection: origin_approved(connection, origin, int(time.time())),
        )
    except (AttributeError, RuntimeError, sqlite3.Error):
        approved = False
    if not approved:
        return JSONResponse({"detail": "Invalid origin"}, status_code=403)
    request.scope["personalcontext.extension_origin"] = origin
    if request.method == "OPTIONS":
        response = Response(status_code=200, headers={"Access-Control-Allow-Methods": method,
                            "Access-Control-Allow-Headers": ", ".join(sorted(_HEADERS)), "Cache-Control": "no-store"})
        return cors_headers(response, origin)
    return None


def cors_headers(response: Response, origin: str) -> Response:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Vary"] = "Origin"
    return response
