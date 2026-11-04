# Tài liệu Bàn giao Hạ tầng, Vận hành & Sao lưu cho Thành viên 1 (TV1)

- **Phạm vi**: Kiến trúc triển khai container, cổng dịch vụ, biến môi trường, quy hoạch kết nối PostgreSQL 16, cấu hình Nginx Reverse Proxy, giám sát log/khóa CSDL và quy trình kiểm chứng Backup/Restore (`TC12`).
- **Tệp cấu hình tham chiếu**: `compose.dev.yml`, `backend/Dockerfile`, `backend/.env.example`, `infra/keycloak/dkhp-realm.json`, `backend/scripts/sql/check_invariants.sql`.

---

## 1. Sơ đồ Cổng, Dịch vụ & Docker Compose Profiles

| Dịch vụ | Image ghim phiên bản | Profile Compose | Cổng nội bộ Container | Cổng Host (Dev) | Ghi chú bảo mật mạng |
|---|---|---|---|---|---|
| `postgres` | `postgres:16.4-alpine3.20` | Mặc định | `5432` | `5432` (chỉ mở ở dev) | Ở môi trường triển khai qua Nginx, **không** publish `5432` ra ngoài mạng công cộng |
| `migrate` | Build từ `backend/Dockerfile` (`python:3.12.7-slim-bookworm`) | Mặc định (chạy 1 lần) | — | — | Giữ `pg_advisory_lock(88022026)`, kiểm tra SHA-256 checksum và áp dụng `backend/migrations/*.sql` trước khi `api` nhận tải |
| `api` | Build từ `backend/Dockerfile` (chạy user `appuser` UID `10001`) | Mặc định | `8080` | `8080` | Chạy `uvicorn app.main:app --workers ${API_WORKERS:-2}`; chỉ Nginx được phép gọi trực tiếp khi lên môi trường chuẩn |
| `redis` | `redis:7.4.1-alpine3.20` | `queue`, `full` | `6379` | `127.0.0.1:6379` | Chỉ dùng cho hàng đợi/rate-limit bổ trợ; **tuyệt đối không mở cổng `6379` ra ngoài** |
| `keycloak` | `quay.io/keycloak/keycloak:26.0.5` | `sso`, `full` | `8080` | `8081` | Tự động nạp `infra/keycloak/dkhp-realm.json` (realm `dkhp`, client `dkhp-backend` PKCE S256) |

### Lệnh khởi chạy theo Profile
```bash
# Chế độ cốt lõi (PostgreSQL 16 + Migrate + API) — dùng cho kiểm thử chuẩn & đo tải k6
docker compose -f compose.dev.yml up -d --build

# Chế độ đầy đủ (bật cả Redis Queue và Keycloak SSO)
QUEUE_ENABLED=true SSO_ENABLED=true docker compose -f compose.dev.yml --profile full up -d --build
```

---

## 2. Readiness / Healthcheck & Thứ tự Khởi động

- **Thứ tự bắt buộc**: `postgres` (`pg_isready` healthy) -> `migrate` (`service_completed_successfully`, exit `0`) -> `api` khởi chạy các worker Uvicorn.
- **Endpoint kiểm tra sẵn sàng**: `GET /api/v1/health`
  - Trả `200 HEALTHY` khi kết nối PostgreSQL thực hiện thành công truy vấn `SELECT 1` (và khi `QUEUE_ENABLED=true`, Redis phản hồi `PING` thành công).
  - Trả `503 SERVICE_UNAVAILABLE` kèm `Retry-After: 1` nếu PostgreSQL (hoặc Redis khi `QUEUE_ENABLED=true`) mất kết nối.
  - Phản hồi cũng cho biết rõ trạng thái công tắc hiện hành: `data.features = {"payments": true, "sso": false, "queue": false}`.

---

## 3. Quy hoạch Connection Pool, Worker & Timeout PostgreSQL 16

Mỗi tiến trình worker của Uvicorn khởi tạo **riêng một `psycopg_pool.ConnectionPool` đồng bộ** bên trong vòng đời `lifespan` (không bao giờ mở kết nối trước khi fork/spawn worker và không dùng chung một `Connection` giữa hai luồng).

### Công thức tính kết nối tối đa
$$\text{Tổng kết nối ứng dụng} = \text{API\_WORKERS} \times \text{DB\_POOL\_MAX\_SIZE} + N_{\text{dự phòng (migrate, backup, monitoring)}}$$

