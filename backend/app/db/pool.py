"""PostgreSQL 16 connection pool and transaction orchestration using psycopg 3."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode


class DatabaseManager:
    """Per-worker synchronous psycopg_pool ConnectionPool manager.

    Connections are never opened at module import time; `open()` and `close()`
    are bound to the FastAPI application lifespan in each worker process.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: ConnectionPool[Connection[dict[str, Any]]] | None = None

    @property
    def is_open(self) -> bool:
        return self._pool is not None

    def open(self) -> None:
        if self._pool is not None:
            return
        self._pool = ConnectionPool(
            conninfo=self._settings.database_url,
            min_size=self._settings.db_pool_min_size,
            max_size=self._settings.db_pool_max_size,
            timeout=self._settings.db_pool_timeout_seconds,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def get_pool_stats(self) -> dict[str, int]:
        if self._pool is None:
            return {}
        return self._pool.get_stats()

    @contextmanager
    def connection(self) -> Iterator[Connection[dict[str, Any]]]:
        """Acquire a connection from the pool for short-lived queries."""
        if self._pool is None:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Kết nối cơ sở dữ liệu chưa sẵn sàng.",
            )
        try:
            with self._pool.connection(timeout=self._settings.db_pool_timeout_seconds) as conn:
                yield conn
        except PoolTimeout as exc:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_BUSY,
                message="Hệ thống đang bận chờ kết nối cơ sở dữ liệu. Vui lòng thử lại.",
            ) from exc
        except psycopg.OperationalError as exc:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Dịch vụ cơ sở dữ liệu tạm thời gián đoạn.",
            ) from exc

    @contextmanager
    def read_snapshot(self, *, repeatable_read: bool = False) -> Iterator[Connection[dict[str, Any]]]:
        """Execute a short read-only transaction with statement_timeout and UTC timezone."""
        stmt_ms = int(self._settings.db_statement_timeout_ms)
        with self.connection() as conn:
            try:
                with conn.transaction():
                    if repeatable_read:
                        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    else:
                        conn.execute("SET TRANSACTION READ ONLY")
                    conn.execute("SET LOCAL timezone = 'GMT'")
                    conn.execute(f"SET LOCAL statement_timeout = '{stmt_ms}ms'")
                    yield conn
            except AppError:
                raise
            except psycopg.errors.QueryCanceled as exc:
                raise AppError(
                    status_code=503,
                    code=ErrorCode.SERVICE_BUSY,
                    message="Truy vấn quá thời gian cho phép.",
                ) from exc
            except psycopg.OperationalError as exc:
                raise AppError(
                    status_code=503,
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Không thể đọc dữ liệu từ cơ sở dữ liệu.",
                ) from exc

    @contextmanager
    def transaction(
        self,
        *,
        lock_timeout_ms: int | None = None,
        statement_timeout_ms: int | None = None,
    ) -> Iterator[Connection[dict[str, Any]]]:
        """Execute an atomic READ COMMITTED write transaction.

        Uses `SET LOCAL` so timeouts never leak across pooled requests.
        Distinguishes known rollback errors (`SERVICE_BUSY`) from uncertain
        commit/network interruptions (`SERVICE_UNAVAILABLE`).
        """
        lock_ms = int(
            lock_timeout_ms if lock_timeout_ms is not None else self._settings.db_lock_timeout_ms
        )
        stmt_ms = int(
            statement_timeout_ms
            if statement_timeout_ms is not None
            else self._settings.db_statement_timeout_ms
        )
        with self.connection() as conn:
            body_finished = False
            try:
                with conn.transaction():
                    conn.execute("SET LOCAL timezone = 'GMT'")
                    conn.execute(f"SET LOCAL lock_timeout = '{lock_ms}ms'")
                    conn.execute(f"SET LOCAL statement_timeout = '{stmt_ms}ms'")
                    yield conn
                    body_finished = True
            except AppError:
                raise
            except (psycopg.errors.LockNotAvailable, psycopg.errors.DeadlockDetected) as exc:
                # PostgreSQL guaranteed rollback before commit
                raise AppError(
                    status_code=503,
                    code=ErrorCode.SERVICE_BUSY,
                    message="Tài nguyên đang bận xử lý giao dịch khác. Giao dịch đã được hoàn tác an toàn.",
                ) from exc
            except psycopg.errors.QueryCanceled as exc:
                if not body_finished:
                    raise AppError(
                        status_code=503,
                        code=ErrorCode.SERVICE_BUSY,
                        message="Thao tác vượt quá thời gian xử lý và đã được hoàn tác.",
                    ) from exc
                raise AppError(
                    status_code=503,
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Không thể xác nhận trạng thái hoàn tất giao dịch. Vui lòng kiểm tra lại bằng cùng Idempotency-Key.",
                ) from exc
            except psycopg.OperationalError as exc:
                # If network failed during COMMIT (`body_finished=True`), outcome is uncertain!
                raise AppError(
                    status_code=503,
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Kết nối cơ sở dữ liệu bị ngắt trong quá trình xử lý. Vui lòng đối soát hoặc gửi lại cùng Idempotency-Key.",
                ) from exc
