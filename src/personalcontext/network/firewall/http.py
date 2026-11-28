"""Local owner-only, read-only firewall assessment; never enables the listener."""

import asyncio
import sqlite3
import sys
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.status import firewall_status
from personalcontext.network.private_settings import StoredCandidate, load_candidate

router = APIRouter(prefix="/api/v1/network/private/firewall")


@router.post("/check", response_model=None)
async def check(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary) or not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")

    def read(connection: sqlite3.Connection) -> tuple[str, StoredCandidate | None]:
        connection.execute("BEGIN IMMEDIATE")
        if not authorize_mutation(connection, token, csrf, int(time.time())):
            return "forbidden", None
        item = load_candidate(connection)
        if item is None:
            exists = connection.execute("SELECT 1 FROM private_network_candidate LIMIT 1").fetchone()
            return ("unavailable" if exists else "missing"), None
        return "ok", item

    try:
        status, candidate = await request.app.state.scheduler.writer.submit(read)
        if status != "ok" or candidate is None:
            return error({"forbidden": 403, "missing": 404, "unavailable": 503}.get(status, 503), status)
        result = await asyncio.to_thread(firewall_status, candidate.candidate.boundary, sys.executable)
        current_status, current = await request.app.state.scheduler.writer.submit(read)
    except (sqlite3.Error, RuntimeError):
        return error(503, "unavailable")
    if current_status == "forbidden":
        return error(403, "forbidden")
    if current_status != "ok" or current != candidate:
        return error(409, "changed")
    return JSONResponse({"firewall": result, "enabled": request.app.state.private_listener.active()},
                        headers={"Cache-Control": "no-store"})
