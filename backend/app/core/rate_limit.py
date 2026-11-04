"""Configurable supplementary rate limiter.

Explicitly distinguishes per-worker in-memory limiting from multi-worker Redis limiting.
Primary production/load-test rate limiting should be enforced at Nginx (`limit_req_zone`)
with standardized JSON 429 + Retry-After, or via `RATE_LIMIT_BACKEND=redis`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = 1

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local last_ts = tonumber(data[2])

if tokens == nil or last_ts == nil then
    tokens = burst
    last_ts = now
else
    local elapsed = math.max(0, now - last_ts)
    tokens = math.min(burst, tokens + elapsed * rate)
    last_ts = now
end

if tokens < cost then
    local retry_after = math.max(1, math.ceil((cost - tokens) / rate))
    redis.call('HMSET', key, 'tokens', tokens, 'ts', last_ts)
    redis.call('EXPIRE', key, math.max(60, math.ceil(burst / rate) * 2))
    return {0, retry_after}
end

tokens = tokens - cost
redis.call('HMSET', key, 'tokens', tokens, 'ts', last_ts)
redis.call('EXPIRE', key, math.max(60, math.ceil(burst / rate) * 2))
return {1, 0}
"""


@dataclass
class _Bucket:
    tokens: float
    last_ts: float


class RateLimiter:
    """Rate limiter supporting 'none', per-worker 'memory', or shared 'redis'."""

    def __init__(self, settings: Settings, redis_client: Redis | None = None) -> None:
        self._settings = settings
        self._redis = redis_client
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    def check(self, scope_key: str, *, rate_per_sec: float, burst: int) -> None:
        backend = self._settings.rate_limit_backend
        if backend == "none":
            return

        now = time.monotonic()
        if backend == "redis" and self._redis is not None:
            try:
                res = self._redis.eval(
                    _TOKEN_BUCKET_LUA,
                    1,
                    f"dkhp:rl:{scope_key}",
                    str(rate_per_sec),
                    str(burst),
                    str(time.time()),
                )
                allowed = int(res[0])
                retry_after = int(res[1])
                if not allowed:
                    raise AppError(
                        status_code=429,
                        code=ErrorCode.RATE_LIMITED,
                        message="Quá nhiều yêu cầu. Vui lòng thử lại sau.",
                        headers={"Retry-After": str(max(1, retry_after))},
                    )
                return
            except RedisError:
                # Fall back to per-worker memory bucket only if Redis rate-limit call fails
                pass

        with self._lock:
            bucket = self._buckets.get(scope_key)
            if bucket is None:
                bucket = _Bucket(tokens=float(burst), last_ts=now)
                self._buckets[scope_key] = bucket
            else:
                elapsed = max(0.0, now - bucket.last_ts)
                bucket.tokens = min(float(burst), bucket.tokens + elapsed * rate_per_sec)
                bucket.last_ts = now

            if bucket.tokens < 1.0:
                retry_after = max(1, int((1.0 - bucket.tokens) / rate_per_sec) + 1)
                raise AppError(
                    status_code=429,
                    code=ErrorCode.RATE_LIMITED,
                    message="Quá nhiều yêu cầu. Vui lòng thử lại sau.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0
