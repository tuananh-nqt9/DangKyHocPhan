"""Safe reset script between lab demos and k6 load-test runs.

Strictly refuses `APP_ENV=prod` and requires `--confirm-lab-reset`.
Clears PostgreSQL transactional tables (`payments`, `registrations`, `idempotency_records`,
`sso_exchange_codes`, `sso_transactions`), restores class seats, and handles Redis queue/rate-limit
keys with explicit per-component reporting:
- When queue/Redis rate-limit is enabled or `--reset-redis` is requested: connects to Redis,
  deletes ONLY `dkhp:queue:*` and `dkhp:rl:*` keys (never `FLUSHALL`), always closes the Redis
  client, and fails with non-zero exit code if Redis fails (explicitly reporting when PostgreSQL
  succeeded while Redis did not).
- When queue is disabled and `--reset-redis` is not requested: skips Redis cleanly without
  requiring a running Redis server and reports that Redis reset was skipped.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import psycopg
from app.core.config import get_settings
from psycopg.rows import dict_row
from redis import Redis
from redis.exceptions import RedisError

from scripts._console import ensure_utf8_stdio
from scripts.seed import seed_database

LAB_REDIS_KEY_PATTERNS: tuple[str, ...] = ("dkhp:queue:*", "dkhp:rl:*")


@dataclass(frozen=True)
class ResetLabResult:
    """Per-component outcome of `reset_lab_state`."""

    postgres_reset: bool
    redis_status: Literal["reset", "skipped", "failed"]
    redis_keys_deleted: int = 0
    redis_error: str | None = None


class IncompleteLabResetError(RuntimeError):
    """Raised when PostgreSQL reset committed, but required Redis cleanup failed."""

    def __init__(self, message: str, *, result: ResetLabResult) -> None:
        super().__init__(message)
        self.result = result


def reset_lab_state(
    database_url: str,
    *,
    app_env: str,
    clear_sessions: bool = False,
    drop_classes: bool = False,
    reseed_mode: str | None = None,
    student_count: int = 3000,
    tuition_per_credit: int = 500000,
    oidc_issuer: str = "http://localhost:8081/realms/dkhp",
    queue_enabled: bool = False,
    reset_redis: bool = False,
    rate_limit_backend: str = "none",
    redis_url: str | None = None,
    redis_client: Redis | None = None,
) -> ResetLabResult:
    """Reset PostgreSQL lab state and (when active/requested) scoped Redis keys."""
    if app_env == "prod":
        raise RuntimeError("Từ chối reset trên môi trường APP_ENV=prod!")

    parsed = urlparse(database_url)
    db_name = (parsed.path or "").lstrip("/").lower()
    if "prod" in db_name:
        raise RuntimeError(
            f"Từ chối reset vì tên cơ sở dữ liệu '{db_name}' có dấu hiệu production!"
        )

    need_redis = bool(queue_enabled or reset_redis or rate_limit_backend == "redis")
    if need_redis and redis_client is None and not (redis_url or "").strip():
        raise ValueError(
            "Cần cung cấp REDIS_URL hợp lệ khi queue/rate-limit Redis đang bật hoặc truyền --reset-redis."
        )

    should_drop_classes = bool(drop_classes or reseed_mode is not None)

    # 1. PostgreSQL reset phase (atomic transaction)
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=False) as conn:
        with conn.transaction():
            conn.execute("SET LOCAL timezone = 'GMT'")
            conn.execute("DELETE FROM payments")
            conn.execute("DELETE FROM registrations")
            conn.execute("DELETE FROM idempotency_records")
            conn.execute("DELETE FROM sso_exchange_codes")
            conn.execute("DELETE FROM sso_transactions")
            if clear_sessions:
                conn.execute("DELETE FROM sessions")
            if should_drop_classes:
                conn.execute("DELETE FROM course_class_schedules")
                conn.execute("DELETE FROM course_class_prerequisites")
                conn.execute("DELETE FROM course_classes")
                conn.execute("SELECT setval('course_class_id_seq', 1, false)")
            else:
                conn.execute(
                    "UPDATE course_classes SET remaining_seats = capacity, updated_at = NOW()"
                )

    if reseed_mode is not None:
        seed_database(
            database_url,
            mode=reseed_mode,
            student_count=student_count,
            tuition_per_credit=tuition_per_credit,
            oidc_issuer=oidc_issuer,
        )

    # 2. Redis reset phase (only when queue/redis-rl is active or explicitly requested)
    if not need_redis:
        return ResetLabResult(
            postgres_reset=True,
            redis_status="skipped",
            redis_keys_deleted=0,
            redis_error=None,
        )

    r_client = redis_client or Redis.from_url(
        str(redis_url),
        socket_timeout=1.5,
        socket_connect_timeout=1.5,
    )
    deleted_count = 0
    try:
        r_client.ping()
        for pattern in LAB_REDIS_KEY_PATTERNS:
            keys = list(r_client.scan_iter(match=pattern, count=500))
            if keys:
                deleted_count += int(r_client.delete(*keys))
    except RedisError as exc:
        err_detail = str(exc) or type(exc).__name__
        failed_res = ResetLabResult(
            postgres_reset=True,
            redis_status="failed",
            redis_keys_deleted=deleted_count,
            redis_error=err_detail,
        )
        raise IncompleteLabResetError(
            f"reset chưa hoàn tất: PostgreSQL đã xử lý, Redis chưa xử lý ({err_detail})",
            result=failed_res,
        ) from exc
    finally:
        try:
            r_client.close()
        except Exception:
            pass

    return ResetLabResult(
        postgres_reset=True,
        redis_status="reset",
        redis_keys_deleted=deleted_count,
        redis_error=None,
    )


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Reset dữ liệu giao dịch giữa các lượt đo tải / demo phòng lab."
    )
    parser.add_argument(
        "--confirm-lab-reset",
        action="store_true",
        help="Xác nhận tường minh thao tác xóa registrations/payments/idempotency trong DB lab.",
    )
    parser.add_argument(
        "--clear-sessions",
        action="store_true",
        help="Xóa luôn các phiên token đang có (mặc định giữ lại token chuẩn bị cho k6).",
    )
    parser.add_argument(
        "--reset-redis",
        action="store_true",
        help="Yêu cầu dọn các key dkhp:queue:* và dkhp:rl:* trên Redis ngay cả khi QUEUE_ENABLED=false.",
    )
    parser.add_argument(
        "--reseed",
        choices=["ui", "loadtest"],
        default=None,
        help="Nạp lại cấu hình lớp học phần ngay sau khi xóa sạch lớp cũ ('ui' hoặc 'loadtest').",
    )
    parser.add_argument(
        "--student-count",
        type=int,
        default=3000,
        help="Số lượng sinh viên khi dùng kèm --reseed.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--redis-url", default=None)
    args = parser.parse_args(argv)

    if not args.confirm_lab_reset:
        print(
            "[RESET REFUSED] Bắt buộc truyền cờ --confirm-lab-reset để xác nhận xóa dữ liệu lab.",
            file=sys.stderr,
        )
        return 2

    settings = get_settings()
    db_url = args.database_url or settings.database_url
    target_redis_url = args.redis_url if args.redis_url is not None else settings.redis_url

    try:
        outcome = reset_lab_state(
            db_url,
            app_env=settings.app_env,
            clear_sessions=args.clear_sessions,
            drop_classes=(args.reseed is not None),
            reseed_mode=args.reseed,
            student_count=args.student_count,
            tuition_per_credit=settings.tuition_per_credit,
            oidc_issuer=settings.oidc_issuer,
            queue_enabled=settings.queue_enabled,
            reset_redis=args.reset_redis,
            rate_limit_backend=settings.rate_limit_backend,
            redis_url=target_redis_url,
        )
    except IncompleteLabResetError as exc:
        print(f"[RESET INCOMPLETE] {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[RESET ERROR] {exc}", file=sys.stderr)
        return 1

    redis_summary = (
        f"Redis đã xử lý (đã xóa {outcome.redis_keys_deleted} key phạm vi dkhp:queue:*/dkhp:rl:*)"
        if outcome.redis_status == "reset"
        else "phần Redis không được thực hiện (queue đang tắt và không yêu cầu --reset-redis)"
    )
    print(
        f"[RESET OK] PostgreSQL đã xử lý"
        f"{' (+ xóa sessions)' if args.clear_sessions else ''}"
        f"{f' (+ reseed mode={args.reseed})' if args.reseed else ''}; "
        f"{redis_summary}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
