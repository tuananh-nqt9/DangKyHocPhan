# Tài liệu Bàn giao Backend cho Thành viên 3 (TV3 — Frontend & Công cụ Đo tải k6)

- **Phiên bản Đặc tả API đối chiếu**: `3.0` (`docs/api_spec_v3_0.md`, `docs/contract_matrix.md`)
- **Phiên bản API**: `1.0.0` — Tiền tố cố định: `/api/v1`
- **Tài liệu mẫu JSON & OpenAPI**: `docs/api_examples/openapi_v3_0.json` và `docs/api_examples/*.json`

---

## 1. Cách Chạy Nhanh Backend để Ghép Giao diện

### Cách 1: Dùng Docker Compose (nếu máy TV3 có Docker Desktop)
```powershell
Copy-Item "backend\.env.example" ".env"
Copy-Item "backend\.env.example" "backend\.env"
docker compose -f compose.dev.yml up -d --build
docker compose -f compose.dev.yml exec api python -m scripts.seed --mode ui
```

### Cách 2: Chạy trực tiếp bằng Python trên Windows (không cần Docker)
```powershell
# Cửa sổ PowerShell 1 — Khởi chạy PostgreSQL 16 cục bộ
Set-Location "backend"
& "..\.venv\Scripts\python.exe" -m scripts.local_pg

# Cửa sổ PowerShell 2 — Gán DATABASE_URL in ra từ Cửa sổ 1, migrate, seed & bật server
Set-Location "backend"
$env:DATABASE_URL = "<chuỗi DATABASE_URL hiển thị ở Cửa sổ 1>"
& "..\.venv\Scripts\python.exe" -m scripts.migrate
& "..\.venv\Scripts\python.exe" -m scripts.seed --mode ui
# Lưu ý trên Windows native: bỏ --workers 2 khi bind 0.0.0.0 để tránh lỗi Winsock WinError 10022 (Docker Linux vẫn chạy --workers 2 bình thường)
& "..\.venv\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8080
```

- **Base URL mặc định**: `http://localhost:8080/api/v1`
- **Swagger UI trực quan**: `http://localhost:8080/docs`
- **OpenAPI 3.1 Schema**: `http://localhost:8080/openapi.json`

---

## 2. Cấu hình Origin, CORS & Ghép qua Mạng LAN giữa 2 Máy

1. Backend **không dùng wildcard `*`** cho CORS mà kiểm tra chặt theo danh sách `CORS_ALLOWED_ORIGINS` trong `.env`.
2. Mặc định cho phép: `http://localhost:5173,http://127.0.0.1:5173`.
3. **Khi TV3 chạy Vite ở cổng khác (vd `3000`) hoặc gọi từ máy khác trong cùng mạng LAN**:
   - Giả sử máy TV2 (chạy Backend) có IP LAN `192.168.1.10` và máy TV3 (chạy Frontend) có IP LAN `192.168.1.25:5173`:
   - Trên máy TV2 (`backend\.env`):
     ```ini
     CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.25:5173
     FRONTEND_ORIGIN=http://192.168.1.25:5173
     PUBLIC_API_BASE_URL=http://192.168.1.10:8080/api/v1
     ```
   - Trên máy TV3 (cấu hình frontend): đặt `VITE_API_BASE_URL=http://192.168.1.10:8080/api/v1` và tắt chế độ mock (`VITE_USE_MOCK=false`).
4. Preflight `OPTIONS` hợp lệ luôn trả `204 No Content` không có body trước khi kiểm tra Bearer token.
5. Backend mở `Access-Control-Expose-Headers: X-Request-ID, Retry-After, Idempotent-Replayed` để `apiClient` của TV3 đọc trực tiếp được `response.headers.get(...)`.

---

## 3. Tài khoản Mẫu Phòng Lab & Bộ Dữ liệu Seed UI (`--mode ui`)

> **Cảnh báo dữ liệu mẫu phòng lab**: Mật khẩu `Demo@123456` dưới đây chỉ dùng cho kiểm thử cục bộ / phòng lab.

