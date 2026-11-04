# Hệ thống Đăng ký Học phần Trực tuyến — Backend & Cơ sở Dữ liệu 

- **Môn học**: Nhập môn Công nghệ Nền tảng
- **Đề tài 08**: Thiết kế hệ thống đăng ký học phần trực tuyến (quy mô 3.000 sinh viên, tập trung xử lý tranh chấp tại thời điểm mở đăng ký)
- **Phạm vi**: Cơ sở dữ liệu PostgreSQL 16, Backend API FastAPI, xác thực/phân quyền, giao dịch & khóa đồng thời, Idempotency-Key, thanh toán/hoàn tiền mô phỏng nội bộ, hàng đợi Redis (Lua), SSO Keycloak OIDC + PKCE, bộ kiểm thử tự động (`TC01–TC25`) và tài liệu.
> **Lưu ý quan trọng về phạm vi mô phỏng & bảo mật phòng lab**:
> 1. Thanh toán (`POST /api/v1/payments`) và hoàn tiền khi hủy lớp **chỉ là mô phỏng nội bộ trên PostgreSQL** để kiểm chứng giao dịch nguyên tử; hệ thống **không** kết nối ngân hàng, SePay hay VietQR thật.
> 2. Mật khẩu mẫu `Demo@123456` của các tài khoản seed (`SV0001`..`SV3000`, `AD0001`) và client secret mẫu trong `compose.dev.yml` **chỉ phục vụ môi trường phát triển / phòng lab**, tuyệt đối không dùng cho môi trường thật.

---

## 1. Cấu trúc Thư mục Dự án

```text
Backend-DKHP/
├── backend/
│   ├── app/
│   │   ├── main.py                # Khởi tạo FastAPI, lifespan pool, CORS, error handlers, OpenAPI v3.0
│   │   ├── core/                  # Cấu hình (.env), Argon2id/token hash, mã lỗi chuẩn, logging redaction, clock, rate limit
│   │   ├── db/                    # psycopg_pool theo từng worker, transaction helper, bộ chạy migration có advisory lock
│   │   ├── api/                   # Dependencies xác thực/RBAC, ContractRoute, 8 routers (19 endpoints)
│   │   ├── schemas/               # Pydantic v2 strict request/response models
│   │   ├── services/              # Điều phối giao dịch: auth, sso, course_class, registration, payment, idempotency, queue, health
│   │   └── repositories/          # Câu lệnh SQL tham số hóa (psycopg 3), không tự COMMIT giữa chừng
│   ├── migrations/
│   │   └── 001_initial_schema.sql # Lược đồ PostgreSQL 16, khóa ngoại, CHECK, partial unique index, sequence LHP
│   ├── scripts/                   # CLI: migrate, seed, prepare_tokens, reset_lab, check_invariants, local_pg, export_openapi
│   │   └── sql/check_invariants.sql
│   ├── tests/                     # Bộ kiểm thử tự động: unit/, contract/, integration/, concurrency/
│   ├── .env.example               # Mẫu biến môi trường đầy đủ chú thích
│   ├── Dockerfile                 # Container Python 3.12 slim chạy non-root
│   ├── pyproject.toml             # Cấu hình gói, pytest, ruff
│   └── requirements.lock          # Ghim phiên bản thư viện ổn định
├── infra/
│   └── keycloak/dkhp-realm.json   # Cấu hình tự động nạp realm `dkhp` & client `dkhp-backend` (PKCE S256)
├── docs/
│   ├── api_spec_v3_0.md           # Bản lưu chuẩn Đặc tả API v3.0 (Mục 01–25)
│   ├── contract_matrix.md         # Ma trận hợp đồng đầy đủ 19 endpoint
│   ├── implementation_decisions.md# Các quyết định nội bộ & điểm đồng bộ TV1/TV3
│   ├── database_design.md         # Thiết kế CSDL PostgreSQL 16, ERD Mermaid & bất biến dữ liệu
│   ├── concurrency_design.md      # Thiết kế khóa giao dịch, chống oversell, idempotency & 10 câu hỏi bảo vệ
│   ├── api_examples/              # OpenAPI v3.0 JSON & các mẫu response thực tế xuất từ schema
│   ├── handoff_tv3.md             # Tài liệu bàn giao ghép nối UI & k6 cho Thành viên 3
│   ├── handoff_tv1.md             # Tài liệu bàn giao hạ tầng, Nginx, giám sát & backup cho Thành viên 1
│   ├── test_results.md            # Kết quả kiểm thử TC01–TC25 & bằng chứng thực thi
│   ├── progress.md                # Nhật ký tiến độ kỹ thuật các giai đoạn
│   └── bao_cao_tv2.md             # Báo cáo kỹ thuật tổng hợp phục vụ ghép báo cáo nhóm & vấn đáp
├── compose.dev.yml                # Docker Compose phát triển (PostgreSQL 16 + API + profiles Redis/Keycloak)
├── TASKS.md                       # Danh sách công việc theo 5 giai đoạn
└── README.md                      # Hướng dẫn cài đặt, chạy và kiểm chứng từng bước
```

