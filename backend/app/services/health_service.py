"""Health check service probing PostgreSQL and (when queue enabled) Redis (Spec Section 17)."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.pool import DatabaseManager
from app.services.queue_service import QueueService


class HealthService:
    """Executes real liveness/readiness probes against configured infrastructure."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        queue_service: QueueService,
    ) -> None:
        self._db = db
        self._settings = settings
        self._queue_service = queue_service

    def check_health(self) -> dict[str, Any]:
        # 1. Probe PostgreSQL 16 with `SELECT 1`
        try:
            with self._db.read_snapshot() as conn:
                row = conn.execute("SELECT 1 AS ok").fetchone()
                if row is None or int(row["ok"]) != 1:
                    raise AppError(
                        status_code=503,
                        code=ErrorCode.SERVICE_UNAVAILABLE,
                        message="Kiểm tra kết nối cơ sở dữ liệu thất bại.",
                    )
        except AppError as err:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Cơ sở dữ liệu hiện không sẵn sàng.",
            ) from err

        # 2. When queue regulation is enabled, Redis MUST also be healthy (fail closed)
        if self._settings.queue_enabled and not self._queue_service.ping():
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Hàng đợi Redis đang bật nhưng không phản hồi.",
            )

        return {
            "status": "UP",
            "database": "UP",
            "api_version": self._settings.api_version,
            "features": {
                "payments": self._settings.payments_enabled,
                "sso": self._settings.sso_enabled,
                "queue": self._settings.queue_enabled,
            },
        }
