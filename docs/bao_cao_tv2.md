# Báo cáo Kỹ thuật Thành viên 2 (TV2) — Cơ sở Dữ liệu & Backend API

- **Học phần**: Nhập môn Công nghệ Nền tảng
- **Đề tài 08**: Thiết kế hệ thống đăng ký học phần trực tuyến (quy mô 3.000 sinh viên, trọng tâm xử lý tranh chấp tại thời điểm mở đăng ký)
- **Thành viên thực hiện**: Thành viên 2 (TV2 — Phụ trách Cơ sở dữ liệu PostgreSQL 16, Backend API FastAPI, xác thực/phân quyền, giao dịch & tính nhất quán đồng thời, kiểm thử backend và tài liệu bàn giao)
- **Hợp đồng giao tiếp áp dụng**: Đặc tả API Hoàn chỉnh TV2–TV3 **v3.0** (`API version 1.0.0`, tiền tố `/api/v1`)

---

## 1. Phạm vi Công việc & Ranh giới Trách nhiệm

Trong kiến trúc tổng thể của nhóm 3 thành viên:
- **TV1** phụ trách kiến trúc triển khai, Nginx reverse proxy, giám sát tài nguyên/log và vận hành sao lưu/khôi phục hạ tầng.
- **TV2 (phần báo cáo này)** phụ trách thiết kế lược đồ PostgreSQL 16, xây dựng đầy đủ **19 API endpoints** theo Đặc tả v3.0 (qua các đợt A0, A, B, C), đảm bảo tính nguyên tử và nhất quán dữ liệu khi hàng chục/hàng trăm yêu cầu tranh chỗ cuối xuyên nhiều worker, cơ chế `Idempotency-Key`, thanh toán/hoàn tiền mô phỏng nội bộ, hàng đợi Redis (Lua), SSO Keycloak OIDC + PKCE, bộ công cụ CLI chuẩn bị tải/đối soát bất biến và bộ kiểm thử tự động `TC01–TC25`.
- **TV3** phụ trách giao diện người dùng (Frontend), `apiClient`, chế độ mock và kịch bản tạo tải phân tán bằng `k6` (10 / 50 / 100 VU).

> **Giới hạn mô phỏng nghiệp vụ**: Nghiệp vụ thanh toán học phí (`POST /api/v1/payments`) và hoàn tiền khi hủy lớp (`DELETE /api/v1/registrations/{id}`) là **mô phỏng trạng thái nội bộ trong giao dịch PostgreSQL** nhằm kiểm chứng tính nguyên tử đa bảng, không tích hợp cổng thanh toán ngân hàng thật.

---

## 2. Kiến trúc Phân tầng & Tổ chức Mã nguồn (Tham chiếu Bảo vệ Đồ án)

Hệ thống sử dụng **Python (FastAPI + Uvicorn)** kết hợp **PostgreSQL 16 (`psycopg 3` + `psycopg_pool`)** theo mô hình đồng bộ nhất quán (`def` route handlers chạy trên threadpool của FastAPI + synchronous `ConnectionPool` riêng trên từng worker). Cách chọn này giúp luồng giao dịch SQL tường minh, không bao giờ làm nghẽn asyncio event loop bởi truy vấn đồng bộ hay phép băm mật khẩu Argon2id.

