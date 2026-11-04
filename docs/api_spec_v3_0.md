# Đặc tả API Hoàn chỉnh TV2 – TV3 (Phiên bản 3.0)

> Bản lưu chuẩn trong repository theo quy tắc Mục 25 của đặc tả nhóm.
> Phiên bản tài liệu: `3.0` | Phiên bản API: `1.0.0` | Tiền tố: `/api/v1`

## 01. Phạm vi và cách sử dụng

| Đợt | Phạm vi | Kết quả bàn giao |
|---|---|---|
| A0 | Login; danh sách/chi tiết lớp; đăng ký; danh sách bản thân; health. | Có backend tối thiểu và UI mock tương ứng. |
| A | Hủy, lịch học, tiên quyết, Idempotency-Key. | Ghép luồng đăng ký/hủy và kiểm thử đồng thời. |
| B | Refresh/logout, quản trị lớp, thanh toán mô phỏng. | Phiên đăng nhập đầy đủ; UI quản trị và học phí. |
| C | SSO qua Keycloak và hàng đợi Redis. | UI SSO/hàng đợi; thử riêng với cơ chế điều tiết bật. |

- Thanh toán và hoàn tiền chỉ là mô phỏng nội bộ, không kết nối ngân hàng hoặc thu tiền thật.
- Khi bật luồng ghi thật, `Idempotency-Key` bắt buộc hoạt động.
- Công nghệ thống nhất: Python 3.12, FastAPI/uvicorn, PostgreSQL 16, psycopg3 pool, Redis cho hàng đợi, opaque token lưu băm, mật khẩu Argon2id, Keycloak OIDC Authorization Code + PKCE, Nginx, Docker Compose.

## 02. Danh sách 19 Endpoint (`/api/v1`)

| Method | Đường dẫn sau `/api/v1` | Chức năng | Mục |
|---|---|---|---|
| `POST` | `/auth/login` | Login | 05 |
| `POST` | `/auth/refresh` | Làm mới phiên | 06 |
| `POST` | `/auth/logout` | Thu hồi phiên | 06 |
| `GET` | `/auth/sso/login` | Chuyển hướng SSO | 07 |
| `GET` | `/auth/sso/callback` | Callback IdP tới backend | 07 |
| `POST` | `/auth/sso/exchange` | Đổi mã lấy token | 07 |
| `GET` | `/course-classes` | Danh sách lớp | 08 |
| `GET` | `/course-classes/{course_class_id}` | Chi tiết lớp | 09 |
| `POST` | `/register` | Đăng ký | 10 |
| `DELETE` | `/registrations/{registration_id}` | Hủy đăng ký | 11 |
| `GET` | `/registrations/me` | Đăng ký của bản thân | 12 |
| `POST` | `/payments` | Thanh toán mô phỏng | 13 |
| `GET` | `/payments/me` | Lịch sử thanh toán | 13 |
| `POST` | `/admin/course-classes` | Tạo lớp | 14 |
| `PUT` | `/admin/course-classes/{course_class_id}` | Sửa lớp | 14 |
| `PATCH` | `/admin/course-classes/{course_class_id}/status` | Mở hoặc đóng lớp | 15 |
| `POST` | `/queue/join` | Vào hàng đợi | 16 |
| `GET` | `/queue/status` | Theo dõi hàng đợi | 16 |
| `GET` | `/health` | Kiểm tra dịch vụ | 17 |

## 03. Kết nối và Cấu trúc Phản hồi
- Base URL dev: `http://localhost:8080/api/v1`.
- Headers: `Accept: application/json`; `POST`/`PUT`/`PATCH` dùng `Content-Type: application/json`; `DELETE` không có body.
- `Authorization: Bearer <access_token>` cho tất cả API trừ `/auth/login`, `/auth/refresh`, `/auth/sso/*`, `/health`.
- JSON UTF-8; tiền nguyên VND; `null` giữ nguyên; mảng rỗng là `[]`; thời gian UTC ISO 8601 có hậu tố `Z`.
- Envelope thành công: `{success: true, code, message, data, request_id}`.
- Envelope lỗi: `{success: false, code, message, data: null, errors: [{field, code, message}], request_id}`.
- Header phản hồi: `X-Request-ID`, `Cache-Control: no-store`, `WWW-Authenticate: Bearer` (401), `Allow` (405), `Retry-After` (409 `REQUEST_IN_PROGRESS`, 429, 503), `Idempotent-Replayed: true` (replay).

## 04. Từ điển Dữ liệu Dùng chung
- `Student`: `student_id` (`^(SV|AD)[0-9]{3,6}$`), `full_name`, `role` (`STUDENT|ADMIN`).
- `CourseClass`: `course_class_id` (`^LHP[0-9]{3,6}$`), `class_code`, `course_code`, `course_name`, `credits`, `capacity`, `remaining_seats`, `registered_count`, `status` (`OPEN|CLOSED`), `schedule` (`[{day_of_week, start_period, end_period, room}]`), `prerequisites` (`[{course_code, course_name, satisfied}]`), `tuition_amount`, `registration_status` (`REGISTERED|NOT_REGISTERED`), `registration_id` (`UUID|null`), `payment_status` (`UNPAID|PAID|null`).
- `Registration`: `registration_id`, `student_id`, `course_class_id`, `class_code`, `course_name`, `credits`, `status` (`ACTIVE|CANCELLED`), `payment_status` (`UNPAID|PAID|REFUNDED`), `tuition_amount`, `registered_at`, `cancelled_at`.
- `Payment`: `payment_id`, `registration_id`, `course_class_id`, `class_code`, `amount`, `currency` (`VND`), `status` (`PAID|REFUNDED`), `paid_at`, `refunded_at`.
- `RefundInfo`: `payment_id`, `amount`, `currency`, `status` (`REFUNDED`), `refunded_at`.
- `Pagination`: `page`, `page_size`, `total_items`, `total_pages`.
- `QueueState`: `queue_enabled`, `status` (`NONE|WAITING|READY|EXPIRED`), `position`, `estimated_wait_seconds`, `ready_expires_at`, `queue_token`.

## 05–25. Quy tắc Nghiệp vụ, Giao dịch, Mã lỗi & Ca Kiểm thử TC01–TC25
- Chi tiết đối chiếu đầy đủ từng endpoint xem tại `docs/contract_matrix.md`.
- Chi tiết ràng buộc DB và bất biến (invariants) xem tại `docs/database_design.md` và `backend/migrations/001_initial_schema.sql`.
- Chi tiết khóa đồng thời, thứ tự kiểm tra và idempotency xem tại `docs/concurrency_design.md`.
- Kết quả nghiệm thu TC01–TC25 xem tại `docs/test_results.md`.
