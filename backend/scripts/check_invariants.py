"""SQL Invariant Checker CLI (exits 0 when all invariants hold, non-zero on any violation)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import psycopg
from app.core.config import get_settings
from psycopg.rows import dict_row

from scripts._console import ensure_utf8_stdio

INVARIANT_CHECKS: list[tuple[str, str, str]] = [
    (
        "seat_balance_mismatch",
        "remaining_seats + COUNT(ACTIVE) == capacity và 0 <= remaining_seats <= capacity trên mọi lớp (kể cả lớp 0 đăng ký)",
        """
        SELECT
            cc.course_class_id,
            cc.class_code,
            cc.capacity,
            cc.remaining_seats,
            COUNT(r.registration_id) AS active_count
        FROM course_classes cc
        LEFT JOIN registrations r
            ON r.course_class_id = cc.course_class_id
           AND r.status = 'ACTIVE'
        GROUP BY cc.course_class_id, cc.class_code, cc.capacity, cc.remaining_seats
        HAVING cc.remaining_seats < 0
            OR COUNT(r.registration_id) > cc.capacity
            OR (cc.remaining_seats + COUNT(r.registration_id)) <> cc.capacity
        """,
    ),
    (
        "duplicate_active_registration",
        "Không có 2 bản ghi ACTIVE trùng cặp (user_id, course_class_id)",
        """
        SELECT user_id, student_id, course_class_id, COUNT(*) AS cnt
        FROM registrations
        WHERE status = 'ACTIVE'
        GROUP BY user_id, student_id, course_class_id
        HAVING COUNT(*) > 1
        """,
    ),
    (
        "cancelled_with_paid_payment",
        "Không có đăng ký CANCELLED nào còn mang trạng thái thanh toán PAID",
        """
        SELECT
            r.registration_id::text AS registration_id,
            r.status,
            r.payment_status,
            p.payment_id::text AS payment_id,
            p.status AS payment_row_status
        FROM registrations r
        LEFT JOIN payments p ON p.registration_id = r.registration_id
        WHERE r.status = 'CANCELLED'
          AND (r.payment_status = 'PAID' OR p.status = 'PAID')
        """,
    ),
    (
        "payment_registration_mismatch",
        "Đối chiếu 1-1 giữa trạng thái payment_status của registrations và bảng payments",
        """
        SELECT
            r.registration_id::text AS registration_id,
            r.payment_status,
            r.tuition_amount,
            p.payment_id::text AS payment_id,
            p.status AS payment_row_status,
            p.amount
        FROM registrations r
        LEFT JOIN payments p ON p.registration_id = r.registration_id
        WHERE (r.payment_status = 'PAID' AND (p.payment_id IS NULL OR p.status <> 'PAID' OR p.amount <> r.tuition_amount))
           OR (r.payment_status = 'REFUNDED' AND (p.payment_id IS NULL OR p.status <> 'REFUNDED' OR p.amount <> r.tuition_amount))
           OR (r.payment_status = 'UNPAID' AND p.payment_id IS NOT NULL)
        """,
    ),
    (
        "active_schedule_conflict",
        "Không có sinh viên nào có hai đăng ký ACTIVE bị chồng lấn tiết học trong tuần",
        """
        SELECT
            r1.student_id,
            r1.course_class_id AS class_1,
            r2.course_class_id AS class_2,
            s1.day_of_week,
            GREATEST(s1.start_period, s2.start_period) AS overlap_start,
            LEAST(s1.end_period, s2.end_period) AS overlap_end
        FROM registrations r1
        JOIN registrations r2
            ON r1.user_id = r2.user_id
           AND r1.registration_id < r2.registration_id
           AND r1.status = 'ACTIVE'
           AND r2.status = 'ACTIVE'
        JOIN course_class_schedules s1 ON s1.course_class_id = r1.course_class_id
        JOIN course_class_schedules s2 ON s2.course_class_id = r2.course_class_id
        WHERE s1.day_of_week = s2.day_of_week
          AND GREATEST(s1.start_period, s2.start_period) <= LEAST(s1.end_period, s2.end_period)
        """,
    ),
]


def run_invariant_checks(database_url: str) -> dict[str, Any]:
    results: dict[str, Any] = {"ok": True, "checks": {}, "stats": {}}
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=False) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            for name, description, sql in INVARIANT_CHECKS:
                violations = conn.execute(sql).fetchall()
                passed = len(violations) == 0
                if not passed:
                    results["ok"] = False
                results["checks"][name] = {
                    "passed": passed,
                    "description": description,
                    "violation_count": len(violations),
                    "violations": violations[:20],
                }

            stats_row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS users_count,
                    (SELECT COUNT(*) FROM course_classes) AS classes_count,
                    (SELECT COUNT(*) FROM registrations WHERE status = 'ACTIVE') AS active_registrations,
                    (SELECT COUNT(*) FROM registrations WHERE status = 'CANCELLED') AS cancelled_registrations,
                    (SELECT COUNT(*) FROM payments WHERE status = 'PAID') AS paid_payments,
                    (SELECT COUNT(*) FROM payments WHERE status = 'REFUNDED') AS refunded_payments,
                    (SELECT COUNT(*) FROM idempotency_records) AS idempotency_records
                """
            ).fetchone()
            results["stats"] = dict(stats_row or {})

    return results


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Kiểm tra toàn vẹn dữ liệu & invariants SQL.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    try:
        report = run_invariant_checks(db_url)
    except Exception as exc:
        print(f"[INVARIANTS ERROR] {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
