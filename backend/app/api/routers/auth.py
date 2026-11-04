"""Authentication & session lifecycle endpoints (Spec Sections 05 & 06)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import (
    AnyAuthContractRoute,
    PublicContractRoute,
    build_success_response,
    require_authenticated,
    require_no_query_params,
)
from app.schemas.auth import (
    AuthTokenData,
    LoginRequest,
    LogoutData,
    LogoutRequest,
    RefreshRequest,
)
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope

public_auth_router = APIRouter(prefix="/auth", tags=["Auth"], route_class=PublicContractRoute)
protected_auth_router = APIRouter(prefix="/auth", tags=["Auth"], route_class=AnyAuthContractRoute)


@public_auth_router.post(
    "/login",
    response_model=ApiSuccessEnvelope[AuthTokenData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "JSON hỏng hoặc dữ liệu không hợp lệ"},
        401: {"model": ApiErrorEnvelope, "description": "Sai tài khoản hoặc mật khẩu"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
        429: {"model": ApiErrorEnvelope, "description": "Quá giới hạn tần suất"},
    },
    summary="Đăng nhập bằng mã sinh viên/quản trị và mật khẩu",
)
def login(
    request: Request,
    payload: LoginRequest,
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    auth_service = request.app.state.auth_service
    data = auth_service.login(student_id=payload.student_id, password=payload.password)
    return build_success_response(
        request,
        code="LOGIN_SUCCESS",
        message="Đăng nhập thành công.",
        data=data,
    )


@public_auth_router.post(
    "/refresh",
    response_model=ApiSuccessEnvelope[AuthTokenData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "JSON hỏng hoặc thiếu refresh_token"},
        401: {"model": ApiErrorEnvelope, "description": "Refresh token không hợp lệ hoặc hết hạn"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
    },
    summary="Làm mới cặp access/refresh token nguyên tử",
)
def refresh_tokens(
    request: Request,
    payload: RefreshRequest,
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    auth_service = request.app.state.auth_service
    data = auth_service.refresh(raw_refresh_token=payload.refresh_token)
    return build_success_response(
        request,
        code="TOKEN_REFRESHED",
        message="Làm mới phiên đăng nhập thành công.",
        data=data,
    )


@protected_auth_router.post(
    "/logout",
    response_model=ApiSuccessEnvelope[LogoutData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "JSON hỏng hoặc thiếu refresh_token"},
        401: {
            "model": ApiErrorEnvelope,
            "description": "Access token hết hạn hoặc refresh token khác phiên",
        },
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
    },
    summary="Thu hồi phiên đăng nhập hiện tại",
)
def logout(
    request: Request,
    payload: LogoutRequest,
    caller: dict[str, Any] = Depends(require_authenticated),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    auth_service = request.app.state.auth_service
    data = auth_service.logout(caller=caller, raw_refresh_token=payload.refresh_token)
    return build_success_response(
        request,
        code="LOGGED_OUT",
        message="Đăng xuất thành công.",
        data=data,
    )
