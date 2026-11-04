"""Export OpenAPI v3.0 specification and schema-validated JSON examples for TV3."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import FieldErrorCode, FieldErrorItem, build_error_envelope
from app.main import create_app
from app.schemas.auth import AuthTokenData, StudentSchema
from app.schemas.common import ApiErrorEnvelope, ApiSuccessEnvelope, PaginationSchema
from app.schemas.course_class import (
    CourseClassListData,
    CourseClassSchema,
    PrerequisiteItemSchema,
    ScheduleItemSchema,
)
from app.schemas.payment import PaymentSchema, PaymentSuccessData
from app.schemas.queue import QueueStateSchema
from app.schemas.registration import (
    CancelSuccessData,
    RefundInfoSchema,
    RegisterSuccessData,
    RegistrationSchema,
)

from scripts._console import ensure_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "docs" / "api_examples"
SAMPLE_REQ_ID = "8c6c3ed0-768d-4fc6-8792-7b7eae691501"
SAMPLE_REG_ID = "4d0ce29e-9e4d-4e0a-8a92-f776fe905001"
SAMPLE_PAY_ID = "61de10f7-8f5e-4d34-a3cd-0dcb5da42519"


def _write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def export_all() -> None:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    app = create_app()
    openapi_schema = app.openapi()
    _write_json(EXAMPLES_DIR / "openapi_v3_0.json", openapi_schema)

    (EXAMPLES_DIR / "README.md").write_text(
        "# Bộ JSON Fixtures Mẫu cho TV3 (`docs/api_examples/`)\n\n"
        "> **LƯU Ý QUAN TRỌNG**:\n"
        "> - Toàn bộ file JSON trong thư mục này được sinh tự động từ Pydantic schemas của backend TV2 (khớp Đặc tả v3.0).\n"
        "> - Các chuỗi `SAMPLE_ONLY_DO_NOT_USE_*` chỉ là dữ liệu minh họa cho UI mock của TV3 — **tuyệt đối không gửi token mẫu này tới backend thật**.\n"
        "> - Khi ghép tích hợp thật (Real API), TV3 phải tắt chế độ mock trong `apiClient`.\n",
        encoding="utf-8",
    )

    # 1. Login success
    login_env = ApiSuccessEnvelope[AuthTokenData](
        success=True,
        code="LOGIN_SUCCESS",
        message="Đăng nhập thành công.",
        data=AuthTokenData(
            access_token="SAMPLE_ONLY_DO_NOT_USE_ACCESS_TOKEN",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="SAMPLE_ONLY_DO_NOT_USE_REFRESH_TOKEN",
            refresh_expires_in=28800,
            student=StudentSchema(
                student_id="SV0001",
                full_name="Sinh viên mẫu 0001",
                role="STUDENT",
            ),
        ),
        request_id=SAMPLE_REQ_ID,
    )
    _write_json(EXAMPLES_DIR / "login_success.json", login_env.model_dump())

    # 2. Course classes list (UI seed)
    lhp001 = CourseClassSchema(
        course_class_id="LHP001",
        class_code="CNNT-01",
        course_code="CNNT",
        course_name="Công nghệ nền tảng",
        credits=3,
        capacity=50,
        remaining_seats=50,
        registered_count=0,
        status="OPEN",
        schedule=[
            ScheduleItemSchema(day_of_week="MON", start_period=1, end_period=3, room="A101")
        ],
        prerequisites=[
            PrerequisiteItemSchema(
                course_code="CS101",
                course_name="Nhập môn lập trình",
                satisfied=True,
            )
        ],
        tuition_amount=1500000,
        registration_status="NOT_REGISTERED",
        registration_id=None,
        payment_status=None,
    )
    list_env = ApiSuccessEnvelope[CourseClassListData](
        success=True,
        code="COURSE_CLASSES_FETCHED",
        message="Lấy danh sách lớp học phần thành công.",
        data=CourseClassListData(
            items=[lhp001],
            pagination=PaginationSchema(page=1, page_size=20, total_items=1, total_pages=1),
        ),
        request_id=SAMPLE_REQ_ID,
    )
    _write_json(EXAMPLES_DIR / "course_classes_list.json", list_env.model_dump())

    # 3. Empty list
    empty_env = ApiSuccessEnvelope[CourseClassListData](
        success=True,
        code="COURSE_CLASSES_FETCHED",
        message="Lấy danh sách lớp học phần thành công.",
        data=CourseClassListData(
            items=[],
            pagination=PaginationSchema(page=1, page_size=20, total_items=0, total_pages=0),
        ),
        request_id=SAMPLE_REQ_ID,
    )
    _write_json(EXAMPLES_DIR / "course_classes_empty.json", empty_env.model_dump())

    # 4. Register success
    reg_model = RegistrationSchema(
        registration_id=SAMPLE_REG_ID,
        student_id="SV0001",
        course_class_id="LHP001",
        class_code="CNNT-01",
        course_name="Công nghệ nền tảng",
        credits=3,
        status="ACTIVE",
        payment_status="UNPAID",
        tuition_amount=1500000,
        registered_at="2026-11-01T08:30:00Z",
        cancelled_at=None,
    )
    lhp001_after = lhp001.model_copy(
        update={
            "remaining_seats": 49,
            "registered_count": 1,
            "registration_status": "REGISTERED",
            "registration_id": SAMPLE_REG_ID,
            "payment_status": "UNPAID",
        }
    )
    reg_env = ApiSuccessEnvelope[RegisterSuccessData](
        success=True,
        code="REGISTERED",
        message="Đăng ký học phần thành công.",
        data=RegisterSuccessData(registration=reg_model, course_class=lhp001_after),
        request_id=SAMPLE_REQ_ID,
    )
    _write_json(EXAMPLES_DIR / "register_success.json", reg_env.model_dump())

    # 5. Payment & Cancel with refund
    pay_model = PaymentSchema(
        payment_id=SAMPLE_PAY_ID,
        registration_id=SAMPLE_REG_ID,
        course_class_id="LHP001",
        class_code="CNNT-01",
        amount=1500000,
        currency="VND",
        status="PAID",
        paid_at="2026-11-01T08:35:00Z",
        refunded_at=None,
    )
    pay_env = ApiSuccessEnvelope[PaymentSuccessData](
        success=True,
        code="PAYMENT_SUCCESS",
        message="Thanh toán học phí mô phỏng thành công.",
        data=PaymentSuccessData(
            payment=pay_model,
            registration=reg_model.model_copy(update={"payment_status": "PAID"}),
        ),
        request_id=SAMPLE_REQ_ID,
    )
    _write_json(EXAMPLES_DIR / "payment_success.json", pay_env.model_dump())

    cancel_refund_env = ApiSuccessEnvelope[CancelSuccessData](
        success=True,
        code="REGISTRATION_CANCELLED",
        message="Hủy đăng ký học phần thành công.",
        data=CancelSuccessData(
            registration=reg_model.model_copy(
                update={
                    "status": "CANCELLED",
                    "payment_status": "REFUNDED",
                    "cancelled_at": "2026-11-01T08:40:00Z",
                }
            ),
            course_class=lhp001,
            refund=RefundInfoSchema(
                payment_id=SAMPLE_PAY_ID,
                amount=1500000,
                currency="VND",
                status="REFUNDED",
                refunded_at="2026-11-01T08:40:00Z",
            ),
        ),
        request_id=SAMPLE_REQ_ID,
    )
    _write_json(EXAMPLES_DIR / "cancel_with_refund.json", cancel_refund_env.model_dump())

    # 6. Queue states
    queue_states = {
        "disabled": ApiSuccessEnvelope[QueueStateSchema](
            success=True,
            code="QUEUE_STATUS_FETCHED",
            message="Lấy trạng thái hàng đợi thành công.",
            data=QueueStateSchema(
                queue_enabled=False,
                status="NONE",
                position=None,
                estimated_wait_seconds=None,
                ready_expires_at=None,
                queue_token=None,
            ),
            request_id=SAMPLE_REQ_ID,
        ).model_dump(),
        "waiting": ApiSuccessEnvelope[QueueStateSchema](
            success=True,
            code="QUEUE_JOINED",
            message="Tham gia hàng đợi thành công.",
            data=QueueStateSchema(
                queue_enabled=True,
                status="WAITING",
                position=3,
                estimated_wait_seconds=None,
                ready_expires_at=None,
                queue_token=None,
            ),
            request_id=SAMPLE_REQ_ID,
        ).model_dump(),
        "ready": ApiSuccessEnvelope[QueueStateSchema](
            success=True,
            code="QUEUE_STATUS_FETCHED",
            message="Lấy trạng thái hàng đợi thành công.",
            data=QueueStateSchema(
                queue_enabled=True,
                status="READY",
                position=None,
                estimated_wait_seconds=None,
                ready_expires_at="2026-11-01T08:35:00Z",
                queue_token="SAMPLE_ONLY_DO_NOT_USE_QUEUE_TOKEN",
            ),
            request_id=SAMPLE_REQ_ID,
        ).model_dump(),
        "expired": ApiSuccessEnvelope[QueueStateSchema](
            success=True,
            code="QUEUE_STATUS_FETCHED",
            message="Lấy trạng thái hàng đợi thành công.",
            data=QueueStateSchema(
                queue_enabled=True,
                status="EXPIRED",
                position=None,
                estimated_wait_seconds=None,
                ready_expires_at=None,
                queue_token=None,
            ),
            request_id=SAMPLE_REQ_ID,
        ).model_dump(),
    }
    _write_json(EXAMPLES_DIR / "queue_states.json", queue_states)

    # 7. Business errors validated against ApiErrorEnvelope
    errors_bundle = {
        "prerequisite_not_met": ApiErrorEnvelope.model_validate(
            build_error_envelope(
                code="PREREQUISITE_NOT_MET",
                message="Chưa đạt tiên quyết.",
                request_id=SAMPLE_REQ_ID,
                errors=[
                    FieldErrorItem(
                        field="prerequisites[0].course_code",
                        code=FieldErrorCode.PREREQUISITE_MISSING,
                        message="CS101 — Nhập môn lập trình chưa hoàn thành.",
                    )
                ],
            )
        ).model_dump(),
        "schedule_conflict": ApiErrorEnvelope.model_validate(
            build_error_envelope(
                code="SCHEDULE_CONFLICT",
                message="Trùng lịch học.",
                request_id=SAMPLE_REQ_ID,
                errors=[
                    FieldErrorItem(
                        field="schedule",
                        code=FieldErrorCode.CLASS_TIME_CONFLICT,
                        message="Trùng lớp LHP002 vào MON tiết 2–3.",
                    )
                ],
            )
        ).model_dump(),
        "class_full": ApiErrorEnvelope.model_validate(
            build_error_envelope(
                code="CLASS_FULL",
                message="Lớp học phần đã hết chỗ.",
                request_id=SAMPLE_REQ_ID,
            )
        ).model_dump(),
        "idempotency_key_reused": ApiErrorEnvelope.model_validate(
            build_error_envelope(
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được sử dụng cho một thao tác hoặc dữ liệu khác.",
                request_id=SAMPLE_REQ_ID,
            )
        ).model_dump(),
    }
    _write_json(EXAMPLES_DIR / "business_errors.json", errors_bundle)


if __name__ == "__main__":
    ensure_utf8_stdio()
    export_all()
    print(f"[EXPORT OK] Đã xuất OpenAPI và JSON fixtures vào {EXAMPLES_DIR}")
