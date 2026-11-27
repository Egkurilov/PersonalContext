"""Owner-only policy configuration; this does not enable any collector."""

import asyncio
import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import authorize_mutation, session_active
from personalcontext.privacy.capture_policy import CapturePolicy
from personalcontext.privacy.policy_input import parse_policy
from personalcontext.privacy.policy_pause import pause_policy
from personalcontext.privacy.policy_store import PolicyResult, load_policy, save_policy

router = APIRouter(prefix="/api/v1/privacy")


def policy_response(policy: CapturePolicy, local_paused: bool) -> JSONResponse:
    assert policy.issued_at is not None and policy.expires_at is not None
    now = int(time.time())
    issued, expires = int(policy.issued_at.timestamp()), int(policy.expires_at.timestamp())
    return JSONResponse({"version": policy.version, "issued_at": issued,
                         "expires_at": expires, "paused": policy.paused,
                         "effective_paused": local_paused or policy.paused or not issued <= now < expires,
                         "local_paused": local_paused,
                         "allowed": sorted(policy.allowed_sources), "denied": sorted(policy.denied_sources),
                         "grants": [{"source": source, "scope": scope} for source, scope in sorted(policy.grants)]},
                        headers={"Cache-Control": "no-store"})


def failure(result: PolicyResult) -> JSONResponse:
    status = {"invalid": 400, "forbidden": 403, "conflict": 409, "unavailable": 503}.get(result.status, 503)
    return error(status, result.status)


@router.get("/policy", response_model=None)
async def get_policy(request: Request) -> Response:
    token = request.cookies.get("pc_session")

    def read(connection: sqlite3.Connection) -> tuple[bool, CapturePolicy | None]:
        if not session_active(connection, token, int(time.time())):
            return False, None
        return True, load_policy(connection)

    active, policy = await request.app.state.scheduler.writer.submit(read)
    if not active:
        return error(401, "unauthorized")
    return policy_response(policy, request.app.state.capture_latch.is_paused()) if policy is not None else error(503, "unavailable")


async def authorize_pause(request: Request) -> bool:
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")

    def authorize(connection: sqlite3.Connection) -> bool:
        connection.execute("BEGIN IMMEDIATE")
        return authorize_mutation(connection, token, csrf, int(time.time()))

    return bool(await request.app.state.scheduler.writer.submit(authorize))


@router.patch("/policy", response_model=None)
async def update_policy(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    latch = request.app.state.capture_latch
    request_generation = latch.generation()
    try:
        value = await read_json(request, limit=65536)
    except OverflowError:
        return error(413, "request_too_large")
    parsed = parse_policy(value)
    if parsed is None:
        return error(400, "invalid_request")
    version, draft = parsed
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    try:
        if draft.paused:
            if not await authorize_pause(request):
                return error(403, "forbidden")
            latch.pause()
        if not await asyncio.to_thread(latch.drain, 10):
            return error(503, "pause_pending")
        generation = latch.generation() if draft.paused else request_generation
        result = await request.app.state.scheduler.writer.submit(
            lambda connection: save_policy(connection, token, csrf, version, draft, now=int(time.time())),
        )
    except (sqlite3.Error, RuntimeError):
        return error(503, "unavailable")
    if result.status != "ok":
        return failure(result)
    healthy = not request.app.state.audit_housekeeping.task.done() and not request.app.state.scheduler.task.done()
    if not draft.paused and healthy and not request.app.state.scheduler.writer.closed and not request.app.state.scheduler.writer.safety_failed.is_set():
        latch.resume_if_unchanged(generation)
    return JSONResponse({"version": result.version, "local_paused": latch.is_paused()}, headers={"Cache-Control": "no-store"})


@router.post("/pause", response_model=None)
async def pause(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    try:
        if not await authorize_pause(request):
            return error(403, "forbidden")
        request.app.state.capture_latch.pause()
        if not await asyncio.to_thread(request.app.state.capture_latch.drain, 10):
            return error(503, "pause_pending")
        result = await request.app.state.scheduler.writer.submit(
            lambda connection: pause_policy(connection, token, csrf, now=int(time.time())),
        )
    except (sqlite3.Error, RuntimeError):
        return error(503, "pause_not_persisted")
    if result.status != "ok":
        return failure(result)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
