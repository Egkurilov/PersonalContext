"""Owner session rotation on the selected authenticated transport."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_routes import _COOKIE, check_origin, error
from personalcontext.auth.session_csrf import rotate_session

router = APIRouter(prefix="/api/v1/auth")


@router.post("/rotate", response_model=None)
async def rotate(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    token, csrf_token = request.cookies.get(_COOKIE), request.headers.get("x-csrf-token")
    value = await request.app.state.scheduler.writer.submit(
        lambda connection: rotate_session(connection, token, csrf_token, int(time.time())),
    )
    if value is None:
        return error(403, "forbidden")
    response = JSONResponse({"csrf": value.csrf}, headers={"Cache-Control": "no-store"})
    response.set_cookie(_COOKIE, value.token, max_age=1800, httponly=True, samesite="strict", path="/",
                        secure=request.url.scheme == "https")
    return response
