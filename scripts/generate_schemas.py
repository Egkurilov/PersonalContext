import json
from pathlib import Path

from pydantic import TypeAdapter

from personalcontext.contracts.event_common import (
    EventId,
    EventKind,
    EventQuality,
    EventTiming,
)
from personalcontext.contracts.health import HealthResponse, ReadinessResponse


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "schemas"
    root.mkdir(exist_ok=True)
    contracts = (
        ("health", HealthResponse), ("readiness", ReadinessResponse),
        ("event-id", EventId), ("event-kind", EventKind),
        ("event-quality", EventQuality), ("event-timing", EventTiming),
    )
    for name, contract in contracts:
        schema = TypeAdapter(contract).json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (root / f"{name}.v1.schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
