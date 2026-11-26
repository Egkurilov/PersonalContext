import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from personalcontext.contracts.event_temporal import EventTemporal


class EventTemporalTests(unittest.TestCase):
    def test_temporal_rules_reject_invalid_intervals(self):
        base = {"started_at": "2026-01-01T12:00:00Z", "ended_at": None,
                "observed_at": "2026-01-01T12:01:00Z", "granularity": "interval", "duration_ms": None}
        for changes in ({}, {"ended_at": "2026-01-01T12:15:00Z"},
                        {"ended_at": "2026-01-01T12:00:00.000000001Z"},
                        {"granularity": "point"}):
            with self.subTest(changes=changes):
                EventTemporal.model_validate(base | changes)
        for changes in ({"ended_at": "2026-01-01T11:59:59Z"},
                        {"ended_at": "2026-01-01T12:15:00.000000001Z"},
                        {"started_at": "2026-01-01T12:00:00+01:00"},
                        {"started_at": "2026-02-30T12:00:00Z"},
                        {"started_at": 123}, {"granularity": "point", "duration_ms": 1},
                        {"granularity": "aggregate"}, {"duration_ms": -1},
                        {"unexpected": "synthetic"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                EventTemporal.model_validate(base | changes)

    def test_published_schema_matches_model_and_structural_rules(self):
        schema = json.loads((Path(__file__).resolve().parent.parent / "schemas/event-temporal.v1.schema.json").read_text(encoding="utf-8"))
        expected = EventTemporal.model_json_schema()
        expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        self.assertEqual(schema, expected)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        Draft202012Validator.check_schema(schema)
        value = {"started_at": "2026-01-01T12:00:00Z", "ended_at": None,
                 "observed_at": "2026-01-01T12:00:00Z", "granularity": "point", "duration_ms": None}
        self.assertTrue(validator.is_valid(value))
        self.assertFalse(validator.is_valid(value | {"duration_ms": 1}))
        self.assertFalse(validator.is_valid(value | {"started_at": "2026-01-01T12:00:00+01:00"}))


if __name__ == "__main__":
    unittest.main()
