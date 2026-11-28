"""Local owner-only private listener controls; always off after restart."""

import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.listener.read import audit_stop

router = APIRouter(prefix="/api/v1/network/private")


@router.post("/start", response_model=None)
async def start(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary) or not check_origin(request):
        return error(403, "forbidden")
    try:
        body = await read_json(request, limit=1024)
        if body is None or set(body) != {"revision"} or type(body["revision"]) is not int:
            return error(400, "invalid_request")
        result = await request.app.state.private_listener.start(
            request.cookies.get("pc_session"), request.headers.get("x-csrf-token"), body["revision"],
        )
    except OverflowError:
        return error(413, "request_too_large")
    except (sqlite3.Error, RuntimeError, TimeoutError):
        return error(503, "unavailable")
    if result != "ok":
        return error({"invalid": 400, "forbidden": 403, "conflict": 409, "unavailable": 503}.get(result, 503), result)
    return JSONResponse({"enabled": True, "revision": body["revision"], "firewall_monitoring": "periodic"},
                        headers={"Cache-Control": "no-store"})


@router.post("/stop", response_model=None)
async def stop(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary) or not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")

    def authorize(connection: sqlite3.Connection) -> bool:
        connection.execute("BEGIN IMMEDIATE")
        return authorize_mutation(connection, token, csrf, int(time.time()))

    try:
        if not await request.app.state.scheduler.writer.submit(authorize):
            return error(403, "forbidden")
        await request.app.state.private_listener.stop()
        await request.app.state.scheduler.writer.submit(lambda c: audit_stop(c, "owner"))
    except (sqlite3.Error, RuntimeError):
        return error(503, "unavailable")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
