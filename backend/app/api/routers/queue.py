"""Redis FIFO admission queue endpoints (Spec Section 16)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import (
    StudentContractRoute,
    build_success_response,
    require_no_query_params,
    require_student,
)
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.schemas.queue import QueueJoinRequest, QueueStateSchema

router = APIRouter(prefix="/queue", tags=["Queue"], route_class=StudentContractRoute)


@router.post(
    "/join",
    response_model=ApiSuccessEnvelope[QueueStateSchema],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Body phải là `{}`"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản STUDENT"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
        503: {"model": ApiErrorEnvelope, "description": "Redis lỗi khi hàng đợi đang bật"},
    },
    summary="Tham gia hàng đợi đăng ký học phần FIFO",
)
def join_queue(
    request: Request,
    _payload: QueueJoinRequest,
    caller: dict[str, Any] = Depends(require_student),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    queue_service = request.app.state.queue_service
    data = queue_service.join_queue(str(caller["student_id"]))
    return build_success_response(
        request,
        code="QUEUE_JOINED",
        message="Tham gia hàng đợi thành công.",
        data=data,
    )


@router.get(
    "/status",
    response_model=ApiSuccessEnvelope[QueueStateSchema],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Tham số truy vấn không hợp lệ"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản STUDENT"},
        503: {"model": ApiErrorEnvelope, "description": "Redis lỗi khi hàng đợi đang bật"},
    },
    summary="Kiểm tra vị trí chờ hoặc nhận token lượt đăng ký READY",
)
def get_queue_status(
    request: Request,
    caller: dict[str, Any] = Depends(require_student),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    queue_service = request.app.state.queue_service
    data = queue_service.get_status(str(caller["student_id"]))
    return build_success_response(
        request,
        code="QUEUE_STATUS_FETCHED",
        message="Lấy trạng thái hàng đợi thành công.",
        data=data,
    )
