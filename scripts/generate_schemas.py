import json
from pathlib import Path

from pydantic import TypeAdapter

from personalcontext.contracts.event_common import (
    EventId,
    EventKind,
    EventQuality,
    EventTiming,
)
from personalcontext.contracts.event_temporal import EventTemporal
from personalcontext.contracts.health import HealthResponse, ReadinessResponse
from personalcontext.ingest.active.model import WebActive
from personalcontext.ingest.visit.model import WebVisit


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "schemas"
    root.mkdir(exist_ok=True)
    contracts = (
        ("health", HealthResponse), ("readiness", ReadinessResponse),
        ("event-id", EventId), ("event-kind", EventKind),
        ("event-quality", EventQuality), ("event-timing", EventTiming),
        ("event-temporal", EventTemporal),
        ("web-visit", WebVisit),
        ("web-active", WebActive),
    )
    for name, contract in contracts:
        schema = TypeAdapter(contract).json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        indent = None if name in ("web-visit", "web-active") else 2
        (root / f"{name}.v1.schema.json").write_text(json.dumps(schema, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
