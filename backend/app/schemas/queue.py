"""Redis FIFO queue schemas (Spec Section 16)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ResponseModel, StrictRequestModel


class QueueJoinRequest(StrictRequestModel):
    """Empty JSON object `{}` required by Spec Section 16; unknown fields rejected."""


class QueueStateSchema(ResponseModel):
    queue_enabled: bool = Field(..., examples=[True])
    status: Literal["NONE", "WAITING", "READY", "EXPIRED"] = Field(..., examples=["WAITING"])
    position: int | None = Field(default=None, examples=[3])
    estimated_wait_seconds: int | None = Field(default=None, examples=[None])
    ready_expires_at: str | None = Field(default=None, examples=[None])
    queue_token: str | None = Field(default=None, examples=[None])
