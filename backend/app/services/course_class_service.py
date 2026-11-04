"""Course class listing, detail, and Admin management service (Spec Sections 08, 09, 14, 15)."""

from __future__ import annotations

import math
from typing import Any

import psycopg

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldErrorCode, FieldErrorItem
from app.db.pool import DatabaseManager
from app.repositories.course_class_repo import CourseClassRepository
from app.repositories.registration_repo import RegistrationRepository
from app.schemas.course_class import AdminCourseClassUpsertRequest


def build_pagination(page: int, page_size: int, total_items: int) -> dict[str, int]:
    total_pages = 0 if total_items == 0 else math.ceil(total_items / page_size)
    return {
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }


def _normalize_schedule_set(
    schedules: list[dict[str, Any]],
) -> list[tuple[str, int, int, str]]:
    return sorted(
        (
            str(s["day_of_week"]),
            int(s["start_period"]),
            int(s["end_period"]),
            str(s["room"]).strip(),
        )
        for s in schedules
    )


class CourseClassService:
    """Handles read snapshots for STUDENT/ADMIN and locked mutations for ADMIN."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        class_repo: CourseClassRepository | None = None,
        reg_repo: RegistrationRepository | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._class_repo = class_repo or CourseClassRepository()
        self._reg_repo = reg_repo or RegistrationRepository()

    def list_course_classes(
        self,
        *,
        caller: dict[str, Any],
        page: int,
        page_size: int,
        q: str | None,
    ) -> dict[str, Any]:
        with self._db.read_snapshot(repeatable_read=True) as conn:
            rows, total_items = self._class_repo.list_course_classes_page(
                conn,
                q=q,
                page=page,
                page_size=page_size,
            )
            items = self._class_repo.hydrate_course_classes(
                conn,
                rows,
                caller_user_id=int(caller["user_id"]),
                caller_role=str(caller["role"]),
            )
        return {
            "items": items,
            "pagination": build_pagination(page, page_size, total_items),
        }

    def get_course_class_detail(
        self,
        *,
        caller: dict[str, Any],
        course_class_id: str,
    ) -> dict[str, Any]:
        with self._db.read_snapshot(repeatable_read=True) as conn:
            row = self._class_repo.get_course_class_by_id(conn, course_class_id)
            if row is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.CLASS_NOT_FOUND,
                    message="Không tìm thấy lớp học phần.",
                )
            hydrated = self._class_repo.hydrate_course_classes(
                conn,
                [row],
                caller_user_id=int(caller["user_id"]),
                caller_role=str(caller["role"]),
            )[0]
        return {"course_class": hydrated}

    def _validate_catalog_codes(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        payload: AdminCourseClassUpsertRequest,
    ) -> None:
        needed_codes = [payload.course_code, *payload.prerequisite_course_codes]
        existing_codes = self._class_repo.get_existing_course_codes(conn, needed_codes)

        field_errors: list[FieldErrorItem] = []
        if payload.course_code not in existing_codes:
            field_errors.append(
                FieldErrorItem(
                    field="course_code",
                    code=FieldErrorCode.INVALID_FORMAT,
                    message=f"Mã học phần '{payload.course_code}' không tồn tại trong danh mục.",
                )
            )
        for idx, p_code in enumerate(payload.prerequisite_course_codes):
            if p_code not in existing_codes:
                field_errors.append(
                    FieldErrorItem(
                        field=f"prerequisite_course_codes[{idx}]",
                        code=FieldErrorCode.INVALID_FORMAT,
                        message=f"Mã học phần tiên quyết '{p_code}' không tồn tại trong danh mục.",
                    )
                )
        if field_errors:
            raise AppError(
                status_code=400,
                code=ErrorCode.VALIDATION_ERROR,
                message="Dữ liệu danh mục học phần không hợp lệ.",
                errors=field_errors,
            )

    def create_course_class(
        self,
        *,
        caller: dict[str, Any],
        payload: AdminCourseClassUpsertRequest,
    ) -> dict[str, Any]:
        schedules_dicts = [s.model_dump() for s in payload.schedule]
        tuition_amount = int(payload.credits) * int(self._settings.tuition_per_credit)

        with self._db.transaction() as conn:
            self._validate_catalog_codes(conn, payload)
            new_id = self._class_repo.next_course_class_id(conn)
            try:
                self._class_repo.insert_course_class(
                    conn,
                    course_class_id=new_id,
                    class_code=payload.class_code,
                    course_code=payload.course_code,
                    course_name=payload.course_name,
                    credits=payload.credits,
                    capacity=payload.capacity,
                    remaining_seats=payload.capacity,
                    status=payload.status,
                    tuition_amount=tuition_amount,
                )
            except psycopg.errors.UniqueViolation as exc:
                constraint = getattr(exc.diag, "constraint_name", "") or ""
                if constraint == "uq_course_classes_class_code":
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.CLASS_CODE_EXISTS,
                        message="Mã lớp học phần đã tồn tại.",
                    ) from exc
                raise

            self._class_repo.replace_schedules_and_prerequisites(
                conn,
                course_class_id=new_id,
                schedules=schedules_dicts,
                prerequisite_codes=payload.prerequisite_course_codes,
            )
            created_row = self._class_repo.get_course_class_by_id(conn, new_id)
            assert created_row is not None
            hydrated = self._class_repo.hydrate_course_classes(
                conn,
                [created_row],
                caller_user_id=int(caller["user_id"]),
                caller_role="ADMIN",
            )[0]

        return {"course_class": hydrated}

    def update_course_class(
        self,
        *,
        caller: dict[str, Any],
        course_class_id: str,
        payload: AdminCourseClassUpsertRequest,
    ) -> dict[str, Any]:
        schedules_dicts = [s.model_dump() for s in payload.schedule]

        with self._db.transaction() as conn:
            self._validate_catalog_codes(conn, payload)

            # Admin locks `course_classes` ONLY (never locks `users` afterwards)
            locked = self._class_repo.lock_course_class_by_id(conn, course_class_id)
            if locked is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.CLASS_NOT_FOUND,
                    message="Không tìm thấy lớp học phần.",
                )

            active_count = self._reg_repo.count_active_registrations_for_class(
                conn, course_class_id
            )
            if payload.capacity < active_count:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.CAPACITY_BELOW_REGISTERED,
                    message="Sĩ số tối đa mới không được nhỏ hơn số sinh viên đang đăng ký.",
                )

            old_schedules = self._class_repo.get_class_schedules(conn, course_class_id)
            old_prereqs = self._class_repo.get_class_prerequisites_with_names(
                conn, course_class_id
            )
            old_prereq_set = {str(p["course_code"]) for p in old_prereqs}
            new_prereq_set = set(payload.prerequisite_course_codes)

            schedules_changed = _normalize_schedule_set(old_schedules) != _normalize_schedule_set(
                schedules_dicts
            )
            prereqs_changed = old_prereq_set != new_prereq_set

            if active_count > 0:
                if (
                    payload.class_code != str(locked["class_code"])
                    or payload.course_code != str(locked["course_code"])
                    or payload.credits != int(locked["credits"])
                    or schedules_changed
                    or prereqs_changed
                ):
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.CLASS_HAS_REGISTRATIONS,
                        message="Lớp đã có sinh viên đăng ký ACTIVE; chỉ được phép đổi tên lớp, sĩ số tối đa hoặc trạng thái.",
                    )
                new_tuition = int(locked["tuition_amount"])
            else:
                if payload.credits != int(locked["credits"]):
                    new_tuition = int(payload.credits) * int(self._settings.tuition_per_credit)
                else:
                    new_tuition = int(locked["tuition_amount"])

            new_remaining = payload.capacity - active_count

            try:
                self._class_repo.update_course_class(
                    conn,
                    course_class_id=course_class_id,
                    class_code=payload.class_code,
                    course_code=payload.course_code,
                    course_name=payload.course_name,
                    credits=payload.credits,
                    capacity=payload.capacity,
                    remaining_seats=new_remaining,
                    status=payload.status,
                    tuition_amount=new_tuition,
                )
            except psycopg.errors.UniqueViolation as exc:
                constraint = getattr(exc.diag, "constraint_name", "") or ""
                if constraint == "uq_course_classes_class_code":
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.CLASS_CODE_EXISTS,
                        message="Mã lớp học phần đã tồn tại.",
                    ) from exc
                raise

            if active_count == 0:
                self._class_repo.replace_schedules_and_prerequisites(
                    conn,
                    course_class_id=course_class_id,
                    schedules=schedules_dicts,
                    prerequisite_codes=payload.prerequisite_course_codes,
                )

            updated_row = self._class_repo.get_course_class_by_id(conn, course_class_id)
            assert updated_row is not None
            hydrated = self._class_repo.hydrate_course_classes(
                conn,
                [updated_row],
                caller_user_id=int(caller["user_id"]),
                caller_role="ADMIN",
            )[0]

        return {"course_class": hydrated}

    def patch_course_class_status(
        self,
        *,
        caller: dict[str, Any],
        course_class_id: str,
        status: str,
    ) -> dict[str, Any]:
        with self._db.transaction() as conn:
            locked = self._class_repo.lock_course_class_by_id(conn, course_class_id)
            if locked is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.CLASS_NOT_FOUND,
                    message="Không tìm thấy lớp học phần.",
                )

            if str(locked["status"]) != status:
                self._class_repo.update_course_class_status(
                    conn,
                    course_class_id=course_class_id,
                    status=status,
                )

            updated_row = self._class_repo.get_course_class_by_id(conn, course_class_id)
            assert updated_row is not None
            hydrated = self._class_repo.hydrate_course_classes(
                conn,
                [updated_row],
                caller_user_id=int(caller["user_id"]),
                caller_role="ADMIN",
            )[0]

        return {"course_class": hydrated}