| Tầng / Mô-đun | File mã nguồn tiêu biểu | Trách nhiệm cốt lõi cần giải thích khi vấn đáp |
|---|---|---|
| **Entrypoint & HTTP Framing** | `backend/app/main.py` (`create_app`) | Khởi tạo `DatabaseManager` trong `lifespan` riêng từng worker; xử lý CORS allowlist chặt & preflight `204` trước xác thực; chuẩn hóa toàn bộ lỗi HTTP/validation về envelope v3.0; xuất OpenAPI sạch (`422` chỉ dành cho `IDEMPOTENCY_KEY_REUSED`). |
| **Cấu hình, Bảo mật & Log** | `backend/app/core/config.py`, `security.py`, `errors.py`, `logging.py`, `clock.py` | Cấu hình biến môi trường có kiểu (`Settings`), băm mật khẩu `Argon2id` (kèm dummy hash chống dò user theo thời gian), băm opaque token bằng `SHA-256`, sinh cặp `PKCE S256`, và JSON logger tự động che `password`/token/`code` OIDC. |
| **Pool & Giao dịch CSDL** | `backend/app/db/pool.py` (`DatabaseManager`), `migrations.py` | Quản lý `ConnectionPool` (`min_size`, `max_size`, `timeout`), thiết lập `SET LOCAL timezone = 'GMT'`, `SET LOCAL lock_timeout`, `SET LOCAL statement_timeout` theo từng giao dịch; bộ chạy migration dùng `pg_advisory_lock(88022026)` và đối chiếu SHA-256 checksum. |
| **Xác thực, RBAC & Route Guards** | `backend/app/api/deps.py` (`ContractRoute`, `require_student`, `require_admin`) | Kiểm tra chặt `Content-Type: application/json` (`415`), từ chối body trên `DELETE`, từ chối query ngoài hợp đồng (`400 UNKNOWN_FIELD`), xác thực Bearer token và kiểm tra quyền `STUDENT` / `ADMIN`. |
| **Idempotency Xuyên Worker** | `backend/app/services/idempotency_service.py` (`IdempotencyService.execute`) | Canonical JSON fingerprint (`SHA-256`), khóa tư vấn giao dịch `pg_advisory_xact_lock`, dùng `SAVEPOINT` để lưu cả kết quả thành công lẫn lỗi nghiệp vụ xác định vào `idempotency_records`, replay nguyên vẹn kèm `Idempotent-Replayed: true`. |
| **Đăng ký, Hủy & Hoàn tiền** | `backend/app/services/registration_service.py` (`RegistrationService`) | Điều phối giao dịch nguyên tử `POST /register` và `DELETE /registrations/{id}` theo thứ tự khóa cố định `user -> course_class -> registration -> payment`. |
| **Thanh toán & Quản trị Lớp** | `backend/app/services/payment_service.py`, `course_class_service.py` | Giao dịch `POST /payments` chống thanh toán trùng/thanh toán đơn đã hủy; CRUD lớp học phần của `ADMIN` bảo toàn số chỗ `remaining_seats = new_capacity - active_count` và snapshot học phí cũ. |
| **Hàng đợi Redis & SSO OIDC** | `backend/app/services/queue_service.py`, `sso_service.py` | Lua scripts nguyên tử quản lý hàng đợi FIFO (`WAITING`/`READY`/`EXPIRED`) fail-closed `503`; OIDC Authorization Code + PKCE S256 + cookie ràng buộc trình duyệt `dkhp_sso_bind` + `exchange_code` 60s dùng 1 lần. |

---

## 3. Thiết kế Cơ sở Dữ liệu & Các Chốt Chặn Toàn vẹn (PostgreSQL 16)

Chi tiết đầy đủ và sơ đồ ERD xem tại `docs/database_design.md` và `backend/migrations/001_initial_schema.sql`. Hệ thống không chỉ kiểm tra điều kiện trong Python mà đặt các chốt chặn cứng ngay ở tầng lưu trữ PostgreSQL 16:

1. **Bảo toàn chỗ ngồi không âm & không vượt sức chứa**:
   - Cột `course_classes.remaining_seats` có ràng buộc cứng `CHECK (remaining_seats >= 0 AND remaining_seats <= capacity)`.
   - Câu lệnh trừ chỗ tại `CourseClassRepository.decrement_remaining_seats` luôn kèm điều kiện nguyên tử `WHERE course_class_id = %s AND remaining_seats > 0`.
2. **Chống đăng ký trùng đồng thời vẫn giữ đầy đủ lịch sử hủy + đăng ký lại**:
   - Không dùng `UNIQUE (user_id, course_class_id)` toàn cục (vì sẽ chặn sinh viên đăng ký lại sau khi đã hủy).
   - Thay vào đó, sử dụng **Partial Unique Index**:
     ```sql
     CREATE UNIQUE INDEX uq_registrations_active_user_class
         ON registrations (user_id, course_class_id)
         WHERE status = 'ACTIVE';
     ```
   - Nhờ vậy, một sinh viên có thể có nhiều bản ghi lịch sử `CANCELLED` ở cùng một lớp, nhưng tại mọi thời điểm chỉ tồn tại **tối đa 1 bản ghi `ACTIVE`**.
3. **Ràng buộc máy trạng thái đăng ký – thanh toán**:
   - Bảng `registrations` có `CHECK ((status = 'ACTIVE' AND cancelled_at IS NULL AND payment_status IN ('UNPAID', 'PAID')) OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL AND payment_status IN ('UNPAID', 'REFUNDED')))` — loại bỏ hoàn toàn khả năng tồn tại bản ghi vừa `CANCELLED` vừa `PAID`.
   - Bảng `payments` đặt `UNIQUE (registration_id)` để mỗi lần đăng ký không bao giờ sinh 2 giao dịch thu tiền.
