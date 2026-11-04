"""Pre-generate opaque access/refresh tokens for k6 load testing (Spec Section 25).

Avoids including Argon2id login CPU time inside `/api/v1/register` benchmark runs.
Writes tokens strictly to a gitignored export file (`exports/loadtest_tokens.json`).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg
from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.security import generate_opaque_token, hash_token
from psycopg.rows import dict_row

from scripts._console import ensure_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "exports" / "loadtest_tokens.json"


def prepare_student_tokens(
    database_url: str,
    *,
    count: int = 1000,
    access_ttl_seconds: int = 7200,
    session_ttl_seconds: int = 28800,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> int:
    if count < 1 or count > 3000:
        raise ValueError("count phải nằm trong khoảng 1..3000.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    abs_exp = now + timedelta(seconds=session_ttl_seconds)
    acc_exp = min(abs_exp, now + timedelta(seconds=access_ttl_seconds))

    target_sids = [f"SV{i:04d}" for i in range(1, count + 1)]
    exported: list[dict[str, object]] = []
    session_rows: list[tuple[object, ...]] = []

    with psycopg.connect(database_url, row_factory=dict_row, autocommit=False) as conn:
        with conn.transaction():
            conn.execute("SET LOCAL timezone = 'GMT'")
            rows = conn.execute(
                """
                SELECT id, student_id
                FROM users
                WHERE student_id = ANY(%s) AND role = 'STUDENT'
                ORDER BY student_id ASC
                """,
                (target_sids,),
            ).fetchall()

            if len(rows) < count:
                raise RuntimeError(
                    f"Chỉ tìm thấy {len(rows)}/{count} sinh viên trong DB. "
                    "Hãy chạy `python -m scripts.seed --mode loadtest` trước!"
                )

            for idx, urow in enumerate(rows):
                raw_access = generate_opaque_token(32)
                raw_refresh = generate_opaque_token(32)
                session_id = str(uuid.uuid4())
                session_rows.append(
                    (
                        session_id,
                        int(urow["id"]),
                        hash_token(raw_access),
                        hash_token(raw_refresh),
                        acc_exp,
                        abs_exp,
                        abs_exp,
                        now,
                        now,
                    )
                )
                exported.append(
                    {
                        "iteration": idx,
                        "student_id": str(urow["student_id"]),
                        "access_token": raw_access,
                    }
                )

            with conn.cursor() as cur:
                cur.executemany(
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
                    session_rows,
                )

    output_path.write_text(
        json.dumps(
            {
                "note": "LAB LOAD-TEST TOKENS ONLY — GITIGNORED, NEVER COMMIT!",
                "count": len(exported),
                "course_class_id": "LHP001",
                "tokens": exported,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return len(exported)


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Chuẩn bị sẵn access token cho 1.000 sinh viên phục vụ bài đo tải k6."
    )
    parser.add_argument("--count", type=int, default=1000, help="Số lượng sinh viên (mặc định 1000).")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Đường dẫn file JSON xuất ra (nằm trong thư mục gitignored `exports/`).",
    )
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    settings = get_settings()
    if settings.app_env == "prod":
        print("[PREPARE TOKENS REFUSED] Không xuất token hàng loạt ở môi trường prod.", file=sys.stderr)
        return 1

    db_url = args.database_url or settings.database_url
    try:
        written = prepare_student_tokens(
            db_url,
            count=args.count,
            access_ttl_seconds=max(settings.access_token_ttl_seconds, 7200),
            session_ttl_seconds=settings.session_absolute_ttl_seconds,
            output_path=args.output,
        )
    except Exception as exc:
        print(f"[PREPARE TOKENS ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[PREPARE TOKENS OK] Đã tạo {written} phiên và lưu vào: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
