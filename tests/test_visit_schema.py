"""The published visit schema describes the internal model's structural contract."""

import json
import unittest
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from test_web_visit_ledger import synthetic_event

from personalcontext.ingest.visit.model import WebVisit


class VisitSchemaTests(unittest.TestCase):
    def test_schema_matches_model_and_rejects_forbidden_structure(self):
        schema = json.loads((Path(__file__).resolve().parent.parent / "schemas/web-visit.v1.schema.json").read_text(encoding="utf-8"))
        expected = WebVisit.model_json_schema()
        expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        self.assertEqual(schema, expected)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        event = synthetic_event(str(uuid.uuid4()), str(uuid.uuid4()))
        self.assertTrue(validator.is_valid(event))
        for invalid in (event | {"kind": "unknown"}, event | {"duration_ms": 1},
                        event | {"unexpected": "synthetic"},
                        event | {"payload": event["payload"] | {"form": "synthetic"}},
                        event | {"provenance": event["provenance"] | {"collector": "unknown"}}):
            with self.subTest(invalid=invalid):
                self.assertFalse(validator.is_valid(invalid))
        unknown_zone = event | {"timezone": "Invalid/Unknown"}
        self.assertTrue(validator.is_valid(unknown_zone))
        with self.assertRaises(ValidationError):
            WebVisit.model_validate(unknown_zone)
