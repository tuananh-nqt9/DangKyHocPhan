"""Health endpoint schemas (Spec Section 17)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ResponseModel


class HealthFeaturesSchema(ResponseModel):
    payments: bool = Field(..., examples=[True])
    sso: bool = Field(..., examples=[False])
    queue: bool = Field(..., examples=[False])


class HealthDataSchema(ResponseModel):
    status: Literal["UP"] = Field(default="UP")
    database: Literal["UP"] = Field(default="UP")
    api_version: str = Field(default="1.0.0", examples=["1.0.0"])
    features: HealthFeaturesSchema
