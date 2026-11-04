# Báo cáo Kết quả Kiểm thử & Bằng chứng Thực thi (`test_results.md`)

- **Thời điểm thực thi kiểm chứng cuối**: `2026-11-03 19:23 – 19:29 (UTC+07:00)`
- **Nhánh / Trạng thái mã nguồn**: `master` (workspace hiện tại tại `d:\Code\Backend-DKHP`)
- **Môi trường thực tế đã xác minh**:
  - Hệ điều hành: Windows (`win32`)
  - Python: `3.11.9` (`.venv\Scripts\python.exe`)
  - Linter & Test Runner: `ruff 0.17.3`, `pytest 8.4.2`
  - Cơ sở dữ liệu nghiệp vụ & kiểm thử: **PostgreSQL `16.2`** thật (`PostgreSQL 16.2 on x86_64-pc-mingw64` chạy độc lập cho kiểm thử, kèm `pg_dump` và `pg_restore` thật; đồng thời đã kiểm chứng chế độ kết nối DB ngoài qua `PYTEST_USE_EXTERNAL_DB=true` + `TEST_DATABASE_URL`)
  - Máy chủ ứng dụng kiểm thử đồng thời: **Uvicorn `0.54.0` chạy 2 tiến trình OS worker thật (`--workers 2`)** với `FastAPI 0.162.0`, `psycopg 3.3.6`, `psycopg-pool 3.3.3`
  - Thành phần chưa cài đặt trên máy hiện tại: `docker`, `redis-server`, `keycloak`, `k6` (không có trong `PATH`)

---

## 1. Tổng hợp Kết quả Chạy Lệnh Kiểm thử

| Hạng mục kiểm tra | Lệnh thực thi (tại `d:\Code\Backend-DKHP\backend`) | Exit Code | `PASS` | `FAIL` | `ERROR` | `SKIPPED` | `NOT_RUN` |
|---|---|---:|---:|---:|---:|---:|---:|
| Kiểm tra tĩnh & chuẩn code (Ruff) | `& "..\.venv\Scripts\ruff.exe" check app scripts tests` | `0` | Toàn bộ (`All checks passed!`) | `0` | `0` | `0` | `0` |
| Toàn bộ Pytest Suite (Unit + Contract + Integration PG16 + 2-Worker Concurrency) | `& "..\.venv\Scripts\pytest.exe" -v` | `0` | **34** hàm test | `0` | `0` | `0` | `0` |
| Kiểm chứng chế độ DB ngoài (`TEST_DATABASE_URL` không chạm DB dev) | `$env:PYTEST_USE_EXTERNAL_DB="true"; & "..\.venv\Scripts\pytest.exe" tests/contract -v` | `0` | **4** hàm test | `0` | `0` | `0` | `0` |
| Xuất OpenAPI v3.0 & JSON Examples (validate ngược bằng Pydantic) | `& "..\.venv\Scripts\python.exe" -m scripts.export_openapi_and_examples` | `0` | **19/19** endpoints + 8 fixtures | `0` | `0` | `0` | `0` |
| Smoke Test HTTP thật (2 workers) + CLI `migrate`/`seed`/`reset_lab`/`prepare_tokens`/`check_invariants` | Chạy qua `uvicorn --workers 2` + `httpx` + `scripts.*` | `0` | **10/10** bước luồng thật | `0` | `0` | `0` | `0` |
| Tích hợp E2E với container `redis:7.4.1-alpine3.20` thật | Xem lệnh mục 4.1 | — | `0` | `0` | `0` | `0` | **1** (`NOT_RUN`) |
| Tích hợp E2E với container `keycloak:26.0.5` thật | Xem lệnh mục 4.2 | — | `0` | `0` | `0` | `0` | **1** (`NOT_RUN`) |
| Đo tải 9 lượt `k6` (10 / 50 / 100 VU × 3 lần lặp) & ghép UI TV3 | Xem lệnh mục 4.3 | — | `0` | `0` | `0` | `0` | **1** (`NOT_RUN`) |

