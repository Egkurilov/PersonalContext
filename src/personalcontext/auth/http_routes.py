"""Loopback authentication endpoints; native bootstrap issuance is separate."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_object
from personalcontext.auth.owner_sessions import session_active
from personalcontext.auth.session_csrf import rotate_csrf, rotate_session

router = APIRouter(prefix="/api/v1/auth")
_ORIGIN = "http://127.0.0.1:17890"
_COOKIE = "pc_session"


def error(status: int, code: str, retry: int | None = None) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if retry is not None and retry > 0:
        headers["Retry-After"] = str(retry)
    return JSONResponse({"error": code}, status_code=status, headers=headers)


def check_origin(request: Request) -> bool:
    return request.headers.getlist("origin") == [_ORIGIN]


async def body_or_error(request: Request, fields: set[str]) -> dict[str, str] | Response:
    if not check_origin(request):
        return error(403, "forbidden")
    try:
        body = await read_object(request, fields)
    except OverflowError:
        return error(413, "request_too_large")
    return body if body is not None else error(400, "invalid_request")


def failure(status: str, retry: int | None) -> JSONResponse:
    if status == "limited":
        return error(429, "rate_limited", retry)
    if status == "unavailable":
        return error(503, "unavailable")
    return error(401, "invalid_credentials")


@router.post("/bootstrap", response_model=None)
async def bootstrap(request: Request) -> Response:
    body = await body_or_error(request, {"code", "password"})
    if isinstance(body, Response):
        return body
    result = await request.app.state.owner_bootstrap.complete(body["code"], body["password"])
    if result.status != "ok":
        return failure(result.status, result.retry_after)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/login", response_model=None)
async def login(request: Request) -> Response:
    body = await body_or_error(request, {"password"})
    if isinstance(body, Response):
        return body
    result = await request.app.state.owner_login.authenticate(body["password"])
    if result.status != "ok" or result.session is None:
        return failure(result.status, result.retry_after)
    response = JSONResponse({"csrf": result.session.csrf}, headers={"Cache-Control": "no-store"})
    response.set_cookie(_COOKIE, result.session.token, max_age=1800, httponly=True, samesite="strict", path="/")
    return response


@router.get("/me", response_model=None)
async def me(request: Request) -> Response:
    token = request.cookies.get(_COOKIE)
    active = await request.app.state.scheduler.writer.submit(
        lambda connection: session_active(connection, token=token, now=int(time.time())),
    )
    if not active:
        return error(401, "unauthorized")
    return JSONResponse({"role": "owner"}, headers={"Cache-Control": "no-store"})


@router.post("/csrf", response_model=None)
async def csrf(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    token = request.cookies.get(_COOKIE)
    value = await request.app.state.scheduler.writer.submit(
        lambda connection: rotate_csrf(connection, token=token, now=int(time.time())),
    )
    if value is None:
        return error(401, "unauthorized")
    return JSONResponse({"csrf": value}, headers={"Cache-Control": "no-store"})


@router.post("/logout", response_model=None)
async def logout(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    revoked = await request.app.state.owner_login.logout(
        request.cookies.get(_COOKIE), request.headers.get("x-csrf-token"),
    )
    if not revoked:
        return error(403, "forbidden")
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(_COOKIE, path="/", httponly=True, samesite="strict")
    return response


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
    response.set_cookie(_COOKIE, value.token, max_age=1800, httponly=True, samesite="strict", path="/")
    return response
