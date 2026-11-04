"""Keycloak OIDC Authorization Code + PKCE S256 SSO service (Spec Section 07)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.core.clock import utc_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.security import (
    constant_time_equals,
    generate_opaque_token,
    generate_pkce_pair,
    hash_token,
)
from app.db.pool import DatabaseManager
from app.repositories.auth_repo import AuthRepository
from app.services.auth_service import AuthService

logger = get_logger("dkhp.sso")

SSO_BIND_COOKIE_NAME = "dkhp_sso_bind"
SSO_BIND_COOKIE_PATH = "/api/v1/auth/sso/callback"


class SsoService:
    """Implements OIDC Authorization Code + PKCE S256 with browser binding and 60s exchange codes."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        auth_service: AuthService,
        repo: AuthRepository | None = None,
        token_exchanger: Callable[[dict[str, str]], dict[str, Any]] | None = None,
        id_token_verifier: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._auth_service = auth_service
        self._repo = repo or AuthRepository()
        self._custom_token_exchanger = token_exchanger
        self._custom_id_token_verifier = id_token_verifier
        self._jwks_client: PyJWKClient | None = None

    def _ensure_enabled(self) -> None:
        if not self._settings.sso_enabled:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Chức năng đăng nhập SSO chưa được bật trên môi trường này.",
            )

    def start_sso_login(self) -> tuple[str, str]:
        """Create 5-minute OIDC transaction and return `(authorization_url, browser_bind_token)`."""
        self._ensure_enabled()

        state = generate_opaque_token(32)
        nonce = generate_opaque_token(32)
        code_verifier, code_challenge = generate_pkce_pair()
        browser_bind_token = generate_opaque_token(32)

        now = utc_now()
        expires_at = now + timedelta(seconds=self._settings.oidc_transaction_ttl_seconds)

        with self._db.transaction() as conn:
            self._repo.create_sso_transaction(
                conn,
                state=state,
                nonce=nonce,
                code_verifier=code_verifier,
                browser_bind_hash=hash_token(browser_bind_token),
                created_at=now,
                expires_at=expires_at,
            )

        query = urlencode(
            {
                "client_id": self._settings.oidc_client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": self._settings.oidc_redirect_uri,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self._settings.oidc_authorization_endpoint}?{query}", browser_bind_token

    def _exchange_code_with_idp(self, *, code: str, code_verifier: str) -> dict[str, Any]:
        payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": self._settings.oidc_redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }
        if self._settings.oidc_client_secret:
            payload["client_secret"] = self._settings.oidc_client_secret

        if self._custom_token_exchanger is not None:
            return self._custom_token_exchanger(payload)

        with httpx.Client(
            timeout=self._settings.oidc_http_timeout_seconds,
            verify=True,
        ) as client:
            resp = client.post(
                self._settings.oidc_token_endpoint,
                data=payload,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Phản hồi token IdP không hợp lệ.")
            return data

    def _verify_id_token(self, raw_id_token: str) -> dict[str, Any]:
        if self._custom_id_token_verifier is not None:
            return self._custom_id_token_verifier(raw_id_token)

        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                self._settings.oidc_jwks_uri,
                timeout=int(max(1.0, self._settings.oidc_http_timeout_seconds)),
            )
        signing_key = self._jwks_client.get_signing_key_from_jwt(raw_id_token)
        claims = jwt.decode(
            raw_id_token,
            signing_key.key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384"],
            audience=self._settings.oidc_client_id,
            issuer=self._settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
        # RFC 9700 / OIDC Core: if multiple audiences or azp is present, azp must match client_id
        azp = claims.get("azp")
        if azp is not None and str(azp) != self._settings.oidc_client_id:
            raise ValueError("Claim azp không khớp client_id.")
        return claims

    def handle_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        idp_error: str | None,
        browser_bind_cookie: str | None,
    ) -> str:
        """Validate callback, map OIDC identity, and return frontend 302 target URL."""
        self._ensure_enabled()
        error_redirect = f"{self._settings.frontend_origin}/sso/callback?error=SSO_FAILED"

        if idp_error or not code or not state or not browser_bind_cookie:
            return error_redirect

        # 1. Atomically consume state in short DB transaction BEFORE calling network IdP!
        now = utc_now()
        with self._db.transaction() as conn:
            tx = self._repo.consume_sso_transaction(conn, state=state, now_utc=now)

        if tx is None:
            return error_redirect

        # 2. Verify browser-binding cookie hash to defeat Login CSRF / Code Injection
        if not constant_time_equals(
            str(tx["browser_bind_hash"]).strip(),
            hash_token(browser_bind_cookie),
        ):
            logger.warning("SSO browser binding mismatch detected.")
            return error_redirect

        # 3. Exchange authorization code & cryptographically verify ID token outside DB lock
        try:
            token_data = self._exchange_code_with_idp(
                code=code,
                code_verifier=str(tx["code_verifier"]),
            )
            raw_id_token = token_data.get("id_token")
            if not isinstance(raw_id_token, str) or not raw_id_token:
                return error_redirect
            claims = self._verify_id_token(raw_id_token)
        except Exception as exc:
            logger.warning(
                "SSO token exchange or ID token verification failed.",
                extra={"structured": {"reason": type(exc).__name__}},
            )
            return error_redirect

        token_nonce = claims.get("nonce")
        if not isinstance(token_nonce, str) or not constant_time_equals(
            str(tx["nonce"]), token_nonce
        ):
            return error_redirect

        issuer = str(claims.get("iss", ""))
        subject = str(claims.get("sub", ""))
        if issuer != self._settings.oidc_issuer or not subject:
            return error_redirect

        # 4. Map (issuer, sub) -> internal user and issue 60s one-time exchange_code
        raw_exchange_code = generate_opaque_token(32)
        issued_at = utc_now()
        code_expires_at = issued_at + timedelta(seconds=self._settings.oidc_exchange_code_ttl_seconds)

        with self._db.transaction() as conn:
            user_row = self._repo.get_user_by_sso_identity(
                conn,
                issuer=issuer,
                subject=subject,
            )
            if user_row is None:
                return error_redirect

            self._repo.create_sso_exchange_code(
                conn,
                code_hash=hash_token(raw_exchange_code),
                user_id=int(user_row["id"]),
                created_at=issued_at,
                expires_at=code_expires_at,
            )

        query = urlencode({"exchange_code": raw_exchange_code})
        return f"{self._settings.frontend_origin}/sso/callback?{query}"

    def exchange_code(self, *, raw_exchange_code: str) -> dict[str, Any]:
        """Atomically consume one-time 60s `exchange_code` and issue internal session tokens."""
        self._ensure_enabled()

        code_hash = hash_token(raw_exchange_code)
        with self._db.transaction() as conn:
            user_row = self._repo.consume_sso_exchange_code(
                conn,
                code_hash=code_hash,
                now_utc=utc_now(),
            )
            if user_row is None:
                raise AppError(
                    status_code=401,
                    code=ErrorCode.SSO_FAILED,
                    message="Mã đăng nhập SSO không hợp lệ, đã hết hạn hoặc đã được sử dụng.",
                )
            return self._auth_service.create_session_for_user(conn, user_row=user_row)