---

## 2. Ma trận Đối chiếu Chi tiết `TC01–TC25` (Đặc tả API v3.0)

> **Lưu ý phương pháp đối chiếu**: Một hàm kiểm thử pytest tích hợp nhiều bước liên tiếp để kiểm tra trọn vẹn chu trình trạng thái, do đó **34 hàm pytest** bao phủ đầy đủ **25 tình huống nghiệm thu `TC01–TC25`** cộng thêm các bài kiểm thử hợp đồng HTTP/OpenAPI, hàm thuần và hồi quy CLI (`reset_lab`, chốt bảo vệ `TEST_DATABASE_URL`). Sau **mọi** bài test có DB, fixture `clean_db` tự động mở kết nối mới chạy `run_invariant_checks` để đối soát toàn vẹn bảng.

| Mã TC | Mô tả tình huống theo Đặc tả v3.0 | Hàm kiểm thử thực tế trong `backend/tests/` | Thực thi thực tế vs Giả lập | Kết quả |
|---|---|---|---|---|
| **TC01** | Đăng nhập `POST /auth/login` đúng (`200 LOGIN_SUCCESS`) và sai mật khẩu / sai mã SV / khoảng trắng đầu cuối (`401 INVALID_CREDENTIALS`) | `integration/test_tc01_to_tc22.py::test_tc01_login_success_and_invalid_credentials` | PostgreSQL 16.2 thật + Argon2id thật | **PASS** |
| **TC02** | Luồng cơ bản: xem danh sách lớp, chi tiết lớp, đăng ký `POST /register` thành công, giảm `remaining_seats`, xem `GET /registrations/me` khớp caller | `integration/test_tc01_to_tc22.py::test_tc02_tc03_register_once_caller_views_and_already_registered` | PostgreSQL 16.2 thật | **PASS** |
| **TC03** | Sinh viên đã đăng ký `ACTIVE` gửi đăng ký lại lớp đó (key mới) -> `409 ALREADY_REGISTERED`, sĩ số không giảm thêm | `integration/test_tc01_to_tc22.py::test_tc02_tc03_register_once_caller_views_and_already_registered` | PostgreSQL 16.2 thật + partial unique index | **PASS** |
| **TC04** | Lớp hết chỗ (`remaining_seats = 0`) -> `409 CLASS_FULL`; replay cùng key vẫn giữ nguyên `409 CLASS_FULL` | `integration/test_tc01_to_tc22.py::test_tc04_tc05_tc08_tc09_class_full_closed_mismatch_and_not_found` | PostgreSQL 16.2 thật | **PASS** |
| **TC05** | Lớp đang `CLOSED` -> `409 REGISTRATION_CLOSED` | `integration/test_tc01_to_tc22.py::test_tc04_tc05_tc08_tc09_class_full_closed_mismatch_and_not_found` | PostgreSQL 16.2 thật | **PASS** |
| **TC06** | **20 sinh viên khác nhau đồng thời tranh 1 chỗ cuối** -> đúng `1` `200 REGISTERED`, `19` `409 CLASS_FULL`, `0` lỗi 5xx, `remaining_seats = 0`, `COUNT(ACTIVE) = 1` | `concurrency/test_concurrency_and_multiworker.py::test_tc06_20_students_compete_for_last_1_seat_across_2_workers` | **Server HTTP thật `uvicorn --workers 2` (2 OS processes)** + PostgreSQL 16.2 thật | **PASS** |
| **TC07** | **1 sinh viên bắn 20 request đồng thời với 20 `Idempotency-Key` khác nhau** vào cùng lớp -> đúng `1` `200 REGISTERED`, `19` `409 ALREADY_REGISTERED` | `concurrency/test_concurrency_and_multiworker.py::test_tc07_1_student_20_different_keys_concurrent_across_2_workers` | **Server HTTP thật `uvicorn --workers 2`** + PostgreSQL 16.2 thật | **PASS** |
| **TC08** | Token của `SV0001` nhưng body gửi `student_id = "SV0002"` -> `403 STUDENT_MISMATCH` | `integration/test_tc01_to_tc22.py::test_tc04_tc05_tc08_tc09_class_full_closed_mismatch_and_not_found` | PostgreSQL 16.2 thật | **PASS** |
| **TC09** | Mã lớp đúng định dạng nhưng không tồn tại (`LHP999`) -> `404 CLASS_NOT_FOUND` | `integration/test_tc01_to_tc22.py::test_tc04_tc05_tc08_tc09_class_full_closed_mismatch_and_not_found` | PostgreSQL 16.2 thật | **PASS** |
| **TC10** | Lỗi phát sinh sau khi `INSERT registrations` nhưng trước khi `UPDATE remaining_seats` -> rollback toàn bộ transaction, không lưu idempotency hỏng | `integration/test_tc01_to_tc22.py::test_tc10_tc11_rollback_on_mid_write_failure_and_replay_after_lost_response` | PostgreSQL 16.2 thật + `FaultHooks.after_registration_insert` | **PASS** |
| **TC11** | Mất kết nối sau khi `COMMIT` -> gửi lại cùng `Idempotency-Key` trả `200` kèm `Idempotent-Replayed: true`, giữ `request_id` gốc, không trừ 2 chỗ | `integration/test_tc01_to_tc22.py::test_tc10_tc11_rollback_on_mid_write_failure_and_replay_after_lost_response` & `concurrency/...::test_tc25_...` | PostgreSQL 16.2 thật | **PASS** |
| **TC12** | Sao lưu nóng `pg_dump` và khôi phục `pg_restore` sang DB độc lập -> bản restore khớp đúng snapshot trước sự cố và đạt mọi SQL invariants | `integration/test_tc01_to_tc22.py::test_tc12_pg_dump_and_pg_restore_snapshot_verification` | Binary **`pg_dump` & `pg_restore` PostgreSQL 16.2 thật** | **PASS** |
| **TC13** | Hủy đăng ký chưa thanh toán `DELETE /registrations/{id}` (kể cả khi lớp đã `CLOSED`) -> `CANCELLED`, `refund: null`, hoàn `+1` chỗ; replay cùng key trả `200` | `integration/test_tc01_to_tc22.py::test_tc13_tc14_tc17_cancel_replay_reregister_and_payment_refund` | PostgreSQL 16.2 thật | **PASS** |
| **TC14** | Đăng ký lại lớp đã từng hủy -> tạo dòng `ACTIVE` mới, giữ nguyên dòng `CANCELLED` cũ trong lịch sử (`?status=ALL`) | `integration/test_tc01_to_tc22.py::test_tc13_tc14_tc17_cancel_replay_reregister_and_payment_refund` | PostgreSQL 16.2 thật | **PASS** |
| **TC15** | Đăng ký lớp trùng thứ & giao tiết học với lớp `ACTIVE` hiện có -> `409 SCHEDULE_CONFLICT` kèm `errors[].code = CLASS_TIME_CONFLICT` | `integration/test_tc01_to_tc22.py::test_tc15_tc16_schedule_conflict_and_prerequisite_missing` | PostgreSQL 16.2 thật | **PASS** |
| **TC16** | Sinh viên chưa hoàn thành môn tiên quyết `CS101` đăng ký `LHP001` -> `409 PREREQUISITE_NOT_MET` kèm `errors[].code = PREREQUISITE_MISSING` | `integration/test_tc01_to_tc22.py::test_tc15_tc16_schedule_conflict_and_prerequisite_missing` | PostgreSQL 16.2 thật | **PASS** |
| **TC17** | Thanh toán mô phỏng `POST /payments` (`UNPAID -> PAID`), từ chối thanh toán trùng (`409 ALREADY_PAID`), hủy sau thanh toán hoàn tiền nguyên tử (`REFUNDED`) | `integration/test_tc01_to_tc22.py::test_tc13_tc14_tc17_cancel_replay_reregister_and_payment_refund` | PostgreSQL 16.2 thật | **PASS** |
| **TC18** | Quản trị `POST/PUT/PATCH /admin/course-classes`: RBAC (`403` cho SV), trùng `class_code` (`409`), giảm `capacity` dưới số đã đăng ký (`409`), khóa sửa cấu trúc khi đã có SV đăng ký (`409 CLASS_HAS_REGISTRATIONS`), bảo toàn snapshot học phí cũ | `integration/test_tc01_to_tc22.py::test_tc18_admin_crud_rbac_capacity_rules_and_snapshot_preservation` & `concurrency/...::test_concurrent_refresh_and_admin_...` | PostgreSQL 16.2 thật + 2 workers | **PASS** |
| **TC19** | Xoay vòng `POST /auth/refresh` một lần (cũ mất hiệu lực ngay), trần phiên tuyệt đối 8 giờ (`expires_in` co lại `1800s` ở mốc 7h30p), `logout` đúng thiết bị, đua 6 request refresh song song (`1` `200` + `5` `401`) | `integration/test_tc01_to_tc22.py::test_tc19_tc20_refresh_rotation_absolute_ttl_logout_and_idempotency_reuse` & `concurrency/...::test_concurrent_refresh_...` | PostgreSQL 16.2 thật + 2 workers | **PASS** |
| **TC20** | Canonical fingerprint: đổi thứ tự khóa JSON vẫn replay `200`; dùng lại `Idempotency-Key` cho lớp khác / endpoint khác -> `422 IDEMPOTENCY_KEY_REUSED`; cô lập phạm vi key giữa 2 sinh viên khác nhau | `integration/test_tc01_to_tc22.py::test_tc19_tc20_refresh_rotation_absolute_ttl_logout_and_idempotency_reuse` | PostgreSQL 16.2 thật | **PASS** |
| **TC21** | Hàng đợi Redis: join lặp không nhân bản, FIFO, giới hạn `READY`, hết hạn sang `EXPIRED` cấp chỗ kế tiếp, chống mượn token user khác, logout nhả lượt, replay không cần queue token, Redis sập -> fail-closed `503` | `integration/test_tc01_to_tc22.py::test_tc21_redis_queue_fifo_expiry_logout_replay_and_fail_closed` | PostgreSQL 16.2 thật + Lua script thật trên **`fakeredis[lua]`** *(chưa chạy daemon `redis-server` thật)* | **PASS (Logic/Lua)** / **NOT_RUN (Redis daemon)** |
| **TC22** | SSO OIDC + PKCE S256: `302` kèm `state`/`nonce`/`code_challenge` + cookie `dkhp_sso_bind`, xác minh chữ ký JWT `RS256` & claims, đổi `exchange_code` 60s đúng 1 lần, chống giả mạo cookie/nonce/unmapped user | `integration/test_tc01_to_tc22.py::test_tc22_oidc_sso_pkce_rsa_jwt_verification_and_one_time_exchange` | PostgreSQL 16.2 thật + RSA 2048 JWT thật *(giả lập bước HTTP tới Keycloak)* | **PASS (Giao thức/DB)** / **NOT_RUN (Keycloak container E2E)** |
| **TC23** | **Cùng 1 sinh viên đồng thời gửi 2 request đăng ký 2 lớp trùng lịch (`LHP001` & `LHP002`)** trên 2 worker -> đúng `1` `REGISTERED` và `1` `SCHEDULE_CONFLICT` | `concurrency/test_concurrency_and_multiworker.py::test_tc23_same_student_concurrently_registers_two_overlapping_classes` | **Server HTTP thật `uvicorn --workers 2`** + PostgreSQL 16.2 thật | **PASS** |
| **TC24** | **Đua đồng thời `POST /payments` và `DELETE /registrations/{id}`** qua 5 vòng lặp liên tiếp -> không bao giờ sinh trạng thái `CANCELLED + PAID` | `concurrency/test_concurrency_and_multiworker.py::test_tc24_concurrent_payment_and_cancellation_never_leaves_cancelled_paid` | **Server HTTP thật `uvicorn --workers 2`** + PostgreSQL 16.2 thật | **PASS** |
| **TC25** | **10 request đồng thời dùng chung một `Idempotency-Key`** xuyên 2 worker -> request đầu giữ khóa xử lý, các request chạm đang xử lý nhận `409 REQUEST_IN_PROGRESS` + `Retry-After`, các request đến sau `COMMIT` nhận `200` cùng `request_id` gốc | `concurrency/test_concurrency_and_multiworker.py::test_tc25_concurrent_same_key_in_progress_409_and_disconnect_after_commit` | **Server HTTP thật `uvicorn --workers 2`** + PostgreSQL 16.2 thật | **PASS** |

