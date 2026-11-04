"""Simulated tuition payment and payment history service (Spec Section 13)."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg import Connection

from app.core.clock import format_utc_z, utc_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.pool import DatabaseManager
from app.repositories.auth_repo import AuthRepository
from app.repositories.course_class_repo import CourseClassRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.registration_repo import RegistrationRepository
from app.schemas.payment import PaymentCreateRequest
from app.services.course_class_service import build_pagination
from app.services.idempotency_service import (
    DomainOperationResult,
    IdempotencyExecutionOutcome,
    IdempotencyService,
    compute_request_fingerprint,
)
from app.services.registration_service import serialize_registration_row


def serialize_payment_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "payment_id": str(row["payment_id"]),
        "registration_id": str(row["registration_id"]),
        "course_class_id": str(row["course_class_id"]),
        "class_code": str(row["class_code"]),
        "amount": int(row["amount"]),
        "currency": str(row["currency"]),
        "status": str(row["status"]),
        "paid_at": format_utc_z(row["paid_at"]) or "",
        "refunded_at": format_utc_z(row["refunded_at"]),
    }


class PaymentService:
    """Simulated internal payment service preserving lock order `user -> class -> registration`."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        idempotency_service: IdempotencyService,
        auth_repo: AuthRepository | None = None,
        class_repo: CourseClassRepository | None = None,
        reg_repo: RegistrationRepository | None = None,
        payment_repo: PaymentRepository | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._idempotency = idempotency_service
        self._auth_repo = auth_repo or AuthRepository()
        self._class_repo = class_repo or CourseClassRepository()
        self._reg_repo = reg_repo or RegistrationRepository()
        self._payment_repo = payment_repo or PaymentRepository()

    def _ensure_enabled(self) -> None:
        if not self._settings.payments_enabled:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Chức năng thanh toán chưa được bật trên môi trường này.",
            )

    def create_payment(
        self,
        *,
        caller: dict[str, Any],
        payload: PaymentCreateRequest,
        idempotency_key: str,
        request_id: str,
    ) -> IdempotencyExecutionOutcome:
        self._ensure_enabled()

        canonical_path = f"{self._settings.api_v1_prefix}/payments"
        body_dict = payload.model_dump()
        fingerprint = compute_request_fingerprint("POST", canonical_path, body_dict)

        prechecked = self._idempotency.precheck_completed_record(
            user_id=int(caller["user_id"]),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if prechecked is not None:
            return prechecked

        def _do_pay(conn: Connection[dict[str, Any]]) -> DomainOperationResult:
            user_id = int(caller["user_id"])
            reg_id = payload.registration_id.lower()

            # Lock 1: User row
            self._auth_repo.lock_user_by_id(conn, user_id)

            # Non-locking lookup of class_id to preserve lock order `user -> class -> registration`
            target_class_id = self._reg_repo.find_course_class_id_for_registration(conn, reg_id)
            if target_class_id is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.REGISTRATION_NOT_FOUND,
                    message="Không tìm thấy đăng ký học phần hợp lệ để thanh toán.",
                    persist_idempotency=True,
                )

            # Lock 2: CourseClass row
            class_row = self._class_repo.lock_course_class_by_id(conn, target_class_id)
            if class_row is None:
                raise AppError(
                    status_code=404,
                    code=ErrorCode.REGISTRATION_NOT_FOUND,
                    message="Không tìm thấy đăng ký học phần hợp lệ để thanh toán.",
                    persist_idempotency=True,
                )

            # Lock 3: Registration row
            reg_row = self._reg_repo.lock_registration_by_id(conn, reg_id)
            if (
                reg_row is None
                or int(reg_row["user_id"]) != user_id
                or str(reg_row["status"]) != "ACTIVE"
            ):
                raise AppError(
                    status_code=404,
                    code=ErrorCode.REGISTRATION_NOT_FOUND,
                    message="Chỉ được thanh toán đăng ký học phần đang ACTIVE của chính mình.",
                    persist_idempotency=True,
                )

            if str(reg_row["payment_status"]) == "PAID":
                raise AppError(
                    status_code=409,
                    code=ErrorCode.ALREADY_PAID,
                    message="Đăng ký học phần này đã được thanh toán.",
                    persist_idempotency=True,
                )

            now = utc_now()
            paid_at = max(now, reg_row["registered_at"])
            new_payment_id = str(uuid.uuid4())

            try:
                pay_row = self._payment_repo.insert_payment(
                    conn,
                    payment_id=new_payment_id,
                    registration_id=reg_id,
                    user_id=user_id,
                    course_class_id=str(reg_row["course_class_id"]),
                    class_code=str(reg_row["class_code"]),
                    amount=int(reg_row["tuition_amount"]),
                    paid_at=paid_at,
                )
            except psycopg.errors.UniqueViolation as exc:
                constraint = getattr(exc.diag, "constraint_name", "") or ""
                if constraint == "uq_payments_registration_id":
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.ALREADY_PAID,
                        message="Đăng ký học phần này đã được thanh toán.",
                        persist_idempotency=True,
                    ) from exc
                raise

            updated_reg = self._reg_repo.mark_paid(conn, registration_id=reg_id)

            return DomainOperationResult(
                status_code=200,
                code="PAYMENT_SUCCESS",
                message="Thanh toán học phí mô phỏng thành công.",
                data={
                    "payment": serialize_payment_row(pay_row),
                    "registration": serialize_registration_row(updated_reg),
                },
            )

        return self._idempotency.execute(
            user_id=int(caller["user_id"]),
            idempotency_key=idempotency_key,
            request_method="POST",
            request_path=canonical_path,
            fingerprint=fingerprint,
            request_id=request_id,
            operation=_do_pay,
        )

    def list_my_payments(
        self,
        *,
        caller: dict[str, Any],
        status_filter: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._ensure_enabled()
        with self._db.read_snapshot(repeatable_read=True) as conn:
            rows, total_items = self._payment_repo.list_user_payments(
                conn,
                user_id=int(caller["user_id"]),
                status_filter=status_filter,
                page=page,
                page_size=page_size,
            )
        return {
            "items": [serialize_payment_row(r) for r in rows],
            "pagination": build_pagination(page, page_size, total_items),
        }
