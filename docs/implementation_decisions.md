# Quyết định Triển khai Nội bộ & Điểm Đồng bộ (`implementation_decisions.md`)

Tài liệu này ghi nhận rõ các quyết định triển khai nội bộ bổ sung cho những khoảng trống trong Đặc tả API v3.0, tuyệt đối không thay đổi đường dẫn, tên trường JSON, HTTP status hay mã lỗi đã thống nhất với TV3.

---

## 1. Chính sách Học phí Lớp học phần (`TUITION_PER_CREDIT`)
- **Khoảng trống trong đặc tả v3.0**: Request `POST /api/v1/admin/course-classes` và `PUT /api/v1/admin/course-classes/{id}` không nhận trường `tuition_amount`, nhưng model `CourseClass` và `Registration` xuất ra `tuition_amount` (ví dụ mẫu 3 tín chỉ = `1500000` VND).
- **Quyết định**:
  - Cấu hình biến môi trường `TUITION_PER_CREDIT=500000` (số nguyên VND, mặc định 500.000 VND/tín chỉ — khớp chính xác ví dụ `3 * 500000 = 1500000` trong Mục 08–15 của đặc tả).
  - Khi tạo lớp mới (`POST`), server tính `tuition_amount = credits * TUITION_PER_CREDIT` và lưu cứng vào cột `course_classes.tuition_amount`.
  - Khi sửa lớp (`PUT`) mà lớp chưa có đăng ký `ACTIVE`: nếu `credits` thay đổi so với giá trị hiện lưu thì tính lại `tuition_amount = new_credits * TUITION_PER_CREDIT`; nếu `credits` giữ nguyên thì bảo toàn `course_classes.tuition_amount` hiện tại (đổi biến môi trường không tự động viết lại học phí các lớp cũ).
  - Khi sinh viên đăng ký (`POST /register`), `registrations.tuition_amount` chụp snapshot từ `course_classes.tuition_amount` tại thời điểm đăng ký và không bao giờ thay đổi về sau.

## 2. Danh mục Học phần (`courses`) và Kết quả Hoàn thành (`course_completions`)
- **Khoảng trống trong đặc tả v3.0**: Chưa có API quản lý danh mục môn học hay nhập điểm, nhưng Mục 04 & 14 yêu cầu hiển thị `course_name` của môn tiên quyết và kiểm tra mã học phần hợp lệ.
- **Quyết định**:
  - Tạo bảng `courses(course_code PRIMARY KEY, course_name, default_credits)` và `course_completions(user_id, course_code, completed_at)`.
  - Dữ liệu danh mục học phần và kết quả hoàn thành được nạp qua CLI `seed` (gồm ít nhất `CS101`, `CNNT`, `WEB`, `JAVA`, và các mã mở rộng phục vụ quản trị thử nghiệm như `DB101`, `NET101`, `AI101`, `SE101`).
  - Khi ADMIN tạo/sửa lớp với `course_code` hoặc `prerequisite_course_codes` không tồn tại trong bảng `courses`, trả `400 VALIDATION_ERROR` với chi tiết trường lỗi rõ ràng. Không tự mở thêm API ngoài hợp đồng.

## 3. Dữ liệu Seed UI (LHP001, LHP002, LHP003)
- Theo Mục 22 của đặc tả v3.0 và hướng dẫn TV2:
  - `LHP001` (`CNNT-01`, `CNNT`, 3 tín chỉ, `50` chỗ, `OPEN`, `MON` tiết `1–3` phòng `A101`, tiên quyết `CS101`).
  - `LHP002` (`WEB-01`, `WEB`, 3 tín chỉ, `50` chỗ, `OPEN`, `MON` tiết `2–4` phòng `B201`, không tiên quyết).
  - `LHP003` (`JAVA-01`, `JAVA`, 3 tín chỉ, `50` chỗ, `OPEN`, `TUE` tiết `1–3` phòng `C301`, không tiên quyết).
  - Tài khoản `SV0001`…`SV3000` (`STUDENT`) và `AD0001` (`ADMIN`), mật khẩu mẫu lab `Demo@123456` băm Argon2id.
  - `SV0001` đã hoàn thành `CS101`; `SV0002` (và các SV còn lại mặc định trong seed UI) chưa hoàn thành `CS101`.

