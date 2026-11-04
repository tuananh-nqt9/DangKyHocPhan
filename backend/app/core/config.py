"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for Backend-DKHP (Spec v3.0)."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application & HTTP Server
    app_env: Literal["dev", "test", "lab", "prod"] = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8080, ge=1, le=65535)
    api_workers: int = Field(default=2, ge=1, le=32)
    api_version: str = "1.0.0"
    spec_version: str = "3.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # PostgreSQL 16 Pool & Timeouts
    database_url: str = "postgresql://dkhp_user:dkhp_dev_pass@localhost:5432/dkhp_dev"
    test_database_url: str = "postgresql://dkhp_user:dkhp_dev_pass@localhost:5432/dkhp_test"
    db_pool_min_size: int = Field(default=2, ge=1, le=50)
    db_pool_max_size: int = Field(default=10, ge=1, le=50)
    db_pool_timeout_seconds: float = Field(default=3.0, gt=0.1, le=30.0)
    db_lock_timeout_ms: int = Field(default=2000, ge=50, le=30000)
    db_idempotency_lock_timeout_ms: int = Field(default=1500, ge=50, le=30000)
    db_statement_timeout_ms: int = Field(default=5000, ge=100, le=60000)

    # Auth & Session TTLs
    access_token_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    session_absolute_ttl_seconds: int = Field(default=28800, ge=60, le=604800)

    # CORS & Frontend Origins
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_origin: str = "http://localhost:5173"
    public_api_base_URL: str = Field(
        default="http://localhost:8080/api/v1", alias="PUBLIC_API_BASE_URL"
    )

    # Business Policy & Idempotency
    idempotency_ttl_seconds: int = Field(default=86400, ge=60)
    tuition_per_credit: int = Field(default=500000, ge=0)

    # Feature Flags (Batch B & C)
    payments_enabled: bool = True
    sso_enabled: bool = False
    queue_enabled: bool = False

    # Redis Queue (Batch C)
    redis_url: str = "redis://localhost:6379/0"
    redis_socket_timeout_seconds: float = Field(default=1.5, gt=0.1, le=10.0)
    queue_max_ready: int = Field(default=100, ge=1, le=10000)
    queue_token_ttl_seconds: int = Field(default=300, ge=5, le=3600)
    queue_expired_marker_ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    # Keycloak OIDC SSO (Batch C)
    oidc_issuer: str = "http://localhost:8081/realms/dkhp"
    oidc_authorization_endpoint: str = (
        "http://localhost:8081/realms/dkhp/protocol/openid-connect/auth"
    )
    oidc_token_endpoint: str = (
        "http://localhost:8081/realms/dkhp/protocol/openid-connect/token"
    )
    oidc_jwks_uri: str = "http://localhost:8081/realms/dkhp/protocol/openid-connect/certs"
    oidc_client_id: str = "dkhp-backend"
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8080/api/v1/auth/sso/callback"
    oidc_http_timeout_seconds: float = Field(default=5.0, gt=0.5, le=30.0)
    oidc_transaction_ttl_seconds: int = Field(default=300, ge=30, le=1800)
    oidc_exchange_code_ttl_seconds: int = Field(default=60, ge=10, le=600)
    oidc_cookie_secure: bool = False

    # Optional Application-Layer Rate Limit
    rate_limit_backend: Literal["none", "memory", "redis"] = "none"
    rate_limit_rps: int = Field(default=1000, ge=1, le=100000)
    rate_limit_burst: int = Field(default=200, ge=1, le=100000)
    login_rate_limit_per_minute: int = Field(default=60, ge=1, le=100000)

    @field_validator("frontend_origin")
    @classmethod
    def normalize_frontend_origin(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("FRONTEND_ORIGIN phải là origin hợp lệ bắt đầu bằng http:// hoặc https://")
        return cleaned

    @property
    def allowed_origins_list(self) -> list[str]:
        origins: list[str] = []
        for raw in self.cors_allowed_origins.split(","):
            item = raw.strip().rstrip("/")
            if item and item != "*" and item not in origins:
                origins.append(item)
        return origins

    @property
    def database_name(self) -> str:
        parsed = urlparse(self.database_url)
        return (parsed.path or "").lstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
