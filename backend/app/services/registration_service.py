"""Atomic student registration, cancellation, simulated refund, and list service (Spec Sections 10, 11, 12)."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg import Connection

from app.core.clock import format_utc_z, utc_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldErrorCode, FieldErrorItem
from app.db.pool import DatabaseManager
from app.repositories.auth_repo import AuthRepository
from app.repositories.course_class_repo import CourseClassRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.registration_repo import RegistrationRepository
from app.schemas.registration import RegisterRequest
from app.services.course_class_service import build_pagination
from app.services.idempotency_service import (
    DomainOperationResult,
    FaultHooks,
    IdempotencyExecutionOutcome,
    IdempotencyService,
    compute_request_fingerprint,
)
from app.services.queue_service import QueueService


def serialize_registration_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "registration_id": str(row["registration_id"]),
        "student_id": str(row["student_id"]),
        "course_class_id": str(row["course_class_id"]),
        "class_code": str(row["class_code"]),
        "course_name": str(row["course_name"]),
        "credits": int(row["credits"]),
        "status": str(row["status"]),
        "payment_status": str(row["payment_status"]),
        "tuition_amount": int(row["tuition_amount"]),
        "registered_at": format_utc_z(row["registered_at"]) or "",
        "cancelled_at": format_utc_z(row["cancelled_at"]),
    }


class RegistrationService:
    """Enforces lock hierarchy `user -> course_class -> registration -> payment`."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        idempotency_service: IdempotencyService,
        queue_service: QueueService,
        auth_repo: AuthRepository | None = None,
        class_repo: CourseClassRepository | None = None,
        reg_repo: RegistrationRepository | None = None,
        payment_repo: PaymentRepository | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._idempotency = idempotency_service
        self._queue = queue_service
        self._auth_repo = auth_repo or AuthRepository()
        self._class_repo = class_repo or CourseClassRepository()
        self._reg_repo = reg_repo or RegistrationRepository()
        self._payment_repo = payment_repo or PaymentRepository()

    def register(
        self,
        *,
        caller: dict[str, Any],
        payload: RegisterRequest,
        idempotency_key: str,
        queue_token: str | None,
        request_id: str,
    ) -> IdempotencyExecutionOutcome:
        # Step 3 of Spec Section 10: verify student_id matches Bearer token owner
        if payload.student_id != str(caller["student_id"]):
            raise AppError(
                status_code=403,
                code=ErrorCode.STUDENT_MISMATCH,
                message="Mã sinh viên trong yêu cầu không khớp phiên đăng nhập hiện tại.",
            )

        canonical_path = f"{self._settings.api_v1_prefix}/register"
        body_dict = payload.model_dump()
        fingerprint = compute_request_fingerprint("POST", canonical_path, body_dict)

        # Step 4: Fast replay pre-check BEFORE queue token verification!
        prechecked = self._idempotency.precheck_completed_record(
            user_id=int(caller["user_id"]),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if prechecked is not None:
            return prechecked

        # Step 5: Queue admission check for new operations when QUEUE_ENABLED=true
        self._queue.verify_ready_token(str(caller["student_id"]), queue_token)

        # Step 6..9: Atomic PostgreSQL transaction + idempotency persistence
        def _do_register(conn: Connection[dict[str, Any]]) -> DomainOperationResult:
            user_id = int(caller["user_id"])
            student_id = str(caller["student_id"])
            class_id = payload.course_class_id

            # Lock 1: User row (serializes concurrent registrations by same student across different classes)
            self._auth_repo.lock_user_by_id(conn, user_id)

            # Lock 2: Target course_class row (serializes seat competition on this class)
            class_row = self._class_repo.lock_course_class_by_id(conn, class_id)
            if class_row is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.CLASS_NOT_FOUND,
                    message="Không tìm thấy lớp học phần.",
                    persist_idempotency=True,
                )

            # Check 1: Already ACTIVE?
            existing_active = self._reg_repo.get_active_registration_for_user_class(
                conn,
                user_id=user_id,
                course_class_id=class_id,
            )
            if existing_active is not None:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.ALREADY_REGISTERED,
                    message="Sinh viên đã đăng ký lớp học phần này.",
                    persist_idempotency=True,
                )

            # Check 2: Is class OPEN?
            if str(class_row["status"]) != "OPEN":
                raise AppError(
                    status_code=409,
                    code=ErrorCode.REGISTRATION_CLOSED,
                    message="Lớp học phần đã đóng đăng ký.",
                    persist_idempotency=True,
                )

            # Check 3: Prerequisites satisfied?
            prereq_rows = self._class_repo.get_class_prerequisites_with_names(conn, class_id)
            if prereq_rows:
                completed = self._class_repo.get_student_completed_courses(conn, user_id)
                missing_errors: list[FieldErrorItem] = []
                for idx, prereq in enumerate(prereq_rows):
                    p_code = str(prereq["course_code"])
                    p_name = str(prereq["course_name"])
                    if p_code not in completed:
                        missing_errors.append(
                            FieldErrorItem(
                                field=f"prerequisites[{idx}].course_code",
                                code=FieldErrorCode.PREREQUISITE_MISSING,
                                message=f"{p_code} — {p_name} chưa hoàn thành.",
                            )
                        )
                if missing_errors:
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.PREREQUISITE_NOT_MET,
                        message="Chưa đạt tiên quyết.",
                        errors=missing_errors,
                        persist_idempotency=True,
                    )

            # Check 4: Schedule conflicts with existing ACTIVE registrations?
            target_schedules = self._class_repo.get_class_schedules(conn, class_id)
            if target_schedules:
                active_schedules = self._reg_repo.get_active_schedules_for_user(conn, user_id)
                conflict_errors: list[FieldErrorItem] = []
                for t_slot in target_schedules:
                    t_day = str(t_slot["day_of_week"])
                    t_start = int(t_slot["start_period"])
                    t_end = int(t_slot["end_period"])
                    for a_slot in active_schedules:
                        if str(a_slot["day_of_week"]) != t_day:
                            continue
                        a_start = int(a_slot["start_period"])
                        a_end = int(a_slot["end_period"])
                        ov_start = max(t_start, a_start)
                        ov_end = min(t_end, a_end)
                        if ov_start <= ov_end:
                            other_id = str(a_slot["course_class_id"])
                            conflict_errors.append(
                                FieldErrorItem(
                                    field="schedule",
                                    code=FieldErrorCode.CLASS_TIME_CONFLICT,
                                    message=f"Trùng lớp {other_id} vào {t_day} tiết {ov_start}–{ov_end}.",
                                )
                            )
                if conflict_errors:
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.SCHEDULE_CONFLICT,
                        message="Trùng lịch học.",
                        errors=conflict_errors,
                        persist_idempotency=True,
                    )

            # Check 5: Remaining seats > 0?
            if int(class_row["remaining_seats"]) <= 0:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.CLASS_FULL,
                    message="Lớp học phần đã hết chỗ.",
                    persist_idempotency=True,
                )

            # Perform atomic registration INSERT + seat decrement
            new_reg_id = str(uuid.uuid4())
            now = utc_now()
            try:
                reg_row = self._reg_repo.insert_registration(
                    conn,
                    registration_id=new_reg_id,
                    user_id=user_id,
                    student_id=student_id,
                    course_class_id=class_id,
                    class_code=str(class_row["class_code"]),
                    course_name=str(class_row["course_name"]),
                    credits=int(class_row["credits"]),
                    tuition_amount=int(class_row["tuition_amount"]),
                    registered_at=now,
                )
            except psycopg.errors.UniqueViolation as exc:
                idx_name = getattr(exc.diag, "constraint_name", "") or ""
                if idx_name == "uq_registrations_active_user_class":
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.ALREADY_REGISTERED,
                        message="Sinh viên đã đăng ký lớp học phần này.",
                        persist_idempotency=True,
                    ) from exc
                raise

            # Test-only fault hook (TC10: simulate failure between INSERT and UPDATE)
            if FaultHooks.after_registration_insert is not None:
                FaultHooks.after_registration_insert()

            seat_updated = self._class_repo.decrement_remaining_seats(conn, class_id)
            if not seat_updated:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.CLASS_FULL,
                    message="Lớp học phần đã hết chỗ.",
                    persist_idempotency=True,
                )

            updated_class_row = self._class_repo.get_course_class_by_id(conn, class_id)
            assert updated_class_row is not None
            hydrated_class = self._class_repo.hydrate_course_classes(
                conn,
                [updated_class_row],
                caller_user_id=user_id,
                caller_role="STUDENT",
            )[0]

            return DomainOperationResult(
                status_code=200,
                code="REGISTERED",
                message="Đăng ký học phần thành công.",
                data={
                    "registration": serialize_registration_row(reg_row),
                    "course_class": hydrated_class,
                },
            )

        return self._idempotency.execute(
            user_id=int(caller["user_id"]),
            idempotency_key=idempotency_key,
            request_method="POST",
            request_path=canonical_path,
            fingerprint=fingerprint,
            request_id=request_id,
            operation=_do_register,
        )

    def cancel_registration(
        self,
        *,
        caller: dict[str, Any],
        registration_id: str,
        idempotency_key: str,
        request_id: str,
    ) -> IdempotencyExecutionOutcome:
        norm_reg_id = registration_id.lower()
        canonical_path = f"{self._settings.api_v1_prefix}/registrations/{norm_reg_id}"
        fingerprint = compute_request_fingerprint("DELETE", canonical_path, None)

        prechecked = self._idempotency.precheck_completed_record(
            user_id=int(caller["user_id"]),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if prechecked is not None:
            return prechecked

        def _do_cancel(conn: Connection[dict[str, Any]]) -> DomainOperationResult:
            user_id = int(caller["user_id"])

            # Lock 1: User row
            self._auth_repo.lock_user_by_id(conn, user_id)

            # Non-locking target lookup so we maintain strict lock order `user -> class -> registration`
            target_class_id = self._reg_repo.find_course_class_id_for_registration(
                conn, norm_reg_id
            )
            if target_class_id is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.REGISTRATION_NOT_FOUND,
                    message="Không tìm thấy đăng ký học phần cần hủy.",
                    persist_idempotency=True,
                )

            # Lock 2: CourseClass row
            class_row = self._class_repo.lock_course_class_by_id(conn, target_class_id)
            if class_row is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.REGISTRATION_NOT_FOUND,
                    message="Không tìm thấy đăng ký học phần cần hủy.",
                    persist_idempotency=True,
                )

            # Lock 3: Registration row — re-verify ownership & ACTIVE status AFTER lock!
            reg_row = self._reg_repo.lock_registration_by_id(conn, norm_reg_id)
            if (
                reg_row is None
                or int(reg_row["user_id"]) != user_id
                or str(reg_row["status"]) != "ACTIVE"
            ):
                raise AppError(
                    status_code=404,
                    code=ErrorCode.REGISTRATION_NOT_FOUND,
                    message="Không tìm thấy đăng ký học phần đang hoạt động.",
                    persist_idempotency=True,
                )

            now = utc_now()
            cancel_ts = max(now, reg_row["registered_at"])
            refund_payload: dict[str, Any] | None = None

            if str(reg_row["payment_status"]) == "PAID":
                # Lock 4: Payment row
                pay_row = self._payment_repo.lock_payment_by_registration_id(conn, norm_reg_id)
                if pay_row is None:
                    raise AppError(
                        status_code=500,
                        code=ErrorCode.INTERNAL_ERROR,
                        message="Dữ liệu thanh toán không đồng nhất.",
                    )
                refund_ts = max(cancel_ts, pay_row["paid_at"])
                refunded_pay = self._payment_repo.mark_refunded(
                    conn,
                    payment_id=str(pay_row["payment_id"]),
                    refunded_at=refund_ts,
                )
                cancelled_reg = self._reg_repo.mark_cancelled(
                    conn,
                    registration_id=norm_reg_id,
                    new_payment_status="REFUNDED",
                    cancelled_at=refund_ts,
                )
                refund_payload = {
                    "payment_id": str(refunded_pay["payment_id"]),
                    "amount": int(refunded_pay["amount"]),
                    "currency": str(refunded_pay["currency"]),
                    "status": "REFUNDED",
                    "refunded_at": format_utc_z(refunded_pay["refunded_at"]) or "",
                }
            else:
                cancelled_reg = self._reg_repo.mark_cancelled(
                    conn,
                    registration_id=norm_reg_id,
                    new_payment_status="UNPAID",
                    cancelled_at=cancel_ts,
                )

            seat_restored = self._class_repo.increment_remaining_seats(conn, target_class_id)
            if not seat_restored:
                raise AppError(
                    status_code=500,
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Không thể hoàn trả chỗ ngồi cho lớp học phần.",
                )

            updated_class_row = self._class_repo.get_course_class_by_id(conn, target_class_id)
            assert updated_class_row is not None
            hydrated_class = self._class_repo.hydrate_course_classes(
                conn,
                [updated_class_row],
                caller_user_id=user_id,
                caller_role="STUDENT",
            )[0]

            return DomainOperationResult(
                status_code=200,
                code="REGISTRATION_CANCELLED",
                message="Hủy đăng ký học phần thành công.",
                data={
                    "registration": serialize_registration_row(cancelled_reg),
                    "course_class": hydrated_class,
                    "refund": refund_payload,
                },
            )

        return self._idempotency.execute(
            user_id=int(caller["user_id"]),
            idempotency_key=idempotency_key,
            request_method="DELETE",
            request_path=canonical_path,
            fingerprint=fingerprint,
            request_id=request_id,
            operation=_do_cancel,
        )

    def list_my_registrations(
        self,
        *,
        caller: dict[str, Any],
        status_filter: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        with self._db.read_snapshot(repeatable_read=True) as conn:
            rows, total_items = self._reg_repo.list_user_registrations(
                conn,
                user_id=int(caller["user_id"]),
                status_filter=status_filter,
                page=page,
                page_size=page_size,
            )
        return {
            "student_id": str(caller["student_id"]),
            "items": [serialize_registration_row(r) for r in rows],
            "pagination": build_pagination(page, page_size, total_items),
        }
