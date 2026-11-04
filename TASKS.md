# Kế hoạch & Tiến độ Triển khai Phần TV2 (Backend & CSDL)

> Đề tài 08: Thiết kế hệ thống đăng ký học phần trực tuyến (3.000 sinh viên)
> Hợp đồng đối chiếu: Đặc tả API Hoàn chỉnh TV2–TV3 v3.0 (`docs/api_spec_v3_0.md`)

## Giai đoạn 1 — Nền tảng (Foundation)
- [x] Đọc toàn bộ đặc tả API v3.0 (Mục 01–25) và yêu cầu triển khai TV2
- [x] Lưu bản đặc tả chuẩn vào `docs/api_spec_v3_0.md`
- [x] Lập ma trận hợp đồng 19 endpoint tại `docs/contract_matrix.md`
- [x] Ghi nhận quyết định triển khai & điểm đồng bộ TV1/TV3 tại `docs/implementation_decisions.md`
- [x] Khởi tạo cấu trúc `backend/`, `pyproject.toml`, `requirements.lock`, `.env.example`, `Dockerfile`, `compose.dev.yml`
- [x] Thiết kế lược đồ PostgreSQL 16 + hệ thống migration có version, checksum và advisory lock (`backend/migrations/001_initial_schema.sql`)
- [x] Triển khai cấu hình (`config.py`), connection pool (`psycopg_pool`), envelope chuẩn, xử lý lỗi tập trung, CORS allowlist, structured logging có redaction, và `GET /api/v1/health`
- [x] Triển khai & kiểm chứng CLI `migrate`, `seed` (UI & load test 3.000 SV), `prepare_tokens`, `reset_lab` (xử lý tách bạch lỗi Redis/PostgreSQL), `check_invariants`

## Giai đoạn 2 — Đăng ký cốt lõi (Đợt A0 + Idempotency nền tảng)
- [x] Xác thực Argon2id & opaque token hash (`POST /api/v1/auth/login`, Bearer dependency, RBAC)
- [x] Danh sách & chi tiết lớp học phần (`GET /api/v1/course-classes`, `GET /api/v1/course-classes/{course_class_id}`) không bị N+1, snapshot nhất quán
- [x] Cơ chế Idempotency-Key xuyên worker bằng PostgreSQL transaction + `pg_advisory_xact_lock` + canonical fingerprint + `SAVEPOINT`
- [x] Đăng ký học phần nguyên tử (`POST /api/v1/register`) với thứ tự khóa `user -> course_class`
- [x] Danh sách đăng ký bản thân (`GET /api/v1/registrations/me`)
- [x] Kiểm thử cốt lõi TC01–TC12 và concurrency tranh chỗ cuối trên PostgreSQL 16.2 thật + Uvicorn 2 workers thật

## Giai đoạn 3 — Nghiệp vụ mở rộng (Đợt A & Đợt B)
- [x] Kiểm tra tiên quyết (`PREREQUISITE_NOT_MET`) và trùng lịch (`SCHEDULE_CONFLICT`) kèm `errors[]` chi tiết
- [x] Hủy đăng ký & hoàn tiền mô phỏng (`DELETE /api/v1/registrations/{registration_id}`) và đăng ký lại giữ nguyên lịch sử
- [x] Thanh toán mô phỏng & lịch sử thanh toán (`POST /api/v1/payments`, `GET /api/v1/payments/me`)
- [x] Quản trị lớp học phần (`POST /api/v1/admin/course-classes`, `PUT /api/v1/admin/course-classes/{course_class_id}`, `PATCH /api/v1/admin/course-classes/{course_class_id}/status`)
- [x] Xoay vòng refresh token nguyên tử & thu hồi phiên (`POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`)
- [x] Kiểm thử mở rộng TC13–TC20, TC23–TC25 (race thanh toán/hủy, trùng lịch đồng thời, replay sau ngắt kết nối) trên 2 workers thật

## Giai đoạn 4 — Điều tiết hàng đợi & SSO (Đợt C)
- [x] Hàng đợi Redis nguyên tử bằng Lua script (`POST /api/v1/queue/join`, `GET /api/v1/queue/status`, kiểm tra `X-Queue-Token` ở `/register`, giải phóng lượt khi logout/hết hạn, fail-closed `503`)
- [x] SSO Keycloak OIDC Authorization Code + PKCE S256 + state/nonce + browser-binding cookie tạm (`dkhp_sso_bind`) + `exchange_code` 60s dùng một lần (`GET /api/v1/auth/sso/login`, `GET /api/v1/auth/sso/callback`, `POST /api/v1/auth/sso/exchange`)
- [x] Cấu hình Keycloak realm import (`infra/keycloak/dkhp-realm.json`) cho `compose.dev.yml` (profile `sso`, `queue`, `full`)
- [x] Kiểm thử tự động logic Lua Queue (TC21 qua `fakeredis[lua]`) và giao thức OIDC/PKCE/RSA-JWKS (TC22)
- [ ] Kiểm chứng E2E với container `redis:7.4.1-alpine3.20` thật và `quay.io/keycloak/keycloak:26.0.5` thật *(NOT_RUN trên máy hiện tại do chưa cài Docker Desktop; đã sẵn sàng cấu hình & lệnh chạy)*

## Giai đoạn 5 — Kiểm chứng, Ví dụ API & Tài liệu Bàn giao
- [x] Chạy toàn bộ bộ kiểm thử tự động (`ruff` PASS, `pytest` 34/34 PASS), smoke test HTTP thật và kiểm tra invariants SQL
- [x] Xuất OpenAPI schema & bộ JSON fixtures hợp lệ từ phiên bản code cuối tại `docs/api_examples/`
- [x] Hoàn thiện `README.md` (hướng dẫn Windows PowerShell từng bước, `TEST_DATABASE_URL` & hành vi mới của `reset_lab`)
- [x] Hoàn thiện `docs/database_design.md` và `docs/concurrency_design.md` (kèm sơ đồ Mermaid & 10 câu hỏi bảo vệ)
- [x] Hoàn thiện `docs/handoff_tv3.md`, `docs/handoff_tv1.md`, `docs/test_results.md`, `docs/progress.md` và `docs/bao_cao_tv2.md`
- [ ] Phối hợp cùng TV1 + TV3 chạy 9 lượt đo tải `k6` (10 / 50 / 100 VU × 3 lần) và điền bảng số đo thực tế vào báo cáo nhóm *(chờ ghép tích hợp nhóm)*