| Tham số môi trường | Mặc định Dev | Khuyến nghị Đo tải (4 vCPU) | Giải thích kỹ thuật |
|---|---|---|---|
| `max_connections` (PostgreSQL) | `100` | `100` | Giới hạn cứng trên PostgreSQL 16 |
| `API_WORKERS` | `2` | `4` | Số tiến trình Uvicorn độc lập |
| `DB_POOL_MIN_SIZE` | `2` | `4` | Kết nối ấm giữ sẵn trên mỗi worker |
| `DB_POOL_MAX_SIZE` | `10` | `15` | `4 workers * 15 = 60` kết nối (< `100`, còn dư 40 kết nối cho `pg_dump`, giám sát và CLI) |
| `DB_POOL_TIMEOUT_SECONDS` | `3.0` | `3.0` | Quá hạn chờ lấy connection từ pool -> trả `503 SERVICE_BUSY` + `Retry-After: 1` |
| `DB_IDEMPOTENCY_LOCK_TIMEOUT_MS` | `1500` | `1500` | Quá hạn chờ `pg_advisory_xact_lock` cùng `(user_id, key)` -> trả `409 REQUEST_IN_PROGRESS` + `Retry-After: 1` |
| `DB_LOCK_TIMEOUT_MS` | `2000` | `2000` | Quá hạn chờ khóa hàng `FOR UPDATE` -> rollback an toàn và trả `503 SERVICE_BUSY` |
| `DB_STATEMENT_TIMEOUT_MS` | `5000` | `5000` | Chặn truy vấn treo giữ connection quá 5 giây (`SET LOCAL` theo từng transaction) |

> **Lưu ý khi bật SSO (`SSO_ENABLED=true`)**:
> - `OIDC_ISSUER` và `OIDC_AUTHORIZATION_ENDPOINT` phải là địa chỉ trình duyệt của người dùng nhìn thấy (ví dụ `http://localhost:8081/realms/dkhp`).
> - `OIDC_TOKEN_ENDPOINT` và `OIDC_JWKS_URI` là địa chỉ container `api` gọi trực tiếp sang container `keycloak` qua mạng nội bộ Docker (`http://keycloak:8080/realms/dkhp/protocol/openid-connect/...`). Cấu hình tách biệt này đã được thiết lập sẵn trong `compose.dev.yml`.

---

## 4. Yêu cầu Cấu hình Nginx Reverse Proxy

Để bảo toàn 100% hợp đồng Đặc tả API v3.0 với giao diện của TV3, cấu hình Nginx của TV1 cần tuân thủ 6 điểm sau:

1. **Giữ nguyên tiền tố `/api/v1`**:
   - Khi `location /api/v1/` chuyển tiếp về `upstream dkhp_backend` (`api:8080`), **không** cắt bỏ `/api/v1` ở `proxy_pass`.
2. **Chuyển tiếp đầy đủ Request Headers**:
   - Đảm bảo `underscores_in_headers` mặc định hợp lệ và giữ nguyên các header chuẩn: `Authorization`, `Content-Type`, `Accept`, `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, `Idempotency-Key`, `X-Queue-Token`, và `Cookie` (cần cho cookie ràng buộc trình duyệt tạm thời `dkhp_sso_bind` tại đường dẫn `/api/v1/auth/sso/callback`).
3. **Không ghi đè hoặc nhân đôi CORS Headers**:
   - FastAPI đã xử lý đầy đủ CORS allowlist (`CORS_ALLOWED_ORIGINS`), trả `204` cho `OPTIONS` preflight, gắn `Vary: Origin` và `Access-Control-Expose-Headers: X-Request-ID, Retry-After, Idempotent-Replayed`. Nginx **không** nên `add_header Access-Control-Allow-Origin` lần thứ hai để tránh trình duyệt từ chối vì duplicate header.
4. **Bảo toàn HTTP Status Codes & Response Headers đặc thù**:
   - Không biến đổi các mã `201`, `204`, `302`, `400`, `401`, `403`, `404`, `405`, `409`, `415`, `422`, `429`, `503`.
   - Giữ nguyên các header phản hồi từ backend: `X-Request-ID`, `Retry-After`, `Idempotent-Replayed`, `WWW-Authenticate`, `Allow`, `Cache-Control`, `Location`, `Set-Cookie`.
5. **Chuẩn hóa phản hồi `429` và `502/503/504` tại tầng Nginx sang JSON Envelope**:
   - Nếu Nginx chặn tần suất bằng `limit_req_zone` (`limit_req_status 429`), không trả trang HTML mặc định của Nginx. Hãy cấu hình `error_page 429 = @json_rate_limited` kèm `add_header Content-Type "application/json; charset=utf-8" always; add_header Retry-After "1" always;` và trả JSON:
     ```json
     {"success":false,"code":"RATE_LIMITED","message":"Quá giới hạn tần suất yêu cầu. Vui lòng thử lại sau.","data":null,"errors":[],"request_id":"00000000-0000-4000-8000-000000000429"}
     ```
6. **Che thông tin nhạy cảm trên Access Log của Nginx**:
   - Tại đường dẫn `/api/v1/auth/sso/callback`, Keycloak gửi `code` và `state` trên query string (`$args`). Trong `log_format` của Nginx, hãy ghi `$uri` thay vì `$request_uri` cho `/api/v1/auth/sso/callback` (hoặc dùng `map` che query string) và không bao giờ ghi header `Authorization`, `Cookie` hay `X-Queue-Token` vào access log.

---

## 5. Cấu trúc Log Ứng dụng & Truy vấn Giám sát Điểm nghẽn PostgreSQL

### 5.1. Định dạng JSON Log trên `stdout`
Mỗi request đi qua `api` sinh ra một dòng JSON duy nhất trên `stdout` (đã tự động che mọi trường nhạy cảm qua `app/core/logging.py`):
```json
{
  "timestamp": "2026-11-03T12:20:00Z",
  "level": "INFO",
  "logger": "dkhp.http",
  "message": "HTTP request processed",
  "request_id": "297a3126-ba97-40c5-9cc4-24879e16cd7f",
  "attempt_id": "78d094a0-9a89-4e02-9d5f-6136753d8087",
  "replayed": true,
  "method": "POST",
  "route": "/api/v1/register",
  "status_code": 200,
  "response_code": "REGISTERED",
  "latency_ms": 10.93,
  "actor": "SV0001"
}
```
*(Khi replay `Idempotency-Key`, `request_id` giữ nguyên mã của kết quả gốc để khớp JSON trả cho client, còn `attempt_id` định danh riêng lần gọi lại phục vụ điều tra sự cố).*

### 5.2. Truy vấn SQL Quan sát Tranh chấp Khóa trong Lúc Đo tải (TV1 Prometheus / `psql`)
```sql
-- Theo dõi số kết nối theo trạng thái & loại khóa chờ (wait_event_type = 'Lock')
SELECT state, wait_event_type, wait_event, COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

