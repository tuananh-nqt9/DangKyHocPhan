"""Controllable UTC clock utilities.

All timestamps stored in PostgreSQL use TIMESTAMPTZ (UTC) and serialize as ISO 8601
with trailing 'Z' (e.g. '2026-11-01T08:30:00Z'). Tests may override the clock
cleanly via `Clock.override` without sleeping in wall-clock time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta


class Clock:
    """Thread-safe / process-local controllable UTC clock."""

    _provider: Callable[[], datetime] | None = None

    @classmethod
    def now(cls) -> datetime:
        if cls._provider is not None:
            dt = cls._provider()
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        return datetime.now(UTC)

    @classmethod
    @contextmanager
    def override(cls, fixed_or_fn: datetime | Callable[[], datetime]) -> Iterator[None]:
        prev = cls._provider
        if callable(fixed_or_fn):
            cls._provider = fixed_or_fn
        else:
            fixed_utc = (
                fixed_or_fn.replace(tzinfo=UTC)
                if fixed_or_fn.tzinfo is None
                else fixed_or_fn.astimezone(UTC)
            )
            cls._provider = lambda: fixed_utc
        try:
            yield
        finally:
            cls._provider = prev

    @classmethod
    @contextmanager
    def advance(cls, delta: timedelta) -> Iterator[None]:
        base = cls.now()
        with cls.override(base + delta):
            yield


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return Clock.now()


def format_utc_z(dt: datetime | None) -> str | None:
    """Format a datetime as UTC ISO 8601 string with trailing 'Z'."""
    if dt is None:
        return None
    utc_dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    # Keep whole-second ISO 8601 'Z' when microseconds == 0, else standard microsecond ISO 'Z'
    if utc_dt.microsecond == 0:
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return utc_dt.isoformat().replace("+00:00", "Z")
