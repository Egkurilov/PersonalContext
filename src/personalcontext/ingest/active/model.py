"""Structural validation for an internally classified active browser interval."""

from fractions import Fraction
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from personalcontext.contracts.event_temporal import _instant
from personalcontext.ingest.browser.model import BrowserEnvelope, WebPayload


class ActivePayload(WebPayload):
    foreground: Literal[True]

    @field_validator("foreground", mode="before")
    @classmethod
    def foreground_is_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Foreground classification required")
        return value


class WebActive(BrowserEnvelope):
    kind: Literal["web_active"]
    granularity: Literal["interval"]
    payload: ActivePayload = Field(repr=False)

    @model_validator(mode="after")
    def duration_matches_interval(self) -> Self:
        if (self.duration_ms is not None and
                (self.ended_at is None or _instant(self.ended_at) - _instant(self.started_at) != Fraction(self.duration_ms, 1000))):
            raise ValueError("Duration does not match interval")
        return self
