"""Bounded packaged-runtime check for IANA data and the internal visit module."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from personalcontext.ingest.active.service import submit_web_active
from personalcontext.ingest.visit.batch import submit_visit_batch
from personalcontext.ingest.visit.service import submit_web_visit


def verify_timezone_runtime() -> bool:
    try:
        zone = ZoneInfo("America/New_York")
        before = datetime(2026, 3, 8, 6, 30, tzinfo=UTC).astimezone(zone)
        after = datetime(2026, 3, 8, 7, 30, tzinfo=UTC).astimezone(zone)
        return (callable(submit_web_visit) and callable(submit_web_active) and callable(submit_visit_batch)
                and before.utcoffset() == timedelta(hours=-5)
                and after.utcoffset() == timedelta(hours=-4) and ZoneInfo("UTC").key == "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
