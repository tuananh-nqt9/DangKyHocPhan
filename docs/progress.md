# Nhật ký Tiến độ Kỹ thuật — Phần Thành viên 2 (`progress.md`)

Cập nhật lần cuối: `2026-11-03 19:31 (UTC+07:00)`

---

## 1. Các Hạng mục Đã Hoàn thành & Kiểm chứng (`DONE`)

1. **Nền tảng kiến trúc, cấu hình & Docker Compose**:
   - Hoàn thiện cấu trúc `backend/app/` (`core`, `db`, `schemas`, `repositories`, `services`, `api/routers`), `backend/Dockerfile`, `backend/pyproject.toml`, `backend/requirements.lock`, `backend/.env.example`, `compose.dev.yml` và `infra/keycloak/dkhp-realm.json`.
   - Đạt `ruff check app scripts tests` với **0 lỗi** (`exit code 0`).
2. **Lược đồ Cơ sở Dữ liệu PostgreSQL 16 & Công cụ CLI**:
   - Hoàn thiện `backend/migrations/001_initial_schema.sql` với đầy đủ khóa ngoại, `CHECK` constraints, `partial unique index uq_registrations_active_user_class`, `course_class_id_seq`, bảng `idempotency_records`, `sessions`, `payments`, `sso_*`.
   - Hoàn thiện và kiểm chứng thực tế các CLI: `scripts.migrate`, `scripts.seed` (`--mode ui` & `--mode loadtest` 3.000 sinh viên), `scripts.prepare_tokens`, `scripts.reset_lab`, `scripts.check_invariants`, `scripts.local_pg`, `scripts.export_openapi_and_examples`, cùng truy vấn SQL độc lập `backend/scripts/sql/check_invariants.sql`.
3. **Triển khai đầy đủ 19/19 Endpoint theo Đặc tả API v3.0**:
   - Đợt A0 & A: `/health`, `/auth/login`, `/course-classes`, `/course-classes/{id}`, `/register` (nguyên tử + `Idempotency-Key` xuyên worker + kiểm tra tiên quyết & trùng lịch), `/registrations/{id}` (`DELETE`), `/registrations/me`.
   - Đợt B: `/auth/refresh` (xoay vòng nguyên tử + trần 8 giờ), `/auth/logout`, `/payments` & `/payments/me` (mô phỏng nội bộ), `/admin/course-classes` (`POST`, `PUT`, `PATCH .../status`).
   - Đợt C: `/queue/join` & `/queue/status` (Lua script nguyên tử trên Redis, fail-closed `503`), `/auth/sso/login`, `/auth/sso/callback`, `/auth/sso/exchange` (OIDC + PKCE S256 + cookie ràng buộc trình duyệt `dkhp_sso_bind` + `exchange_code` 60s một lần).
4. **Sửa triệt để các lỗi phát hiện trong quá trình kiểm chứng**:
   - **`backend/scripts/reset_lab.py`**: Loại bỏ hoàn toàn `except RedisError: pass`; bổ sung `ResetLabResult`, `IncompleteLabResetError`, cờ `--reset-redis` và `--redis-url`. Báo rõ từng thành phần (`PostgreSQL đã xử lý, Redis chưa xử lý` với exit code `3` khi Redis lỗi lúc đang cần; bỏ qua không cần Redis khi `QUEUE_ENABLED=false`; chỉ xóa key `dkhp:queue:*` & `dkhp:rl:*`, không `FLUSHALL`; luôn đóng Redis client trong `finally`).
   - **`backend/app/services/queue_service.py`**: Thay `PEXPIREAT` bằng `PEXPIRE` (TTL tương đối) để không bị lệch đồng hồ giữa App và Redis hoặc khi dịch chuyển đồng hồ kiểm thử.
   - **`backend/app/db/pool.py`, `migrations.py`, `scripts/*.py`**: Chuẩn hóa `SET LOCAL timezone = 'GMT'` tương thích trên cả PostgreSQL Linux Alpine lẫn bản tối giản MinGW (`pgserver`).
   - **`backend/tests/conftest.py` & `tests/concurrency/test_concurrency_and_multiworker.py`**: Bổ sung chế độ `PYTEST_USE_EXTERNAL_DB=true` + `verify_safe_test_database_url` (cấm chạm DB `dev`/`demo`/`prod` và không tắt PostgreSQL ngoài); cấu hình `--basetemp=.pytest_tmp`; chuyển log Uvicorn 2 worker ra tệp tạm tránh nghẽn pipe `stderr` trên Windows.
   - **`backend/app/main.py`**: Đổi khóa log HTTP sang `response_code` để không bị bộ che khóa OIDC `code` ẩn mất mã kết quả nghiệp vụ.
5. **Kiểm thử tự động, Smoke Test HTTP thật & Tài liệu bàn giao**:
   - Đạt **34/34 bài kiểm thử pytest PASS** (`0 FAIL`, `0 ERROR`, `0 SKIPPED`) trên PostgreSQL 16.2 thật và server HTTP `uvicorn --workers 2` thật.
   - Xuất mới bộ `docs/api_examples/openapi_v3_0.json` và 8 tệp JSON mẫu từ phiên bản code cuối.
   - Hoàn thiện đầy đủ toàn bộ tài liệu trong `docs/` (`api_spec_v3_0.md`, `contract_matrix.md`, `implementation_decisions.md`, `database_design.md`, `concurrency_design.md`, `handoff_tv3.md`, `handoff_tv1.md`, `test_results.md`, `progress.md`, `bao_cao_tv2.md`), `README.md` và `TASKS.md`.

---

## 2. Công việc Đang Chờ Phối hợp Nhóm / Hạ tầng Ngoài (`NOT_RUN`)

- **Kiểm chứng E2E container Redis 7.4 thật & Keycloak 26.0.5 thật**: Chờ chạy `docker compose -f compose.dev.yml --profile full up -d --build` trên máy có Docker Desktop (do máy Windows hiện tại không cài Docker/`redis-server`).
- **Ghép nối giao diện Frontend với TV3 và Nginx/Monitoring với TV1**.
- **Thực hiện 9 lượt đo tải `k6` (10 / 50 / 100 VU × 3 lần lặp)** và điền số đo thực tế vào bảng trong `docs/bao_cao_tv2.md`.

---

## 3. Hướng dẫn Tiếp tục Nhanh (Nếu Mở Lại Phiên Sau)

1. Kiểm tra lại toàn bộ bài test backend bất kỳ lúc nào:
   ```powershell
   Set-Location "d:\Code\Backend-DKHP\backend"
   & "..\.venv\Scripts\ruff.exe" check app scripts tests
   & "..\.venv\Scripts\pytest.exe" -v
   ```
2. Khi sang máy có Docker để kiểm chứng nốt Redis & Keycloak container thật:
   ```powershell
   Set-Location "d:\Code\Backend-DKHP"
   Copy-Item "backend\.env.example" ".env"
   $env:QUEUE_ENABLED="true"; $env:SSO_ENABLED="true"
   docker compose -f compose.dev.yml --profile full up -d --build
   docker compose -f compose.dev.yml exec api python -m scripts.seed --mode ui
   ```

