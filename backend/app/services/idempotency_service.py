"""Transactional idempotency service across multiple workers (Spec Section 18)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from psycopg import Connection

from app.core.clock import utc_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, build_error_envelope
from app.db.pool import DatabaseManager
from app.repositories.idempotency_repo import IdempotencyRepository


class FaultHooks:
    """Internal test-only fault injection hooks (TC10, TC11, TC25).

    NEVER exposed via any HTTP header, query param, or public endpoint.
    Only set directly inside automated Python test processes.
    """

    after_registration_insert: Callable[[], None] | None = None
    after_commit_before_response: Callable[[], None] | None = None
    in_transaction_hold: Callable[[], None] | None = None

    @classmethod
    def reset(cls) -> None:
        cls.after_registration_insert = None
        cls.after_commit_before_response = None
        cls.in_transaction_hold = None


@dataclass(frozen=True)
class DomainOperationResult:
    status_code: int
    code: str
    message: str
    data: dict[str, Any]


@dataclass(frozen=True)
class IdempotencyExecutionOutcome:
    status_code: int
    body: dict[str, Any]
    replayed: bool
    original_request_id: str


def compute_request_fingerprint(
    method: str,
    canonical_path: str,
    body_dict: dict[str, Any] | None,
) -> str:
    """Compute SHA-256 fingerprint of `(METHOD, canonical_path, canonical_json_body)`.

    Excludes access token, queue token, and request_id so token refresh never breaks replay.
    """
    method_norm = method.strip().upper()
    path_norm = canonical_path.strip()
    if body_dict is None:
        body_norm = ""
    else:
        body_norm = json.dumps(
            body_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    raw = f"{method_norm}\n{path_norm}\n{body_norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyService:
    """Coordinates fast replay pre-checks and atomic in-transaction idempotency persistence."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        repo: IdempotencyRepository | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._repo = repo or IdempotencyRepository()

    def precheck_completed_record(
        self,
        *,
        user_id: int,
        idempotency_key: str,
        fingerprint: str,
    ) -> IdempotencyExecutionOutcome | None:
        """Fast check before queue token verification.

        Allows already-committed operations to replay even if the student's queue token
        has subsequently expired, and rejects key reuse with a different payload (`422`).
        """
        now = utc_now()
        with self._db.read_snapshot() as conn:
            rec = self._repo.get_record(
                conn,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            if rec is None:
                return None
            if rec["expires_at"] <= now:
                return None
            if str(rec["fingerprint"]) != fingerprint:
                raise AppError(
                    status_code=422,
                    code=ErrorCode.IDEMPOTENCY_KEY_REUSED,
                    message="Idempotency-Key đã được sử dụng cho một thao tác hoặc dữ liệu khác.",
                )
            return IdempotencyExecutionOutcome(
                status_code=int(rec["response_status"]),
                body=dict(rec["response_body"]),
                replayed=True,
                original_request_id=str(rec["original_request_id"]),
            )

    def execute(
        self,
        *,
        user_id: int,
        idempotency_key: str,
        request_method: str,
        request_path: str,
        fingerprint: str,
        request_id: str,
        operation: Callable[[Connection[dict[str, Any]]], DomainOperationResult],
    ) -> IdempotencyExecutionOutcome:
        """Serialize same-key calls, execute `operation`, and commit result + idempotency atomically."""
        outcome: IdempotencyExecutionOutcome | None = None

        with self._db.transaction() as conn:
            # 1. Serialize concurrent requests with the exact same (user_id, idempotency_key)
            self._repo.acquire_xact_lock(
                conn,
                user_id=user_id,
                idempotency_key=idempotency_key,
                idempotency_lock_timeout_ms=self._settings.db_idempotency_lock_timeout_ms,
                restore_lock_timeout_ms=self._settings.db_lock_timeout_ms,
            )

            now = utc_now()
            # 2. Clean up if an old record for this key has expired (>24h)
            self._repo.delete_if_expired(
                conn,
                user_id=user_id,
                idempotency_key=idempotency_key,
                now_utc=now,
            )

            # 3. Re-check after acquiring the advisory lock (handles concurrent duplicate arrivals)
            existing = self._repo.get_record(
                conn,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                if str(existing["fingerprint"]) != fingerprint:
                    raise AppError(
                        status_code=422,
                        code=ErrorCode.IDEMPOTENCY_KEY_REUSED,
                        message="Idempotency-Key đã được sử dụng cho một thao tác hoặc dữ liệu khác.",
                    )
                outcome = IdempotencyExecutionOutcome(
                    status_code=int(existing["response_status"]),
                    body=dict(existing["response_body"]),
                    replayed=True,
                    original_request_id=str(existing["original_request_id"]),
                )
            else:
                if FaultHooks.in_transaction_hold is not None:
                    FaultHooks.in_transaction_hold()

                # 4. Run business logic inside a SAVEPOINT so deterministic business errors
                # roll back partial writes while allowing the outer transaction to persist
                # the deterministic error response in `idempotency_records` and COMMIT.
                try:
                    with conn.transaction():
                        op_res = operation(conn)
                        response_status = op_res.status_code
                        response_code = op_res.code
                        response_body: dict[str, Any] = {
                            "success": True,
                            "code": op_res.code,
                            "message": op_res.message,
                            "data": op_res.data,
                            "request_id": request_id,
                        }
                except AppError as domain_err:
                    if not domain_err.persist_idempotency:
                        raise
                    response_status = domain_err.status_code
                    response_code = str(domain_err.code)
                    response_body = build_error_envelope(
                        code=domain_err.code,
                        message=domain_err.message,
                        request_id=request_id,
                        errors=domain_err.errors,
                    )

                # Validate JSON serializability BEFORE commit
                json.dumps(response_body, ensure_ascii=False)

                completed_at = utc_now()
                expires_at = completed_at + timedelta(seconds=self._settings.idempotency_ttl_seconds)
                self._repo.save_record(
                    conn,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    request_method=request_method.upper(),
                    request_path=request_path,
                    fingerprint=fingerprint,
                    response_status=response_status,
                    response_code=response_code,
                    response_body=response_body,
                    original_request_id=request_id,
                    created_at=completed_at,
                    expires_at=expires_at,
                )
                outcome = IdempotencyExecutionOutcome(
                    status_code=response_status,
                    body=response_body,
                    replayed=False,
                    original_request_id=request_id,
                )

        # Outer PostgreSQL transaction is now COMMITTED.
        assert outcome is not None
        if not outcome.replayed and FaultHooks.after_commit_before_response is not None:
            FaultHooks.after_commit_before_response()
        return outcome

    def cleanup_expired(self, batch_size: int = 1000) -> int:
        with self._db.transaction() as conn:
            return self._repo.cleanup_expired_batch(
                conn,
                now_utc=utc_now(),
                batch_size=batch_size,
            )
