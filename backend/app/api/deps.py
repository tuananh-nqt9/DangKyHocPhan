"""Shared FastAPI dependencies: Bearer auth, RBAC, strict query/path/header parsing, and response helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from fastapi import Header, Request, Security
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AppError, ErrorCode, FieldErrorCode, FieldErrorItem
from app.schemas.common import COURSE_CLASS_ID_RE, UUID_ANY_RE, UUID_V4_RE
from app.services.idempotency_service import IdempotencyExecutionOutcome

_INT_QUERY_RE = re.compile(r"^-?[0-9]+$")

# Swagger / OpenAPI Bearer security scheme (`auto_error=False` so we return 401 Envelope, not FastAPI 403)
bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="Opaque access token cấp từ `/api/v1/auth/login` hoặc `/api/v1/auth/sso/exchange`.",
    auto_error=False,
)


def extract_bearer_token(auth_header: str | None) -> str:
    if not auth_header:
        raise AppError(
            status_code=401,
            code=ErrorCode.UNAUTHORIZED,
            message="Thiếu thông tin xác thực Bearer token.",
        )
    parts = auth_header.strip().split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AppError(
            status_code=401,
            code=ErrorCode.UNAUTHORIZED,
            message="Định dạng header Authorization phải là 'Bearer <access_token>'.",
        )
    return parts[1].strip()


def authenticate_request(
    request: Request,
    allowed_roles: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Authenticate Bearer token (cached on `request.state.caller` within the single request) and check role."""
    caller: dict[str, Any] | None = getattr(request.state, "caller", None)
    if caller is None:
        raw_token = extract_bearer_token(request.headers.get("Authorization"))
        auth_service = request.app.state.auth_service
        caller = auth_service.authenticate_access_token(raw_token)
        request.state.caller = caller

    if allowed_roles is not None and str(caller["role"]) not in allowed_roles:
        raise AppError(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            message="Tài khoản không có quyền thực hiện thao tác này.",
        )
    return caller


def require_authenticated(
    request: Request,
    _cred: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    return authenticate_request(request, allowed_roles=frozenset({"STUDENT", "ADMIN"}))


def require_student(
    request: Request,
    _cred: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    return authenticate_request(request, allowed_roles=frozenset({"STUDENT"}))


def require_admin(
    request: Request,
    _cred: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    return authenticate_request(request, allowed_roles=frozenset({"ADMIN"}))


def get_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def validate_allowed_query_params(
    request: Request,
    allowed_names: frozenset[str] = frozenset(),
) -> None:
    errors: list[FieldErrorItem] = []
    seen_counts: dict[str, int] = {}
    for key, _ in request.query_params.multi_items():
        seen_counts[key] = seen_counts.get(key, 0) + 1
        if key not in allowed_names:
            errors.append(
                FieldErrorItem(
                    field=key,
                    code=FieldErrorCode.UNKNOWN_FIELD,
                    message=f"Tham số truy vấn '{key}' không được hỗ trợ.",
                )
            )
    for key, count in seen_counts.items():
        if key in allowed_names and count > 1:
            errors.append(
                FieldErrorItem(
                    field=key,
                    code=FieldErrorCode.INVALID_FORMAT,
                    message=f"Tham số truy vấn '{key}' không được truyền lặp nhiều lần.",
                )
            )
    if errors:
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Tham số truy vấn không hợp lệ.",
            errors=errors,
        )


def parse_pagination_params(
    request: Request,
    *,
    extra_allowed: frozenset[str] = frozenset(),
) -> tuple[int, int]:
    allowed = frozenset({"page", "page_size"}) | extra_allowed
    validate_allowed_query_params(request, allowed)

    errors: list[FieldErrorItem] = []
    page = 1
    page_size = 20

    raw_page = request.query_params.get("page")
    if raw_page is not None:
        if not _INT_QUERY_RE.fullmatch(raw_page):
            errors.append(
                FieldErrorItem(
                    field="page",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Tham số 'page' phải là số nguyên.",
                )
            )
        else:
            val = int(raw_page)
            if val < 1:
                errors.append(
                    FieldErrorItem(
                        field="page",
                        code=FieldErrorCode.OUT_OF_RANGE,
                        message="Tham số 'page' phải lớn hơn hoặc bằng 1.",
                    )
                )
            else:
                page = val

    raw_page_size = request.query_params.get("page_size")
    if raw_page_size is not None:
        if not _INT_QUERY_RE.fullmatch(raw_page_size):
            errors.append(
                FieldErrorItem(
                    field="page_size",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Tham số 'page_size' phải là số nguyên.",
                )
            )
        else:
            val = int(raw_page_size)
            if val < 1 or val > 100:
                errors.append(
                    FieldErrorItem(
                        field="page_size",
                        code=FieldErrorCode.OUT_OF_RANGE,
                        message="Tham số 'page_size' phải nằm trong khoảng từ 1 đến 100.",
                    )
                )
            else:
                page_size = val

    if errors:
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Tham số phân trang không hợp lệ.",
            errors=errors,
        )
    return page, page_size


def require_no_query_params(request: Request) -> None:
    validate_allowed_query_params(request, frozenset())


def require_idempotency_key(
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="UUID v4 duy nhất cho mỗi ý định thao tác ghi (Spec Mục 18).",
        examples=["7f9c2b10-53a4-4f1b-9c8a-2a1e9f0c1234"],
    ),
) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Thiếu header Idempotency-Key.",
            errors=[
                FieldErrorItem(
                    field="Idempotency-Key",
                    code=FieldErrorCode.REQUIRED,
                    message="Header 'Idempotency-Key' là bắt buộc.",
                )
            ],
        )
    cleaned = idempotency_key.strip()
    if not UUID_V4_RE.fullmatch(cleaned):
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Header Idempotency-Key phải là UUID v4 hợp lệ.",
            errors=[
                FieldErrorItem(
                    field="Idempotency-Key",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Header 'Idempotency-Key' phải đúng định dạng UUID v4.",
                )
            ],
        )
    return cleaned.lower()


