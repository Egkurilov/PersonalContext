"""Structural validation for internal point browser visits."""

from typing import Literal

from pydantic import Field

from personalcontext.ingest.browser.model import BrowserEnvelope, WebPayload

__all__ = ["WebPayload", "WebVisit"]


class WebVisit(BrowserEnvelope):
    kind: Literal["web_visit"]
    granularity: Literal["point"]
    payload: WebPayload = Field(repr=False)