---

## 2. Yêu cầu Môi trường trên Windows

- **Hệ điều hành**: Windows 10/11 (sử dụng **PowerShell**).
- **Lựa chọn A (Khuyến nghị khi ghép nhóm / có Docker)**: Cài đặt **Docker Desktop** (hỗ trợ `docker compose`).
- **Lựa chọn B (Chạy trực tiếp trên Windows không cần Docker Desktop)**:
  - **Python 3.12** (tương thích tốt trên cả **Python 3.11.9+**).
  - **PostgreSQL 16** cài trên máy *hoặc* dùng ngay tiện ích PostgreSQL 16 cục bộ đóng gói sẵn trong `.venv` (`python -m scripts.local_pg` qua gói `pgserver`).

---

## 3. Cấu hình Biến Môi trường (`.env`)

Mở PowerShell tại thư mục gốc `d:\Code\Backend-DKHP` và tạo file `.env` từ file mẫu:

```powershell
Copy-Item "backend\.env.example" "backend\.env"
Copy-Item "backend\.env.example" ".env"
```

Các biến quan trọng nhất trong `backend\.env`:

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `APP_ENV` | `dev` | `dev` \| `test` \| `lab` \| `prod` (script `seed`, `reset_lab`, `prepare_tokens` tự động từ chối nếu là `prod`) |
| `DATABASE_URL` | `postgresql://dkhp_user:dkhp_dev_pass@localhost:5432/dkhp_dev` | Kết nối PostgreSQL 16 chính của ứng dụng |
| `TEST_DATABASE_URL` | `postgresql://dkhp_user:dkhp_dev_pass@localhost:5432/dkhp_test` | Kết nối DB riêng cho kiểm thử, tách biệt hoàn toàn với `DATABASE_URL` |
| `API_PORT` / `API_WORKERS` | `8080` / `2` | Cổng lắng nghe HTTP và số tiến trình Uvicorn worker |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Danh sách origin của UI TV3 (phân tách bằng dấu phẩy, không dùng `*`). Thêm IP LAN của TV3 nếu test qua mạng LAN |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Origin điều hướng trình duyệt về sau khi SSO callback hoàn tất |
| `PAYMENTS_ENABLED` | `true` | Công tắc bật API thanh toán mô phỏng (Đợt B) |
| `SSO_ENABLED` | `false` | Công tắc bật SSO Keycloak OIDC (Đợt C — mặc định tắt cho đo tải chuẩn) |
| `QUEUE_ENABLED` | `false` | Công tắc bật hàng đợi ảo Redis (Đợt C — mặc định tắt cho đo tải chuẩn) |
| `TUITION_PER_CREDIT` | `500000` | Đơn giá học phí mỗi tín chỉ (`VND`, số nguyên; 3 tín chỉ = `1500000`) |

---

## 4. Hướng dẫn Khởi chạy Hệ thống

### Cách A — Chạy bằng Docker Compose (Tái lập đầy đủ nhất)

