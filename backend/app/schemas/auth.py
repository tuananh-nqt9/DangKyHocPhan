"""Authentication, session refresh/logout, and SSO schemas (Spec Sections 04–07)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.errors import FieldErrorCode
from app.schemas.common import ResponseModel, StrictRequestModel, validate_student_id


class StudentSchema(ResponseModel):
    student_id: str = Field(..., examples=["SV0001"])
    full_name: str = Field(..., examples=["Sinh viên mẫu 0001"])
    role: Literal["STUDENT", "ADMIN"] = Field(..., examples=["STUDENT"])


class LoginRequest(StrictRequestModel):
    student_id: str = Field(..., examples=["SV0001"])
    password: str = Field(..., examples=["Demo@123456"])

    @field_validator("student_id")
    @classmethod
    def check_student_id(cls, value: str) -> str:
        return validate_student_id(value)

    @field_validator("password")
    @classmethod
    def check_password_len(cls, value: str) -> str:
        # Spec Section 05: password length 8–128, NEVER trim whitespace
        if len(value) < 8 or len(value) > 128:
            raise PydanticCustomError(
                "password_length",
                "Mật khẩu phải có độ dài từ 8 đến 128 ký tự.",
                {"field_code": FieldErrorCode.OUT_OF_RANGE},
            )
        return value


class RefreshRequest(StrictRequestModel):
    refresh_token: str = Field(..., examples=["REFRESH_TOKEN_SAMPLE"])

    @field_validator("refresh_token")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip() or len(value) > 512:
            raise PydanticCustomError(
                "refresh_token_format",
                "Refresh token không hợp lệ.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        return value


class LogoutRequest(StrictRequestModel):
    refresh_token: str = Field(..., examples=["REFRESH_TOKEN_SAMPLE"])

    @field_validator("refresh_token")
    @classmethod
    def check_non_empty(cls, value: str) -> str:
        if not value or not value.strip() or len(value) > 512:
            raise PydanticCustomError(
                "refresh_token_format",
                "Refresh token không hợp lệ.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        return value


class SsoExchangeRequest(StrictRequestModel):
    exchange_code: str = Field(..., examples=["ONE_TIME_CODE_SAMPLE"])

    @field_validator("exchange_code")
    @classmethod
    def check_exchange_code(cls, value: str) -> str:
        if not value or not value.strip() or len(value) > 512:
            raise PydanticCustomError(
                "exchange_code_format",
                "Mã trao đổi SSO không hợp lệ.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        return value


class AuthTokenData(ResponseModel):
    access_token: str = Field(..., examples=["ACCESS_TOKEN_SAMPLE"])
    token_type: Literal["Bearer"] = Field(default="Bearer")
    expires_in: int = Field(..., ge=1, examples=[3600])
    refresh_token: str = Field(..., examples=["REFRESH_TOKEN_SAMPLE"])
    refresh_expires_in: int = Field(..., ge=1, examples=[28800])
    student: StudentSchema


class LogoutData(ResponseModel):
    logged_out: bool = Field(default=True)