def validate_path_course_class_id(course_class_id: str) -> str:
    if not COURSE_CLASS_ID_RE.fullmatch(course_class_id):
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Mã lớp học phần trên đường dẫn không hợp lệ.",
            errors=[
                FieldErrorItem(
                    field="course_class_id",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Mã lớp học phần phải khớp định dạng ^LHP[0-9]{3,6}$.",
                )
            ],
        )
    return course_class_id


def validate_path_registration_id(registration_id: str) -> str:
    if not UUID_ANY_RE.fullmatch(registration_id):
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Mã đăng ký trên đường dẫn không hợp lệ.",
            errors=[
                FieldErrorItem(
                    field="registration_id",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Mã đăng ký phải là UUID hợp lệ.",
                )
            ],
        )
    return registration_id.lower()


def build_success_response(
    request: Request,
    *,
    code: str,
    message: str,
    data: dict[str, Any],
    status_code: int = 200,
) -> JSONResponse:
    req_id = get_request_id(request)
    request.state.response_code = code
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "code": code,
            "message": message,
            "data": data,
            "request_id": req_id,
        },
    )


def build_idempotent_response(
    request: Request,
    outcome: IdempotencyExecutionOutcome,
) -> JSONResponse:
    body_code = str(outcome.body.get("code", ""))
    request.state.response_code = body_code
    request.state.effective_request_id = outcome.original_request_id
    request.state.idempotent_replayed = outcome.replayed
    headers: dict[str, str] = {}
    if outcome.replayed:
        headers["Idempotent-Replayed"] = "true"
    return JSONResponse(
        status_code=outcome.status_code,
        content=outcome.body,
        headers=headers,
    )


