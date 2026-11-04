"""Local portable PostgreSQL 16 helper for Windows dev environments without Docker Desktop.

Uses `pgserver` (PostgreSQL 16 binaries installed inside `.venv`) to host a local DB
inside `.pgdata/dev` so TV2 can test migrations, seeding, and API flows immediately.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import psycopg

from scripts._console import ensure_utf8_stdio


def main() -> int:
    ensure_utf8_stdio()
    try:
        import pgserver
    except ImportError:
        print(
            "Chưa cài gói `pgserver` trong môi trường dev. Chạy: pip install pgserver",
            file=sys.stderr,
        )
        return 1

    parser = argparse.ArgumentParser(description="Khởi chạy PostgreSQL 16 cục bộ không cần Docker.")
    parser.add_argument(
        "--pgdata",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".pgdata" / "dev_instance",
    )
    parser.add_argument("--db-name", default="dkhp_dev")
    args = parser.parse_args()

    args.pgdata.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(args.pgdata)
    admin_uri = server.get_uri()

    with psycopg.connect(admin_uri, autocommit=True) as conn:
        for db in (args.db_name, "dkhp_test"):
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{db}"')

    dev_uri = server.get_uri(database=args.db_name)
    test_uri = server.get_uri(database="dkhp_test")
    print("=" * 72)
    print("[LOCAL POSTGRESQL 16 READY]")
    print(f"DATABASE_URL={dev_uri}")
    print(f"TEST_DATABASE_URL={test_uri}")
    print("Nhấn Ctrl+C để dừng PostgreSQL 16 cục bộ.")
    print("=" * 72, flush=True)

    stop = False

    def _handle_sig(_sig: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        while not stop:
            time.sleep(0.5)
    finally:
        server.cleanup()
        print("\n[LOCAL POSTGRESQL 16 STOPPED]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
