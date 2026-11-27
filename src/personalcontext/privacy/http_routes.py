"""Owner-only policy configuration; this does not enable any collector."""

import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import session_active
from personalcontext.privacy.capture_policy import CapturePolicy
from personalcontext.privacy.policy_input import parse_policy
from personalcontext.privacy.policy_pause import pause_policy
from personalcontext.privacy.policy_store import PolicyResult, load_policy, save_policy

router = APIRouter(prefix="/api/v1/privacy")


def policy_response(policy: CapturePolicy) -> JSONResponse:
    assert policy.issued_at is not None and policy.expires_at is not None
    now = int(time.time())
    issued, expires = int(policy.issued_at.timestamp()), int(policy.expires_at.timestamp())
    return JSONResponse({"version": policy.version, "issued_at": issued,
                         "expires_at": expires, "paused": policy.paused,
                         "effective_paused": policy.paused or not issued <= now < expires,
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
    return policy_response(policy) if policy is not None else error(503, "unavailable")


@router.patch("/policy", response_model=None)
async def update_policy(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    try:
        value = await read_json(request, limit=65536)
    except OverflowError:
        return error(413, "request_too_large")
    parsed = parse_policy(value)
    if parsed is None:
        return error(400, "invalid_request")
    version, draft = parsed
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    result = await request.app.state.scheduler.writer.submit(
        lambda connection: save_policy(connection, token, csrf, version, draft, now=int(time.time())),
    )
    if result.status != "ok":
        return failure(result)
    return JSONResponse({"version": result.version}, headers={"Cache-Control": "no-store"})


@router.post("/pause", response_model=None)
async def pause(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    result = await request.app.state.scheduler.writer.submit(
        lambda connection: pause_policy(connection, token, csrf, now=int(time.time())),
    )
    if result.status != "ok":
        return failure(result)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
