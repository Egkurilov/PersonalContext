import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from personalcontext.contracts.event_common import (
    EventId,
    EventKind,
    EventQuality,
    EventTiming,
)


class EventComponentTests(unittest.TestCase):
    def test_generated_schemas_match_contract_types(self):
        root = Path(__file__).resolve().parent.parent / "schemas"
        for name, contract in (("event-id", EventId), ("event-kind", EventKind), ("event-quality", EventQuality), ("event-timing", EventTiming)):
            with self.subTest(name=name):
                schema = json.loads((root / f"{name}.v1.schema.json").read_text(encoding="utf-8"))
                expected = TypeAdapter(contract).json_schema()
                expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
                self.assertEqual(schema, expected)
                Draft202012Validator.check_schema(schema)

    def test_timing_point_unknown_and_interval_limits(self):
        schema = TypeAdapter(EventTiming).json_schema()
        validator = Draft202012Validator(schema)
        for value in (
            {"granularity": "point", "duration_ms": None},
            {"granularity": "interval", "duration_ms": None},
            {"granularity": "interval", "duration_ms": 900000},
            {"granularity": "interval", "duration_ms": 1.0},
        ):
            with self.subTest(value=value):
                self.assertTrue(validator.is_valid(value))
                EventTiming.model_validate(value)
        for value in (
            {"granularity": "aggregate", "duration_ms": None},
            {"granularity": "point", "duration_ms": 0},
            {"granularity": "interval", "duration_ms": -1},
            {"granularity": "interval", "duration_ms": True},
            {"granularity": "interval", "duration_ms": "1"},
            {"granularity": "interval", "duration_ms": 1.5},
            {"granularity": "interval", "duration_ms": 900001},
            {"granularity": "interval", "duration_ms": 10, "unexpected": "synthetic"},
        ):
            with self.subTest(value=value):
                self.assertFalse(validator.is_valid(value))
                with self.assertRaises(ValidationError):
                    EventTiming.model_validate(value)

    def test_event_id_kind_and_quality(self):
        identifiers = TypeAdapter(EventId)
        identifier_schema = Draft202012Validator(identifiers.json_schema())
        for value in ("018f0010-0000-7000-8000-000000000001", "123e4567-e89b-42d3-a456-426614174000"):
            self.assertEqual(identifiers.validate_python(value), value)
            self.assertTrue(identifier_schema.is_valid(value))
        for value in ("123e4567-e89b-12d3-a456-426614174000", "123e4567-e89b-42d3-0456-426614174000", "018f0010-0000-7000-8000-000000000001\n", "invalid"):
            self.assertFalse(identifier_schema.is_valid(value))
            with self.assertRaises(ValidationError):
                identifiers.validate_python(value)
        self.assertEqual(TypeAdapter(EventKind).validate_python("web_active"), "web_active")
        self.assertEqual(TypeAdapter(EventQuality).validate_python("unknown"), "unknown")
        with self.assertRaises(ValidationError):
            TypeAdapter(EventKind).validate_python("unapproved")
