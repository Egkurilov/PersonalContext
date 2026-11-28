"""Owner issues a code bound to a single browser extension origin."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_routes import body_or_error, error
from personalcontext.devices.extension_origin import valid_origin
from personalcontext.devices.http_routes import scope_mask
from personalcontext.devices.pairing import issue_pairing

router = APIRouter(prefix="/api/v1/devices/pairing-codes")


@router.post("/extension", response_model=None)
async def issue_extension(request: Request) -> Response:
    body = await body_or_error(request, {"scopes", "origin"})
    if isinstance(body, Response):
        return body
    mask = scope_mask(body["scopes"])
    if mask is None or not valid_origin(body["origin"]):
        return error(400, "invalid_request")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    code = await request.app.state.scheduler.writer.submit(
        lambda connection: issue_pairing(connection, token, csrf, mask, int(time.time()), body["origin"]),
    )
    if code is None:
        return error(403, "forbidden")
    return JSONResponse({"code": code, "expires_in": 300}, headers={"Cache-Control": "no-store"})
