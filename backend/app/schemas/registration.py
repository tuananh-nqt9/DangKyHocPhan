"""Registration, cancellation, refund, and student registration list schemas (Spec Sections 04, 10, 11, 12)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import (
    PaginationSchema,
    ResponseModel,
    StrictRequestModel,
    validate_course_class_id,
    validate_student_id,
)
from app.schemas.course_class import CourseClassSchema


class RegisterRequest(StrictRequestModel):
    student_id: str = Field(..., examples=["SV0001"])
    course_class_id: str = Field(..., examples=["LHP001"])

    @field_validator("student_id")
    @classmethod
    def check_student_id(cls, value: str) -> str:
        return validate_student_id(value)

    @field_validator("course_class_id")
    @classmethod
    def check_course_class_id(cls, value: str) -> str:
        return validate_course_class_id(value)


class RegistrationSchema(ResponseModel):
    registration_id: str = Field(..., examples=["4d0ce29e-9e4d-4e0a-8a92-f776fe905001"])
    student_id: str = Field(..., examples=["SV0001"])
    course_class_id: str = Field(..., examples=["LHP001"])
    class_code: str = Field(..., examples=["CNNT-01"])
    course_name: str = Field(..., examples=["Công nghệ nền tảng"])
    credits: int = Field(..., ge=1, examples=[3])
    status: Literal["ACTIVE", "CANCELLED"] = Field(..., examples=["ACTIVE"])
    payment_status: Literal["UNPAID", "PAID", "REFUNDED"] = Field(..., examples=["UNPAID"])
    tuition_amount: int = Field(..., ge=0, examples=[1500000])
    registered_at: str = Field(..., examples=["2026-11-01T08:30:00Z"])
    cancelled_at: str | None = Field(default=None, examples=[None])


class RegisterSuccessData(ResponseModel):
    registration: RegistrationSchema
    course_class: CourseClassSchema


class RefundInfoSchema(ResponseModel):
    payment_id: str = Field(..., examples=["61de10f7-8f5e-4d34-a3cd-0dcb5da42519"])
    amount: int = Field(..., ge=0, examples=[1500000])
    currency: Literal["VND"] = Field(default="VND")
    status: Literal["REFUNDED"] = Field(default="REFUNDED")
    refunded_at: str = Field(..., examples=["2026-11-01T08:40:00Z"])


class CancelSuccessData(ResponseModel):
    registration: RegistrationSchema
    course_class: CourseClassSchema
    refund: RefundInfoSchema | None = Field(default=None)


class MyRegistrationsData(ResponseModel):
    student_id: str = Field(..., examples=["SV0001"])
    items: list[RegistrationSchema]
    pagination: PaginationSchema
