"""Simulated payment and payment history endpoints (Spec Section 13)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.deps import (
    StudentContractRoute,
    build_idempotent_response,
    build_success_response,
    get_request_id,
    parse_pagination_params,
    require_idempotency_key,
    require_no_query_params,
    require_student,
)
from app.core.errors import AppError, ErrorCode, FieldErrorCode, FieldErrorItem
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.schemas.payment import (
    MyPaymentsData,
    PaymentCreateRequest,
    PaymentSuccessData,
)

router = APIRouter(prefix="/payments", tags=["Payments"], route_class=StudentContractRoute)


@router.post(
    "",
    response_model=ApiSuccessEnvelope[PaymentSuccessData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Dữ liệu sai hoặc thiếu Idempotency-Key"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản STUDENT"},
        404: {"model": ApiErrorEnvelope, "description": "Đăng ký không tồn tại, không thuộc mình hoặc không còn ACTIVE"},
        409: {"model": ApiErrorEnvelope, "description": "Đã thanh toán (ALREADY_PAID) hoặc đang xử lý"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
        422: {"model": ApiErrorEnvelope, "description": "Tái sử dụng Idempotency-Key cho dữ liệu khác"},
        503: {"model": ApiErrorEnvelope, "description": "Chức năng tắt hoặc hệ thống bận"},
    },
    summary="Thanh toán học phí mô phỏng theo registration_id",
)
def create_payment(
    request: Request,
    payload: PaymentCreateRequest,
    caller: dict[str, Any] = Depends(require_student),
    idempotency_key: str = Depends(require_idempotency_key),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    service = request.app.state.payment_service
    outcome = service.create_payment(
        caller=caller,
        payload=payload,
        idempotency_key=idempotency_key,
        request_id=get_request_id(request),
    )
    return build_idempotent_response(request, outcome)


@router.get(
    "/me",
    response_model=ApiSuccessEnvelope[MyPaymentsData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Tham số phân trang hoặc trạng thái sai"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản STUDENT"},
        503: {"model": ApiErrorEnvelope, "description": "Chức năng thanh toán đang tắt"},
    },
    summary="Lịch sử thanh toán và hoàn tiền mô phỏng của sinh viên",
)
def get_my_payments(
    request: Request,
    caller: dict[str, Any] = Depends(require_student),
    _page_doc: int | None = Query(default=1, alias="page"),
    _page_size_doc: int | None = Query(default=20, alias="page_size"),
    _status_doc: str | None = Query(
        default="ALL",
        alias="status",
        description="PAID | REFUNDED | ALL (mặc định ALL)",
    ),
) -> JSONResponse:
    page, page_size = parse_pagination_params(
        request,
        extra_allowed=frozenset({"status"}),
    )
    raw_status = request.query_params.get("status", "ALL")
    if raw_status not in ("PAID", "REFUNDED", "ALL"):
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Tham số 'status' phải là PAID, REFUNDED hoặc ALL.",
            errors=[
                FieldErrorItem(
                    field="status",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Giá trị hợp lệ của 'status' gồm PAID, REFUNDED, ALL.",
                )
            ],
        )

    service = request.app.state.payment_service
    data = service.list_my_payments(
        caller=caller,
        status_filter=raw_status,
        page=page,
        page_size=page_size,
    )
    return build_success_response(
        request,
        code="PAYMENTS_FETCHED",
        message="Lấy lịch sử thanh toán thành công.",
        data=data,
    )
