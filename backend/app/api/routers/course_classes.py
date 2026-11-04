"""Course class list and detail endpoints for STUDENT and ADMIN (Spec Sections 08 & 09)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse

from app.api.deps import (
    AnyAuthContractRoute,
    build_success_response,
    parse_pagination_params,
    require_authenticated,
    require_no_query_params,
    validate_path_course_class_id,
)
from app.core.errors import AppError, ErrorCode, FieldErrorCode, FieldErrorItem
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope
from app.schemas.course_class import CourseClassDetailData, CourseClassListData

router = APIRouter(
    prefix="/course-classes",
    tags=["Course Classes"],
    route_class=AnyAuthContractRoute,
)


@router.get(
    "",
    response_model=ApiSuccessEnvelope[CourseClassListData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Tham số phân trang hoặc tìm kiếm sai"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
    },
    summary="Danh sách lớp học phần kèm trạng thái đăng ký của người gọi",
)
def list_course_classes(
    request: Request,
    caller: dict[str, Any] = Depends(require_authenticated),
    _page_doc: int | None = Query(default=1, alias="page", description="Trang (>= 1)"),
    _page_size_doc: int | None = Query(
        default=20, alias="page_size", description="Kích thước trang (1–100)"
    ),
    _q_doc: str | None = Query(
        default=None, alias="q", description="Từ khóa tìm theo mã lớp hoặc tên học phần (<= 100 ký tự)"
    ),
) -> JSONResponse:
    page, page_size = parse_pagination_params(
        request,
        extra_allowed=frozenset({"q"}),
    )
    raw_q = request.query_params.get("q")
    q_clean: str | None = None
    if raw_q is not None:
        trimmed = raw_q.strip()
        if len(trimmed) > 100:
            raise AppError(
                status_code=400,
                code=ErrorCode.VALIDATION_ERROR,
                message="Từ khóa tìm kiếm vượt quá 100 ký tự.",
                errors=[
                    FieldErrorItem(
                        field="q",
                        code=FieldErrorCode.OUT_OF_RANGE,
                        message="Tham số 'q' tối đa 100 ký tự sau khi cắt khoảng trắng.",
                    )
                ],
            )
        q_clean = trimmed if trimmed else None

    service = request.app.state.course_class_service
    data = service.list_course_classes(
        caller=caller,
        page=page,
        page_size=page_size,
        q=q_clean,
    )
    return build_success_response(
        request,
        code="COURSE_CLASSES_FETCHED",
        message="Lấy danh sách lớp học phần thành công.",
        data=data,
    )


@router.get(
    "/{course_class_id}",
    response_model=ApiSuccessEnvelope[CourseClassDetailData],
    responses={
        400: {"model": ApiErrorEnvelope, "description": "Mã lớp sai định dạng"},
        401: {"model": ApiErrorEnvelope, "description": "Chưa xác thực"},
        404: {"model": ApiErrorEnvelope, "description": "Lớp không tồn tại"},
    },
    summary="Chi tiết một lớp học phần kèm trạng thái của người gọi",
)
def get_course_class_detail(
    request: Request,
    course_class_id: str = Path(..., examples=["LHP001"]),
    caller: dict[str, Any] = Depends(require_authenticated),
    _no_query: None = Depends(require_no_query_params),
) -> JSONResponse:
    valid_id = validate_path_course_class_id(course_class_id)
    service = request.app.state.course_class_service
    data = service.get_course_class_detail(caller=caller, course_class_id=valid_id)
    return build_success_response(
        request,
        code="COURSE_CLASS_FETCHED",
        message="Lấy chi tiết lớp học phần thành công.",
        data=data,
    )