def make_contract_route_class(
    *,
    auth_roles: frozenset[str] | None = None,
) -> type[APIRoute]:
    """Create an APIRoute subclass that enforces strict Spec v3.0 HTTP framing order:

    1. Bearer authentication & role check (if route is protected) -> 401 / 403
    2. Content-Type check on POST/PUT/PATCH -> 415 UNSUPPORTED_MEDIA_TYPE
    3. UTF-8 & JSON syntax check on POST/PUT/PATCH -> 400 INVALID_JSON
    4. JSON object root check / empty DELETE body check -> 400 VALIDATION_ERROR
    5. FastAPI dependency & strict Pydantic field validation -> 400 VALIDATION_ERROR
    """

    class ContractRoute(APIRoute):
        def get_route_handler(self) -> Callable[[Request], Any]:
            original_handler = super().get_route_handler()

            async def custom_handler(request: Request) -> Any:
                # 1. Optional rate limit check
                rate_limiter = getattr(request.app.state, "rate_limiter", None)
                settings = request.app.state.settings
                if rate_limiter is not None:
                    if request.url.path.endswith("/auth/login"):
                        client_ip = request.client.host if request.client else "local"
                        rate_limiter.check(
                            f"login:{client_ip}",
                            rate_per_sec=max(0.1, settings.login_rate_limit_per_minute / 60.0),
                            burst=max(5, settings.login_rate_limit_per_minute),
                        )
                    else:
                        rate_limiter.check(
                            "api:global",
                            rate_per_sec=float(settings.rate_limit_rps),
                            burst=int(settings.rate_limit_burst),
                        )

                # 2. Enforce authentication & RBAC BEFORE body framing on protected routes
                if auth_roles is not None:
                    # Run synchronous DB-backed token lookup in worker threadpool
                    from starlette.concurrency import run_in_threadpool

                    await run_in_threadpool(authenticate_request, request, auth_roles)

                # 3. Enforce strict Content-Type & JSON framing
                method = request.method.upper()
                if method in ("POST", "PUT", "PATCH"):
                    raw_ct = request.headers.get("content-type", "")
                    media_type = raw_ct.split(";", 1)[0].strip().lower()
                    if media_type != "application/json":
                        raise AppError(
                            status_code=415,
                            code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                            message="Yêu cầu POST/PUT/PATCH bắt buộc dùng Content-Type: application/json.",
                        )
                    raw_body = await request.body()
                    if not raw_body or not raw_body.strip():
                        raise AppError(
                            status_code=400,
                            code=ErrorCode.INVALID_JSON,
                            message="Dữ liệu JSON bị rỗng hoặc không hợp lệ.",
                        )
                    try:
                        decoded = raw_body.decode("utf-8")
                        parsed = json.loads(decoded)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise AppError(
                            status_code=400,
                            code=ErrorCode.INVALID_JSON,
                            message="Cú pháp JSON không hợp lệ.",
                        ) from exc
                    if not isinstance(parsed, dict):
                        raise AppError(
                            status_code=400,
                            code=ErrorCode.VALIDATION_ERROR,
                            message="Dữ liệu JSON gốc phải là một đối tượng (object).",
                            errors=[
                                FieldErrorItem(
                                    field="body",
                                    code=FieldErrorCode.INVALID_FORMAT,
                                    message="Body JSON phải là object.",
                                )
                            ],
                        )
                elif method == "DELETE":
                    raw_body = await request.body()
                    if raw_body and raw_body.strip():
                        raise AppError(
                            status_code=400,
                            code=ErrorCode.VALIDATION_ERROR,
                            message="Phương thức DELETE không nhận dữ liệu body.",
                            errors=[
                                FieldErrorItem(
                                    field="body",
                                    code=FieldErrorCode.UNKNOWN_FIELD,
                                    message="DELETE không được phép gửi kèm body.",
                                )
                            ],
                        )

                return await original_handler(request)

            return custom_handler

    return ContractRoute


PublicContractRoute = make_contract_route_class(auth_roles=None)
AnyAuthContractRoute = make_contract_route_class(auth_roles=frozenset({"STUDENT", "ADMIN"}))
StudentContractRoute = make_contract_route_class(auth_roles=frozenset({"STUDENT"}))
AdminContractRoute = make_contract_route_class(auth_roles=frozenset({"ADMIN"}))