### Các bài kiểm thử bổ sung ngoài `TC01–TC25` (đều **PASS**)
- **Contract & OpenAPI (`tests/contract/test_http_contract_and_openapi.py` — 4 tests PASS)**: kiểm tra đủ 19 endpoint, không lọt `422` mặc định của FastAPI, CORS preflight `204` & allowlist, lỗi `415`, `400 INVALID_JSON`, từ chối trường thừa `UNKNOWN_FIELD`, chống ép kiểu ngầm (`true`/`3.5`/`"3"`), từ chối body trên `DELETE`, `404 ENDPOINT_NOT_FOUND`, `405 METHOD_NOT_ALLOWED` + `Allow`, kiểm tra query string chặt.
- **CLI, Seed 3.000 SV & Hồi quy `reset_lab.py` (`tests/integration/test_cli_scripts_and_invariants.py` — 5 tests PASS)**:
  - Seed đủ `3.001` tài khoản (`3.000` SV + `AD0001`), xuất `1.000` token cho k6, phát hiện sai lệch sĩ số bằng `check_invariants`.
  - Regression Redis thành công: chỉ xóa `dkhp:queue:*` & `dkhp:rl:*` (giữ nguyên key ngoài phạm vi, không `FLUSHALL`), đóng client đầy đủ.
  - Regression Redis lỗi khi `QUEUE_ENABLED=true`: báo chính xác `"reset chưa hoàn tất: PostgreSQL đã xử lý, Redis chưa xử lý"`, đóng client và trả mã thoát `3` (`!= 0`).
  - Regression `QUEUE_ENABLED=false`: không yêu cầu Redis chạy, ghi rõ `"phần Redis không được thực hiện"`, trả mã thoát `0`.
  - Chốt an toàn `verify_safe_test_database_url`: chặn tuyệt đối việc chạy pytest xóa dữ liệu nhầm vào DB `dev`, `demo`, `prod` hoặc trùng `DATABASE_URL`.
