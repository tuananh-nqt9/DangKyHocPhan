"""Student registration, cancellation, and personal registration list endpoints (Spec Sections 10, 11, 12)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request
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
    validate_path_registration_id,
)
from app.core.errors import AppError, ErrorCode, FieldErrorCode, FieldErrorItem
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.schemas.registration import (
    CancelSuccessData,
    MyRegistrationsData,
    RegisterRequest,
    RegisterSuccessData,
)

router = APIRouter(tags=["Registrations"], route_class=StudentContractRoute)


@router.post(
    "/register",
    response_model=ApiSuccessEnvelope[RegisterSuccessData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Lỗi dữ liệu đầu vào hoặc thiếu Idempotency-Key"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Sai quyền, lệch student_id hoặc thiếu/sai queue token"},
        404: {"model": ApiErrorEnvelope, "description": "Lớp học phần không tồn tại"},
        409: {"model": ApiErrorEnvelope, "description": "Hết chỗ, trùng đăng ký, đóng lớp, thiếu tiên quyết, trùng lịch hoặc đang xử lý"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
        422: {"model": ApiErrorEnvelope, "description": "Tái sử dụng Idempotency-Key cho dữ liệu khác"},
        503: {"model": ApiErrorEnvelope, "description": "Hệ thống bận hoặc dịch vụ gián đoạn"},
    },
    summary="Đăng ký lớp học phần nguyên tử có kiểm soát đồng thời và Idempotency-Key",
)
def register_course_class(
    request: Request,
    payload: RegisterRequest,
    caller: dict[str, Any] = Depends(require_student),
    idempotency_key: str = Depends(require_idempotency_key),
    x_queue_token: str | None = Header(
        default=None,
        alias="X-Queue-Token",
        description="Token lượt đăng ký từ `/api/v1/queue/status` khi hàng đợi bật.",
    ),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    service = request.app.state.registration_service
    outcome = service.register(
        caller=caller,
        payload=payload,
        idempotency_key=idempotency_key,
        queue_token=x_queue_token,
        request_id=get_request_id(request),
    )
    return build_idempotent_response(request, outcome)


@router.delete(
    "/registrations/{registration_id}",
    response_model=ApiSuccessEnvelope[CancelSuccessData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "ID sai định dạng hoặc thiếu Idempotency-Key"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản STUDENT"},
        404: {"model": ApiErrorEnvelope, "description": "Đăng ký không tồn tại, không thuộc mình hoặc đã hủy"},
        409: {"model": ApiErrorEnvelope, "description": "Cùng Idempotency-Key đang xử lý"},
        422: {"model": ApiErrorEnvelope, "description": "Tái sử dụng Idempotency-Key cho thao tác khác"},
    },
    summary="Hủy đăng ký học phần và hoàn tiền mô phỏng nếu đã thanh toán",
)
def cancel_registration(
    request: Request,
    registration_id: str = Path(..., examples=["4d0ce29e-9e4d-4e0a-8a92-f776fe905001"]),
    caller: dict[str, Any] = Depends(require_student),
    idempotency_key: str = Depends(require_idempotency_key),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    valid_reg_id = validate_path_registration_id(registration_id)
    service = request.app.state.registration_service
    outcome = service.cancel_registration(
        caller=caller,
        registration_id=valid_reg_id,
        idempotency_key=idempotency_key,
        request_id=get_request_id(request),
    )
    return build_idempotent_response(request, outcome)


@router.get(
    "/registrations/me",
    response_model=ApiSuccessEnvelope[MyRegistrationsData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Tham số lọc hoặc phân trang không hợp lệ"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản STUDENT"},
    },
    summary="Danh sách đăng ký và lịch sử đăng ký của sinh viên đang đăng nhập",
)
def get_my_registrations(
    request: Request,
    caller: dict[str, Any] = Depends(require_student),
    _page_doc: int | None = Query(default=1, alias="page"),
    _page_size_doc: int | None = Query(default=20, alias="page_size"),
    _status_doc: str | None = Query(
        default="ACTIVE",
        alias="status",
        description="ACTIVE | CANCELLED | ALL (mặc định ACTIVE)",
    ),
) -> JSONResponse:
    page, page_size = parse_pagination_params(
        request,
        extra_allowed=frozenset({"status"}),
    )
    raw_status = request.query_params.get("status", "ACTIVE")
    if raw_status not in ("ACTIVE", "CANCELLED", "ALL"):
        raise AppError(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message="Tham số 'status' phải là ACTIVE, CANCELLED hoặc ALL.",
            errors=[
                FieldErrorItem(
                    field="status",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message="Giá trị hợp lệ của 'status' gồm ACTIVE, CANCELLED, ALL.",
                )
            ],
        )

    service = request.app.state.registration_service
    data = service.list_my_registrations(
        caller=caller,
        status_filter=raw_status,
        page=page,
        page_size=page_size,
    )
    return build_success_response(
        request,
        code="REGISTRATIONS_FETCHED",
        message="Lấy danh sách đăng ký thành công.",
        data=data,
    )
