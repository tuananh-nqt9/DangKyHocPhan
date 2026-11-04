"""Repository for multi-worker PostgreSQL transactional idempotency."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import psycopg
from psycopg import Connection

from app.core.errors import AppError, ErrorCode


def compute_advisory_lock_id(user_id: int, idempotency_key: str) -> int:
    """Compute a deterministic process-independent signed 64-bit integer for `pg_advisory_xact_lock`.

    Never uses Python's randomized `hash()`.
    """
    digest = hashlib.sha256(f"{user_id}:{idempotency_key.lower()}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class IdempotencyRepository:
    """Parameterized SQL operations for `idempotency_records`."""

    def acquire_xact_lock(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_id: int,
        idempotency_key: str,
        idempotency_lock_timeout_ms: int,
        restore_lock_timeout_ms: int,
    ) -> None:
        """Acquire transaction-scoped advisory lock for `(user_id, idempotency_key)`.

        If another worker is concurrently executing the same `(user_id, key)` and holds
        the lock past `idempotency_lock_timeout_ms`, raises `409 REQUEST_IN_PROGRESS`.
        """
        lock_id = compute_advisory_lock_id(user_id, idempotency_key)
        try:
            conn.execute(f"SET LOCAL lock_timeout = '{int(idempotency_lock_timeout_ms)}ms'")
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
        except psycopg.errors.LockNotAvailable as exc:
            raise AppError(
                status_code=409,
                code=ErrorCode.REQUEST_IN_PROGRESS,
                message="Yêu cầu với cùng Idempotency-Key đang được xử lý. Vui lòng thử lại sau.",
                headers={"Retry-After": "1"},
            ) from exc
        conn.execute(f"SET LOCAL lock_timeout = '{int(restore_lock_timeout_ms)}ms'")

    def get_record(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_id: int,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                id,
                user_id,
                idempotency_key::text AS idempotency_key,
                request_method,
                request_path,
                fingerprint,
                response_status,
                response_code,
                response_body,
                original_request_id::text AS original_request_id,
                created_at,
                expires_at
            FROM idempotency_records
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (user_id, idempotency_key.lower()),
        ).fetchone()

    def delete_if_expired(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_id: int,
        idempotency_key: str,
        now_utc: datetime,
    ) -> int:
        cur = conn.execute(
            """
            DELETE FROM idempotency_records
            WHERE user_id = %s
              AND idempotency_key = %s
              AND expires_at <= %s
            """,
            (user_id, idempotency_key.lower(), now_utc),
        )
        return cur.rowcount

    def save_record(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_id: int,
        idempotency_key: str,
        request_method: str,
        request_path: str,
        fingerprint: str,
        response_status: int,
        response_code: str,
        response_body: dict[str, Any],
        original_request_id: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO idempotency_records (
                user_id,
                idempotency_key,
                request_method,
                request_path,
                fingerprint,
                response_status,
                response_code,
                response_body,
                original_request_id,
                created_at,
                expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                user_id,
                idempotency_key.lower(),
                request_method,
                request_path,
                fingerprint,
                response_status,
                response_code,
                json.dumps(response_body, ensure_ascii=False),
                original_request_id,
                created_at,
                expires_at,
            ),
        )

    def cleanup_expired_batch(
        self,
        conn: Connection[dict[str, Any]],
        *,
        now_utc: datetime,
        batch_size: int = 1000,
    ) -> int:
        """Delete expired completed records safely without touching active advisory-locked rows."""
        cur = conn.execute(
            """
            DELETE FROM idempotency_records
            WHERE id IN (
                SELECT id
                FROM idempotency_records
                WHERE expires_at <= %s
                ORDER BY expires_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            """,
            (now_utc, batch_size),
        )
        return cur.rowcount