4. **Snapshot dữ liệu lịch sử**:
   - Khi sinh viên đăng ký thành công, `class_code`, `course_name`, `credits`, `tuition_amount` được chụp vào dòng `registrations` để mọi thay đổi cấu hình lớp về sau không làm sai lệch biên lai học phí đã ghi nhận.

---

## 4. Xử lý Đồng thời, Thứ tự Khóa & Cơ chế Idempotency

Chi tiết luồng tuần tự xem tại `docs/concurrency_design.md`. Tóm tắt cơ chế cốt lõi:

1. **Thứ tự khóa nghiêm ngặt chống Deadlock**:
   $$\texttt{pg\_advisory\_xact\_lock(user, key)} \longrightarrow \texttt{users (FOR UPDATE)} \longrightarrow \texttt{course\_classes (FOR UPDATE)} \longrightarrow \texttt{registrations (FOR UPDATE)} \longrightarrow \texttt{payments (FOR UPDATE)}$$
   - Việc khóa hàng `users` **trước** `course_classes` tuần tự hóa mọi thao tác đồng thời của **cùng một sinh viên** (ngăn sinh viên mở 2 tab bấm cùng lúc 2 lớp trùng lịch `LHP001` và `LHP002` — ca kiểm thử `TC23`, hoặc vừa thanh toán vừa hủy cùng lúc — ca kiểm thử `TC24`), mà **không hề làm nghẽn** các sinh viên khác nhau đang tranh chỗ cuối trên cùng một lớp (`TC06`).
   - Các API của `ADMIN` chỉ khóa `course_classes (FOR UPDATE)` và không bao giờ khóa ngược lên `users`, triệt tiêu chu trình chờ vòng tròn.
2. **Tách Argon2id khỏi giao dịch CSDL**:
   - Trong `AuthService.login`, kết nối đọc `users` được trả về pool ngay trước khi thực hiện `verify_password` bằng Argon2id (~70–90ms CPU). Nhờ vậy, hàng trăm lượt đăng nhập đồng thời không làm cạn kiệt connection pool của `/register`.
3. **`SAVEPOINT` cho Idempotency lỗi nghiệp vụ xác định**:
   - Trong `IdempotencyService.execute`, hàm nghiệp vụ chạy bên trong một nested transaction (`SAVEPOINT`). Nếu gặp lỗi nghiệp vụ xác định (`409 CLASS_FULL`, `409 ALREADY_REGISTERED`, `409 SCHEDULE_CONFLICT`, `409 PREREQUISITE_NOT_MET`, `404 CLASS_NOT_FOUND`...), `SAVEPOINT` tự động rollback phần ghi dở dang nhưng giao dịch ngoài vẫn lưu envelope lỗi đó vào `idempotency_records` và `COMMIT`. Các lỗi hạ tầng hoặc lỗi tiền kiểm (`400`, `401`, `403`, `415`, `422`, `503`) không ghi vào `idempotency_records`.

---

## 5. Các Vấn đề Kỹ thuật Đã Phát hiện & Khắc phục Trong Quá trình Triển khai

1. **Xử lý lỗi Redis tường minh khi reset phòng lab (`backend/scripts/reset_lab.py`)**:
   - *Vấn đề*: Phiên bản đầu tiên dùng `except RedisError: pass`, có nguy cơ âm thầm bỏ qua các khóa hàng đợi cũ trên Redis khi `QUEUE_ENABLED=true`.
   - *Khắc phục*: Thiết kế `ResetLabResult` và ngoại lệ `IncompleteLabResetError`:
     - Khi `QUEUE_ENABLED=false` và không truyền `--reset-redis`, không bắt buộc Redis phải chạy và in rõ `"phần Redis không được thực hiện"` (`exit code 0`).
     - Khi `QUEUE_ENABLED=true` (hoặc có `--reset-redis`), kiểm tra `ping()`, chỉ quét xóa đúng phạm vi `dkhp:queue:*` và `dkhp:rl:*` (không dùng `FLUSHALL`), luôn đóng kết nối Redis trong khối `finally`. Nếu PostgreSQL đã commit xong mà Redis gặp sự cố, báo chính xác `"reset chưa hoàn tất: PostgreSQL đã xử lý, Redis chưa xử lý"` và trả mã thoát `3` (khác `0`).
