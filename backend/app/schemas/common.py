"""Common envelope, pagination, and strict validation base schemas."""

from __future__ import annotations

import re
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.core.errors import FieldErrorCode

STUDENT_ID_RE = re.compile(r"^(SV|AD)[0-9]{3,6}$")
COURSE_CLASS_ID_RE = re.compile(r"^LHP[0-9]{3,6}$")
UUID_ANY_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

T = TypeVar("T")


class StrictRequestModel(BaseModel):
    """Base model for JSON request bodies: forbids unknown fields and type coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ResponseModel(BaseModel):
    """Base model for JSON response objects."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorDetailSchema(ResponseModel):
    field: str = Field(..., examples=["course_class_id"])
    code: str = Field(..., examples=["REQUIRED"])
    message: str = Field(..., examples=["Trường 'course_class_id' là bắt buộc."])


class ApiSuccessEnvelope(ResponseModel, Generic[T]):
    success: bool = Field(default=True, examples=[True])
    code: str = Field(..., examples=["HEALTHY"])
    message: str = Field(..., examples=["Thao tác thành công."])
    data: T
    request_id: str = Field(..., examples=["8c6c3ed0-768d-4fc6-8792-7b7eae691501"])


class ApiErrorEnvelope(ResponseModel):
    success: bool = Field(default=False, examples=[False])
    code: str = Field(..., examples=["CLASS_FULL"])
    message: str = Field(..., examples=["Lớp học phần đã hết chỗ."])
    data: None = Field(default=None)
    errors: list[ErrorDetailSchema] = Field(default_factory=list)
    request_id: str = Field(..., examples=["8c6c3ed0-768d-4fc6-8792-7b7eae691501"])


class PaginationSchema(ResponseModel):
    page: int = Field(..., ge=1, examples=[1])
    page_size: int = Field(..., ge=1, le=100, examples=[20])
    total_items: int = Field(..., ge=0, examples=[1])
    total_pages: int = Field(..., ge=0, examples=[1])


def validate_student_id(value: str) -> str:
    if not STUDENT_ID_RE.fullmatch(value):
        raise PydanticCustomError(
            "student_id_format",
            "Mã tài khoản phải khớp định dạng ^(SV|AD)[0-9]{3,6}$.",
            {"field_code": FieldErrorCode.INVALID_FORMAT},
        )
    return value


def validate_course_class_id(value: str) -> str:
    if not COURSE_CLASS_ID_RE.fullmatch(value):
        raise PydanticCustomError(
            "course_class_id_format",
            "Mã lớp học phần phải khớp định dạng ^LHP[0-9]{3,6}$.",
            {"field_code": FieldErrorCode.INVALID_FORMAT},
        )
    return value


def validate_uuid_str(value: str) -> str:
    if not UUID_ANY_RE.fullmatch(value):
        raise PydanticCustomError(
            "uuid_format",
            "Định danh phải là UUID hợp lệ.",
            {"field_code": FieldErrorCode.INVALID_FORMAT},
        )
    return value.lower()
