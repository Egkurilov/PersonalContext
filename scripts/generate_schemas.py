import json
from pathlib import Path

from personalcontext.contracts.health import HealthResponse, ReadinessResponse


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "schemas"
    root.mkdir(exist_ok=True)
    for name, model in (("health", HealthResponse), ("readiness", ReadinessResponse)):
        schema = model.model_json_schema()
        (root / f"{name}.v1.schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
