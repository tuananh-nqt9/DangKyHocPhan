"""CLI script to apply versioned PostgreSQL SQL migrations safely."""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.db.migrations import run_migrations

from scripts._console import ensure_utf8_stdio


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Chạy SQL migrations cho Backend-DKHP.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Ghi đè DATABASE_URL (mặc định đọc từ biến môi trường / .env).",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    try:
        applied = run_migrations(db_url)
    except Exception as exc:
        print(f"[MIGRATE ERROR] {exc}", file=sys.stderr)
        return 1

    if applied:
        print(f"[MIGRATE OK] Đã áp dụng {len(applied)} migration: {', '.join(applied)}")
    else:
        print("[MIGRATE OK] Lược đồ cơ sở dữ liệu đã ở phiên bản mới nhất.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
