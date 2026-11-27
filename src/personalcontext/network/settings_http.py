"""Local owner-only preparation of a disabled private HTTPS candidate."""

import asyncio
import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import authorize_mutation, session_active
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import (
    StoredCandidate,
    load_candidate,
    save_candidate,
)
from personalcontext.network.settings_prepare import prepare_candidate

router = APIRouter(prefix="/api/v1/network/private")


@router.get("/config", response_model=None)
async def get_config(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary):
        return error(403, "forbidden")
    token = request.cookies.get("pc_session")

    def read(connection: sqlite3.Connection) -> tuple[bool, StoredCandidate | None, bool]:
        if not session_active(connection, token, int(time.time())):
            return False, None, False
        candidate = load_candidate(connection)
        if candidate is None and connection.execute("SELECT 1 FROM private_network_candidate LIMIT 1").fetchone():
            return True, None, True
        return True, candidate, False

    allowed, candidate, corrupted = await request.app.state.scheduler.writer.submit(read)
    if not allowed:
        return error(401, "unauthorized")
    if corrupted:
        return error(503, "unavailable")
    value: dict[str, object] = {"configured": candidate is not None, "revision": candidate.revision if candidate else 0,
                                "enabled": False}
    if candidate is not None:
        item, boundary = candidate.candidate, candidate.candidate.boundary
        value["settings"] = {"address": boundary.address, "hostname": boundary.hostname, "port": boundary.port,
                             "peers": list(boundary.peers), "cert": item.cert_name, "key": item.key_name}
    return JSONResponse(value, headers={"Cache-Control": "no-store"})


@router.post("/config", response_model=None)
async def set_config(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary) or not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")

    def authorize(connection: sqlite3.Connection) -> bool:
        connection.execute("BEGIN IMMEDIATE")
        return authorize_mutation(connection, token, csrf, int(time.time()))

    try:
        if not await request.app.state.scheduler.writer.submit(authorize):
            return error(403, "forbidden")
        body = await read_json(request, limit=16384)
        if body is None or type(body.get("revision")) is not int:
            return error(400, "invalid_request")
        candidate = await asyncio.to_thread(prepare_candidate, request.app.state.private_tls_dir, body)
        result = await request.app.state.scheduler.writer.submit(
            lambda connection: save_candidate(connection, token, csrf, body["revision"], candidate, int(time.time())),
        )
    except OverflowError:
        return error(413, "request_too_large")
    except ValueError:
        return error(400, "invalid_settings")
    except (sqlite3.Error, RuntimeError):
        return error(503, "unavailable")
    if result.status != "ok":
        return error({"invalid": 400, "forbidden": 403, "conflict": 409, "unavailable": 503}[result.status], result.status)
    return JSONResponse({"revision": result.revision, "enabled": False}, headers={"Cache-Control": "no-store"})
