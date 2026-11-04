"""Simulated payment and payment history schemas (Spec Sections 04, 13)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import (
    PaginationSchema,
    ResponseModel,
    StrictRequestModel,
    validate_uuid_str,
)
from app.schemas.registration import RegistrationSchema


class PaymentCreateRequest(StrictRequestModel):
    registration_id: str = Field(..., examples=["4d0ce29e-9e4d-4e0a-8a92-f776fe905001"])

    @field_validator("registration_id")
    @classmethod
    def check_registration_uuid(cls, value: str) -> str:
        return validate_uuid_str(value)


class PaymentSchema(ResponseModel):
    payment_id: str = Field(..., examples=["61de10f7-8f5e-4d34-a3cd-0dcb5da42519"])
    registration_id: str = Field(..., examples=["4d0ce29e-9e4d-4e0a-8a92-f776fe905001"])
    course_class_id: str = Field(..., examples=["LHP001"])
    class_code: str = Field(..., examples=["CNNT-01"])
    amount: int = Field(..., ge=0, examples=[1500000])
    currency: Literal["VND"] = Field(default="VND")
    status: Literal["PAID", "REFUNDED"] = Field(..., examples=["PAID"])
    paid_at: str = Field(..., examples=["2026-11-01T08:35:00Z"])
    refunded_at: str | None = Field(default=None, examples=[None])


class PaymentSuccessData(ResponseModel):
    payment: PaymentSchema
    registration: RegistrationSchema


class MyPaymentsData(ResponseModel):
    items: list[PaymentSchema]
    pagination: PaginationSchema
