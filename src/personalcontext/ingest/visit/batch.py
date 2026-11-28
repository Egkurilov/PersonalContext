"""Bounded internal batches; caller must supply a trusted classification context."""

import json
from collections.abc import Callable
from datetime import datetime

from personalcontext.ingest.visit.service import VisitResult, submit_web_visit
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.privacy.sanitizer.rules import SanitizerContext

_MAX_BYTES = 1024 * 1024
_MAX_ITEMS = 100


class InvalidBatch(ValueError):
    """The envelope is malformed or exceeds a transport-independent limit."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidBatch("Invalid batch")
        result[key] = value
    return result


def _constant(_value: str) -> object:
    raise InvalidBatch("Invalid batch")


def _parse(raw: object) -> list[object]:
    if type(raw) is not bytes or len(raw) > _MAX_BYTES:
        raise InvalidBatch("Invalid batch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidBatch("Invalid batch") from error
    if type(value) is not list or len(value) > _MAX_ITEMS:
        raise InvalidBatch("Invalid batch")
    return value


async def submit_visit_batch(writer: Writer, latch: CaptureLatch, token: object, device_id: object, raw: object,
                             context: SanitizerContext, *, origin: object = None,
                             clock: Callable[[], datetime] | None = None) -> list[VisitResult]:
    """Each result follows its own durable commit; an interrupted batch can be retried."""
    values = _parse(raw)
    results: list[VisitResult] = []
    for value in values:
        result = await submit_web_visit(writer, latch, token, device_id, value, context, origin=origin, clock=clock)
        results.append(result)
    return results