- **Unit Tests (`tests/unit/test_pure_units.py` — 8 tests PASS)**: Argon2id, opaque token hash, PKCE S256 RFC 7636, canonical fingerprint, advisory lock hash, escape `ILIKE`, đồng hồ UTC, redaction log nhạy cảm.

---

## 3. Bằng chứng Log Thực thi (Đã Che Thông tin Nhạy cảm)

### 3.1. Kết quả chạy Pytest toàn bộ (`exit code = 0`)
```text
platform win32 -- Python 3.11.9, pytest-8.4.2, pluggy-1.7.0
rootdir: D:\Code\Backend-DKHP\backend
configfile: pyproject.toml
collected 34 items

tests/concurrency/test_concurrency_and_multiworker.py::test_tc06_20_students_compete_for_last_1_seat_across_2_workers PASSED [  2%]
tests/concurrency/test_concurrency_and_multiworker.py::test_tc07_1_student_20_different_keys_concurrent_across_2_workers PASSED [  5%]
tests/concurrency/test_concurrency_and_multiworker.py::test_tc23_same_student_concurrently_registers_two_overlapping_classes PASSED [  8%]
tests/concurrency/test_concurrency_and_multiworker.py::test_tc24_concurrent_payment_and_cancellation_never_leaves_cancelled_paid PASSED [ 11%]
tests/concurrency/test_concurrency_and_multiworker.py::test_tc25_concurrent_same_key_in_progress_409_and_disconnect_after_commit PASSED [ 14%]
tests/concurrency/test_concurrency_and_multiworker.py::test_concurrent_refresh_and_admin_capacity_vs_register_across_2_workers PASSED [ 17%]
tests/contract/test_http_contract_and_openapi.py::test_openapi_schema_matches_all_19_v3_0_endpoints_and_no_stray_422 PASSED [ 20%]
tests/contract/test_http_contract_and_openapi.py::test_cors_allowlist_preflight_204_and_error_headers PASSED [ 23%]
tests/contract/test_http_contract_and_openapi.py::test_strict_media_type_invalid_json_extra_fields_and_type_coercion PASSED [ 26%]
tests/contract/test_http_contract_and_openapi.py::test_404_endpoint_not_found_405_allow_and_query_validation PASSED [ 29%]
tests/integration/test_cli_scripts_and_invariants.py::test_seed_3000_users_loadtest_reset_guards_and_invariant_checker PASSED [ 32%]
tests/integration/test_cli_scripts_and_invariants.py::test_reset_lab_redis_success_deletes_only_scoped_keys_and_closes_client PASSED [ 35%]
tests/integration/test_cli_scripts_and_invariants.py::test_reset_lab_redis_failure_when_required_reports_incomplete_closes_client_and_exits_nonzero PASSED [ 38%]
tests/integration/test_cli_scripts_and_invariants.py::test_reset_lab_queue_disabled_does_not_require_redis_and_logs_skipped PASSED [ 41%]
tests/integration/test_cli_scripts_and_invariants.py::test_external_test_db_safety_guard PASSED [ 44%]
tests/integration/test_tc01_to_tc22.py::test_tc01_login_success_and_invalid_credentials PASSED [ 47%]
...
tests/integration/test_tc01_to_tc22.py::test_tc22_oidc_sso_pkce_rsa_jwt_verification_and_one_time_exchange PASSED [ 76%]
tests/unit/test_pure_units.py::test_argon2id_password_hashing_and_no_trim PASSED [ 79%]
...
tests/unit/test_pure_units.py::test_log_redaction_strips_all_secrets PASSED [100%]

================== 34 passed, 1 warning in 68.80s (0:01:08) ===================
```

