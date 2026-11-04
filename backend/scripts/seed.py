"""Idempotent database seeder for UI integration (`ui`) and k6 benchmarks (`loadtest`).

WARNING: Lab demo credentials (`Demo@123456`) are strictly for local/lab testing.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psycopg
from app.core.config import get_settings
from app.core.security import hash_password
from psycopg.rows import dict_row

from scripts._console import ensure_utf8_stdio

LAB_DEMO_PASSWORD = "Demo@123456"
KEYCLOAK_SV0001_SUB = "11111111-2222-3333-4444-555555550001"

CATALOG_COURSES: list[tuple[str, str, int]] = [
    ("CS101", "Nhập môn lập trình", 3),
    ("CNNT", "Công nghệ nền tảng", 3),
    ("WEB", "Phát triển ứng dụng Web", 3),
    ("JAVA", "Lập trình hướng đối tượng với Java", 3),
    ("DB101", "Cơ sở dữ liệu", 3),
    ("NET101", "Mạng máy tính", 3),
    ("SE101", "Công nghệ phần mềm", 3),
    ("AI101", "Trí tuệ nhân tạo", 3),
]


def _build_ui_classes(tuition_per_credit: int) -> list[dict[str, Any]]:
    return [
        {
            "course_class_id": "LHP001",
            "class_code": "CNNT-01",
            "course_code": "CNNT",
            "course_name": "Công nghệ nền tảng",
            "credits": 3,
            "capacity": 50,
            "status": "OPEN",
            "tuition_amount": 3 * tuition_per_credit,
            "schedule": [
                {
                    "day_of_week": "MON",
                    "start_period": 1,
                    "end_period": 3,
                    "room": "A101",
                }
            ],
            "prerequisites": ["CS101"],
        },
        {
            "course_class_id": "LHP002",
            "class_code": "WEB-01",
            "course_code": "WEB",
            "course_name": "Phát triển ứng dụng Web",
            "credits": 3,
            "capacity": 50,
            "status": "OPEN",
            "tuition_amount": 3 * tuition_per_credit,
            "schedule": [
                {
                    "day_of_week": "MON",
                    "start_period": 2,
                    "end_period": 4,
                    "room": "B201",
                }
            ],
            "prerequisites": [],
        },
        {
            "course_class_id": "LHP003",
            "class_code": "JAVA-01",
            "course_code": "JAVA",
            "course_name": "Lập trình hướng đối tượng với Java",
            "credits": 3,
            "capacity": 50,
            "status": "OPEN",
            "tuition_amount": 3 * tuition_per_credit,
            "schedule": [
                {
                    "day_of_week": "TUE",
                    "start_period": 1,
                    "end_period": 3,
                    "room": "C301",
                }
            ],
            "prerequisites": [],
        },
    ]


def _build_loadtest_classes(tuition_per_credit: int) -> list[dict[str, Any]]:
    return [
        {
            "course_class_id": "LHP001",
            "class_code": "CNNT-01",
            "course_code": "CNNT",
            "course_name": "Công nghệ nền tảng",
            "credits": 3,
            "capacity": 1000,
            "status": "OPEN",
            "tuition_amount": 3 * tuition_per_credit,
            "schedule": [],
            "prerequisites": [],
        }
    ]


def seed_database(
    database_url: str,
    *,
    mode: str = "ui",
    student_count: int = 3000,
    tuition_per_credit: int = 500000,
    oidc_issuer: str = "http://localhost:8081/realms/dkhp",
    distinct_salts: bool = True,
) -> dict[str, int]:
    """Seed catalog, users, completions, SSO mapping, and mode-specific course classes.

    Idempotent: re-running does not duplicate rows or corrupt active seat balances.
    Synchronizes `course_class_id_seq` after upserting seeded classes.
    """
    if mode not in ("ui", "loadtest"):
        raise ValueError("Chế độ seed chỉ nhận 'ui' hoặc 'loadtest'.")
    if student_count < 2 or student_count > 10000:
        raise ValueError("student_count phải nằm trong khoảng 2..10000.")

    desired_accounts: list[tuple[str, str, str]] = [
        ("AD0001", "Quản trị viên hệ thống 0001", "ADMIN"),
        *[
            (f"SV{i:04d}", f"Sinh viên mẫu {i:04d}", "STUDENT")
            for i in range(1, student_count + 1)
        ],
    ]

    with psycopg.connect(database_url, row_factory=dict_row, autocommit=False) as conn:
        with conn.transaction():
            conn.execute("SET LOCAL timezone = 'GMT'")

            # 1. Seed course catalog
            for code, name, default_credits in CATALOG_COURSES:
                conn.execute(
                    """
                    INSERT INTO courses (course_code, course_name, default_credits)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (course_code) DO UPDATE
                    SET course_name = EXCLUDED.course_name,
                        default_credits = EXCLUDED.default_credits
                    """,
                    (code, name, default_credits),
                )

            # 2. Seed only missing users with genuine Argon2id hashes (parallelized across CPU threads)
            existing_rows = conn.execute("SELECT student_id FROM users").fetchall()
            existing_ids = {str(r["student_id"]) for r in existing_rows}
            missing_accounts = [acc for acc in desired_accounts if acc[0] not in existing_ids]

            if missing_accounts:
                if distinct_salts:
                    workers = min(16, max(2, (os.cpu_count() or 4)))
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        hashes = list(
                            pool.map(
                                lambda _: hash_password(LAB_DEMO_PASSWORD),
                                range(len(missing_accounts)),
                            )
                        )
                else:
                    shared_hash = hash_password(LAB_DEMO_PASSWORD)
                    hashes = [shared_hash] * len(missing_accounts)

                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO users (student_id, full_name, role, password_hash)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (student_id) DO NOTHING
                        """,
                        [
                            (sid, fname, role, pw_hash)
                            for (sid, fname, role), pw_hash in zip(
                                missing_accounts, hashes, strict=True
                            )
                        ],
                    )

            # 3. Completions & SSO mapping for SV0001
            sv1 = conn.execute(
                "SELECT id FROM users WHERE student_id = 'SV0001'"
            ).fetchone()
            sv2 = conn.execute(
                "SELECT id FROM users WHERE student_id = 'SV0002'"
            ).fetchone()

            if sv1 is not None:
                sv1_id = int(sv1["id"])
                if mode == "ui":
                    conn.execute(
                        """
                        INSERT INTO course_completions (user_id, course_code)
                        VALUES (%s, 'CS101')
                        ON CONFLICT (user_id, course_code) DO NOTHING
                        """,
                        (sv1_id,),
                    )
                conn.execute(
                    """
                    INSERT INTO sso_identities (issuer, subject, user_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (issuer, user_id) DO UPDATE
                    SET subject = EXCLUDED.subject
                    """,
                    (oidc_issuer, KEYCLOAK_SV0001_SUB, sv1_id),
                )

            if sv2 is not None and mode == "ui":
                conn.execute(
                    "DELETE FROM course_completions WHERE user_id = %s AND course_code = 'CS101'",
                    (int(sv2["id"]),),
                )

            # 4. Seed classes for chosen mode while respecting existing ACTIVE registrations
            class_defs = (
                _build_ui_classes(tuition_per_credit)
                if mode == "ui"
                else _build_loadtest_classes(tuition_per_credit)
            )
            for cdef in class_defs:
                cid = cdef["course_class_id"]
                active_row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM registrations
                    WHERE course_class_id = %s AND status = 'ACTIVE'
                    """,
                    (cid,),
                ).fetchone()
                active_cnt = int(active_row["cnt"]) if active_row else 0
                if active_cnt > cdef["capacity"]:
                    raise RuntimeError(
                        f"Không thể seed lớp {cid} với capacity={cdef['capacity']} "
                        f"khi đang có {active_cnt} đăng ký ACTIVE. Hãy chạy reset_lab trước."
                    )
                rem = cdef["capacity"] - active_cnt
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
                    ON CONFLICT (course_class_id) DO UPDATE
                    SET class_code = EXCLUDED.class_code,
                        course_code = EXCLUDED.course_code,
                        course_name = EXCLUDED.course_name,
                        credits = EXCLUDED.credits,
                        capacity = EXCLUDED.capacity,
                        remaining_seats = EXCLUDED.capacity - %s,
                        status = EXCLUDED.status,
                        tuition_amount = EXCLUDED.tuition_amount,
                        updated_at = NOW()
                    """,
                    (
                        cid,
                        cdef["class_code"],
                        cdef["course_code"],
                        cdef["course_name"],
                        cdef["credits"],
                        cdef["capacity"],
                        rem,
                        cdef["status"],
                        cdef["tuition_amount"],
                        active_cnt,
                    ),
                )

                conn.execute(
                    "DELETE FROM course_class_schedules WHERE course_class_id = %s",
                    (cid,),
                )
                for slot in cdef["schedule"]:
                    conn.execute(
                        """
                        INSERT INTO course_class_schedules (
                            course_class_id, day_of_week, start_period, end_period, room
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            cid,
                            slot["day_of_week"],
                            slot["start_period"],
                            slot["end_period"],
                            slot["room"],
                        ),
                    )

                conn.execute(
                    "DELETE FROM course_class_prerequisites WHERE course_class_id = %s",
                    (cid,),
                )
                for idx, pcode in enumerate(cdef["prerequisites"]):
                    conn.execute(
                        """
                        INSERT INTO course_class_prerequisites (
                            course_class_id, prerequisite_course_code, sort_order
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (cid, pcode, idx),
                    )

            # 5. Synchronize `course_class_id_seq` to max numeric suffix in `course_classes`
            conn.execute(
                """
                SELECT setval(
                    'course_class_id_seq',
                    GREATEST(
                        COALESCE(
                            (SELECT MAX(SUBSTRING(course_class_id FROM 4)::bigint) FROM course_classes),
                            1
                        ),
                        1
                    ),
                    true
                )
                """
            )

            total_users = int(
                (conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone() or {"cnt": 0})["cnt"]
            )
            total_classes = int(
                (
                    conn.execute("SELECT COUNT(*) AS cnt FROM course_classes").fetchone()
                    or {"cnt": 0}
                )["cnt"]
            )

    return {
        "users_total": total_users,
        "users_inserted": len(missing_accounts),
        "classes_total": total_classes,
    }


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Seed dữ liệu mẫu cho UI (TV3) hoặc đo tải k6 (chỉ dùng cho môi trường lab/dev)."
    )
    parser.add_argument(
        "--mode",
        choices=["ui", "loadtest"],
        default="ui",
        help="Bộ dữ liệu cần nạp: 'ui' (LHP001..003 có lịch/tiên quyết) hoặc 'loadtest' (LHP001 1000 chỗ rỗng lịch/tiên quyết).",
    )
    parser.add_argument(
        "--student-count",
        type=int,
        default=3000,
        help="Số lượng tài khoản sinh viên SV0001..SVxxxx (mặc định 3000).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Ghi đè DATABASE_URL.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.app_env == "prod":
        print("[SEED REFUSED] Không chạy seed mẫu Demo@123456 trên môi trường prod.", file=sys.stderr)
        return 1

    db_url = args.database_url or settings.database_url
    try:
        summary = seed_database(
            db_url,
            mode=args.mode,
            student_count=args.student_count,
            tuition_per_credit=settings.tuition_per_credit,
            oidc_issuer=settings.oidc_issuer,
        )
    except Exception as exc:
        print(f"[SEED ERROR] {exc}", file=sys.stderr)
        return 1

    print(
        f"[SEED OK] mode={args.mode} | users_total={summary['users_total']} "
        f"(new={summary['users_inserted']}) | classes_total={summary['classes_total']} "
        "| LƯU Ý: Mật khẩu mẫu Demo@123456 chỉ dùng trong phòng lab!"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