## 4. Hành vi khi Tắt Feature (`PAYMENTS_ENABLED`, `SSO_ENABLED`, `QUEUE_ENABLED`)
- `GET /api/v1/health` luôn phản ánh đúng trạng thái bật/tắt thực tế tại `data.features = {payments, sso, queue}`.
- **`QUEUE_ENABLED=false` (mặc định cho kiểm thử tính đúng và đo tải chuẩn)**:
  - Theo đúng Mục 16: `POST /api/v1/queue/join` và `GET /api/v1/queue/status` vẫn trả `200` với `queue_enabled=false`, `status="NONE"`, các trường còn lại `null`, và **không kết nối tới Redis** (core chạy hoàn toàn độc lập với Redis).
  - `POST /api/v1/register` bỏ qua bước kiểm tra `X-Queue-Token`.
- **`SSO_ENABLED=false` (mặc định khi chưa bật profile Keycloak)**:
  - `GET /api/v1/auth/sso/login`, `GET /api/v1/auth/sso/callback`, và `POST /api/v1/auth/sso/exchange` trả `503 SERVICE_UNAVAILABLE` (envelope lỗi chuẩn kèm `Retry-After: 1`) thay vì giả lập thành công hay sinh mã lỗi ngoài danh mục Mục 20.
- **`PAYMENTS_ENABLED=false`**:
  - `POST /api/v1/payments` và `GET /api/v1/payments/me` trả `503 SERVICE_UNAVAILABLE`. Mặc định `PAYMENTS_ENABLED=true` vì thanh toán mô phỏng chỉ dùng PostgreSQL nội bộ.

## 5. Ràng buộc Trình duyệt (Browser Binding) và Chống Login CSRF cho SSO OIDC
- **Yêu cầu bảo mật & tương thích hợp đồng**:
  - Đặc tả Mục 07 & 17 quy định frontend không dùng cookie phiên và không bật `credentials: include` trên `fetch` cho các API JSON (bao gồm `POST /api/v1/auth/sso/exchange`).
  - Đồng thời cần chống tấn công Login CSRF / Authorization Code Injection ở bước trình duyệt quay về từ Keycloak (`GET /api/v1/auth/sso/callback`).
- **Quyết định**:
  - Tại `GET /api/v1/auth/sso/login` (điều hướng top-level trên trình duyệt): Backend sinh `state`, `nonce`, `code_verifier` (PKCE S256) và `browser_Session_secret` ngẫu nhiên 32 byte; lưu bản băm SHA-256 của `browser_session_secret` trong bảng `sso_transactions` (TTL 300 giây) và đặt cookie tạm `dkhp_sso_bind` với thuộc tính `HttpOnly; SameSite=Lax; Max-Age=300; Path=/api/v1/auth/sso/callback` (`Secure` bật khi chạy HTTPS).
  - Tại `GET /api/v1/auth/sso/callback` (top-level GET redirect từ Keycloak): Trình duyệt tự động đính kèm cookie `dkhp_sso_bind` do `SameSite=Lax` cho phép điều hướng GET cấp cao nhất. Backend kiểm tra nguyên tử `state` chưa dùng + còn hạn **và** đối chiếu hằng thời gian băm của cookie `dkhp_sso_bind`, xóa cookie ngay trong phản hồi `302`, đổi mã với PKCE, xác minh chữ ký JWKS, `iss`, `aud`/`azp`, `exp`, `nonce`, rồi phát hành `exchange_code` ngẫu nhiên 32 byte (lưu băm SHA-256 trong `sso_exchange_codes`, TTL 60 giây, consume nguyên tử 1 lần).
  - Tại `POST /api/v1/auth/sso/exchange`: TV3 chỉ cần gửi JSON `{"exchange_code": "..."}` như đặc tả Mục 07 mà **không cần `credentials: include`**. Để tăng cường an toàn phía UI, hướng dẫn TV3 xóa ngay `exchange_code` trên thanh địa chỉ bằng `window.history.replaceState` trước khi render thành phần bên thứ ba (đúng Mục 07). Nếu nhóm muốn ràng buộc chặt cả bước `exchange` với trình duyệt trong môi trường production sau này, TV3 sẽ cần bật `credentials: include` riêng cho endpoint `/auth/sso/exchange` — hiện tại giữ không bắt buộc để không phá `apiClient` của TV3.

