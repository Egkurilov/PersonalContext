import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from personalcontext.app import create_app
from personalcontext.contracts.health import HealthResponse, ReadinessResponse


class HealthContractTests(unittest.TestCase):
    def test_committed_schemas_match_models_and_live_responses(self):
        root = Path(__file__).resolve().parent.parent / "schemas"
        health = json.loads((root / "health.v1.schema.json").read_text(encoding="utf-8"))
        readiness = json.loads((root / "readiness.v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(health, HealthResponse.model_json_schema())
        self.assertEqual(readiness, ReadinessResponse.model_json_schema())
        Draft202012Validator.check_schema(health)
        Draft202012Validator.check_schema(readiness)
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "fixture.db")
            with TestClient(app, base_url="http://127.0.0.1:17890", client=("127.0.0.1", 1)) as client:
                Draft202012Validator(health).validate(client.get("/healthz").json())
                Draft202012Validator(readiness).validate(client.get("/readyz").json())
                app.state.ready = False
                response = client.get("/readyz")
                self.assertEqual(response.status_code, 503)
                Draft202012Validator(readiness).validate(response.json())
        for invalid in ({"status": "ready", "unexpected": "synthetic"}, {"status": "unknown"}, {}):
            self.assertFalse(Draft202012Validator(readiness).is_valid(invalid))
