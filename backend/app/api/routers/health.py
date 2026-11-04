"""Service health check endpoint (Spec Section 17)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import (
    PublicContractRoute,
    build_success_response,
    require_no_query_params,
)
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.schemas.health import HealthDataSchema

router = APIRouter(tags=["Health"], route_class=PublicContractRoute)


@router.get(
    "/health",
    response_model=ApiSuccessEnvelope[HealthDataSchema],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Tham số truy vấn không hợp lệ"},
        503: {"model": ApiErrorEnvelope, "description": "Cơ sở dữ liệu hoặc Redis (khi bật queue) không sẵn sàng"},
    },
    summary="Kiểm tra kết nối CSDL và trạng thái các tính năng bật",
)
def health_check(
    request: Request,
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    health_service = request.app.state.health_service
    data = health_service.check_health()
    return build_success_response(
        request,
        code="HEALTHY",
        message="Dịch vụ sẵn sàng.",
        data=data,
    )
