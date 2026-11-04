"""Centralized error definitions and response mapping per API Spec v3.0 (Section 20 & 21)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    # 400
    INVALID_JSON = "INVALID_JSON"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    # 401
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_REFRESH_TOKEN = "INVALID_REFRESH_TOKEN"
    SSO_FAILED = "SSO_FAILED"
    # 403
    FORBIDDEN = "FORBIDDEN"
    STUDENT_MISMATCH = "STUDENT_MISMATCH"
    QUEUE_TOKEN_REQUIRED = "QUEUE_TOKEN_REQUIRED"
    QUEUE_TOKEN_INVALID = "QUEUE_TOKEN_INVALID"
    # 404
    CLASS_NOT_FOUND = "CLASS_NOT_FOUND"
    REGISTRATION_NOT_FOUND = "REGISTRATION_NOT_FOUND"
    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
    # 405
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    # 409
    ALREADY_REGISTERED = "ALREADY_REGISTERED"
    CLASS_FULL = "CLASS_FULL"
    REGISTRATION_CLOSED = "REGISTRATION_CLOSED"
    PREREQUISITE_NOT_MET = "PREREQUISITE_NOT_MET"
    SCHEDULE_CONFLICT = "SCHEDULE_CONFLICT"
    ALREADY_PAID = "ALREADY_PAID"
    REQUEST_IN_PROGRESS = "REQUEST_IN_PROGRESS"
    CAPACITY_BELOW_REGISTERED = "CAPACITY_BELOW_REGISTERED"
    CLASS_CODE_EXISTS = "CLASS_CODE_EXISTS"
    CLASS_HAS_REGISTRATIONS = "CLASS_HAS_REGISTRATIONS"
    # 415
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    # 422
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    # 429
    RATE_LIMITED = "RATE_LIMITED"
    # 503
    SERVICE_BUSY = "SERVICE_BUSY"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    # 500
    INTERNAL_ERROR = "INTERNAL_ERROR"


class FieldErrorCode(StrEnum):
    REQUIRED = "REQUIRED"
    INVALID_FORMAT = "INVALID_FORMAT"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    PREREQUISITE_MISSING = "PREREQUISITE_MISSING"
    CLASS_TIME_CONFLICT = "CLASS_TIME_CONFLICT"


@dataclass(frozen=True)
class FieldErrorItem:
    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class AppError(Exception):
    """Structured domain/HTTP error mapped directly to the v3.0 error envelope."""

    status_code: int
    code: ErrorCode | str
    message: str
    errors: list[FieldErrorItem] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    # Whether this error represents a deterministic post-validation business outcome
    # that MUST be saved in idempotency_records when raised inside an idempotent operation.
    persist_idempotency: bool = False

    def __post_init__(self) -> None:
        super().__init__(self.message)
        if self.status_code == 401 and "WWW-Authenticate" not in self.headers:
            self.headers["WWW-Authenticate"] = "Bearer"
        if (
            self.code
            in (
                ErrorCode.REQUEST_IN_PROGRESS,
                ErrorCode.RATE_LIMITED,
                ErrorCode.SERVICE_BUSY,
                ErrorCode.SERVICE_UNAVAILABLE,
            )
            and "Retry-After" not in self.headers
        ):
            self.headers["Retry-After"] = "1"


def build_error_envelope(
    *,
    code: ErrorCode | str,
    message: str,
    request_id: str,
    errors: list[FieldErrorItem] | list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    serialized_errors: list[dict[str, str]] = []
    for item in errors or []:
        if isinstance(item, FieldErrorItem):
            serialized_errors.append(item.to_dict())
        else:
            serialized_errors.append(
                {
                    "field": str(item.get("field", "")),
                    "code": str(item.get("code", FieldErrorCode.INVALID_FORMAT)),
                    "message": str(item.get("message", "Dữ liệu không hợp lệ.")),
                }
            )
    return {
        "success": False,
        "code": str(code),
        "message": message,
        "data": None,
        "errors": serialized_errors,
        "request_id": request_id,
    }


def map_pydantic_errors(raw_errors: list[dict[str, Any]]) -> list[FieldErrorItem]:
    """Convert Pydantic/FastAPI validation error items into Spec v3.0 FieldErrorItems.

    Never leaks raw input values (passwords/tokens) or stack traces into error messages.
    """
    mapped: list[FieldErrorItem] = []
    for err in raw_errors:
        loc_parts = [str(p) for p in err.get("loc", ()) if str(p) not in ("body", "query", "path", "header")]
        field_name = ".".join(loc_parts) if loc_parts else "body"
        # Format list index nicely: schedule.0.room -> schedule[0].room
        formatted_parts: list[str] = []
        for part in loc_parts:
            if part.isdigit() and formatted_parts:
                formatted_parts[-1] = f"{formatted_parts[-1]}[{part}]"
            else:
                formatted_parts.append(part)
        if formatted_parts:
            field_name = ".".join(formatted_parts)

        err_type = str(err.get("type", ""))
        ctx = err.get("ctx") or {}
        custom_code = ctx.get("field_code")

        if custom_code:
            code = str(custom_code)
            msg = str(ctx.get("error") or err.get("msg") or "Dữ liệu không hợp lệ.")
            # Strip Pydantic "Value error, " prefix if present
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, ") :]
        elif err_type == "missing":
            code = FieldErrorCode.REQUIRED
            msg = f"Trường '{field_name}' là bắt buộc."
        elif err_type == "extra_forbidden":
            code = FieldErrorCode.UNKNOWN_FIELD
            msg = f"Trường '{field_name}' không được phép trong yêu cầu."
        elif err_type in (
            "greater_than",
            "greater_than_equal",
            "less_than",
            "less_than_equal",
            "too_short",
            "too_long",
            "string_too_short",
            "string_too_long",
            "int_from_float",
        ):
            if err_type == "int_from_float":
                code = FieldErrorCode.INVALID_FORMAT
                msg = f"Trường '{field_name}' phải là số nguyên."
            else:
                code = FieldErrorCode.OUT_OF_RANGE
                msg = f"Giá trị của '{field_name}' nằm ngoài phạm vi cho phép."
        else:
            code = FieldErrorCode.INVALID_FORMAT
            raw_msg = str(err.get("msg", ""))
            if raw_msg.startswith("Value error, "):
                msg = raw_msg[len("Value error, ") :]
            else:
                msg = f"Trường '{field_name}' sai kiểu hoặc định dạng."

        mapped.append(FieldErrorItem(field=field_name, code=code, message=msg))
    return mapped
