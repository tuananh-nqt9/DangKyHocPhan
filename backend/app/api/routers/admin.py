"""Admin course class management endpoints (Spec Sections 14 & 15)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.api.deps import (
    AdminContractRoute,
    build_success_response,
    require_admin,
    require_no_query_params,
    validate_path_course_class_id,
)
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.schemas.course_class import (
    AdminCourseClassStatusRequest,
    AdminCourseClassUpsertRequest,
    CourseClassDetailData,
)

router = APIRouter(
    prefix="/admin/course-classes",
    tags=["Admin Course Classes"],
    route_class=AdminContractRoute,
)


@router.post(
    "",
    status_code=201,
    response_model=ApiSuccessEnvelope[CourseClassDetailData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Dữ liệu tạo lớp hoặc mã học phần không hợp lệ"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản ADMIN"},
        409: {"model": ApiErrorEnvelope, "description": "Trùng class_code (CLASS_CODE_EXISTS)"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
    },
    summary="Tạo lớp học phần mới (ADMIN)",
)
def admin_create_course_class(
    request: Request,
    payload: AdminCourseClassUpsertRequest,
    caller: dict[str, Any] = Depends(require_admin),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    service = request.app.state.course_class_service
    data = service.create_course_class(caller=caller, payload=payload)
    return build_success_response(
        request,
        code="COURSE_CLASS_CREATED",
        message="Tạo lớp học phần thành công.",
        data=data,
        status_code=201,
    )


@router.put(
    "/{course_class_id}",
    response_model=ApiSuccessEnvelope[CourseClassDetailData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Dữ liệu sửa lớp không hợp lệ"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản ADMIN"},
        404: {"model": ApiErrorEnvelope, "description": "Không tìm thấy lớp học phần"},
        409: {
            "model": ApiErrorEnvelope,
            "description": "CAPACITY_BELOW_REGISTERED, CLASS_HAS_REGISTRATIONS hoặc CLASS_CODE_EXISTS",
        },
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
    },
    summary="Cập nhật toàn bộ thông tin lớp học phần (ADMIN)",
)
def admin_update_course_class(
    request: Request,
    payload: AdminCourseClassUpsertRequest,
    course_class_id: str = Path(..., examples=["LHP001"]),
    caller: dict[str, Any] = Depends(require_admin),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    valid_id = validate_path_course_class_id(course_class_id)
    service = request.app.state.course_class_service
    data = service.update_course_class(
        caller=caller,
        course_class_id=valid_id,
        payload=payload,
    )
    return build_success_response(
        request,
        code="COURSE_CLASS_UPDATED",
        message="Cập nhật lớp học phần thành công.",
        data=data,
    )


@router.patch(
    "/{course_class_id}/status",
    response_model=ApiSuccessEnvelope[CourseClassDetailData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Dữ liệu trạng thái không hợp lệ"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        403: {"model": ApiErrorEnvelope, "description": "Không phải tài khoản ADMIN"},
        404: {"model": ApiErrorEnvelope, "description": "Không tìm thấy lớp học phần"},
        415: {"model": ApiErrorEnvelope, "description": "Sai Content-Type"},
    },
    summary="Mở hoặc đóng đăng ký cho lớp học phần (ADMIN)",
)
def admin_patch_course_class_status(
    request: Request,
    payload: AdminCourseClassStatusRequest,
    course_class_id: str = Path(..., examples=["LHP001"]),
    caller: dict[str, Any] = Depends(require_admin),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    valid_id = validate_path_course_class_id(course_class_id)
    service = request.app.state.course_class_service
    data = service.patch_course_class_status(
        caller=caller,
        course_class_id=valid_id,
        status=payload.status,
    )
    return build_success_response(
        request,
        code="COURSE_CLASS_STATUS_UPDATED",
        message="Cập nhật trạng thái lớp học phần thành công.",
        data=data,
    )