### 3.2. Kết quả Smoke Test HTTP thật & Đối soát `check_invariants` (`exit code = 0`)
```text
POSTGRES_VERSION: PostgreSQL 16.2 on x86_64-pc-mingw64, compiled by gcc.exe 12.2.0, 64-bit
CLI [scripts.migrate] exit=0 | [MIGRATE OK] Đã áp dụng 1 migration: 001_initial_schema.sql
CLI [scripts.seed --mode ui --student-count 50] exit=0 | [SEED OK] mode=ui | users_total=51 (new=51) | classes_total=3
SMOKE 1 [GET /health]: 200 HEALTHY {'status': 'UP', 'database': 'UP', 'api_version': '1.0.0', 'features': {'payments': True, 'sso': False, 'queue': False}}
SMOKE 2 [OPTIONS /register CORS]: 204 No Content
SMOKE 3 [POST /auth/login]: 200 LOGIN_SUCCESS (tokens redacted)
SMOKE 4 [GET /course-classes & /course-classes/LHP001]: 200 (3 classes, LHP001 seats=50)
SMOKE 5 [POST /register + Replay + 422 Reuse]: 200 -> 200 (Idempotent-Replayed=true) -> 422
SMOKE 6 [Domain & RBAC errors]: 409 SCHEDULE_CONFLICT, 409 PREREQUISITE_NOT_MET, 403 FORBIDDEN
SMOKE 7 [Registrations/me -> Payment -> Cancel+Refund -> History]: seats=50, status=CANCELLED, payment_status=REFUNDED
SMOKE 8 [Refresh & Logout]: 200 TOKEN_REFRESHED -> 200 LOGGED_OUT -> 401 UNAUTHORIZED
CLI [scripts.check_invariants] exit=0 | "ok": true (0 violations across all 5 SQL invariant checks)
SMOKE 9 [External TEST_DATABASE_URL pytest]: exit= 0
SMOKE 10 [External DB non-destruction check]: live dev DB still alive and untouched!
```

