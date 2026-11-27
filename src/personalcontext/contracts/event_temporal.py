import re
from datetime import datetime
from fractions import Fraction
from typing import Annotated, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from personalcontext.contracts.event_common import EventTiming

UTC_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|\+00:00)$"
UtcTimestamp = Annotated[
    str, StringConstraints(strict=True, max_length=128, pattern=UTC_PATTERN),
    Field(json_schema_extra={"format": "date-time"}),
]


def _instant(value: str) -> Fraction:
    if re.fullmatch(UTC_PATTERN, value) is None:
        raise ValueError("Expected an ISO UTC timestamp")
    whole = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    elapsed = whole - datetime(1, 1, 1)
    seconds = elapsed.days * 86400 + elapsed.seconds
    fraction = value[19:].split("Z")[0].split("+")[0]
    return Fraction(seconds) + (Fraction(fraction) if fraction else 0)


class EventTemporal(EventTiming):
    started_at: UtcTimestamp
    ended_at: UtcTimestamp | None
    observed_at: UtcTimestamp

    @field_validator("started_at", "ended_at", "observed_at")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            _instant(value)
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.ended_at is not None:
            duration = _instant(self.ended_at) - _instant(self.started_at)
            if duration < 0 or duration > 900:
                raise ValueError("Invalid event interval")
        return self
