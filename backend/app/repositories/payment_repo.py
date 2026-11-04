"""Repository for simulated payments and refunds."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection


class PaymentRepository:
    """Parameterized SQL operations for `payments`."""

    def lock_payment_by_registration_id(
        self, conn: Connection[dict[str, Any]], registration_id: str
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                payment_id::text AS payment_id,
                registration_id::text AS registration_id,
                user_id,
                course_class_id,
                class_code,
                amount,
                currency,
                status,
                paid_at,
                refunded_at
            FROM payments
            WHERE registration_id = %s
            FOR UPDATE
            """,
            (registration_id,),
        ).fetchone()

    def insert_payment(
        self,
        conn: Connection[dict[str, Any]],
        *,
        payment_id: str,
        registration_id: str,
        user_id: int,
        course_class_id: str,
        class_code: str,
        amount: int,
        paid_at: datetime,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO payments (
                payment_id,
                registration_id,
                user_id,
                course_class_id,
                class_code,
                amount,
                currency,
                status,
                paid_at,
                refunded_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'VND', 'PAID', %s, NULL)
            RETURNING
                payment_id::text AS payment_id,
                registration_id::text AS registration_id,
                user_id,
                course_class_id,
                class_code,
                amount,
                currency,
                status,
                paid_at,
                refunded_at
            """,
            (
                payment_id,
                registration_id,
                user_id,
                course_class_id,
                class_code,
                amount,
                paid_at,
            ),
        ).fetchone()
        assert row is not None
        return row

    def mark_refunded(
        self,
        conn: Connection[dict[str, Any]],
        *,
        payment_id: str,
        refunded_at: datetime,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED',
                refunded_at = %s
            WHERE payment_id = %s
            RETURNING
                payment_id::text AS payment_id,
                registration_id::text AS registration_id,
                user_id,
                course_class_id,
                class_code,
                amount,
                currency,
                status,
                paid_at,
                refunded_at
            """,
            (refunded_at, payment_id),
        ).fetchone()
        assert row is not None
        return row

    def list_user_payments(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_id: int,
        status_filter: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        where_clauses = ["user_id = %s"]
        params: list[Any] = [user_id]
        if status_filter in ("PAID", "REFUNDED"):
            where_clauses.append("status = %s")
            params.append(status_filter)

        where_sql = " AND ".join(where_clauses)
        count_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM payments WHERE {where_sql}",
            tuple(params),
        ).fetchone()
        total_items = int(count_row["total"]) if count_row else 0

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT
                payment_id::text AS payment_id,
                registration_id::text AS registration_id,
                course_class_id,
                class_code,
                amount,
                currency,
                status,
                paid_at,
                refunded_at
            FROM payments
            WHERE {where_sql}
            ORDER BY paid_at DESC, payment_id ASC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size, offset),
        ).fetchall()
        return rows, total_items
