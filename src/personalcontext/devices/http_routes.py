"""Owner-authorized pairing and enrollment on the local listener."""

import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_object
from personalcontext.auth.http_routes import body_or_error, check_origin, error
from personalcontext.auth.owner_sessions import session_active
from personalcontext.auth.rate_limit import consume_attempt
from personalcontext.devices.pairing import enroll, issue_pairing, revoke_device

router = APIRouter(prefix="/api/v1/devices")
_SCOPES = {"ingest": 1, "heartbeat": 2, "config": 4}


def scope_mask(value: str) -> int | None:
    parts = value.split(",")
    if not parts or len(parts) != len(set(parts)) or any(part not in _SCOPES for part in parts):
        return None
    return sum(_SCOPES[part] for part in parts)


@router.post("/pairing-codes", response_model=None)
async def pairing_code(request: Request) -> Response:
    body = await body_or_error(request, {"scopes"})
    if isinstance(body, Response):
        return body
    mask = scope_mask(body["scopes"])
    if mask is None:
        return error(400, "invalid_request")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    code = await request.app.state.scheduler.writer.submit(
        lambda connection: issue_pairing(connection, token, csrf, mask, now=int(time.time())),
    )
    if code is None:
        return error(403, "forbidden")
    return JSONResponse({"code": code, "expires_in": 300}, headers={"Cache-Control": "no-store"})


@router.post("/enroll", response_model=None)
async def device_enroll(request: Request) -> Response:
    try:
        body = await read_object(request, {"code"})
    except OverflowError:
        return error(413, "request_too_large")
    if body is None:
        return error(400, "invalid_request")
    writer = request.app.state.scheduler.writer
    decision = await writer.submit(lambda connection: consume_attempt(connection, "device_enroll", int(time.time())))
    if not decision.allowed:
        return error(429, "rate_limited", decision.retry_after)
    device = await writer.submit(lambda connection: enroll(connection, body["code"], now=int(time.time())))
    if device is None:
        return error(401, "invalid_credentials")
    return JSONResponse({"device_id": device.device_id, "token": device.token}, headers={"Cache-Control": "no-store"})


@router.get("", response_model=None)
async def devices(request: Request) -> Response:
    token = request.cookies.get("pc_session")

    def read(connection: sqlite3.Connection) -> list[dict[str, object]] | None:
        if not session_active(connection, token, int(time.time())):
            return None
        rows = connection.execute("SELECT device_id,scope_mask,created_at,last_seen,revoked_at FROM devices ORDER BY created_at,device_id")
        return [{"device_id": item, "scope_mask": scope, "created_at": created, "last_seen": seen,
                 "revoked": revoked is not None} for item, scope, created, seen, revoked in rows]

    result = await request.app.state.scheduler.writer.submit(read)
    if result is None:
        return error(401, "unauthorized")
    return JSONResponse({"devices": result}, headers={"Cache-Control": "no-store"})


@router.post("/{device_id}/revoke", response_model=None)
async def revoke(request: Request, device_id: str) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    revoked = await request.app.state.scheduler.writer.submit(
        lambda connection: revoke_device(connection, token, csrf, device_id, now=int(time.time())),
    )
    if not revoked:
        return error(403, "forbidden")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
