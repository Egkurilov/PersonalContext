"""Owner-only, non-persistent sanitizer preview; never an authorization decision."""

import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.auth.http_input import read_json
from personalcontext.auth.http_routes import check_origin, error
from personalcontext.auth.owner_sessions import authorize_mutation
from personalcontext.privacy.sanitizer.app import sanitize_app
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.web import sanitize_web

router = APIRouter(prefix="/api/v1/privacy")


@router.post("/preview", response_model=None)
async def preview(request: Request) -> Response:
    if not check_origin(request):
        return error(403, "forbidden")
    token, csrf = request.cookies.get("pc_session"), request.headers.get("x-csrf-token")

    def authorize(connection: sqlite3.Connection) -> bool:
        connection.execute("BEGIN IMMEDIATE")
        return authorize_mutation(connection, token, csrf, int(time.time()))

    if not await request.app.state.scheduler.writer.submit(authorize):
        return error(403, "forbidden")
    try:
        body = await read_json(request, limit=65536)
    except OverflowError:
        return error(413, "request_too_large")
    if body is None or body.keys() != {"kind", "source", "data"}:
        return error(400, "invalid_request")
    kind, source = body["kind"], body["source"]
    if kind not in ("web", "app") or not isinstance(source, str) or len(source) > 253:
        return error(400, "invalid_request")
    if kind == "web":
        context = SanitizerContext(allowed_domains=frozenset({source}), private=False, sensitivity="ordinary")
        web = sanitize_web(body["data"], context)
        result = {"url": web.url, "title": web.title} if web is not None else None
    else:
        context = SanitizerContext(allowed_apps=frozenset({source}), private=False, sensitivity="ordinary")
        app = sanitize_app(body["data"], context)
        result = {"app": app.app, "title": app.title} if app is not None else None
    return JSONResponse({"preview_only": True, "scenario": "public_ordinary", "result": result},
                        headers={"Cache-Control": "no-store"})
