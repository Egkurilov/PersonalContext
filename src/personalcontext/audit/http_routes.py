"""Owner-only audit listing with bounded keyset pagination and no payloads."""

import re
import sqlite3
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from personalcontext.audit.record import ACTORS, EVENTS, RETENTION
from personalcontext.auth.http_routes import error
from personalcontext.auth.owner_sessions import session_active

router = APIRouter(prefix="/api/v1/audit")


def parse_query(request: Request) -> tuple[int, tuple[int, int] | None] | None:
    items = list(request.query_params.multi_items())
    if len(items) > 2 or len({key for key, _ in items}) != len(items) or any(key not in {"limit", "cursor"} for key, _ in items):
        return None
    limit_raw = request.query_params.get("limit", "100")
    cursor_raw = request.query_params.get("cursor")
    if re.fullmatch(r"[0-9]{1,3}", limit_raw) is None or not 1 <= int(limit_raw) <= 100:
        return None
    if cursor_raw is None:
        return int(limit_raw), None
    if re.fullmatch(r"[0-9]{1,16}:[0-9]{1,19}", cursor_raw) is None:
        return None
    stamp, row_id = (int(part) for part in cursor_raw.split(":"))
    if stamp > 2**53 - 1 or not 1 <= row_id <= 2**63 - 1:
        return None
    return int(limit_raw), (stamp, row_id)


def valid_row(row: tuple[object, ...]) -> bool:
    row_id, event, actor, status, stamp, correlation = row
    if (type(row_id) is not int or row_id < 1 or not isinstance(event, str) or event not in EVENTS
            or not isinstance(actor, str) or actor not in ACTORS or status not in ("success", "denied")
            or type(stamp) is not int or not 0 <= stamp <= 2**53 - 1
            or not isinstance(correlation, str) or len(correlation) != 36):
        return False
    try:
        parsed = uuid.UUID(correlation)
        return parsed.version == 4 and str(parsed) == correlation
    except ValueError:
        return False


@router.get("", response_model=None)
async def audit(request: Request) -> Response:
    query = parse_query(request)
    if query is None:
        return error(400, "invalid_request")
    limit, cursor = query
    token = request.cookies.get("pc_session")

    def read(connection: sqlite3.Connection) -> tuple[bool, list[tuple[object, ...]]]:
        now = int(time.time())
        if not session_active(connection, token, now):
            return False, []
        params: list[object] = [now - RETENTION]
        condition = "occurred_at >= ?"
        if cursor is not None:
            condition += " AND (occurred_at < ? OR (occurred_at = ? AND id < ?))"
            params.extend((cursor[0], cursor[0], cursor[1]))
        params.append(limit + 1)
        rows = connection.execute("SELECT id,event_type,actor,status,occurred_at,correlation_id FROM security_audit WHERE "
                                  + condition + " ORDER BY occurred_at DESC,id DESC LIMIT ?", params).fetchall()
        return True, rows

    active, rows = await request.app.state.scheduler.writer.submit(read)
    if not active:
        return error(401, "unauthorized")
    if not all(valid_row(row) for row in rows):
        return error(503, "unavailable")
    page = rows[:limit]
    cursor_out = f"{page[-1][4]}:{page[-1][0]}" if len(rows) > limit and page else None
    items = [{"event_type": event, "actor": actor, "target_id": None, "status": status,
              "timestamp": stamp, "correlation_id": correlation} for _, event, actor, status, stamp, correlation in page]
    return JSONResponse({"events": items, "next_cursor": cursor_out}, headers={"Cache-Control": "no-store"})