---

## 4. Danh mục Chưa Chạy Thực tế (`NOT_RUN`), Nguyên nhân & Lệnh Chạy Tiếp Theo

Các hạng mục dưới đây **chưa được thực thi trên máy phát triển hiện tại** vì máy chưa cài Docker Desktop, `redis-server`, Keycloak và `k6`. Tuyệt đối không ghi `PASS` cho các phần tích hợp hạ tầng ngoài chưa chạy:

### 4.1. Kiểm chứng Hàng đợi trên tiến trình `redis:7.4.1-alpine3.20` thật (`NOT_RUN`)
- **Nguyên nhân**: Không có `docker` hoặc `redis-server` trên máy Windows hiện tại (logic Lua script đã PASS trên `fakeredis[lua]`).
- **Lệnh chạy ngay khi có Docker Desktop**:
  ```powershell
  $env:QUEUE_ENABLED = "true"
  docker compose -f compose.dev.yml --profile queue up -d --build
  docker compose -f compose.dev.yml exec api python -m scripts.seed --mode ui
  # Kiểm tra /api/v1/health (features.queue = true), /api/v1/queue/join, /api/v1/queue/status và dừng container redis để xác nhận trả 503
  ```

### 4.2. Kiểm chứng E2E SSO với container `quay.io/keycloak/keycloak:26.0.5` thật (`NOT_RUN`)
- **Nguyên nhân**: Không có `docker` / Keycloak server đang chạy trên máy hiện tại (bước trao đổi HTTP tới IdP trong `test_tc22` dùng hàm callback nội bộ kèm chữ ký RSA/JWKS 2048-bit thật, chưa đi qua trình duyệt + container Keycloak thật).
- **Lệnh chạy ngay khi có Docker Desktop**:
  ```powershell
  $env:SSO_ENABLED = "true"
  docker compose -f compose.dev.yml --profile sso up -d --build
  docker compose -f compose.dev.yml exec api python -m scripts.seed --mode ui
  # Mở trình duyệt vào http://localhost:8080/api/v1/auth/sso/login -> đăng nhập sv0001 / Demo@123456 -> nhận exchange_code -> POST /api/v1/auth/sso/exchange
  ```

### 4.3. Đo tải 9 lượt bằng `k6` (10 / 50 / 100 VU × 3 lần) & Ghép Giao diện TV3 (`NOT_RUN`)
- **Nguyên nhân**: Công cụ `k6`, giao diện của TV3 và lớp Nginx của TV1 thuộc phạm vi phối hợp 3 thành viên.
- **Lệnh chuẩn bị & đối soát dành cho buổi đo chung**: xem mục 6 trong `docs/handoff_tv3.md` (`reset_lab --confirm-lab-reset --reseed loadtest`, `prepare_tokens --count 1000`, `check_invariants`).

