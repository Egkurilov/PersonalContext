"""Device-bound configuration; unverified collectors receive no capture scope."""

import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_routes import error
from personalcontext.devices.scopes import CONFIG, authorize_device
from personalcontext.privacy.capture_policy import CapturePolicy
from personalcontext.privacy.policy_store import load_policy
from personalcontext.sources.read import Source, read_sources

router = APIRouter(prefix="/api/v1/device")


@router.get("/config", response_model=None)
async def config(request: Request) -> Response:
    authorizations, device_ids = request.headers.getlist("authorization"), request.headers.getlist("x-device-id")
    if len(authorizations) != 1 or not authorizations[0].startswith("Bearer ") or len(device_ids) != 1:
        return error(401, "unauthorized")
    if request.query_params:
        return error(400, "invalid_request")
    token, device_id = authorizations[0][7:], device_ids[0]
    latch = request.app.state.capture_latch
    ticket = latch.ticket()

    def read(connection: sqlite3.Connection) -> tuple[bool, CapturePolicy | None, list[Source] | None, int]:
        now = int(time.time())
        if not authorize_device(connection, token, device_id, CONFIG):
            return False, None, None, now
        return True, load_policy(connection), read_sources(connection, device_id=device_id, limit=17), now

    active, policy, rows, now = await request.app.state.scheduler.writer.submit(read)
    if not active:
        return error(401, "unauthorized")
    if policy is None or rows is None or len(rows) > 16 or policy.issued_at is None or policy.expires_at is None:
        return error(503, "unavailable")
    issued, expires = int(policy.issued_at.timestamp()), int(policy.expires_at.timestamp())
    paused = policy.paused or not issued <= now < expires or ticket is None or not latch.allows(ticket)
    values = [{"source_id": row.source_id, "kind": row.kind, "revision": row.revision,
               "owner_paused": row.paused, "paused": True, "capability": "unverified", "scopes": []}
              for row in rows]
    return JSONResponse({"policy_version": policy.version, "expires_at": now if paused else expires,
                         "paused": paused, "collection_enabled": False, "sources": values},
                        headers={"Cache-Control": "no-store"})
