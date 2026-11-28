"""Owner-only filter configuration; changes always pause local capture."""

import asyncio
import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import authorize_mutation, session_active
from personalcontext.privacy.filters.input import parse_filters
from personalcontext.privacy.filters.rules import FIELDS, FilterRules
from personalcontext.privacy.filters.store import load_filters, save_filters
from personalcontext.privacy.policy_store import load_policy

router = APIRouter(prefix="/api/v1/privacy/filters")


@router.get("", response_model=None)
async def get_filters(request: Request) -> Response:
    token = request.cookies.get("pc_session")

    def read(connection: sqlite3.Connection) -> tuple[str, int, FilterRules | None]:
        if not session_active(connection, token, int(time.time())):
            return "forbidden", 0, None
        policy, rules = load_policy(connection), load_filters(connection)
        if policy is None or rules is None:
            return "unavailable", 0, None
        return "ok", policy.version, rules

    try:
        status, version, rules = await request.app.state.scheduler.writer.submit(read)
    except (sqlite3.Error, RuntimeError):
        return error(503, "unavailable")
    if status != "ok" or rules is None:
        return error(401 if status == "forbidden" else 503, status)
    return JSONResponse({"version": version, **{field: sorted(getattr(rules, field)) for field in FIELDS}},
                        headers={"Cache-Control": "no-store"})


@router.patch("", response_model=None)
async def update_filters(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    try:
        parsed = parse_filters(await read_json(request, limit=65536))
    except OverflowError:
        return error(413, "request_too_large")
    if parsed is None:
        return error(400, "invalid_request")
    version, rules = parsed
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")

    def authorize(connection: sqlite3.Connection) -> bool:
        connection.execute("BEGIN IMMEDIATE")
        return authorize_mutation(connection, token, csrf, int(time.time()))

    try:
        if not await request.app.state.scheduler.writer.submit(authorize):
            return error(403, "forbidden")
        latch = request.app.state.capture_latch
        latch.pause()
        if not await asyncio.to_thread(latch.drain, 10):
            return error(503, "pause_pending")
        result = await request.app.state.scheduler.writer.submit(
            lambda connection: save_filters(connection, token, csrf, version, rules, int(time.time())),
        )
    except (sqlite3.Error, RuntimeError):
        return error(503, "unavailable")
    if result.status != "ok":
        return error({"invalid": 400, "forbidden": 403, "conflict": 409, "unavailable": 503}[result.status], result.status)
    return JSONResponse({"version": result.version, "paused": True}, headers={"Cache-Control": "no-store"})
