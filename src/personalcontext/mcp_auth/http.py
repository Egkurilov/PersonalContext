"""Local owner management and MCP-scoped, non-personal status endpoint."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_routes import body_or_error, check_origin, error
from personalcontext.mcp_auth.credentials import authorize, issue, revoke
from personalcontext.network.boundary import PrivateBoundary

router = APIRouter(prefix="/api/v1/mcp")


@router.post("/credentials", response_model=None)
async def create_credential(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary):
        return error(403, "forbidden")
    body = await body_or_error(request, {"scope"})
    if isinstance(body, Response):
        return body
    if body["scope"] != "status:read":
        return error(400, "invalid_request")
    owner, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    result = await request.app.state.scheduler.writer.submit(
        lambda connection: issue(connection, owner, csrf, body["scope"], int(time.time())),
    )
    if result is None:
        return error(403, "forbidden")
    return JSONResponse({"id": result.id, "token": result.token, "scope": "status:read", "expires_in": 900},
                        headers={"Cache-Control": "no-store"})


@router.post("/credentials/{identifier}/revoke", response_model=None)
async def revoke_credential(request: Request, identifier: str) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary) or not check_origin(request):
        return error(403, "forbidden")
    owner, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")
    result = await request.app.state.scheduler.writer.submit(
        lambda connection: revoke(connection, owner, csrf, identifier, int(time.time())),
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"}) if result else error(403, "forbidden")


@router.get("/status", response_model=None)
async def status(request: Request) -> Response:
    if isinstance(request.scope.get("personalcontext.boundary"), PrivateBoundary):
        return error(403, "forbidden")
    if request.query_params:
        return error(400, "invalid_request")
    headers = request.headers.getlist("authorization")
    if len(headers) != 1 or not headers[0].startswith("Bearer "):
        return error(401, "unauthorized")
    allowed = await request.app.state.scheduler.writer.submit(
        lambda connection: authorize(connection, headers[0][7:], "status:read", int(time.time())),
    )
    if not allowed:
        return error(401, "unauthorized")
    app = request.app
    ready = (getattr(app.state, "ready", False) and not app.state.scheduler.task.done()
             and not app.state.audit_housekeeping.task.done())
    return JSONResponse({"scope": "status:read", "status": "ready" if ready else "unavailable"},
                        status_code=200 if ready else 503, headers={"Cache-Control": "no-store"})
