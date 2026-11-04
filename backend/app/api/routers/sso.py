"""Keycloak OIDC SSO login, callback, and one-time code exchange endpoints (Spec Section 07)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import (
    PublicContractRoute,
    build_success_response,
    require_no_query_params,
)
from app.schemas.auth import AuthTokenData, SsoExchangeRequest
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.services.sso_service import SSO_BIND_COOKIE_NAME, SSO_BIND_COOKIE_PATH

router = APIRouter(prefix="/auth/sso", tags=["SSO"], route_class=PublicContractRoute)


@router.get(
    "/login",
    status_code=302,
    response_class=RedirectResponse,
    responses={
        302: {"description": "Chuyển hướng sang Keycloak OIDC Authorization Endpoint"},
        400: {"model": ApiErrorEnvelope, "description": "Tham số truy vấn không hợp lệ"},
        503: {"model": ApiErrorEnvelope, "description": "SSO chưa được bật"},
    },
    summary="Khởi tạo giao dịch SSO OIDC + PKCE S256",
)
def sso_login(
    request: Request,
    _no_query: None = Depends(require_no_query_params),
) -> RedirectResponse:
    sso_service = request.app.state.sso_service
    settings = request.app.state.settings
    auth_url, bind_token = sso_service.start_sso_login()
    request.state.response_code = "SSO_REDIRECT"
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(
        key=SSO_BIND_COOKIE_NAME,
        value=bind_token,
        max_age=settings.oidc_transaction_ttl_seconds,
        path=SSO_BIND_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.oidc_cookie_secure,
    )
    return response


@router.get(
    "/callback",
    status_code=302,
    response_class=RedirectResponse,
    responses={
        302: {"description": "Chuyển hướng về FRONTEND_ORIGIN/sso/callback"},
        503: {"model": ApiErrorEnvelope, "description": "SSO chưa được bật"},
    },
    summary="Nhận callback OIDC từ Keycloak và phát mã trao đổi 60 giây",
)
def sso_callback(request: Request) -> RedirectResponse:
    sso_service = request.app.state.sso_service
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    idp_error = request.query_params.get("error")
    bind_cookie = request.cookies.get(SSO_BIND_COOKIE_NAME)

    target_url = sso_service.handle_callback(
        code=code,
        state=state,
        idp_error=idp_error,
        browser_bind_cookie=bind_cookie,
    )
    request.state.response_code = "SSO_CALLBACK_REDIRECT"
    response = RedirectResponse(url=target_url, status_code=302)
    response.delete_cookie(key=SSO_BIND_COOKIE_NAME, path=SSO_BIND_COOKIE_PATH)
    return response


@router.post(
    "/exchange",
    response_model=ApiSuccessEnvelope[AuthTokenData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "JSON hỏng hoặc thiếu exchange_code"},
        401: {"model": ApiErrorEnvelope, "description": "Mã SSO sai, hết hạn hoặc đã dùng"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
        503: {"model": ApiErrorEnvelope, "description": "SSO chưa được bật"},
    },
    summary="Đổi mã một lần exchange_code lấy cặp access/refresh token nội bộ",
)
def sso_exchange(
    request: Request,
    payload: SsoExchangeRequest,
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    sso_service = request.app.state.sso_service
    data = sso_service.exchange_code(raw_exchange_code=payload.exchange_code)
    return build_success_response(
        request,
        code="LOGIN_SUCCESS",
        message="Đăng nhập SSO thành công.",
        data=data,
    )
