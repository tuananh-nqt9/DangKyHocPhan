"""Structured JSON logging with strict secret redaction."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.core.clock import format_utc_z, utc_now

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "access_token",
        "refresh_token",
        "authorization",
        "x-queue-token",
        "queue_token",
        "exchange_code",
        "code",
        "state",
        "nonce",
        "code_verifier",
        "client_secret",
        "oidc_client_secret",
        "cookie",
        "set-cookie",
    }
)


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys from dictionaries before logging."""
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            redacted[key] = value
    return redacted


class StructuredJsonFormatter(logging.Formatter):
    """Emit single-line JSON logs suitable for Nginx/Docker log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": format_utc_z(utc_now()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "structured", None)
        if isinstance(extra_fields, dict):
            payload.update(redact_dict(extra_fields))
        if record.exc_info:
            payload["exc_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] is not None else "Exception"
            )
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level_name: str = "INFO") -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass
    level = getattr(logging, level_name.upper(), logging.INFO)
    root = logging.getLogger("dkhp")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        root.addHandler(handler)
    root.propagate = False


def get_logger(name: str = "dkhp.api") -> logging.Logger:
    return logging.getLogger(name)