### 5.3. Đối soát Toàn vẹn Dữ liệu sau Đo tải & sau Khôi phục Sao lưu
TV2 cung cấp sẵn cả công cụ CLI lẫn file SQL thuần để TV1 tích hợp vào script vận hành:
- Chạy bằng Python CLI (trả exit code `0` nếu toàn vẹn tuyệt đối, khác `0` nếu vi phạm):
  ```bash
  python -m scripts.check_invariants
  ```
- Chạy trực tiếp bằng `psql`: sử dụng file `backend/scripts/sql/check_invariants.sql` (5 truy vấn kiểm tra bảo toàn chỗ `remaining_seats + COUNT(ACTIVE) = capacity`, không trùng `ACTIVE`, không tồn tại `CANCELLED + PAID`, đối xứng 1-1 `registrations`/`payments`, và không chồng lấn lịch học `ACTIVE` — toàn bộ 5 truy vấn đều phải trả về **0 dòng vi phạm**).

---

## 6. Quy trình Phối hợp Kiểm chứng Backup & Restore (`TC12`)

Khi TV1 thực hiện diễn tập sao lưu/khôi phục PostgreSQL 16 (đã được tự động hóa kiểm chứng ở mức backend trong `test_tc12_pg_dump_and_pg_restore_snapshot_verification`):

1. **Sao lưu nóng (Consistent Snapshot)** bằng định dạng custom của PostgreSQL 16 (chạy ở chế độ `REPEATABLE READ` nội bộ của `pg_dump`, không khóa đọc/ghi bảng):
   ```bash
   pg_dump --format=custom --no-owner --no-privileges --file=/backups/dkhp_snapshot.dump "$DATABASE_URL"
   ```
2. **Khôi phục kiểm chứng sang một database tách biệt hoàn toàn** (ví dụ `dkhp_restore_verify`, **tuyệt đối không** restore đè trực tiếp lên DB đang chạy nếu chưa xác nhận):
   ```bash
   psql "$ADMIN_DATABASE_URL" -c 'DROP DATABASE IF EXISTS "dkhp_restore_verify";'
   psql "$ADMIN_DATABASE_URL" -c 'CREATE DATABASE "dkhp_restore_verify";'
   pg_restore --no-owner --no-privileges --dbname="$RESTORE_DATABASE_URL" /backups/dkhp_snapshot.dump
   ```
3. **Chạy đối soát bất biến trên bản vừa khôi phục**:
   ```bash
   python -m scripts.check_invariants --database-url "$RESTORE_DATABASE_URL"
   ```
   Xác nhận `"ok": true`, số bản ghi `ACTIVE`/`PAID` khớp đúng thời điểm chụp snapshot và các giao dịch phát sinh sau thời điểm `pg_dump` trên DB chính không bị ảnh hưởng.

