"""Repository for student registrations and schedule conflict queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection


class RegistrationRepository:
    """Parameterized SQL operations for `registrations`."""

    def get_active_registration_for_user_class(
        self,
        conn: Connection[dict[str, Any]],
        *,
        user_id: int,
        course_class_id: str,
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                registration_id::text AS registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            FROM registrations
            WHERE user_id = %s
              AND course_class_id = %s
              AND status = 'ACTIVE'
            """,
            (user_id, course_class_id),
        ).fetchone()

    def count_active_registrations_for_class(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM registrations
            WHERE course_class_id = %s AND status = 'ACTIVE'
            """,
            (course_class_id,),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def get_active_schedules_for_user(
        self, conn: Connection[dict[str, Any]], user_id: int
    ) -> list[dict[str, Any]]:
        """Fetch schedules of all ACTIVE registrations belonging to `user_id`."""
        return conn.execute(
            """
            SELECT
                r.course_class_id,
                r.class_code,
                s.day_of_week,
                s.start_period,
                s.end_period,
                s.room
            FROM registrations r
            JOIN course_class_schedules s ON s.course_class_id = r.course_class_id
            WHERE r.user_id = %s
              AND r.status = 'ACTIVE'
            ORDER BY r.course_class_id ASC, s.id ASC
            """,
            (user_id,),
        ).fetchall()

    def insert_registration(
        self,
        conn: Connection[dict[str, Any]],
        *,
        registration_id: str,
        user_id: int,
        student_id: str,
        course_class_id: str,
        class_code: str,
        course_name: str,
        credits: int,
        tuition_amount: int,
        registered_at: datetime,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO registrations (
                registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 'UNPAID', %s, NULL)
            RETURNING
                registration_id::text AS registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            """,
            (
                registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                registered_at,
            ),
        ).fetchone()
        assert row is not None
        return row

    def find_course_class_id_for_registration(
        self, conn: Connection[dict[str, Any]], registration_id: str
    ) -> str | None:
        """Non-locking lookup of target class_id so caller can lock user -> class -> registration."""
        row = conn.execute(
            "SELECT course_class_id FROM registrations WHERE registration_id = %s",
            (registration_id,),
        ).fetchone()
        return str(row["course_class_id"]) if row else None

    def lock_registration_by_id(
        self, conn: Connection[dict[str, Any]], registration_id: str
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                registration_id::text AS registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            FROM registrations
            WHERE registration_id = %s
            FOR UPDATE
            """,
            (registration_id,),
        ).fetchone()

    def mark_cancelled(
        self,
        conn: Connection[dict[str, Any]],
        *,
        registration_id: str,
        new_payment_status: str,
        cancelled_at: datetime,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            UPDATE registrations
            SET status = 'CANCELLED',
                payment_status = %s,
                cancelled_at = %s
            WHERE registration_id = %s
            RETURNING
                registration_id::text AS registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            """,
            (new_payment_status, cancelled_at, registration_id),
        ).fetchone()
        assert row is not None
        return row

    def mark_paid(
        self,
        conn: Connection[dict[str, Any]],
        *,
        registration_id: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            UPDATE registrations
            SET payment_status = 'PAID'
            WHERE registration_id = %s
            RETURNING
                registration_id::text AS registration_id,
                user_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            """,
            (registration_id,),
        ).fetchone()
        assert row is not None
        return row

    def list_user_registrations(
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
        if status_filter in ("ACTIVE", "CANCELLED"):
            where_clauses.append("status = %s")
            params.append(status_filter)

        where_sql = " AND ".join(where_clauses)
        count_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM registrations WHERE {where_sql}",
            tuple(params),
        ).fetchone()
        total_items = int(count_row["total"]) if count_row else 0

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT
                registration_id::text AS registration_id,
                student_id,
                course_class_id,
                class_code,
                course_name,
                credits,
                tuition_amount,
                status,
                payment_status,
                registered_at,
                cancelled_at
            FROM registrations
            WHERE {where_sql}
            ORDER BY registered_at DESC, registration_id ASC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size, offset),
        ).fetchall()
        return rows, total_items