Tại thư mục gốc `d:\Code\Backend-DKHP`:

```powershell
# 1. Khởi chạy PostgreSQL 16 + tự động chạy migration + API (2 workers tại cổng 8080)
docker compose -f compose.dev.yml up -d --build

# 2. Seed dữ liệu mẫu chế độ UI (3.000 SV + AD0001 + 3 lớp LHP001, LHP002, LHP003)
docker compose -f compose.dev.yml exec api python -m scripts.seed --mode ui

# 3. Kiểm tra trạng thái container
docker compose -f compose.dev.yml ps
```

**Bật thêm thành phần mở rộng Đợt C (tùy chọn)**:
- Bật thêm **Redis 7.4** cho hàng đợi ảo:
  ```powershell
  $env:QUEUE_ENABLED="true"
  docker compose -f compose.dev.yml --profile queue up -d --build
  ```
- Bật thêm **Keycloak 26.0.5** (tự động nạp `infra/keycloak/dkhp-realm.json` tại `http://localhost:8081`):
  ```powershell
  $env:SSO_ENABLED="true"
  docker compose -f compose.dev.yml --profile sso up -d --build
  ```
- Bật đồng thời cả Redis và Keycloak:
  ```powershell
  $env:QUEUE_ENABLED="true"; $env:SSO_ENABLED="true"
  docker compose -f compose.dev.yml --profile full up -d --build
  ```

---

### Cách B — Chạy Trực tiếp bằng Python trên Windows (Không cần Docker Desktop)

#### Bước 1: Tạo môi trường ảo `.venv` và cài đặt thư viện

```powershell
Set-Location "d:\Code\Backend-DKHP"
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r "backend\requirements.lock"
& ".\.venv\Scripts\pip.exe" install -e "backend[dev]"
```

*(Nếu máy chưa cài sẵn PostgreSQL 16 hệ thống, cài thêm gói PostgreSQL 16 nhúng cho dev: `& ".\.venv\Scripts\pip.exe" install pgserver==0.1.4`)*

#### Bước 2: Khởi động PostgreSQL 16
- **Nếu đã có PostgreSQL 16 trên máy**: tạo database `dkhp_dev` và cập nhật `DATABASE_URL` trong `backend\.env`.
- **Nếu chưa cài PostgreSQL hệ thống**: mở **Cửa sổ PowerShell số 1** và chạy máy chủ PostgreSQL 16 cục bộ đi kèm dự án:
  ```powershell
  Set-Location "d:\Code\Backend-DKHP\backend"
  & "..\.venv\Scripts\python.exe" -m scripts.local_pg
  ```
  Terminal 1 sẽ in ra dòng `DATABASE_URL=postgresql://...` (giữ cửa sổ này mở; sao chép chuỗi `DATABASE_URL` đó vào `backend\.env` hoặc gán biến `$env:DATABASE_URL` ở cửa sổ số 2).

#### Bước 3: Chạy Migration, Seed dữ liệu mẫu và Khởi chạy API
Mở **Cửa sổ PowerShell số 2**:

```powershell
Set-Location "d:\Code\Backend-DKHP\backend"
# Nếu dùng local_pg ở Bước 2, gán chuỗi DATABASE_URL vừa in ở Cửa sổ 1:
# $env:DATABASE_URL = "postgresql://postgres:password@localhost:xxxxx/dkhp_dev"

# 1. Áp dụng lược đồ PostgreSQL 16 (có bảng schema_migrations & checksum)
& "..\.venv\Scripts\python.exe" -m scripts.migrate

# 2. Nạp dữ liệu mẫu cho giao diện TV3 (SV0001..SV3000, AD0001, LHP001..LHP003)
& "..\.venv\Scripts\python.exe" -m scripts.seed --mode ui

# 3. Khởi động Uvicorn tại http://localhost:8080
# (Trên Windows chạy trực tiếp không dùng --workers 2 với 0.0.0.0 để tránh lỗi Winsock WinError 10022; đa luồng pool vẫn xử lý song song bình thường. Trên Docker Linux dùng --workers 2 chuẩn)
& "..\.venv\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8080
```

