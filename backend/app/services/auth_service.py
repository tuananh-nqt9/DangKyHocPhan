"""Authentication, session token rotation, and logout service (Spec Sections 05 & 06)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from psycopg import Connection

from app.core.clock import utc_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    constant_time_equals,
    generate_opaque_token,
    hash_token,
    verify_password,
)
from app.db.pool import DatabaseManager
from app.repositories.auth_repo import AuthRepository
from app.services.queue_service import QueueService


class AuthService:
    """Manages Argon2id login, opaque Bearer/refresh token rotation, and session revocation."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        queue_service: QueueService,
        repo: AuthRepository | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._queue_service = queue_service
        self._repo = repo or AuthRepository()

    def create_session_for_user(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_row: dict[str, Any],
    ) -> dict[str, Any]:
        """Issue a new opaque token pair inside an existing DB transaction."""
        now = utc_now()
        access_ttl = self._settings.access_token_ttl_seconds
        abs_ttl = self._settings.session_absolute_ttl_seconds
        effective_access_ttl = min(access_ttl, abs_ttl)

        raw_access = generate_opaque_token(32)
        raw_refresh = generate_opaque_token(32)
        session_id = str(uuid.uuid4())

        absolute_expires_at = now + timedelta(seconds=abs_ttl)
        access_expires_at = now + timedelta(seconds=effective_access_ttl)
        refresh_expires_at = absolute_expires_at

        self._repo.create_session(
            conn,
            session_id=session_id,
            user_id=int(user_row["id"]),
            access_token_hash=hash_token(raw_access),
            refresh_token_hash=hash_token(raw_refresh),
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            absolute_expires_at=absolute_expires_at,
            now_utc=now,
        )

        return {
            "access_token": raw_access,
            "token_type": "Bearer",
            "expires_in": effective_access_ttl,
            "refresh_token": raw_refresh,
            "refresh_expires_in": abs_ttl,
            "student": {
                "student_id": str(user_row["student_id"]),
                "full_name": str(user_row["full_name"]),
                "role": str(user_row["role"]),
            },
        }

    def login(self, *, student_id: str, password: str) -> dict[str, Any]:
        # 1. Short read query so we NEVER hold a DB connection open during CPU-heavy Argon2id!
        with self._db.read_snapshot() as conn:
            user_row = self._repo.get_user_by_student_id(conn, student_id)

        pw_hash = str(user_row["password_hash"]) if user_row is not None else None
        if not verify_password(password, pw_hash) or user_row is None:
            raise AppError(
                status_code=401,
                code=ErrorCode.INVALID_CREDENTIALS,
                message="Thông tin đăng nhập không chính xác.",
            )

        # 2. Short write transaction to persist hashed opaque tokens
        with self._db.transaction() as conn:
            return self.create_session_for_user(conn, user_row=user_row)

    def authenticate_access_token(self, raw_access_token: str) -> dict[str, Any]:
        """Validate Bearer opaque token using a short-lived DB connection."""
        token_hash = hash_token(raw_access_token)
        now = utc_now()
        with self._db.read_snapshot() as conn:
            session = self._repo.get_active_session_by_access_hash(
                conn,
                access_token_hash=token_hash,
                now_utc=now,
            )
        if session is None:
            raise AppError(
                status_code=401,
                code=ErrorCode.UNAUTHORIZED,
                message="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            )
        return {
            "session_id": str(session["session_id"]),
            "user_id": int(session["user_id"]),
            "student_id": str(session["student_id"]),
            "full_name": str(session["full_name"]),
            "role": str(session["role"]),
        }

    def refresh(self, *, raw_refresh_token: str) -> dict[str, Any]:
        """Atomically lock session row, verify absolute lifetime, and rotate both tokens."""
        refresh_hash = hash_token(raw_refresh_token)
        with self._db.transaction() as conn:
            session = self._repo.lock_session_by_refresh_hash(
                conn,
                refresh_token_hash=refresh_hash,
            )
            now = utc_now()
            if session is None:
                raise AppError(
                    status_code=401,
                    code=ErrorCode.INVALID_REFRESH_TOKEN,
                    message="Refresh token không hợp lệ, đã được sử dụng hoặc phiên đã kết thúc.",
                )

            if (
                session["revoked_at"] is not None
                or session["refresh_expires_at"] <= now
                or session["absolute_expires_at"] <= now
            ):
                raise AppError(
                    status_code=401,
                    code=ErrorCode.INVALID_REFRESH_TOKEN,
                    message="Refresh token đã hết hạn hoặc phiên đăng nhập đã bị thu hồi.",
                )

            remaining_abs_seconds = int((session["absolute_expires_at"] - now).total_seconds())
            if remaining_abs_seconds <= 0:
                raise AppError(
                    status_code=401,
                    code=ErrorCode.INVALID_REFRESH_TOKEN,
                    message="Phiên đăng nhập đã hết thời hạn tuyệt đối.",
                )

            effective_access_ttl = min(
                self._settings.access_token_ttl_seconds,
                remaining_abs_seconds,
            )
            new_access_expires_at = min(
                session["absolute_expires_at"],
                now + timedelta(seconds=effective_access_ttl),
            )
            new_refresh_expires_at = session["absolute_expires_at"]

            raw_new_access = generate_opaque_token(32)
            raw_new_refresh = generate_opaque_token(32)

            self._repo.rotate_session_tokens(
                conn,
                session_id=str(session["session_id"]),
                new_access_hash=hash_token(raw_new_access),
                new_refresh_hash=hash_token(raw_new_refresh),
                new_access_expires_at=new_access_expires_at,
                new_refresh_expires_at=new_refresh_expires_at,
                now_utc=now,
            )

            return {
                "access_token": raw_new_access,
                "token_type": "Bearer",
                "expires_in": max(1, effective_access_ttl),
                "refresh_token": raw_new_refresh,
                "refresh_expires_in": max(1, remaining_abs_seconds),
                "student": {
                    "student_id": str(session["student_id"]),
                    "full_name": str(session["full_name"]),
                    "role": str(session["role"]),
                },
            }

    def logout(self, *, caller: dict[str, Any], raw_refresh_token: str) -> dict[str, Any]:
        """Revoke the exact session matching both Bearer access token and body refresh_token."""
        provided_refresh_hash = hash_token(raw_refresh_token)
        with self._db.transaction() as conn:
            locked_session = self._repo.lock_session_by_id(
                conn,
                session_id=caller["session_id"],
            )
            if (
                locked_session is None
                or locked_session["revoked_at"] is not None
                or int(locked_session["user_id"]) != int(caller["user_id"])
                or not constant_time_equals(
                    str(locked_session["refresh_token_hash"]).strip(),
                    provided_refresh_hash,
                )
            ):
                raise AppError(
                    status_code=401,
                    code=ErrorCode.INVALID_REFRESH_TOKEN,
                    message="Refresh token không khớp phiên đăng nhập hiện tại.",
                )

            self._repo.revoke_session(
                conn,
                session_id=caller["session_id"],
                now_utc=utc_now(),
            )

        if caller["role"] == "STUDENT":
            self._queue_service.release_user_slot_on_logout(caller["student_id"])

        return {"logged_out": True}
