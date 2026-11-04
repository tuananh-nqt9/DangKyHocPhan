"""Repository for courses, course_classes, schedules, prerequisites, and caller-aware hydration."""

from __future__ import annotations

from typing import Any

from psycopg import Connection


def escape_like_literal(raw_query: str) -> str:
    """Escape '\\', '%', and '_' so user search input never acts as SQL LIKE wildcards."""
    return (
        raw_query.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class CourseClassRepository:
    """Parameterized SQL operations for course classes without N+1 queries."""

    def get_existing_course_codes(
        self, conn: Connection[dict[str, Any]], codes: list[str]
    ) -> set[str]:
        if not codes:
            return set()
        rows = conn.execute(
            "SELECT course_code FROM courses WHERE course_code = ANY(%s)",
            (codes,),
        ).fetchall()
        return {str(r["course_code"]) for r in rows}

    def list_course_classes_page(
        self,
        conn: Connection[dict[str, Any]],
        *,
        q: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        where_sql = ""
        params: list[Any] = []
        if q:
            pattern = f"%{escape_like_literal(q)}%"
            where_sql = (
                "WHERE (class_code ILIKE %s ESCAPE '\\' OR course_name ILIKE %s ESCAPE '\\')"
            )
            params.extend([pattern, pattern])

        count_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM course_classes {where_sql}",
            tuple(params),
        ).fetchone()
        total_items = int(count_row["total"]) if count_row else 0

        offset = (page - 1) * page_size
        page_params = [*params, page_size, offset]
        rows = conn.execute(
            f"""
            SELECT
                course_class_id,
                class_code,
                course_code,
                course_name,
                credits,
                capacity,
                remaining_seats,
                status,
                tuition_amount
            FROM course_classes
            {where_sql}
            ORDER BY course_class_id ASC
            LIMIT %s OFFSET %s
            """,
            tuple(page_params),
        ).fetchall()
        return rows, total_items

    def get_course_class_by_id(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT
                course_class_id,
                class_code,
                course_code,
                course_name,
                credits,
                capacity,
                remaining_seats,
                status,
                tuition_amount
            FROM course_classes
            WHERE course_class_id = %s
            """,
            (course_class_id,),
        ).fetchone()

    def lock_course_class_by_id(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> dict[str, Any] | None:
        """Acquire FOR UPDATE row lock on `course_classes`."""
        return conn.execute(
            """
            SELECT
                course_class_id,
                class_code,
                course_code,
                course_name,
                credits,
                capacity,
                remaining_seats,
                status,
                tuition_amount
            FROM course_classes
            WHERE course_class_id = %s
            FOR UPDATE
            """,
            (course_class_id,),
        ).fetchone()

    def hydrate_course_classes(
        self,
        conn: Connection[dict[str, Any]],
        class_rows: list[dict[str, Any]],
        *,
        caller_user_id: int,
        caller_role: str,
    ) -> list[dict[str, Any]]:
        """Batch-load schedules, prerequisites, completions, and caller's ACTIVE registration.

        Executes at most 4 constant queries regardless of page_size (zero N+1).
        """
        if not class_rows:
            return []

        class_ids = [str(r["course_class_id"]) for r in class_rows]

        schedule_rows = conn.execute(
            """
            SELECT course_class_id, day_of_week, start_period, end_period, room
            FROM course_class_schedules
            WHERE course_class_id = ANY(%s)
            ORDER BY course_class_id ASC, id ASC
            """,
            (class_ids,),
        ).fetchall()

        prereq_rows = conn.execute(
            """
            SELECT
                p.course_class_id,
                p.prerequisite_course_code AS course_code,
                c.course_name
            FROM course_class_prerequisites p
            JOIN courses c ON c.course_code = p.prerequisite_course_code
            WHERE p.course_class_id = ANY(%s)
            ORDER BY p.course_class_id ASC, p.sort_order ASC, p.prerequisite_course_code ASC
            """,
            (class_ids,),
        ).fetchall()

        schedules_by_class: dict[str, list[dict[str, Any]]] = {cid: [] for cid in class_ids}
        for s in schedule_rows:
            schedules_by_class[str(s["course_class_id"])].append(
                {
                    "day_of_week": str(s["day_of_week"]),
                    "start_period": int(s["start_period"]),
                    "end_period": int(s["end_period"]),
                    "room": str(s["room"]),
                }
            )

        prereqs_by_class: dict[str, list[dict[str, Any]]] = {cid: [] for cid in class_ids}
        all_prereq_codes: set[str] = set()
        for p in prereq_rows:
            code = str(p["course_code"])
            all_prereq_codes.add(code)
            prereqs_by_class[str(p["course_class_id"])].append(
                {
                    "course_code": code,
                    "course_name": str(p["course_name"]),
                }
            )

        completed_codes: set[str] = set()
        active_regs_by_class: dict[str, dict[str, Any]] = {}

        if caller_role == "STUDENT":
            if all_prereq_codes:
                comp_rows = conn.execute(
                    """
                    SELECT course_code
                    FROM course_completions
                    WHERE user_id = %s AND course_code = ANY(%s)
                    """,
                    (caller_user_id, list(all_prereq_codes)),
                ).fetchall()
                completed_codes = {str(r["course_code"]) for r in comp_rows}

            reg_rows = conn.execute(
                """
                SELECT
                    course_class_id,
                    registration_id::text AS registration_id,
                    payment_status
                FROM registrations
                WHERE user_id = %s
                  AND status = 'ACTIVE'
                  AND course_class_id = ANY(%s)
                """,
                (caller_user_id, class_ids),
            ).fetchall()
            for r in reg_rows:
                active_regs_by_class[str(r["course_class_id"])] = r

        hydrated: list[dict[str, Any]] = []
        for row in class_rows:
            cid = str(row["course_class_id"])
            capacity = int(row["capacity"])
            remaining = int(row["remaining_seats"])
            registered_count = capacity - remaining

            prereq_list: list[dict[str, Any]] = []
            for p_item in prereqs_by_class[cid]:
                satisfied: bool | None
                if caller_role == "ADMIN":
                    satisfied = None
                else:
                    satisfied = p_item["course_code"] in completed_codes
                prereq_list.append(
                    {
                        "course_code": p_item["course_code"],
                        "course_name": p_item["course_name"],
                        "satisfied": satisfied,
                    }
                )

            active_reg = active_regs_by_class.get(cid)
            if caller_role == "STUDENT" and active_reg is not None:
                reg_status = "REGISTERED"
                reg_id: str | None = str(active_reg["registration_id"])
                pay_status: str | None = str(active_reg["payment_status"])
            else:
                reg_status = "NOT_REGISTERED"
                reg_id = None
                pay_status = None

            hydrated.append(
                {
                    "course_class_id": cid,
                    "class_code": str(row["class_code"]),
                    "course_code": str(row["course_code"]),
                    "course_name": str(row["course_name"]),
                    "credits": int(row["credits"]),
                    "capacity": capacity,
                    "remaining_seats": remaining,
                    "registered_count": registered_count,
                    "status": str(row["status"]),
                    "schedule": schedules_by_class[cid],
                    "prerequisites": prereq_list,
                    "tuition_amount": int(row["tuition_amount"]),
                    "registration_status": reg_status,
                    "registration_id": reg_id,
                    "payment_status": pay_status,
                }
            )
        return hydrated

    def next_course_class_id(self, conn: Connection[dict[str, Any]]) -> str:
        row = conn.execute("SELECT nextval('course_class_id_seq') AS seq_val").fetchone()
        seq_val = int(row["seq_val"]) if row else 1
        if seq_val < 1000:
            return f"LHP{seq_val:03d}"
        return f"LHP{seq_val}"

    def insert_course_class(
        self,
        conn: Connection[dict[str, Any]],
        *,
        course_class_id: str,
        class_code: str,
        course_code: str,
        course_name: str,
        credits: int,
        capacity: int,
        remaining_seats: int,
        status: str,
        tuition_amount: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO course_classes (
                course_class_id,
                class_code,
                course_code,
                course_name,
                credits,
                capacity,
                remaining_seats,
                status,
                tuition_amount
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                course_class_id,
                class_code,
                course_code,
                course_name,
                credits,
                capacity,
                remaining_seats,
                status,
                tuition_amount,
            ),
        )

    def replace_schedules_and_prerequisites(
        self,
        conn: Connection[dict[str, Any]],
        *,
        course_class_id: str,
        schedules: list[dict[str, Any]],
        prerequisite_codes: list[str],
    ) -> None:
        conn.execute(
            "DELETE FROM course_class_schedules WHERE course_class_id = %s",
            (course_class_id,),
        )
        for slot in schedules:
            conn.execute(
                """
                INSERT INTO course_class_schedules (
                    course_class_id, day_of_week, start_period, end_period, room
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    course_class_id,
                    slot["day_of_week"],
                    slot["start_period"],
                    slot["end_period"],
                    slot["room"],
                ),
            )

        conn.execute(
            "DELETE FROM course_class_prerequisites WHERE course_class_id = %s",
            (course_class_id,),
        )
        for idx, code in enumerate(prerequisite_codes):
            conn.execute(
                """
                INSERT INTO course_class_prerequisites (
                    course_class_id, prerequisite_course_code, sort_order
                )
                VALUES (%s, %s, %s)
                """,
                (course_class_id, code, idx),
            )

    def update_course_class(
        self,
        conn: Connection[dict[str, Any]],
        *,
        course_class_id: str,
        class_code: str,
        course_code: str,
        course_name: str,
        credits: int,
        capacity: int,
        remaining_seats: int,
        status: str,
        tuition_amount: int,
    ) -> None:
        conn.execute(
            """
            UPDATE course_classes
            SET class_code = %s,
                course_code = %s,
                course_name = %s,
                credits = %s,
                capacity = %s,
                remaining_seats = %s,
                status = %s,
                tuition_amount = %s,
                updated_at = NOW()
            WHERE course_class_id = %s
            """,
            (
                class_code,
                course_code,
                course_name,
                credits,
                capacity,
                remaining_seats,
                status,
                tuition_amount,
                course_class_id,
            ),
        )

    def update_course_class_status(
        self,
        conn: Connection[dict[str, Any]],
        *,
        course_class_id: str,
        status: str,
    ) -> None:
        conn.execute(
            """
            UPDATE course_classes
            SET status = %s,
                updated_at = NOW()
            WHERE course_class_id = %s
            """,
            (status, course_class_id),
        )

    def get_class_schedules(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT day_of_week, start_period, end_period, room
            FROM course_class_schedules
            WHERE course_class_id = %s
            ORDER BY id ASC
            """,
            (course_class_id,),
        ).fetchall()

    def get_class_prerequisites_with_names(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT
                p.prerequisite_course_code AS course_code,
                c.course_name
            FROM course_class_prerequisites p
            JOIN courses c ON c.course_code = p.prerequisite_course_code
            WHERE p.course_class_id = %s
            ORDER BY p.sort_order ASC, p.prerequisite_course_code ASC
            """,
            (course_class_id,),
        ).fetchall()

    def get_student_completed_courses(
        self, conn: Connection[dict[str, Any]], user_id: int
    ) -> set[str]:
        rows = conn.execute(
            "SELECT course_code FROM course_completions WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        return {str(r["course_code"]) for r in rows}

    def decrement_remaining_seats(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> bool:
        cur = conn.execute(
            """
            UPDATE course_classes
            SET remaining_seats = remaining_seats - 1,
                updated_at = NOW()
            WHERE course_class_id = %s
              AND remaining_seats > 0
            """,
            (course_class_id,),
        )
        return cur.rowcount == 1

    def increment_remaining_seats(
        self, conn: Connection[dict[str, Any]], course_class_id: str
    ) -> bool:
        cur = conn.execute(
            """
            UPDATE course_classes
            SET remaining_seats = remaining_seats + 1,
                updated_at = NOW()
            WHERE course_class_id = %s
              AND remaining_seats < capacity
            """,
            (course_class_id,),
        )
        return cur.rowcount == 1
