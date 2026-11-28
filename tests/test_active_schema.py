"""Published active-tab schema covers structure; runtime handles interval math."""

import json
import unittest
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from test_web_active import active_event

from personalcontext.ingest.active.model import WebActive


class ActiveSchemaTests(unittest.TestCase):
    def test_schema_structure_and_runtime_duration_check(self):
        schema = json.loads((Path(__file__).resolve().parent.parent / "schemas/web-active.v1.schema.json").read_text(encoding="utf-8"))
        expected = WebActive.model_json_schema()
        expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        self.assertEqual(schema, expected)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        event = active_event(str(uuid.uuid4()), str(uuid.uuid4()))
        self.assertTrue(validator.is_valid(event))
        self.assertFalse(validator.is_valid(event | {"payload": event["payload"] | {"foreground": False}}))
        self.assertFalse(validator.is_valid(event | {"payload": event["payload"] | {"form": "synthetic"}}))
        mismatch = event | {"duration_ms": 999}
        self.assertTrue(validator.is_valid(mismatch))
        with self.assertRaises(ValidationError):
            WebActive.model_validate(mismatch)