| Tài khoản (`student_id`) | Mật khẩu Lab | Vai trò (`role`) | Đặc điểm dữ liệu mẫu (`--mode ui`) |
|---|---|---|---|
| `SV0001` | `Demo@123456` | `STUDENT` | **Đã hoàn thành** môn tiên quyết `CS101`; đã ánh xạ sẵn danh tính SSO Keycloak (`sv0001`) |
| `SV0002` .. `SV3000` | `Demo@123456` | `STUDENT` | **Chưa hoàn thành** `CS101` (dùng để test lỗi thiếu tiên quyết ở `LHP001`) |
| `AD0001` | `Demo@123456` | `ADMIN` | Tài khoản quản trị tạo/sửa/đóng-mở lớp học phần (`403 FORBIDDEN` nếu gọi API sinh viên) |

### 3 Lớp học phần trong `--mode ui` & Kịch bản Test Giao diện Nhanh

| Mã lớp (`course_class_id`) | `class_code` | Tên học phần | Tín chỉ / Học phí | Chỗ (`capacity`) | Lịch học | Tiên quyết | Kịch bản kiểm thử trên UI |
|---|---|---|---|---|---|---|---|
| `LHP001` | `CNNT-01` | Công nghệ nền tảng | 3 TC / `1500000` VND | `50` (`OPEN`) | `MON` tiết `1–3` (`A101`) | `CS101` | `SV0001` đăng ký **200 REGISTERED**; `SV0002` đăng ký bị **409 PREREQUISITE_NOT_MET** |
| `LHP002` | `WEB-01` | Phát triển ứng dụng Web | 3 TC / `1500000` VND | `50` (`OPEN`) | `MON` tiết `2–4` (`B201`) | `[]` | Nếu `SV0001` đã đăng ký `LHP001`, đăng ký tiếp `LHP002` sẽ nhận **409 SCHEDULE_CONFLICT** (`MON` tiết `2–3`) |
| `LHP003` | `JAVA-01` | Lập trình hướng đối tượng với Java | 3 TC / `1500000` VND | `50` (`OPEN`) | `TUE` tiết `1–3` (`C301`) | `[]` | Mọi sinh viên đăng ký hợp lệ -> thử tiếp Thanh toán mô phỏng (`POST /payments`) -> Hủy có hoàn tiền (`DELETE /registrations/{id}`) |

---

## 4. Trạng thái 19 API & Công tắc Feature Flags

Toàn bộ **19/19 endpoint** của Đặc tả v3.0 đã triển khai đầy đủ và vượt qua kiểm thử hợp đồng + tích hợp. Frontend có thể đọc trạng thái bật/tắt thời gian thực tại `GET /api/v1/health` (`data.features`):

- `payments`: mặc định **`true`** (`PAYMENTS_ENABLED=true`) — mô phỏng nội bộ trên PostgreSQL, không gọi cổng thanh toán ngoài.
- `queue`: mặc định **`false`** (`QUEUE_ENABLED=false`). Khi tắt, `POST /queue/join` và `GET /queue/status` vẫn trả `200` với `queue_enabled: false, status: "NONE"`, và `POST /register` không yêu cầu `X-Queue-Token`.
- `sso`: mặc định **`false`** (`SSO_ENABLED=false`). Khi chưa bật Keycloak container (`--profile sso`), các endpoint `/auth/sso/*` trả `503 SERVICE_UNAVAILABLE` kèm `Retry-After: 1`.

---

## 5. Quy tắc Bắt buộc cho `apiClient` của TV3

