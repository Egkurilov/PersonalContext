"""IANA validation and daylight-saving data are available on Windows too."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import test_web_visit_ledger as fixture
from pydantic import ValidationError

from personalcontext.ingest.visit.model import WebVisit
from personalcontext.ingest.visit.timezone_probe import verify_timezone_runtime


class VisitTimezoneTests(unittest.TestCase):
    def test_iana_zone_and_daylight_transition(self):
        self.assertTrue(verify_timezone_runtime())
        zone = ZoneInfo("America/New_York")
        before = datetime(2026, 3, 8, 6, 30, tzinfo=UTC).astimezone(zone)
        after = datetime(2026, 3, 8, 7, 30, tzinfo=UTC).astimezone(zone)
        self.assertEqual(before.utcoffset(), timedelta(hours=-5))
        self.assertEqual(after.utcoffset(), timedelta(hours=-4))
        event = fixture.synthetic_event("00000000-0000-4000-8000-000000000001",
                                        "00000000-0000-4000-8000-000000000002")
        self.assertEqual(WebVisit.model_validate({**event, "timezone": "America/New_York"}).timezone, "America/New_York")
        with self.assertRaises(ValidationError):
            WebVisit.model_validate({**event, "timezone": "Invalid/Unknown"})

    def test_missing_iana_data_fails_the_runtime_probe(self):
        with patch("personalcontext.ingest.visit.timezone_probe.ZoneInfo", side_effect=ZoneInfoNotFoundError("synthetic")):
            self.assertFalse(verify_timezone_runtime())