2. **Loại bỏ phụ thuộc lệch đồng hồ giữa App và Redis trong Lua Queue (`backend/app/services/queue_service.py`)**:
   - *Vấn đề*: Dùng `PEXPIREAT` với mốc epoch từ ứng dụng khiến Redis xóa nhầm khóa `token` ngay lập tức nếu đồng hồ App chậm hơn Redis hoặc khi test dịch chuyển thời gian ảo (`Clock.override`).
   - *Khắc phục*: Đổi sang `PEXPIRE` (TTL tương đối) để dọn rác bộ nhớ, kết hợp logic thu hồi chính xác theo `ZRANGEBYSCORE(ready_key, '-inf', now_ms)` bên trong Lua script nguyên tử.
3. **Tương thích múi giờ PostgreSQL đa nền tảng (`SET LOCAL timezone = 'GMT'`)**:
   - *Vấn đề*: Bản PostgreSQL 16 tối giản đóng gói trên Windows (`pgserver` MinGW) không đi kèm thư mục IANA `share/postgresql/timezone` nên từ chối `'UTC'`, còn `SET LOCAL TIME ZONE 0` sinh tên POSIX `'<+00>-00'` làm `psycopg` in cảnh báo.
   - *Khắc phục*: Sử dụng `SET LOCAL timezone = 'GMT'` (tương đương tuyệt đối UTC `00:00`, không có DST, tích hợp sẵn trong nhân C của mọi bản PostgreSQL 16 và `zoneinfo` của Python).
4. **Chống nghẽn pipe `stderr` khi chạy Uvicorn đa worker trên Windows & cô lập `TEST_DATABASE_URL`**:
   - Chuyển hướng log của server con `uvicorn --workers 2` ra tệp tạm trong `.pytest_tmp` thay vì `subprocess.PIPE` không đọc (vốn chỉ có bộ đệm 4 KB trên Windows), chờ đủ 2 tiến trình worker hoàn tất `lifespan` trước khi bắn tải đồng thời.
   - Bổ sung hàm bảo vệ `verify_safe_test_database_url` trong `backend/tests/conftest.py` để hỗ trợ cả `pgserver` lẫn PostgreSQL 16 ngoài qua `PYTEST_USE_EXTERNAL_DB=true` + `TEST_DATABASE_URL` mà không bao giờ chạm vào DB `dev`/`demo`/`prod` hoặc tắt máy chủ PostgreSQL bên ngoài.
5. **Tách khóa log HTTP `response_code` khỏi danh sách che khóa nhạy cảm (`backend/app/main.py`)**:
   - Đổi tên trường mã kết quả trong JSON log HTTP từ `code` sang `response_code` để vừa hiển thị rõ `REGISTERED`/`CLASS_FULL` phục vụ giám sát, vừa tiếp tục che an toàn tham số `code` của OIDC callback trong `SENSITIVE_KEYS`.

---

## 6. Tổng hợp Kết quả Kiểm thử Thực tế & Các Hạng mục Chưa Đo (`NOT_RUN`)

Chi tiết đầy đủ lệnh chạy, phiên bản và bảng đối chiếu `TC01–TC25` được lưu tại `docs/test_results.md`.

