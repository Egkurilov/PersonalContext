"""Structural validation for a browser visit; no input is logged or persisted here."""

from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from personalcontext.contracts.event_common import EventId, EventQuality
from personalcontext.contracts.event_temporal import EventTemporal
from personalcontext.privacy.sanitizer.text import sanitize_text
from personalcontext.privacy.url_normalize import normalize_url


class WebPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    domain: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=253)]
    url: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=8192)] = Field(repr=False)
    title: Annotated[str, StringConstraints(strict=True, max_length=512)] | None = Field(default=None, repr=False)

    @field_validator("domain")
    @classmethod
    def canonical_domain(cls, value: str) -> str:
        if any(char in "/\\?#@:%" for char in value):
            raise ValueError("Invalid domain")
        try:
            host = urlsplit(normalize_url("https://" + value + "/")).hostname
        except ValueError:
            raise ValueError("Invalid domain") from None
        if host is None:
            raise ValueError("Invalid domain")
        return host


class BrowserProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    collector: Literal["browser"]
    collector_version: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)]
    import_id: None


class WebVisit(EventTemporal):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    event_id: EventId
    device_id: EventId
    source_id: EventId
    source_event_key: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{1,64}$")] = Field(repr=False)
    kind: Literal["web_visit"]
    granularity: Literal["point"]
    quality: EventQuality
    timezone: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    policy_version: Annotated[int, Field(strict=True, ge=1, le=2**53 - 1)]
    consent_scope: Literal["metadata"]
    payload: WebPayload = Field(repr=False)
    provenance: BrowserProvenance

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_is_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid schema version")
        return value

    @field_validator("event_id", "device_id", "source_id")
    @classmethod
    def canonical_uuid(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("source_event_key")
    @classmethod
    def safe_key(cls, value: str) -> str:
        if sanitize_text(value, 64, allow_multiline=False) != value:
            raise ValueError("Invalid source key")
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("Unknown timezone") from None
        return value
