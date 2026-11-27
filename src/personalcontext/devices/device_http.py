"""Device-only local endpoints; never accept an owner cookie as a bearer."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

from personalcontext.auth.http_input import read_object
from personalcontext.auth.http_routes import error
from personalcontext.devices.heartbeat import record_heartbeat

router = APIRouter(prefix="/api/v1/device")


@router.post("/heartbeat", response_model=None)
async def heartbeat(request: Request) -> Response:
    headers = request.headers.getlist("authorization")
    if len(headers) != 1 or not headers[0].startswith("Bearer "):
        return error(401, "unauthorized")
    try:
        body = await read_object(request, {"device_id"})
    except OverflowError:
        return error(413, "request_too_large")
    if body is None:
        return error(400, "invalid_request")
    token = headers[0][7:]
    accepted = await request.app.state.scheduler.writer.submit(
        lambda connection: record_heartbeat(connection, token, body["device_id"], now=int(time.time())),
    )
    if not accepted:
        return error(401, "unauthorized")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