- **Swagger UI trực quan**: mở trình duyệt tại http://localhost:8080/docs
- **OpenAPI JSON chuẩn v3.0**: http://localhost:8080/openapi.json

---

## 5. Kiểm tra Nhanh Toàn bộ Luồng Nghiệp vụ bằng PowerShell

Mở một cửa sổ PowerShell mới khi API đang chạy tại `http://localhost:8080` và chạy lần lượt các lệnh dưới đây:

```powershell
$BaseUrl = "http://localhost:8080/api/v1"

# 1. Kiểm tra Healthcheck & các tính năng đang bật
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" | ConvertTo-Json -Depth 5

# 2. Đăng nhập bằng tài khoản SV0001 (đã hoàn thành môn tiên quyết CS101)
$LoginBody = @{ student_id = "SV0001"; password = "Demo@123456" } | ConvertTo-Json
$LoginResp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" `
    -ContentType "application/json" -Body $LoginBody
$AccessToken = $LoginResp.data.access_token
Write-Host "Đăng nhập thành công SV: $($LoginResp.data.student.student_id)"

# 3. Xem danh sách lớp học phần đang mở
$AuthHeaders = @{ Authorization = "Bearer $AccessToken" }
Invoke-RestMethod -Method Get -Uri "$BaseUrl/course-classes?page=1&page_size=20" `
    -Headers $AuthHeaders | ConvertTo-Json -Depth 6

# 4. Đăng ký lớp LHP001 (sinh UUID v4 cho Idempotency-Key)
$RegKey = [guid]::NewGuid().ToString()
$RegBody = @{ student_id = "SV0001"; course_class_id = "LHP001" } | ConvertTo-Json
$RegResp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/register" `
    -Headers @{ Authorization = "Bearer $AccessToken"; "Idempotency-Key" = $RegKey } `
    -ContentType "application/json" -Body $RegBody
$RegId = $RegResp.data.registration.registration_id
Write-Host "Đã đăng ký thành công! registration_id=$RegId | chỗ còn lại=$($RegResp.data.course_class.remaining_seats)"

# 5. Thanh toán học phí mô phỏng cho đăng ký vừa tạo
$PayKey = [guid]::NewGuid().ToString()
$PayBody = @{ registration_id = $RegId } | ConvertTo-Json
$PayResp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/payments" `
    -Headers @{ Authorization = "Bearer $AccessToken"; "Idempotency-Key" = $PayKey } `
    -ContentType "application/json" -Body $PayBody
Write-Host "Trạng thái thanh toán: $($PayResp.data.payment.status) | Số tiền: $($PayResp.data.payment.amount) VND"

# 6. Hủy đăng ký (tự động hoàn chỗ + chuyển trạng thái sang REFUNDED nguyên tử)
$CancelKey = [guid]::NewGuid().ToString()
$CancelResp = Invoke-RestMethod -Method Delete -Uri "$BaseUrl/registrations/$RegId" `
    -Headers @{ Authorization = "Bearer $AccessToken"; "Idempotency-Key" = $CancelKey }
Write-Host "Sau khi hủy: status=$($CancelResp.data.registration.status), payment_status=$($CancelResp.data.registration.payment_status), chỗ còn lại=$($CancelResp.data.course_class.remaining_seats)"

