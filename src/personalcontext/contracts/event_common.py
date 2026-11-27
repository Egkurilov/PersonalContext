import math
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

EventId = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[47][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    ),
]
EventKind = Literal[
    "app_active", "idle", "lock", "web_visit", "web_active", "media_play", "shared_item",
    "document_reference", "imported_visit", "note", "ocr_text",
]
EventQuality = Literal["measured", "imported", "estimated", "unknown"]


class EventTiming(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [{
                "if": {"properties": {"granularity": {"const": "point"}}, "required": ["granularity"]},
                "then": {"properties": {"duration_ms": {"type": "null"}}},
            }],
        },
    )
    granularity: Literal["point", "interval"]
    duration_ms: int | None = Field(ge=0, le=900000)

    @field_validator("duration_ms", mode="before")
    @classmethod
    def duration_is_numeric_integer(cls, value: object) -> int | float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Duration must be an integer or null")  # noqa: TRY004 - Pydantic converts ValueError into a validation error
        if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
            raise ValueError("Duration must be an integer or null")
        return value

    @model_validator(mode="after")
    def point_has_no_duration(self) -> Self:
        if self.granularity == "point" and self.duration_ms is not None:
            raise ValueError("Point events require a null duration")
        return self