### 5.1. Quản lý Token, Single-Flight Refresh & Logout
- Tất cả API bảo vệ dùng header `Authorization: Bearer <access_token>`. **Không** dùng cookie phiên và **không** bật `credentials: "include"` trên `fetch`/`axios`.
- `POST /api/v1/auth/refresh` xoay vòng **nguyên tử cả `access_token` lẫn `refresh_token`**; token cũ mất hiệu lực ngay lập tức.
  - **Quan trọng**: `apiClient` trên UI phải gom các request bị `401 UNAUTHORIZED` vào **một lời gọi `/auth/refresh` duy nhất (single-flight promise)**. Nếu bắn song song 2 request `/auth/refresh` bằng cùng một `refresh_token`, request thứ hai chắc chắn nhận `401 INVALID_REFRESH_TOKEN`.
- Phiên có thời hạn tuyệt đối `28800` giây (8 giờ tính từ lúc login); gần mốc 8 giờ, `expires_in` và `refresh_expires_in` sẽ tự co lại theo thời gian còn lại thực tế.
- `POST /api/v1/auth/logout` yêu cầu **đồng thời** cả `Authorization: Bearer <access_token>` và body `{"refresh_token": "<refresh_token_cùng_phiên>"}`. Logout chỉ thu hồi đúng phiên của thiết bị hiện tại, không làm văng các thiết bị khác.

### 5.2. `Idempotency-Key`, Xử lý Timeout & Đồng bộ State sau Replay
- Bắt buộc đính kèm header `Idempotency-Key: <UUID v4>` cho **3 thao tác ghi**:
  1. `POST /api/v1/register`
  2. `DELETE /api/v1/registrations/{registration_id}`
  3. `POST /api/v1/payments`
- **Quy tắc sinh & giữ key**:
  - Mỗi lần người dùng bấm nút thực hiện **một ý định nghiệp vụ mới**, sinh một UUID v4 mới (`crypto.randomUUID()`).
  - Nếu gặp lỗi mạng, timeout phía trình duyệt, `409 REQUEST_IN_PROGRESS` hoặc `503 SERVICE_BUSY` / `503 SERVICE_UNAVAILABLE`: khi tự động hoặc cho phép người dùng "Thử lại", **phải gửi lại đúng `Idempotency-Key` và đúng body ban đầu** (tôn trọng số giây trong header `Retry-After`).
  - **Không** dùng lại `Idempotency-Key` cũ cho một lớp khác hoặc thao tác khác (sẽ nhận `422 IDEMPOTENCY_KEY_REUSED`).
  - **Lưu ý quan trọng khi Replay lỗi nghiệp vụ / sau Timeout**: Nếu lần trước trả `409 CLASS_FULL`, mọi lần gửi lại cùng `Idempotency-Key` trong 24h vẫn sẽ replay đúng `409 CLASS_FULL` (kèm header `Idempotent-Replayed: true`), kể cả khi lớp vừa có người hủy trả chỗ. Nếu sinh viên muốn thử đăng ký lại từ đầu sau khi thấy chỗ trống mới, UI cần tạo **một `Idempotency-Key` mới**. Sau khi gặp timeout không rõ kết quả hoặc nhận `Idempotent-Replayed: true`, khuyến nghị UI gọi lại `GET /api/v1/registrations/me` và `GET /api/v1/course-classes` để làm mới số chỗ hiện hành.

### 5.3. Hàng đợi Redis (`QUEUE_ENABLED=true`)
- `GET /api/v1/queue/status` chỉ xem trạng thái (`NONE | WAITING | READY | EXPIRED`), **không tự xếp hàng**. Sinh viên phải gọi `POST /api/v1/queue/join` với body `{}`.
- Khi `status === "WAITING"`, poll `GET /api/v1/queue/status` mỗi **3 giây** (không spam liên tục).
- Khi `status === "READY"`, đính kèm header `X-Queue-Token: <queue_token>` vào `POST /api/v1/register`. Trong thời gian hiệu lực `ready_expires_at` (mặc định 300s), sinh viên có thể dùng lại cùng `queue_token` để đăng ký nhiều lớp học phần.

