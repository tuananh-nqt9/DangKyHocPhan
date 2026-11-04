"""Pytest fixtures backed by a REAL PostgreSQL 16 instance (`pgserver` or verified `TEST_DATABASE_URL`) and Lua-enabled Redis."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import fakeredis
import psycopg
import pytest
from app.core.clock import Clock
from app.core.config import Settings
from app.db.migrations import run_migrations
from app.main import create_app
from app.services.idempotency_service import FaultHooks
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from scripts.check_invariants import run_invariant_checks
from scripts.seed import LAB_DEMO_PASSWORD, seed_database

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_PGDATA = REPO_ROOT / ".pgdata" / "pytest_pg16"


def _normalize_pg_identity(url: str) -> tuple[str, int, str]:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "localhost").lower()
    if host == "127.0.0.1":
        host = "localhost"
    port = int(parsed.port or 5432)
    db_name = (parsed.path or "").lstrip("/").lower()
    return (host, port, db_name)


def verify_safe_test_database_url(test_url: str, active_dev_url: str | None = None) -> None:
    """Strictly verify an external PostgreSQL URL points to an isolated test DB before destructive ops."""
    parsed = urlparse(test_url.strip())
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError(f"TEST_DATABASE_URL không phải kết nối PostgreSQL hợp lệ: {test_url!r}")

    db_name = (parsed.path or "").lstrip("/").lower()
    if not db_name:
        raise RuntimeError("TEST_DATABASE_URL thiếu tên database kiểm thử.")

    forbidden_tokens = ("prod", "production", "demo", "live", "staging")
    for bad in forbidden_tokens:
        if bad in db_name:
            raise RuntimeError(
                f"Từ chối dùng database '{db_name}' cho pytest vì chứa từ khóa bảo vệ '{bad}'!"
            )

    if "test" not in db_name and "pytest" not in db_name:
        raise RuntimeError(
            f"Từ chối xóa dữ liệu trên database ngoài '{db_name}': tên DB kiểm thử bắt buộc chứa 'test' hoặc 'pytest' (ví dụ 'dkhp_test')."
        )

    if (
        active_dev_url
        and active_dev_url.strip()
        and _normalize_pg_identity(test_url) == _normalize_pg_identity(active_dev_url)
    ):
        raise RuntimeError(
            "Từ chối chạy pytest: TEST_DATABASE_URL trùng với DATABASE_URL đang phục vụ ứng dụng!"
        )


def _derive_admin_uri(db_url: str) -> str:
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(path="/postgres"))


@dataclass
class PgTestBackend:
    test_db_url: str
    admin_uri: str
    owned_server: Any | None = None


def _start_owned_pgserver() -> PgTestBackend:
    import pgserver

    if PYTEST_PGDATA.exists():
        shutil.rmtree(PYTEST_PGDATA, ignore_errors=True)
    PYTEST_PGDATA.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(PYTEST_PGDATA)
    admin_uri = str(server.get_uri())

    with psycopg.connect(admin_uri, autocommit=True) as conn:
        conn.execute('DROP DATABASE IF EXISTS "dkhp_pytest"')
        conn.execute('CREATE DATABASE "dkhp_pytest"')

    test_uri = str(server.get_uri(database="dkhp_pytest"))
    return PgTestBackend(test_db_url=test_uri, admin_uri=admin_uri, owned_server=server)


def _connect_external_test_db(ext_url: str) -> PgTestBackend:
    verify_safe_test_database_url(ext_url, os.environ.get("DATABASE_URL"))
    admin_uri = _derive_admin_uri(ext_url)
    target_db = (urlparse(ext_url).path or "").lstrip("/")

    # Ensure target test database exists without stopping or dropping external server resources
    try:
        with psycopg.connect(ext_url, autocommit=True) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        with psycopg.connect(admin_uri, autocommit=True) as adm:
            exists = adm.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (target_db,)
            ).fetchone()
            if not exists:
                adm.execute(f'CREATE DATABASE "{target_db}"')

    return PgTestBackend(test_db_url=ext_url, admin_uri=admin_uri, owned_server=None)


@pytest.fixture(scope="session")
def pg_backend() -> Iterator[PgTestBackend]:
    """Provide real PostgreSQL 16 test DB via `pgserver` or verified external `TEST_DATABASE_URL`.

    Only cleans up resources owned by this fixture; never stops/drops an external PostgreSQL server.
    """
    force_external = os.environ.get("PYTEST_USE_EXTERNAL_DB", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    explicit_test_url = os.environ.get("TEST_DATABASE_URL", "").strip()

    backend: PgTestBackend
    if force_external:
        if not explicit_test_url:
            raise RuntimeError(
                "PYTEST_USE_EXTERNAL_DB=true nhưng chưa cấu hình biến môi trường TEST_DATABASE_URL."
            )
        backend = _connect_external_test_db(explicit_test_url)
    else:
        try:
            backend = _start_owned_pgserver()
        except Exception as pgserver_exc:
            if explicit_test_url:
                backend = _connect_external_test_db(explicit_test_url)
            else:
                raise RuntimeError(
                    f"Không thể khởi tạo pgserver ({pgserver_exc}) và không có TEST_DATABASE_URL dự phòng."
                ) from pgserver_exc

    run_migrations(backend.test_db_url)
    seed_database(
        backend.test_db_url,
        mode="ui",
        student_count=30,
        tuition_per_credit=500000,
        oidc_issuer="http://localhost:8081/realms/dkhp",
        distinct_salts=False,
    )
    try:
        yield backend
    finally:
        if backend.owned_server is not None:
            backend.owned_server.cleanup()
            shutil.rmtree(PYTEST_PGDATA, ignore_errors=True)


@pytest.fixture(scope="session")
def pg_admin_uri(pg_backend: PgTestBackend) -> str:
    return pg_backend.admin_uri


@pytest.fixture(scope="session")
def test_db_url(pg_backend: PgTestBackend) -> str:
    return pg_backend.test_db_url


@pytest.fixture(autouse=True)
def reset_hooks_and_clock() -> Iterator[None]:
    FaultHooks.reset()
    Clock._provider = None
    yield
    FaultHooks.reset()
    Clock._provider = None


@pytest.fixture()
def clean_db(test_db_url: str) -> Iterator[str]:
    """Reset mutable tables in the dedicated test DB and restore canonical UI seed before each test."""
    verify_safe_test_database_url(test_db_url, os.environ.get("DATABASE_URL"))
    with psycopg.connect(test_db_url, row_factory=dict_row, autocommit=False) as conn:
        with conn.transaction():
            conn.execute("DELETE FROM payments")
            conn.execute("DELETE FROM registrations")
            conn.execute("DELETE FROM idempotency_records")
            conn.execute("DELETE FROM sso_exchange_codes")
            conn.execute("DELETE FROM sso_transactions")
            conn.execute("DELETE FROM sessions")
            conn.execute(
                "DELETE FROM course_classes WHERE course_class_id NOT IN ('LHP001', 'LHP002', 'LHP003')"
            )

    seed_database(
        test_db_url,
        mode="ui",
        student_count=30,
        tuition_per_credit=500000,
        oidc_issuer="http://localhost:8081/realms/dkhp",
        distinct_salts=False,
    )
    yield test_db_url

    # Automatically assert all cross-table SQL invariants hold on a fresh connection at the end of EVERY test!
    inv = run_invariant_checks(test_db_url)
    assert inv["ok"], f"SQL Invariant violation detected after test: {inv}"


def make_test_settings(test_db_url: str, **overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "app_env": "test",
        "database_url": test_db_url,
        "test_database_url": test_db_url,
        "db_pool_min_size": 2,
        "db_pool_max_size": 12,
        "db_pool_timeout_seconds": 5.0,
        "db_lock_timeout_ms": 2500,
        "db_idempotency_lock_timeout_ms": 400,
        "db_statement_timeout_ms": 5000,
        "cors_allowed_origins": "http://localhost:5173,http://127.0.0.1:5173",
        "frontend_origin": "http://localhost:5173",
        "payments_enabled": True,
        "sso_enabled": False,
        "queue_enabled": False,
        "rate_limit_backend": "none",
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture()
def lua_redis() -> Iterator[Any]:
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture()
def client(clean_db: str) -> Iterator[TestClient]:
    settings = make_test_settings(clean_db)
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def login_and_get_tokens(tc: TestClient, student_id: str = "SV0001") -> dict[str, Any]:
    resp = tc.post(
        "/api/v1/auth/login",
        json={"student_id": student_id, "password": LAB_DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "LOGIN_SUCCESS"
    return dict(body["data"])


def auth_headers(access_token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    headers.update(extra)
    return headers
