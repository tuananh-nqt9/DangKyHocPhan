# Ma trận Hợp đồng API v3.0 (`contract_matrix.md`)

- **Phiên bản tài liệu đặc tả**: `3.0`
- **Phiên bản API**: `1.0.0`
- **Tiền tố đường dẫn**: `/api/v1`
- **Định dạng thời gian**: UTC ISO 8601 có hậu tố `Z` (`TIMESTAMPTZ`)
- **Định dạng tiền tệ**: Số nguyên `VND` (không dùng số thực)
- **Header phản hồi chung**: `X-Request-ID`, `Cache-Control: no-store`, `Vary: Origin` (khi có CORS), `WWW-Authenticate: Bearer` (khi 401), `Allow` (khi 405), `Retry-After` (khi 409 `REQUEST_IN_PROGRESS`, 429, 503), `Idempotent-Replayed: true` (khi replay kết quả idempotency)

## Tổng hợp 19 Endpoint bắt buộc (18 API cho Frontend + 1 Callback cho IdP)

| # | Đợt | Method & Path (sau `/api/v1`) | Auth / Role | Input (Headers / Query / Body) | Thành công (HTTP & `code`) | Schema `data` đầu ra | Các mã lỗi chính (HTTP `code`) | Test liên quan | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|
| 1 | A0 | `POST /auth/login` | Công khai | Body JSON: `student_id` (`^(SV\|AD)[0-9]{3,6}$`), `password` (`8..128` ký tự, không trim) | `200 LOGIN_SUCCESS` | `{access_token, token_type: "Bearer", expires_in, refresh_token, refresh_expires_in, student: Student}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 INVALID_CREDENTIALS`, `415 UNSUPPORTED_MEDIA_TYPE`, `429 RATE_LIMITED` | TC01 | DONE |
| 2 | B | `POST /auth/refresh` | Công khai (dùng `refresh_token`) | Body JSON: `refresh_token` | `200 TOKEN_REFRESHED` | `{access_token, token_type: "Bearer", expires_in, refresh_token, refresh_expires_in, student: Student}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 INVALID_REFRESH_TOKEN`, `415 UNSUPPORTED_MEDIA_TYPE`, `429 RATE_LIMITED` | TC19 | DONE |
| 3 | B | `POST /auth/logout` | Bearer (`STUDENT` / `ADMIN`) + `refresh_token` cùng phiên | Header: `Authorization: Bearer`; Body JSON: `refresh_token` | `200 LOGGED_OUT` | `{logged_out: true}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `401 INVALID_REFRESH_TOKEN`, `415 UNSUPPORTED_MEDIA_TYPE` | TC19 | DONE |
| 4 | C | `GET /auth/sso/login` | Công khai (trình duyệt điều hướng) | Không nhận redirect URI tùy ý; từ chối query lạ | `302 Found` tới Keycloak Authorization Endpoint + cookie tạm ràng buộc trình duyệt | Redirect (không body JSON) | `400 VALIDATION_ERROR`, `503 SERVICE_UNAVAILABLE` (khi `SSO_ENABLED=false`) | TC22 | DONE (Code & OIDC/PKCE/JWKS test; chờ Keycloak container E2E) |
| 5 | C | `GET /auth/sso/callback` | Callback từ IdP | Query chuẩn OIDC (`code`, `state`, `error`, ...); cookie ràng buộc trình duyệt | `302 Found` về `{FRONTEND_ORIGIN}/sso/callback?exchange_code=...` | Redirect (thất bại về `?error=SSO_FAILED`) | `302 ?error=SSO_FAILED`, `503 SERVICE_UNAVAILABLE` (khi `SSO_ENABLED=false`) | TC22 | DONE (Code & OIDC/PKCE/JWKS test; chờ Keycloak container E2E) |
| 6 | C | `POST /auth/sso/exchange` | Công khai (mã một lần 60s) | Body JSON: `exchange_code` | `200 LOGIN_SUCCESS` | `{access_token, token_type: "Bearer", expires_in, refresh_token, refresh_expires_in, student: Student}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 SSO_FAILED`, `415 UNSUPPORTED_MEDIA_TYPE`, `503 SERVICE_UNAVAILABLE` | TC22 | DONE |
| 7 | A0 | `GET /course-classes` | Bearer: `STUDENT`, `ADMIN` | Query: `page=1` (`>=1`), `page_size=20` (`1..100`), `q` (trim, `<=100` ký tự) | `200 COURSE_CLASSES_FETCHED` | `{items: [CourseClass], pagination: Pagination}` | `400 VALIDATION_ERROR`, `401 UNAUTHORIZED` | TC02, TC15, TC16 | DONE |
| 8 | A0 | `GET /course-classes/{course_class_id}` | Bearer: `STUDENT`, `ADMIN` | Path: `course_class_id` (`^LHP[0-9]{3,6}$`) | `200 COURSE_CLASS_FETCHED` | `{course_class: CourseClass}` | `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `404 CLASS_NOT_FOUND` | TC02, TC09 | DONE |
| 9 | A0/A | `POST /register` | Bearer: `STUDENT` | Headers: `Idempotency-Key` (UUIDv4), `X-Queue-Token` (khi queue bật); Body JSON: `{student_id, course_class_id}` | `200 REGISTERED` | `{registration: Registration, course_class: CourseClass}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `403 STUDENT_MISMATCH`, `403 QUEUE_TOKEN_REQUIRED`, `403 QUEUE_TOKEN_INVALID`, `404 CLASS_NOT_FOUND`, `409 ALREADY_REGISTERED`, `409 REGISTRATION_CLOSED`, `409 PREREQUISITE_NOT_MET`, `409 SCHEDULE_CONFLICT`, `409 CLASS_FULL`, `409 REQUEST_IN_PROGRESS`, `415`, `422 IDEMPOTENCY_KEY_REUSED`, `429`, `503` | TC02–TC11, TC15, TC16, TC20, TC21, TC23, TC25 | DONE |
| 10 | A | `DELETE /registrations/{registration_id}` | Bearer: `STUDENT` | Header: `Idempotency-Key` (UUIDv4); Path: `registration_id` (UUID); Không có body | `200 REGISTRATION_CANCELLED` | `{registration: Registration, course_class: CourseClass, refund: RefundInfo \| null}` | `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `404 REGISTRATION_NOT_FOUND`, `409 REQUEST_IN_PROGRESS`, `422 IDEMPOTENCY_KEY_REUSED`, `503` | TC13, TC14, TC17, TC20, TC24 | DONE |
| 11 | A0/A | `GET /registrations/me` | Bearer: `STUDENT` | Query: `page=1`, `page_size=20` (`1..100`), `status=ACTIVE\|CANCELLED\|ALL` (mặc định `ACTIVE`) | `200 REGISTRATIONS_FETCHED` | `{student_id, items: [Registration], pagination: Pagination}` | `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN` | TC02, TC13, TC14 | DONE |
| 12 | B | `POST /payments` | Bearer: `STUDENT` | Header: `Idempotency-Key` (UUIDv4); Body JSON: `{registration_id}` | `200 PAYMENT_SUCCESS` | `{payment: Payment, registration: Registration}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `404 REGISTRATION_NOT_FOUND`, `409 ALREADY_PAID`, `409 REQUEST_IN_PROGRESS`, `415`, `422 IDEMPOTENCY_KEY_REUSED`, `503` | TC17, TC20, TC24 | DONE |
| 13 | B | `GET /payments/me` | Bearer: `STUDENT` | Query: `page=1`, `page_size=20` (`1..100`), `status=PAID\|REFUNDED\|ALL` (mặc định `ALL`) | `200 PAYMENTS_FETCHED` | `{items: [Payment], pagination: Pagination}` | `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `503` | TC17 | DONE |
| 14 | B | `POST /admin/course-classes` | Bearer: `ADMIN` | Body JSON: `{class_code, course_code, course_name, credits, capacity, status, schedule, prerequisite_course_codes}` | `201 COURSE_CLASS_CREATED` | `{course_class: CourseClass}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `409 CLASS_CODE_EXISTS`, `415` | TC18 | DONE |
| 15 | B | `PUT /admin/course-classes/{course_class_id}` | Bearer: `ADMIN` | Path: `course_class_id`; Body JSON đầy đủ như `POST` | `200 COURSE_CLASS_UPDATED` | `{course_class: CourseClass}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `404 CLASS_NOT_FOUND`, `409 CLASS_CODE_EXISTS`, `409 CAPACITY_BELOW_REGISTERED`, `409 CLASS_HAS_REGISTRATIONS`, `415` | TC18 | DONE |
| 16 | B | `PATCH /admin/course-classes/{course_class_id}/status` | Bearer: `ADMIN` | Path: `course_class_id`; Body JSON: `{status: "OPEN"\|"CLOSED"}` | `200 COURSE_CLASS_STATUS_UPDATED` | `{course_class: CourseClass}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `404 CLASS_NOT_FOUND`, `415` | TC05, TC18 | DONE |
| 17 | C | `POST /queue/join` | Bearer: `STUDENT` | Body JSON: `{}` | `200 QUEUE_JOINED` | `{queue_enabled, status, position, estimated_wait_seconds, ready_expires_at, queue_token}` | `400 INVALID_JSON`, `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `415`, `503 SERVICE_UNAVAILABLE` | TC21 | DONE (Code & Lua test; chờ Redis daemon E2E) |
| 18 | C | `GET /queue/status` | Bearer: `STUDENT` | Không nhận query lạ | `200 QUEUE_STATUS_FETCHED` | `{queue_enabled, status, position, estimated_wait_seconds, ready_expires_at, queue_token}` | `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `503 SERVICE_UNAVAILABLE` | TC21 | DONE (Code & Lua test; chờ Redis daemon E2E) |
| 19 | A0 | `GET /health` | Công khai | Không nhận query lạ | `200 HEALTHY` | `{status: "UP", database: "UP", api_version: "1.0.0", features: {payments, sso, queue}}` | `400 VALIDATION_ERROR`, `503 SERVICE_UNAVAILABLE` | Health & Smoke | DONE |

## Quy tắc Thứ tự Ưu tiên Kiểm tra tại `POST /api/v1/register`

1. `Authorization: Bearer` hợp lệ (`401 UNAUTHORIZED` nếu thiếu/sai/hết hạn/thu hồi) và role là `STUDENT` (`403 FORBIDDEN` nếu `ADMIN`).
2. Kiểm tra `Content-Type: application/json` (`415`), cú pháp JSON (`400 INVALID_JSON`), query/body/header `Idempotency-Key` UUID v4 (`400 VALIDATION_ERROR`).
3. Đối chiếu `body.student_id == token.student_id` (`403 STUDENT_MISMATCH`).
4. Đối chiếu `Idempotency-Key` theo `(user_id, key)`:
   - Đã hoàn tất và còn hạn + cùng fingerprint → Replay nguyên trạng HTTP status + JSON body (giữ `request_id` gốc, kèm `Idempotent-Replayed: true`). Không kiểm tra lại queue token.
   - Đã hoàn tất (hoặc đang xử lý) + khác fingerprint → `422 IDEMPOTENCY_KEY_REUSED`.
5. Nếu là thao tác mới và `QUEUE_ENABLED=true`: kiểm tra `X-Queue-Token` (`403 QUEUE_TOKEN_REQUIRED` nếu thiếu, `403 QUEUE_TOKEN_INVALID` nếu sai/hết hạn/khác user, `503 SERVICE_UNAVAILABLE` nếu Redis lỗi). Không ghi kết quả lỗi queue vào bảng idempotency.
6. Mở transaction PostgreSQL (`READ COMMITTED`), lấy `pg_advisory_xact_lock` theo `(user_id, idempotency_key)` (quá hạn khóa → `409 REQUEST_IN_PROGRESS` kèm `Retry-After`), kiểm tra lại bản ghi idempotency sau khi giữ khóa.
7. Khóa hàng `users` (`FOR UPDATE`) → Khóa hàng `course_classes` (`FOR UPDATE`).
8. Kiểm tra tuần tự các điều kiện nghiệp vụ (mọi lỗi nghiệp vụ xác định ở bước này đều được lưu vào `idempotency_records` và `COMMIT` để bảo đảm replay nhất quán):
   - Lớp tồn tại → sai trả `404 CLASS_NOT_FOUND`
   - Chưa có đăng ký `ACTIVE` của sinh viên tại lớp này → sai trả `409 ALREADY_REGISTERED`
   - `status == 'OPEN'` → sai trả `409 REGISTRATION_CLOSED`
   - Hoàn thành đủ tiên quyết trong `course_completions` → sai trả `409 PREREQUISITE_NOT_MET` kèm `errors[]`
   - Không trùng lịch với các đăng ký `ACTIVE` hiện có của sinh viên → sai trả `409 SCHEDULE_CONFLICT` kèm `errors[]`
   - `remaining_seats > 0` → sai trả `409 CLASS_FULL`
9. Ghi `INSERT INTO registrations`, cập nhật `UPDATE course_classes SET remaining_seats = remaining_seats - 1`, serialize & validate response JSON, ghi `INSERT INTO idempotency_records`, và `COMMIT` trong cùng một transaction.
