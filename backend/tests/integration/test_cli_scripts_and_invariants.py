"""Integration tests for CLI scripts (seed 3,000 users, reset_lab Redis & PG handling, token export, SQL invariants)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import fakeredis
import psycopg
import pytest
from app.core.config import clear_settings_cache
from app.db.migrations import run_migrations
from psycopg.rows import dict_row
from redis.exceptions import ConnectionError as RedisConnectionError
from scripts import reset_lab
from scripts.check_invariants import run_invariant_checks
from scripts.prepare_tokens import prepare_student_tokens
from scripts.reset_lab import IncompleteLabResetError, reset_lab_state
from scripts.seed import seed_database
from tests.conftest import verify_safe_test_database_url

pytestmark = pytest.mark.integration


def test_seed_3000_users_loadtest_reset_guards_and_invariant_checker(
    pg_admin_uri: str,
    test_db_url: str,
    tmp_path: Path,
) -> None:
    cli_db_name = "dkhp_cli_test"
    with psycopg.connect(pg_admin_uri, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{cli_db_name}"')
        conn.execute(f'CREATE DATABASE "{cli_db_name}"')

    parsed_base = urlparse(test_db_url)
    cli_db_url = urlunparse(parsed_base._replace(path=f"/{cli_db_name}"))
    try:
        # 1. Run migrations twice (second run must be a no-op with 0 newly applied)
        applied1 = run_migrations(cli_db_url)
        applied2 = run_migrations(cli_db_url)
        assert applied1 == ["001_initial_schema.sql"]
        assert applied2 == []

        # 2. Seed full 3,000 students + AD0001 in loadtest mode (1000-seat LHP001)
        summary = seed_database(
            cli_db_url,
            mode="loadtest",
            student_count=3000,
            distinct_salts=False,
        )
        assert summary["users_total"] == 3001
        assert summary["classes_total"] == 1

        # Re-running seed does NOT duplicate users
        summary2 = seed_database(
            cli_db_url,
            mode="loadtest",
            student_count=3000,
            distinct_salts=False,
        )
        assert summary2["users_total"] == 3001
        assert summary2["users_inserted"] == 0

        # 3. Pre-generate 1,000 load-test tokens into a temporary export file
        out_file = tmp_path / "tokens_1000.json"
        written = prepare_student_tokens(cli_db_url, count=1000, output_path=out_file)
        assert written == 1000
        assert out_file.exists()

        # 4. Production environment reset MUST be refused!
        with pytest.raises(RuntimeError, match="prod"):
            reset_lab_state(cli_db_url, app_env="prod")

        # 5. Lab reset with queue disabled skips Redis cleanly and keeps invariants valid
        res_skip = reset_lab_state(
            cli_db_url,
            app_env="lab",
            clear_sessions=True,
            queue_enabled=False,
        )
        assert res_skip.postgres_reset is True
        assert res_skip.redis_status == "skipped"
        inv_ok = run_invariant_checks(cli_db_url)
        assert inv_ok["ok"] is True

        # 6. Deliberately corrupt remaining_seats directly via raw SQL -> invariant checker MUST detect it!
        with psycopg.connect(cli_db_url, row_factory=dict_row, autocommit=True) as conn:
            conn.execute(
                "UPDATE course_classes SET remaining_seats = 999 WHERE course_class_id = 'LHP001'"
            )
        inv_bad = run_invariant_checks(cli_db_url)
        assert inv_bad["ok"] is False
        assert inv_bad["checks"]["seat_balance_mismatch"]["passed"] is False
    finally:
        with psycopg.connect(pg_admin_uri, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{cli_db_name}"')


def test_reset_lab_redis_success_deletes_only_scoped_keys_and_closes_client(
    clean_db: str,
) -> None:
    fake_srv = fakeredis.FakeServer()
    backing = fakeredis.FakeRedis(server=fake_srv, decode_responses=False)
    backing.zadd("dkhp:queue:waiting", {"SV0001": 1})
    backing.set("dkhp:queue:token:SV0001", b"tok1")
    backing.set("dkhp:rl:login:127.0.0.1", b"5")
    backing.set("other_app:keep_me", b"must_not_be_deleted")

    closed_flag = {"closed": False}

    class TrackedRedisProxy:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def ping(self) -> Any:
            return self._inner.ping()

        def scan_iter(self, **kwargs: Any) -> Any:
            return self._inner.scan_iter(**kwargs)

        def delete(self, *names: Any) -> Any:
            return self._inner.delete(*names)

        def close(self) -> None:
            closed_flag["closed"] = True

    proxy = TrackedRedisProxy(backing)
    outcome = reset_lab_state(
        clean_db,
        app_env="lab",
        queue_enabled=True,
        redis_client=proxy,  # type: ignore[arg-type]
    )
    assert outcome.postgres_reset is True
    assert outcome.redis_status == "reset"
    assert outcome.redis_keys_deleted == 3
    assert closed_flag["closed"] is True

    # App/lab keys deleted, unrelated Redis key preserved (NO FLUSHALL!)
    assert backing.exists("dkhp:queue:waiting") == 0
    assert backing.exists("dkhp:queue:token:SV0001") == 0
    assert backing.exists("dkhp:rl:login:127.0.0.1") == 0
    assert backing.get("other_app:keep_me") == b"must_not_be_deleted"
    backing.close()


def test_reset_lab_redis_failure_when_required_reports_incomplete_closes_client_and_exits_nonzero(
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Seed an active registration row in PostgreSQL so we verify PostgreSQL reset committed
    with psycopg.connect(clean_db, row_factory=dict_row, autocommit=False) as conn:
        with conn.transaction():
            uid = conn.execute("SELECT id FROM users WHERE student_id = 'SV0001'").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO registrations (
                    registration_id, user_id, student_id, course_class_id,
                    class_code, course_name, credits, status, payment_status, tuition_amount
                )
                VALUES ('11111111-1111-4111-8111-111111111111', %s, 'SV0001', 'LHP003',
                        'JAVA-01', 'Lập trình hướng đối tượng với Java', 3, 'ACTIVE', 'UNPAID', 1500000)
                """,
                (uid,),
            )
            conn.execute(
                "UPDATE course_classes SET remaining_seats = 49 WHERE course_class_id = 'LHP003'"
            )

    closed_on_err = {"closed": False}

    class BrokenRedisClient:
        def ping(self) -> bool:
            raise RedisConnectionError("Simulated Redis connection refused")

        def close(self) -> None:
            closed_on_err["closed"] = True

    with pytest.raises(IncompleteLabResetError) as exc_info:
        reset_lab_state(
            clean_db,
            app_env="lab",
            queue_enabled=True,
            redis_client=BrokenRedisClient(),  # type: ignore[arg-type]
        )

    msg = str(exc_info.value)
    assert "reset chưa hoàn tất: PostgreSQL đã xử lý, Redis chưa xử lý" in msg
    assert "rollback" not in msg.lower()
    assert exc_info.value.result.postgres_reset is True
    assert exc_info.value.result.redis_status == "failed"
    assert closed_on_err["closed"] is True

    # Verify PostgreSQL WAS indeed reset and seat restored to 50
    with psycopg.connect(clean_db, row_factory=dict_row) as conn:
        reg_cnt = conn.execute("SELECT COUNT(*) AS c FROM registrations").fetchone()["c"]
        seats = conn.execute(
            "SELECT remaining_seats FROM course_classes WHERE course_class_id = 'LHP003'"
        ).fetchone()["remaining_seats"]
        assert reg_cnt == 0
        assert seats == 50

    # Also verify CLI `main()` returns non-zero exit code (3) and prints exact incomplete message
    monkeypatch.setenv("APP_ENV", "lab")
    monkeypatch.setenv("QUEUE_ENABLED", "true")
    clear_settings_cache()
    try:
        rc = reset_lab.main(
            [
                "--confirm-lab-reset",
                "--database-url",
                clean_db,
                "--redis-url",
                "redis://127.0.0.1:1/0",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 3
        assert "reset chưa hoàn tất: PostgreSQL đã xử lý, Redis chưa xử lý" in captured.err
    finally:
        clear_settings_cache()


def test_reset_lab_queue_disabled_does_not_require_redis_and_logs_skipped(
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("APP_ENV", "lab")
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "none")
    clear_settings_cache()
    try:
        # Even when `--redis-url` points to dead port 1, queue is disabled -> skips Redis and exits 0!
        rc = reset_lab.main(
            [
                "--confirm-lab-reset",
                "--database-url",
                clean_db,
                "--redis-url",
                "redis://127.0.0.1:1/0",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert "phần Redis không được thực hiện" in captured.out
    finally:
        clear_settings_cache()


def test_external_test_db_safety_guard() -> None:
    # Dedicated test DB names pass
    verify_safe_test_database_url(
        "postgresql://dkhp_user:pw@localhost:5432/dkhp_test",
        "postgresql://dkhp_user:pw@localhost:5432/dkhp_dev",
    )
    verify_safe_test_database_url("postgresql://postgres:@127.0.0.1:60400/dkhp_pytest", None)

    # Dev, demo, prod, or identical DB URL MUST be rejected before any destructive op!
    for unsafe_url in (
        "postgresql://dkhp_user:pw@localhost:5432/dkhp_dev",
        "postgresql://dkhp_user:pw@localhost:5432/dkhp_prod_test",
        "postgresql://dkhp_user:pw@localhost:5432/dkhp_demo_test",
        "postgresql://dkhp_user:pw@localhost:5432/dkhp_main",
    ):
        with pytest.raises(RuntimeError):
            verify_safe_test_database_url(unsafe_url)

    with pytest.raises(RuntimeError, match="trùng với DATABASE_URL"):
        verify_safe_test_database_url(
            "postgresql://dkhp_user:pw@127.0.0.1:5432/dkhp_test",
            "postgresql://dkhp_user:pw@localhost:5432/dkhp_test",
        )