### 6.1. Đã Kiểm chứng Thực tế trên Máy Phát triển (`PASS`)
- **Ruff Linter (`ruff 0.17.3`)**: `ruff check app scripts tests` -> **PASS** (`All checks passed!`, exit code `0`).
- **Bộ kiểm thử tự động Pytest (`pytest 8.4.2`, Python `3.11.9`, PostgreSQL `16.2` thật)**:
  - Tổng cộng **34/34 hàm kiểm thử PASS** (`0 FAIL`, `0 ERROR`, `0 SKIPPED`), bao phủ đầy đủ các tình huống `TC01–TC25` của Đặc tả v3.0:
    - **8 Unit tests**: Argon2id, opaque token SHA-256, PKCE S256, canonical fingerprint, advisory lock ID, escape `ILIKE`, UTC clock, redaction log.
    - **4 Contract tests**: khớp 19/19 endpoint OpenAPI v3.0, không lọt `422` mặc định của FastAPI, CORS allowlist & `204` preflight, từ chối sai `Content-Type` (`415`), JSON hỏng (`400`), trường thừa & ép kiểu ngầm (`true`/`3.5`/`"3"`).
    - **16 Integration & CLI tests** trên PostgreSQL 16.2 thật: `TC01–TC05`, `TC08–TC22`, bao gồm rollback khi lỗi giữa chừng (`TC10`), replay sau mất kết nối (`TC11`), sao lưu & khôi phục snapshot thật bằng `pg_dump`/`pg_restore` sang DB độc lập (`TC12`), thanh toán & hoàn tiền nguyên tử (`TC17`), xoay vòng refresh token & giới hạn 8h (`TC19`), seed 3.000 sinh viên, chuẩn bị 1.000 token và regression tests cho `reset_lab.py` + chốt an toàn `TEST_DATABASE_URL`.
    - **6 Multi-worker Concurrency tests** chạy qua **server HTTP thật `uvicorn --workers 2` (2 tiến trình OS độc lập)**: 20 sinh viên tranh 1 chỗ cuối (`TC06`: đúng `1` `200 REGISTERED` + `19` `409 CLASS_FULL`), 1 sinh viên bắn 20 request khác key (`TC07`: đúng `1` `200` + `19` `409 ALREADY_REGISTERED`), đăng ký đồng thời 2 lớp trùng lịch (`TC23`), đua thanh toán vs hủy 5 vòng liên tiếp (`TC24`), 10 request cùng `Idempotency-Key` đồng thời + đứt mạng sau `COMMIT` (`TC25`), và đua xoay vòng `refresh_token` / sửa `capacity` khi đang đăng ký.
- **Kiểm thử Smoke HTTP thật & đối soát SQL Invariants**: đã chạy toàn trình `health -> login -> danh sách/chi tiết lớp -> đăng ký -> replay -> thanh toán -> hủy hoàn tiền -> lịch sử -> refresh/logout -> check_invariants` (`ok: true`, exit code `0`).

### 6.2. Hạng mục Chưa Chạy Thực tế (`NOT_RUN`) & Hạn chế Cần Phối hợp Nhóm
Để đảm bảo tính trung thực khoa học tuyệt đối trong báo cáo học phần, các mục sau được ghi nhận rõ là **`NOT_RUN` (chưa đo / chưa chạy container thật trên máy hiện tại)** do môi trường Windows hiện tại chưa cài Docker Desktop, `redis-server`, Keycloak daemon và `k6`:

1. **Tích hợp E2E với Redis Container thật & Keycloak 26.0.5 Container thật (`NOT_RUN`)**:
   - Logic Lua script của hàng đợi (`TC21`) đã kiểm chứng trên `fakeredis[lua]` (Lupa Lua runtime), và luồng OIDC + PKCE + xác thực chữ ký RSA/JWKS (`TC22`) đã kiểm chứng bằng cặp khóa RSA 2048-bit thật trong test tích hợp; tuy nhiên **chưa chạy E2E qua container `redis:7.4.1-alpine3.20` và `quay.io/keycloak/keycloak:26.0.5` thật**. Cấu hình `compose.dev.yml` và `infra/keycloak/dkhp-realm.json` đã hoàn tất để chạy ngay trên máy có Docker của nhóm.
2. **Bảng số liệu Đo tải 9 Lượt bằng k6 ở 3 Mức tải 10 / 50 / 100 VU (`CHƯA ĐO — CHỜ PHỐI HỢP TV1 + TV2 + TV3`)**:
   - TV2 đã chuẩn bị sẵn đầy đủ dữ liệu `--mode loadtest` (3.000 SV, `LHP001` 1.000 chỗ), `prepare_tokens.py`, `reset_lab.py` và `check_invariants.py`. Bảng dưới đây để trống trung thực để cả nhóm điền số đo thật khi ghép hệ thống với Nginx (TV1) và script `k6` (TV3):

| Mức tải (VUs) | Lần chạy | Tổng Iterations | `200 REGISTERED` | Lỗi 5xx / 429 | Throughput (req/s) | Latency p50 (ms) | Latency p95 (ms) | Latency p99 (ms) | Đối soát `check_invariants` |
|---|---|---|---|---|---|---|---|---|---|
| 10 VU | Lần 1–3 | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chờ chạy thực tế* |
| 50 VU | Lần 1–3 | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chờ chạy thực tế* |
| 100 VU | Lần 1–3 | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chưa đo* | *Chờ chạy thực tế* |