# 7. Kiểm tra toàn vẹn dữ liệu & bất biến SQL trực tiếp trên DB
Set-Location "d:\Code\Backend-DKHP\backend"
& "..\.venv\Scripts\python.exe" -m scripts.check_invariants
```

---

## 6. Chạy Kiểm thử Tự động & Kiểm tra Mã nguồn

Bộ kiểm thử tự động hỗ trợ hai chế độ cơ sở dữ liệu thật (tuyệt đối không dùng SQLite hay mock DB):
- **Mặc định (`pgserver`)**: tự khởi tạo một máy chủ **PostgreSQL 16.2 riêng biệt**, chạy migration/seed sạch cho từng bài test, kiểm tra đầy đủ **TC01–TC25** (bao gồm chạy 2 tiến trình Uvicorn OS workers thật cho các kịch bản tranh chấp đồng thời) và tự động đối soát bất biến SQL sau mỗi test.
- **Dùng PostgreSQL 16 ngoài hoặc Docker (`PYTEST_USE_EXTERNAL_DB=true`)**: kết nối vào `TEST_DATABASE_URL` (fixture tự động kiểm tra tên DB bắt buộc chứa `test`/`pytest`, từ chối nếu trùng `DATABASE_URL` hoặc chứa `prod`/`demo`, và **không** tắt máy chủ PostgreSQL bên ngoài khi kết thúc test).

```powershell
Set-Location "d:\Code\Backend-DKHP\backend"

# 1. Kiểm tra chuẩn mã nguồn Ruff
& "..\.venv\Scripts\ruff.exe" check app scripts tests

# 2. Chạy toàn bộ bộ kiểm thử bằng PostgreSQL 16 cô lập (pgserver)
& "..\.venv\Scripts\pytest.exe" -v

# 3. Chạy kiểm thử trên PostgreSQL 16 ngoài / Docker qua TEST_DATABASE_URL:
# $env:PYTEST_USE_EXTERNAL_DB = "true"
# $env:TEST_DATABASE_URL = "postgresql://dkhp_user:dkhp_dev_pass@localhost:5432/dkhp_test"
# & "..\.venv\Scripts\pytest.exe" -v

# 4. Hoặc chạy riêng từng nhóm kiểm thử:
& "..\.venv\Scripts\pytest.exe" tests/unit -v
& "..\.venv\Scripts\pytest.exe" tests/contract -v
& "..\.venv\Scripts\pytest.exe" tests/integration -v
& "..\.venv\Scripts\pytest.exe" tests/concurrency -v
```

---

## 7. Chuyển đổi giữa Chế độ Ghép UI và Chế độ Đo tải k6 (10 / 50 / 100 VU)

Theo Mục 25 của Đặc tả API v3.0, cấu hình dữ liệu UI (`LHP001` có 50 chỗ và yêu cầu môn tiên quyết `CS101`) khác với cấu hình đo tải chuẩn (`LHP001` có `1.000` chỗ, không tiên quyết, không lịch học để 1.000 sinh viên khác nhau đăng ký hợp lệ):

```powershell
Set-Location "d:\Code\Backend-DKHP\backend"

# A. Trước mỗi lượt chạy k6 (bắt buộc chạy để xóa idempotency_records cũ & nạp LHP001 = 1000 chỗ):
& "..\.venv\Scripts\python.exe" -m scripts.reset_lab --confirm-lab-reset --reseed loadtest

# (Nếu đang bật QUEUE_ENABLED=true hoặc muốn ép xóa key dkhp:queue:* / dkhp:rl:* trên Redis):
# & "..\.venv\Scripts\python.exe" -m scripts.reset_lab --confirm-lab-reset --reset-redis --reseed loadtest
# Lưu ý hành vi reset_lab với Redis:
# - Khi QUEUE_ENABLED=false và không truyền --reset-redis: script không yêu cầu Redis phải chạy và ghi rõ phần Redis không được thực hiện (exit code 0).
# - Khi QUEUE_ENABLED=true hoặc có --reset-redis: script chỉ xóa các key phạm vi dkhp:queue:* và dkhp:rl:* (không FLUSHALL), luôn đóng Redis client; nếu PostgreSQL đã xong mà Redis lỗi, script báo rõ "reset chưa hoàn tất: PostgreSQL đã xử lý, Redis chưa xử lý" và trả mã thoát 3 (khác 0).

# B. Tạo trước 1.000 access_token cho SV0001..SV1000 (tránh đo lẫn Argon2id của /auth/login vào /register):
# File xuất ra nằm tại d:\Code\Backend-DKHP\exports\loadtest_tokens.json (đã gitignore)
& "..\.venv\Scripts\python.exe" -m scripts.prepare_tokens --count 1000

