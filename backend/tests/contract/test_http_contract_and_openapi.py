"""Contract tests for HTTP framing, OpenAPI v3.0 schema, CORS, headers, and strict validation."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_headers, login_and_get_tokens

pytestmark = pytest.mark.contract

EXPECTED_19_ENDPOINTS: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/sso/login"),
    ("GET", "/api/v1/auth/sso/callback"),
    ("POST", "/api/v1/auth/sso/exchange"),
    ("GET", "/api/v1/course-classes"),
    ("GET", "/api/v1/course-classes/{course_class_id}"),
    ("POST", "/api/v1/register"),
    ("DELETE", "/api/v1/registrations/{registration_id}"),
    ("GET", "/api/v1/registrations/me"),
    ("POST", "/api/v1/payments"),
    ("GET", "/api/v1/payments/me"),
    ("POST", "/api/v1/admin/course-classes"),
    ("PUT", "/api/v1/admin/course-classes/{course_class_id}"),
    ("PATCH", "/api/v1/admin/course-classes/{course_class_id}/status"),
    ("POST", "/api/v1/queue/join"),
    ("GET", "/api/v1/queue/status"),
    ("GET", "/api/v1/health"),
}


def test_openapi_schema_matches_all_19_v3_0_endpoints_and_no_stray_422(
    client: TestClient,
) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.1.")
    assert spec["info"]["title"] == "Hệ thống Đăng ký Học phần Trực tuyến"
    assert spec["info"]["description"] == (
        "API hỗ trợ đăng nhập, tra cứu lớp học phần, đăng ký và hủy đăng ký học phần. "
        "Tài liệu cung cấp thông tin đầu vào, kết quả trả về và cách xác thực cho từng chức năng."
    )
    assert spec["info"]["version"] == "1.0.0"
    assert spec["info"]["x-spec-version"] == "3.0"

    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    assert "text/html" in docs_resp.headers["content-type"]
    assert "<title>Hệ thống Đăng ký Học phần Trực tuyến - Swagger UI</title>" in docs_resp.text
    assert ".swagger-ui .info .title small:not(.version-stamp) { display: none; }" in docs_resp.text
    assert "url: '/openapi.json'" in docs_resp.text
    assert "/docs/oauth2-redirect" in docs_resp.text

    oauth_redir_resp = client.get("/docs/oauth2-redirect")
    assert oauth_redir_resp.status_code == 200

    schemas = spec.get("components", {}).get("schemas", {})
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    assert "BearerAuth" in spec["components"]["securitySchemes"]

    discovered: set[tuple[str, str]] = set()
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                discovered.add((method.upper(), path))
                responses = op.get("responses", {})
                if path not in {
                    "/api/v1/register",
                    "/api/v1/registrations/{registration_id}",
                    "/api/v1/payments",
                } or method.upper() == "GET":
                    assert "422" not in responses, f"Unexpected 422 in {method} {path}"

    assert discovered == EXPECTED_19_ENDPOINTS


def test_cors_allowlist_preflight_204_and_error_headers(client: TestClient) -> None:
    # 1. Valid preflight OPTIONS runs BEFORE Bearer auth and returns 204 without body
    pre = client.options(
        "/api/v1/register",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type, Idempotency-Key, X-Queue-Token",
        },
    )
    assert pre.status_code == 204
    assert pre.content == b""
    assert pre.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Idempotency-Key" in pre.headers["Access-Control-Allow-Headers"]
    assert "Idempotent-Replayed" in pre.headers["Access-Control-Expose-Headers"]
    assert "Origin" in pre.headers["Vary"]
    assert "Access-Control-Allow-Credentials" not in pre.headers

    # 2. Disallowed origin must NEVER be reflected
    bad_origin = client.get(
        "/api/v1/health",
        headers={"Origin": "http://evil.attacker.example"},
    )
    assert bad_origin.status_code == 200
    assert "Access-Control-Allow-Origin" not in bad_origin.headers
    assert "Origin" in bad_origin.headers["Vary"]

    # 3. Error responses (e.g. 401 UNAUTHORIZED) STILL carry CORS headers for allowed origin
    err_resp = client.get(
        "/api/v1/course-classes",
        headers={"Origin": "http://localhost:5173"},
    )
    assert err_resp.status_code == 401
    assert err_resp.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert err_resp.headers["WWW-Authenticate"] == "Bearer"
    assert err_resp.headers["Cache-Control"] == "no-store"
    body = err_resp.json()
    assert err_resp.headers["X-Request-ID"] == body["request_id"]
    assert body["code"] == "UNAUTHORIZED"


def test_strict_media_type_invalid_json_extra_fields_and_type_coercion(
    client: TestClient,
) -> None:
    tokens = login_and_get_tokens(client, "SV0001")
    admin_tokens = login_and_get_tokens(client, "AD0001")

    # 1. Wrong Content-Type -> 415 UNSUPPORTED_MEDIA_TYPE
    r_415 = client.post(
        "/api/v1/auth/login",
        content="student_id=SV0001",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r_415.status_code == 415
    assert r_415.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"

    # 2. Malformed JSON -> 400 INVALID_JSON
    r_bad_json = client.post(
        "/api/v1/auth/login",
        content=b'{"student_id": "SV0001", ',
        headers={"Content-Type": "application/json"},
    )
    assert r_bad_json.status_code == 400
    assert r_bad_json.json()["code"] == "INVALID_JSON"

    # 3. Extra field rejected -> 400 VALIDATION_ERROR with UNKNOWN_FIELD
    r_extra = client.post(
        "/api/v1/register",
        headers=auth_headers(tokens["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP001", "extra_field": 123},
    )
    assert r_extra.status_code == 400
    b_extra = r_extra.json()
    assert b_extra["code"] == "VALIDATION_ERROR"
    assert any(e["code"] == "UNKNOWN_FIELD" and e["field"] == "extra_field" for e in b_extra["errors"])

    # 4. Strict integer validation: boolean `true` or float `3.5` or string `"3"` NOT coerced to int!
    for bad_credits in (True, 3.5, "3"):
        r_coercion = client.post(
            "/api/v1/admin/course-classes",
            headers=auth_headers(admin_tokens["access_token"]),
            json={
                "class_code": "STRICT-01",
                "course_code": "CNNT",
                "course_name": "Kiểm tra kiểu chặt",
                "credits": bad_credits,
                "capacity": 30,
                "status": "OPEN",
                "schedule": [],
                "prerequisite_course_codes": [],
            },
        )
        assert r_coercion.status_code == 400, f"Failed to reject credits={bad_credits!r}"
        assert r_coercion.json()["code"] == "VALIDATION_ERROR"

    # 5. DELETE with non-empty body rejected -> 400 VALIDATION_ERROR
    r_del_body = client.request(
        "DELETE",
        f"/api/v1/registrations/{uuid.uuid4()}",
        headers=auth_headers(
            tokens["access_token"],
            **{"Idempotency-Key": str(uuid.uuid4()), "Content-Type": "application/json"},
        ),
        content=b'{"unexpected": true}',
    )
    assert r_del_body.status_code == 400
    assert r_del_body.json()["code"] == "VALIDATION_ERROR"


def test_404_endpoint_not_found_405_allow_and_query_validation(client: TestClient) -> None:
    tokens = login_and_get_tokens(client, "SV0001")

    # Unknown URL -> 404 ENDPOINT_NOT_FOUND
    r_404 = client.get("/api/v1/does-not-exist")
    assert r_404.status_code == 404
    assert r_404.json()["code"] == "ENDPOINT_NOT_FOUND"

    # Wrong method -> 405 METHOD_NOT_ALLOWED + Allow header
    r_405 = client.get("/api/v1/auth/login")
    assert r_405.status_code == 405
    assert r_405.json()["code"] == "METHOD_NOT_ALLOWED"
    assert "POST" in r_405.headers.get("Allow", "")

    # Unknown query param on business API -> 400 VALIDATION_ERROR
    r_uk_q = client.get(
        "/api/v1/registrations/me?student_id=SV0002",
        headers=auth_headers(tokens["access_token"]),
    )
    assert r_uk_q.status_code == 400
    assert r_uk_q.json()["code"] == "VALIDATION_ERROR"
    assert any(e["field"] == "student_id" and e["code"] == "UNKNOWN_FIELD" for e in r_uk_q.json()["errors"])

    # Valid string query `?page=1&page_size=10` works; `?page=0` -> OUT_OF_RANGE; `?page=1.5` -> INVALID_FORMAT
    r_ok_q = client.get(
        "/api/v1/course-classes?page=1&page_size=10",
        headers=auth_headers(tokens["access_token"]),
    )
    assert r_ok_q.status_code == 200

    r_range_q = client.get(
        "/api/v1/course-classes?page=0",
        headers=auth_headers(tokens["access_token"]),
    )
    assert r_range_q.status_code == 400
    assert r_range_q.json()["errors"][0]["code"] == "OUT_OF_RANGE"

    r_fmt_q = client.get(
        "/api/v1/course-classes?page=1.5",
        headers=auth_headers(tokens["access_token"]),
    )
    assert r_fmt_q.status_code == 400
    assert r_fmt_q.json()["errors"][0]["code"] == "INVALID_FORMAT"
