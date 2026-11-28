"""Owner-only source registration and local pause controls."""

import re
import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import body_or_error, check_origin, error
from personalcontext.auth.owner_sessions import session_active
from personalcontext.devices.scopes import valid_device_id
from personalcontext.sources.read import Source, read_sources
from personalcontext.sources.registry import (
    SourceResult,
    create_source,
    set_source_pause,
)

router = APIRouter(prefix="/api/v1/sources")


def failure(result: SourceResult) -> JSONResponse:
    status = {"invalid": 400, "forbidden": 403, "conflict": 409, "unavailable": 503}.get(result.status, 503)
    return error(status, result.status)


def parse_query(request: Request) -> tuple[int, tuple[int, str] | None] | None:
    items = list(request.query_params.multi_items())
    if len(items) > 2 or len({key for key, _ in items}) != len(items) or any(key not in {"limit", "cursor"} for key, _ in items):
        return None
    limit_raw, cursor = request.query_params.get("limit", "100"), request.query_params.get("cursor")
    if re.fullmatch(r"[0-9]{1,3}", limit_raw) is None or not 1 <= int(limit_raw) <= 500:
        return None
    if cursor is None:
        return int(limit_raw), None
    parts = cursor.split(":")
    if len(parts) != 2 or re.fullmatch(r"[0-9]{1,16}", parts[0]) is None or not valid_device_id(parts[1]):
        return None
    stamp = int(parts[0])
    return (int(limit_raw), (stamp, parts[1])) if stamp <= 2**53 - 1 else None


@router.get("", response_model=None)
async def sources(request: Request) -> Response:
    query = parse_query(request)
    if query is None:
        return error(400, "invalid_request")
    limit, cursor = query
    token = request.cookies.get("pc_session")

    def read(connection: sqlite3.Connection) -> tuple[bool, list[Source] | None]:
        if not session_active(connection, token, int(time.time())):
            return False, None
        return True, read_sources(connection, cursor=cursor, limit=limit + 1)

    active, rows = await request.app.state.scheduler.writer.submit(read)
    if not active:
        return error(401, "unauthorized")
    if rows is None:
        return error(503, "unavailable")
    page = rows[:limit]
    next_cursor = f"{page[-1].created_at}:{page[-1].source_id}" if len(rows) > limit and page else None
    values = [{"source_id": row.source_id, "device_id": row.device_id, "kind": row.kind, "paused": row.paused,
               "revision": row.revision, "created_at": row.created_at, "updated_at": row.updated_at,
               "capability": "unverified"} for row in page]
    return JSONResponse({"sources": values, "next_cursor": next_cursor}, headers={"Cache-Control": "no-store"})


@router.post("", response_model=None)
async def register(request: Request) -> Response:
    body = await body_or_error(request, {"device_id", "kind"})
    if isinstance(body, Response):
        return body
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    result = await request.app.state.scheduler.writer.submit(
        lambda connection: create_source(connection, token, csrf, body["device_id"], body["kind"], int(time.time())),
    )
    if result.status != "ok":
        return failure(result)
    return JSONResponse({"source_id": result.source_id, "revision": result.revision, "paused": True,
                         "capability": "unverified"}, headers={"Cache-Control": "no-store"})


@router.patch("/{source_id}", response_model=None)
async def update(request: Request, source_id: str) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    try:
        body = await read_json(request)
    except OverflowError:
        return error(413, "request_too_large")
    if body is None or body.keys() != {"revision", "paused"}:
        return error(400, "invalid_request")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    result = await request.app.state.scheduler.writer.submit(
        lambda connection: set_source_pause(connection, token, csrf, source_id, body["revision"], body["paused"], int(time.time())),
    )
    if result.status != "ok":
        return failure(result)
    return JSONResponse({"revision": result.revision, "capability": "unverified"}, headers={"Cache-Control": "no-store"})