# C. Sau mỗi lượt chạy k6: kiểm tra bất biến SQL (phải trả về ok=true và mã thoát 0):
& "..\.venv\Scripts\python.exe" -m scripts.check_invariants

# D. Quay trở lại bộ dữ liệu mẫu để demo giao diện với TV3:
& "..\.venv\Scripts\python.exe" -m scripts.reset_lab --confirm-lab-reset --clear-sessions --reseed ui
```

---

## 8. Xử lý Lỗi Thường gặp (Troubleshooting)

1. **Lỗi kết nối DB (`OperationalError: connection failed` hoặc `503 SERVICE_UNAVAILABLE`)**:
   - Kiểm tra PostgreSQL 16 đã chạy chưa (`docker compose ps` hoặc cửa sổ `scripts.local_pg`) và cổng/mật khẩu trong `DATABASE_URL` có khớp thực tế không.
2. **Đăng nhập báo `401 INVALID_CREDENTIALS` với `SV0001` / `Demo@123456` hoặc danh sách lớp trống**:
   - Bạn mới chạy `scripts.migrate` nhưng chưa chạy `python -m scripts.seed --mode ui`.
3. **Frontend TV3 gọi API bị trình duyệt chặn CORS**:
   - Kiểm tra origin thật trên thanh địa chỉ trình duyệt của TV3 (ví dụ `http://localhost:3000` hoặc `http://192.168.1.25:5173`), bổ sung chính xác origin đó vào biến `CORS_ALLOWED_ORIGINS` trong `.env` và khởi động lại Uvicorn.
4. **Gọi `POST /register`, `POST /payments` hoặc `DELETE /registrations/{id}` nhận `400 VALIDATION_ERROR` ở trường `Idempotency-Key`**:
   - Cả 3 API ghi dữ liệu này bắt buộc truyền header `Idempotency-Key` đúng định dạng **UUID v4** (ví dụ `crypto.randomUUID()` trên JS hoặc `[guid]::NewGuid().ToString()` trên PowerShell).
   - Nếu dùng lại `Idempotency-Key` cũ cho một lớp khác hoặc `registration_id` khác, backend trả `422 IDEMPOTENCY_KEY_REUSED` theo đúng đặc tả.
5. **Chạy lại bài k6 thấy kết quả trả rất nhanh kèm header `Idempotent-Replayed: true` mà chỗ không giảm**:
   - Do chưa chạy `python -m scripts.reset_lab --confirm-lab-reset --reseed loadtest` giữa hai lượt đo hoặc script k6 dùng lại `Idempotency-Key` cố định.
6. **Lỗi hiển thị ký tự tiếng Việt trong PowerShell cũ**:
   - Chạy `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` trước khi in kết quả JSON ra màn hình console.

---

## 9. Tài liệu Bàn giao & Thiết kế Chi tiết

- Ma trận hợp đồng 19 API: [`docs/contract_matrix.md`](docs/contract_matrix.md)
- Thiết kế CSDL & bất biến toàn vẹn: [`docs/database_design.md`](docs/database_design.md)
- Thiết kế xử lý đồng thời, khóa giao dịch & 10 câu hỏi vấn đáp: [`docs/concurrency_design.md`](docs/concurrency_design.md)
- Quyết định triển khai nội bộ: [`docs/implementation_decisions.md`](docs/implementation_decisions.md)
- Ví dụ JSON & OpenAPI v3.0: [`docs/api_examples/README.md`](docs/api_examples/README.md)
- Hướng dẫn bàn giao cho **TV3 (Frontend & k6)**: [`docs/handoff_tv3.md`](docs/handoff_tv3.md)
- Hướng dẫn bàn giao cho **TV1 (Hạ tầng, Nginx & Backup)**: [`docs/handoff_tv1.md`](docs/handoff_tv1.md)
- Báo cáo kết quả kiểm thử `TC01–TC25`: [`docs/test_results.md`](docs/test_results.md)
- Báo cáo kỹ thuật tổng hợp TV2: [`docs/bao_cao_tv2.md`](docs/bao_cao_tv2.md)
