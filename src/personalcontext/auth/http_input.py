"""Bounded, secret-safe parsing for authentication requests."""

import json

from fastapi import Request


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


async def read_json(request: Request, limit: int = 4096) -> dict[str, object] | None:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return None
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > limit:
            raise OverflowError("Request too large")
        body.extend(part)
    try:
        value = json.loads(body, object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    return value


async def read_object(request: Request, fields: set[str]) -> dict[str, str] | None:
    value = await read_json(request)
    if value is None or value.keys() != fields:
        return None
    if any(not isinstance(item, str) or len(item) > 1024 for item in value.values()):
        return None
    return {key: item for key, item in value.items() if isinstance(item, str)}
