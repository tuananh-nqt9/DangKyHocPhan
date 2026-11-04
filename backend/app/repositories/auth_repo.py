"""Repository for users, sessions, and OIDC SSO persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection


class AuthRepository:
    """Parameterized SQL operations for users, sessions, and SSO tables."""

    def get_user_by_student_id(
        self, conn: Connection[dict[str, Any]], student_id: str
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT id, student_id, full_name, role, password_hash, created_at
            FROM users
            WHERE student_id = %s
            """,
            (student_id,),
        ).fetchone()

    def get_user_by_id(
        self, conn: Connection[dict[str, Any]], user_id: int
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT id, student_id, full_name, role, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()

    def lock_user_by_id(
        self, conn: Connection[dict[str, Any]], user_id: int
    ) -> dict[str, Any] | None:
        """Acquire FOR UPDATE row lock on `users` (Step 1 of student lock order)."""
        return conn.execute(
            """
            SELECT id, student_id, full_name, role
            FROM users
            WHERE id = %s
            FOR UPDATE
            """,
            (user_id,),
        ).fetchone()

    def create_session(
        self,
        conn: Connection[dict[str, Any]],
        *,
        session_id: str,
        user_id: int,
        access_token_hash: str,
        refresh_token_hash: str,
        access_expires_at: datetime,
        refresh_expires_at: datetime,
        absolute_expires_at: datetime,
        now_utc: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sessions (
                session_id,
                user_id,
                access_token_hash,
                refresh_token_hash,
                access_expires_at,
                refresh_expires_at,
                absolute_expires_at,
                revoked_at,
                created_at,
                rotated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
            """,
            (
                session_id,
                user_id,
                access_token_hash,
                refresh_token_hash,
                access_expires_at,
                refresh_expires_at,
                absolute_expires_at,
                now_utc,
                now_utc,
            ),
        )

    def get_active_session_by_access_hash(
        self,
        conn: Connection[dict[str, Any]],
        *,
        access_token_hash: str,
        now_utc: datetime,
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                s.session_id::text AS session_id,
                s.user_id,
                s.access_expires_at,
                s.refresh_expires_at,
                s.absolute_expires_at,
                s.revoked_at,
                u.student_id,
                u.full_name,
                u.role
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.access_token_hash = %s
              AND s.revoked_at IS NULL
              AND s.access_expires_at > %s
              AND s.absolute_expires_at > %s
            """,
            (access_token_hash, now_utc, now_utc),
        ).fetchone()

    def lock_session_by_refresh_hash(
        self,
        conn: Connection[dict[str, Any]],
        *,
        refresh_token_hash: str,
    ) -> dict[str, Any] | None:
        """Lock session row FOR UPDATE during atomic token refresh."""
        return conn.execute(
            """
            SELECT
                s.session_id::text AS session_id,
                s.user_id,
                s.access_token_hash,
                s.refresh_token_hash,
                s.access_expires_at,
                s.refresh_expires_at,
                s.absolute_expires_at,
                s.revoked_at,
                u.student_id,
                u.full_name,
                u.role
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.refresh_token_hash = %s
            FOR UPDATE OF s
            """,
            (refresh_token_hash,),
        ).fetchone()

    def lock_session_by_id(
        self,
        conn: Connection[dict[str, Any]],
        *,
        session_id: str,
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                session_id::text AS session_id,
                user_id,
                access_token_hash,
                refresh_token_hash,
                access_expires_at,
                refresh_expires_at,
                absolute_expires_at,
                revoked_at
            FROM sessions
            WHERE session_id = %s
            FOR UPDATE
            """,
            (session_id,),
        ).fetchone()

    def rotate_session_tokens(
        self,
        conn: Connection[dict[str, Any]],
        *,
        session_id: str,
        new_access_hash: str,
        new_refresh_hash: str,
        new_access_expires_at: datetime,
        new_refresh_expires_at: datetime,
        now_utc: datetime,
    ) -> None:
        conn.execute(
            """
            UPDATE sessions
            SET access_token_hash = %s,
                refresh_token_hash = %s,
                access_expires_at = %s,
                refresh_expires_at = %s,
                rotated_at = %s
            WHERE session_id = %s
            """,
            (
                new_access_hash,
                new_refresh_hash,
                new_access_expires_at,
                new_refresh_expires_at,
                now_utc,
                session_id,
            ),
        )

    def revoke_session(
        self,
        conn: Connection[dict[str, Any]],
        *,
        session_id: str,
        now_utc: datetime,
    ) -> None:
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = %s
            WHERE session_id = %s AND revoked_at IS NULL
            """,
            (now_utc, session_id),
        )

    def create_sso_transaction(
        self,
        conn: Connection[dict[str, Any]],
        *,
        state: str,
        nonce: str,
        code_verifier: str,
        browser_bind_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sso_transactions (
                state, nonce, code_verifier, browser_bind_hash, created_at, expires_at, consumed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
            """,
            (state, nonce, code_verifier, browser_bind_hash, created_at, expires_at),
        )

    def consume_sso_transaction(
        self,
        conn: Connection[dict[str, Any]],
        *,
        state: str,
        now_utc: datetime,
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            UPDATE sso_transactions
            SET consumed_at = %s
            WHERE state = %s
              AND consumed_at IS NULL
              AND expires_at > %s
            RETURNING state, nonce, code_verifier, browser_bind_hash, expires_at
            """,
            (now_utc, state, now_utc),
        ).fetchone()

    def get_user_by_sso_identity(
        self,
        conn: Connection[dict[str, Any]],
        *,
        issuer: str,
        subject: str,
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT u.id, u.student_id, u.full_name, u.role
            FROM sso_identities si
            JOIN users u ON u.id = si.user_id
            WHERE si.issuer = %s AND si.subject = %s
            """,
            (issuer, subject),
        ).fetchone()

    def create_sso_exchange_code(
        self,
        conn: Connection[dict[str, Any]],
        *,
        code_hash: str,
        user_id: int,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sso_exchange_codes (code_hash, user_id, created_at, expires_at, consumed_at)
            VALUES (%s, %s, %s, %s, NULL)
            """,
            (code_hash, user_id, created_at, expires_at),
        )

    def consume_sso_exchange_code(
        self,
        conn: Connection[dict[str, Any]],
        *,
        code_hash: str,
        now_utc: datetime,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            UPDATE sso_exchange_codes
            SET consumed_at = %s
            WHERE code_hash = %s
              AND consumed_at IS NULL
              AND expires_at > %s
            RETURNING user_id
            """,
            (now_utc, code_hash, now_utc),
        ).fetchone()
        if row is None:
            return None
        return self.get_user_by_id(conn, int(row["user_id"]))
