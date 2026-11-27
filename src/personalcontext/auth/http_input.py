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


async def read_object(request: Request, fields: set[str]) -> dict[str, str] | None:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return None
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > 4096:
            raise OverflowError("Request too large")
        body.extend(part)
    try:
        value = json.loads(body, object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(value, dict) or value.keys() != fields:
        return None
    if any(not isinstance(item, str) or len(item) > 1024 for item in value.values()):
        return None
    return value
