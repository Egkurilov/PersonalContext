from typing import Literal

from pydantic import BaseModel, ConfigDict


class _StatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )


class HealthResponse(_StatusResponse):
    status: Literal["ok"]


class ReadinessResponse(_StatusResponse):
    status: Literal["ready", "unavailable"]