### 5.4. Đăng nhập SSO Keycloak (`SSO_ENABLED=true`)
1. Điều hướng trình duyệt cấp cao nhất (`window.location.assign`) tới `{API_BASE_URL}/auth/sso/login`.
2. Sau khi đăng nhập trên Keycloak (`sv0001` / `Demo@123456`), backend điều hướng trình duyệt về `{FRONTEND_ORIGIN}/sso/callback?exchange_code=...` (hoặc `?error=SSO_FAILED`).
3. **Bắt buộc bảo mật trên trang `/sso/callback`**: Ngay khi đọc `exchange_code` từ `URLSearchParams`, gọi ngay `window.history.replaceState({}, document.title, "/sso/callback")` để xóa mã một lần khỏi thanh địa chỉ và lịch sử trình duyệt trước khi render các thành phần khác, sau đó gọi `POST /api/v1/auth/sso/exchange` với JSON `{"exchange_code": "..."}` (hiệu lực 60 giây, chỉ đổi được đúng 1 lần).

---

## 6. Phối hợp Chạy Công cụ Đo tải k6 (10 / 50 / 100 VU)

Để đo đúng năng lực xử lý tranh chấp tại `POST /api/v1/register` theo Mục 25 của đặc tả (mỗi mức tải `10`, `50`, `100` VU chạy **3 lần lặp**, mỗi lần **1.000 iterations** = 1.000 sinh viên khác nhau `SV0001..SV1000` đăng ký vào lớp `LHP001` có `capacity = 1000`):

1. **Đảm bảo cấu hình chuẩn đo tải**: `QUEUE_ENABLED=false`, `SSO_ENABLED=false`, `RATE_LIMIT_BACKEND=none`.
2. **Trước lượt đo đầu tiên**, tạo sẵn file token cho 1.000 sinh viên (để không cộng thời gian băm Argon2id của `/auth/login` vào latency của `/register`):
   ```powershell
   Set-Location "d:\Code\Backend-DKHP\backend"
   & "..\.venv\Scripts\python.exe" -m scripts.reset_lab --confirm-lab-reset --clear-sessions --reseed loadtest
   & "..\.venv\Scripts\python.exe" -m scripts.prepare_tokens --count 1000
   ```
   File JSON xuất ra tại `d:\Code\Backend-DKHP\exports\loadtest_tokens.json` (đã gitignore) có mảng `tokens: [{iteration, student_id, access_token}]`. Trong script k6, mỗi iteration `i` (`exec.scenario.iterationInTest`) lấy `tokens[i]`, sinh UUID v4 mới cho `Idempotency-Key`, và gửi `{"student_id": tokens[i].student_id, "course_class_id": "LHP001"}`.
3. **Giữa mỗi lượt chạy k6 (bắt buộc!)**: chạy reset không xóa `sessions` để giữ nguyên 1.000 token vừa tạo nhưng làm sạch `registrations`, `idempotency_records` và khôi phục `LHP001` về `1000/1000` chỗ:
   ```powershell
   & "..\.venv\Scripts\python.exe" -m scripts.reset_lab --confirm-lab-reset --reseed loadtest
   ```
4. **Ngay sau mỗi lượt chạy k6**, chạy kiểm tra bất biến SQL để ghi vào bảng đối chiếu báo cáo nhóm:
   ```powershell
   & "..\.venv\Scripts\python.exe" -m scripts.check_invariants
   ```
   Kỳ vọng: `"ok": true`, `active_registrations = 1000`, `remaining_seats = 0`, mã thoát `0`.

---

## 7. Mẫu Gửi Báo Lỗi Khi Ghép Tích Hợp

Khi phát hiện hành vi lệch hợp đồng, TV3 chỉ cần gửi cho TV2 các thông tin sau (**lưu ý che `access_token`, `refresh_token`, `password`, `X-Queue-Token`**):
- Method & URL đầy đủ (kèm query string nếu có)
- Giá trị header `X-Request-ID` (hoặc trường `request_id` trong JSON trả về) và `Idempotency-Key`
- Payload JSON đã gửi (đã che mật khẩu/token)
- HTTP status code và nguyên văn JSON envelope nhận được