## 6. Đồng bộ Idempotency Xuyên Nhiều Worker
- Sử dụng kết hợp:
  1. Tra cứu nhanh bản ghi hoàn tất trước khi giữ khóa nặng để phục vụ replay tốc độ cao (nhất là khi queue token đã hết hạn).
  2. Khóa tư vấn cấp giao dịch `pg_advisory_xact_lock(hashtextextended(user_id::text || ':' || idempotency_key, 0))` bên trong transaction PostgreSQL cùng với ràng buộc `UNIQUE (user_id, idempotency_key)` trên bảng `idempotency_records`.
  3. Dùng `SET LOCAL lock_timeout` ngắn cho bước chờ khóa idempotency: nếu request đầu cùng key đang xử lý chưa xong sau thời gian chờ, giao dịch thứ hai bắt lỗi lock timeout và trả `409 REQUEST_IN_PROGRESS` kèm `Retry-After: 1`.
  4. Mọi kết quả nghiệp vụ xác định (thành công `200` hoặc lỗi nghiệp vụ xác định như `404 CLASS_NOT_FOUND`, `404 REGISTRATION_NOT_FOUND`, `409 ALREADY_REGISTERED`, `409 CLASS_FULL`, `409 REGISTRATION_CLOSED`, `409 PREREQUISITE_NOT_MET`, `409 SCHEDULE_CONFLICT`, `409 ALREADY_PAID`) đều được serialize thành JSON hợp lệ và `INSERT` vào `idempotency_records` rồi **COMMIT** cùng transaction (kể cả khi nghiệp vụ từ chối ghi dữ liệu lớp/đăng ký). Các lỗi tiền kiểm (`400`, `401`, `403`, `415`, `422`, lỗi Redis queue, lỗi hạ tầng rollback) **không** lưu vào `idempotency_records`.

## 7. Chính sách Hàng đợi Redis khi Logout Đa Thiết bị
- Trạng thái hàng đợi được quản lý theo `student_id` (mỗi sinh viên tối đa 1 lượt `WAITING` hoặc `READY` theo Mục 16), trong khi phiên đăng nhập (`sessions`) được quản lý độc lập theo từng thiết bị.
- Khi sinh viên gọi `POST /api/v1/auth/logout`:
  - Chỉ thu hồi đúng phiên (`session_id`) tương ứng với cặp access/refresh token đó; các phiên đăng nhập khác của cùng sinh viên vẫn hợp lệ.
  - Nếu `QUEUE_ENABLED=true`, giải phóng lượt hàng đợi hiện tại của sinh viên đó trên Redis (và kích hoạt cấp lượt kế tiếp nguyên tử qua Lua script) theo đúng quy định Mục 16 ("Slot READY giải phóng khi hết hạn/logout"). Nếu sinh viên đang mở phiên thứ hai trên thiết bị khác, thiết bị đó sẽ cần `POST /queue/join` lại nếu muốn đăng ký mới.

## 8. Giới hạn Tần suất (Rate Limiting) Đa Worker
- Để không dùng dictionary in-memory sai lệch giữa nhiều worker rồi tuyên bố chia sẻ toàn cục:
- Hỗ trợ cấu hình `RATE_LIMIT_BACKEND=none|memory|redis` (mặc định môi trường kiểm thử tính đúng đặt `none` hoặc ngưỡng cao `1000 r/s, burst 200`; ở môi trường triển khai qua Nginx, khuyến nghị TV1 áp `limit_req_zone` tại tầng Nginx làm chốt chặn chính và chuẩn hóa JSON `429 RATE_LIMITED` + `Retry-After`, đồng thời backend có bộ giới hạn bổ trợ cho `/auth/login` ghi rõ phạm vi per-worker khi chạy `memory` hoặc toàn cục xuyên worker khi bật `redis`).

## 9. Điểm Đồng bộ Môi trường Thực thi
- `Dockerfile` và `compose.dev.yml` ghim `python:3.12-slim`, `postgres:16.4-alpine`, `redis:7.4-alpine`, `quay.io/keycloak/keycloak:26.0.5`.
- Mã nguồn `pyproject.toml` khai báo tương thích `>=3.11,<3.14` để vừa chạy chuẩn trên Python 3.12 container của nhóm, vừa chạy trực tiếp kiểm thử cục bộ trên Windows Python 3.11.9 nếu máy dev chưa cài Python 3.12.
