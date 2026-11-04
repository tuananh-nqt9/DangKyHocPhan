"""Atomic Redis FIFO queue service using Lua scripts (Spec Section 16)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.clock import format_utc_z, utc_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import constant_time_equals, generate_opaque_token

# Common Lua preamble: reaps expired READY slots (marking them EXPIRED)
# and promotes FIFO WAITING users using their pre-generated CSPRNG tokens.
_REAP_AND_PROMOTE_LUA = """
local waiting_key = KEYS[1]
local ready_key = KEYS[2]
local seq_key = KEYS[3]
local token_prefix = KEYS[4]
local pending_prefix = KEYS[5]
local expired_prefix = KEYS[6]

local now_ms = tonumber(ARGV[1])
local max_ready = tonumber(ARGV[2])
local ready_ttl_ms = tonumber(ARGV[3])
local expired_ttl_sec = tonumber(ARGV[4])

-- 1. Reap expired READY entries
local expired_users = redis.call('ZRANGEBYSCORE', ready_key, '-inf', now_ms)
for _, uid in ipairs(expired_users) do
    redis.call('ZREM', ready_key, uid)
    redis.call('DEL', token_prefix .. uid)
    redis.call('SET', expired_prefix .. uid, '1', 'EX', expired_ttl_sec)
end

-- 2. Promote FIFO WAITING entries while READY slots are available
local ready_count = redis.call('ZCARD', ready_key)
while ready_count < max_ready do
    local popped = redis.call('ZPOPMIN', waiting_key, 1)
    if not popped or #popped == 0 then
        break
    end
    local next_uid = popped[1]
    local pending_tok = redis.call('GET', pending_prefix .. next_uid)
    redis.call('DEL', pending_prefix .. next_uid)
    if pending_tok then
        local exp_ms = now_ms + ready_ttl_ms
        redis.call('ZADD', ready_key, exp_ms, next_uid)
        redis.call('HSET', token_prefix .. next_uid, 'token', pending_tok, 'exp_ms', tostring(exp_ms))
        redis.call('PEXPIRE', token_prefix .. next_uid, ready_ttl_ms + 60000)
        redis.call('DEL', expired_prefix .. next_uid)
        ready_count = ready_count + 1
    end
end
"""

_JOIN_LUA = (
    _REAP_AND_PROMOTE_LUA
    + """
local caller_uid = ARGV[5]
local candidate_token = ARGV[6]

-- Already READY? Return current READY state WITHOUT extending TTL
local existing_exp = redis.call('ZSCORE', ready_key, caller_uid)
if existing_exp and tonumber(existing_exp) > now_ms then
    local tok = redis.call('HGET', token_prefix .. caller_uid, 'token')
    return {'READY', '', tostring(math.floor(tonumber(existing_exp))), tok or ''}
end

-- Already WAITING? Return current 1-based FIFO position
local existing_rank = redis.call('ZRANK', waiting_key, caller_uid)
if existing_rank ~= false then
    return {'WAITING', tostring(existing_rank + 1), '', ''}
end

-- Clear previous EXPIRED marker on fresh join
redis.call('DEL', expired_prefix .. caller_uid)

-- Grant READY immediately if capacity permits and nobody is waiting ahead
local current_ready = redis.call('ZCARD', ready_key)
local current_waiting = redis.call('ZCARD', waiting_key)
if current_ready < max_ready and current_waiting == 0 then
    local exp_ms = now_ms + ready_ttl_ms
    redis.call('ZADD', ready_key, exp_ms, caller_uid)
    redis.call('HSET', token_prefix .. caller_uid, 'token', candidate_token, 'exp_ms', tostring(exp_ms))
    redis.call('PEXPIRE', token_prefix .. caller_uid, ready_ttl_ms + 60000)
    return {'READY', '', tostring(math.floor(exp_ms)), candidate_token}
end

-- Otherwise enqueue FIFO
local seq = redis.call('INCR', seq_key)
redis.call('SET', pending_prefix .. caller_uid, candidate_token, 'EX', 86400)
redis.call('ZADD', waiting_key, seq, caller_uid)
local rank = redis.call('ZRANK', waiting_key, caller_uid)
return {'WAITING', tostring((rank or 0) + 1), '', ''}
"""
)

_STATUS_LUA = (
    _REAP_AND_PROMOTE_LUA
    + """
local caller_uid = ARGV[5]

local existing_exp = redis.call('ZSCORE', ready_key, caller_uid)
if existing_exp and tonumber(existing_exp) > now_ms then
    local tok = redis.call('HGET', token_prefix .. caller_uid, 'token')
    return {'READY', '', tostring(math.floor(tonumber(existing_exp))), tok or ''}
end

local existing_rank = redis.call('ZRANK', waiting_key, caller_uid)
if existing_rank ~= false then
    return {'WAITING', tostring(existing_rank + 1), '', ''}
end

local was_expired = redis.call('EXISTS', expired_prefix .. caller_uid)
if was_expired == 1 then
    return {'EXPIRED', '', '', ''}
end

return {'NONE', '', '', ''}
"""
)

_RELEASE_LUA = """
local waiting_key = KEYS[1]
local ready_key = KEYS[2]
local seq_key = KEYS[3]
local token_prefix = KEYS[4]
local pending_prefix = KEYS[5]
local expired_prefix = KEYS[6]

local caller_uid = ARGV[5]
redis.call('ZREM', waiting_key, caller_uid)
redis.call('ZREM', ready_key, caller_uid)
redis.call('DEL', token_prefix .. caller_uid)
redis.call('DEL', pending_prefix .. caller_uid)
redis.call('DEL', expired_prefix .. caller_uid)
""" + _REAP_AND_PROMOTE_LUA + "\nreturn 1\n"


class QueueService:
    """Multi-worker FIFO admission queue backed by Redis Lua scripts."""

    KEYS = [
        "dkhp:queue:waiting",
        "dkhp:queue:ready",
        "dkhp:queue:seq",
        "dkhp:queue:token:",
        "dkhp:queue:pending:",
        "dkhp:queue:expired:",
    ]

    def __init__(self, settings: Settings, redis_client: Redis | None = None) -> None:
        self._settings = settings
        self._redis = redis_client

    def set_redis_client(self, redis_client: Redis | None) -> None:
        self._redis = redis_client

    def _require_redis(self) -> Redis:
        if self._redis is None:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Hàng đợi đăng ký tạm thời không khả dụng.",
            )
        return self._redis

    def _now_ms(self) -> int:
        return int(utc_now().timestamp() * 1000)

    def _disabled_payload(self) -> dict[str, Any]:
        return {
            "queue_enabled": False,
            "status": "NONE",
            "position": None,
            "estimated_wait_seconds": None,
            "ready_expires_at": None,
            "queue_token": None,
        }

    def _parse_lua_state(self, raw: list[Any]) -> dict[str, Any]:
        state = str(raw[0].decode("utf-8") if isinstance(raw[0], bytes) else raw[0])
        pos_raw = str(raw[1].decode("utf-8") if isinstance(raw[1], bytes) else raw[1])
        exp_raw = str(raw[2].decode("utf-8") if isinstance(raw[2], bytes) else raw[2])
        tok_raw = str(raw[3].decode("utf-8") if isinstance(raw[3], bytes) else raw[3])

        position = int(pos_raw) if pos_raw else None
        ready_expires_at: str | None = None
        if exp_raw:
            exp_dt = datetime.fromtimestamp(int(exp_raw) / 1000.0, tz=UTC).replace(microsecond=0)
            ready_expires_at = format_utc_z(exp_dt)
        queue_token = tok_raw if tok_raw else None

        return {
            "queue_enabled": True,
            "status": state,
            "position": position,
            "estimated_wait_seconds": None,
            "ready_expires_at": ready_expires_at,
            "queue_token": queue_token,
        }

    def join_queue(self, student_id: str) -> dict[str, Any]:
        if not self._settings.queue_enabled:
            return self._disabled_payload()

        redis_conn = self._require_redis()
        candidate_token = generate_opaque_token(32)
        try:
            res = redis_conn.eval(
                _JOIN_LUA,
                len(self.KEYS),
                *self.KEYS,
                str(self._now_ms()),
                str(self._settings.queue_max_ready),
                str(self._settings.queue_token_ttl_seconds * 1000),
                str(self._settings.queue_expired_marker_ttl_seconds),
                student_id,
                candidate_token,
            )
            return self._parse_lua_state(res)
        except RedisError as exc:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Dịch vụ hàng đợi tạm thời không khả dụng.",
            ) from exc

    def get_status(self, student_id: str) -> dict[str, Any]:
        if not self._settings.queue_enabled:
            return self._disabled_payload()

        redis_conn = self._require_redis()
        try:
            res = redis_conn.eval(
                _STATUS_LUA,
                len(self.KEYS),
                *self.KEYS,
                str(self._now_ms()),
                str(self._settings.queue_max_ready),
                str(self._settings.queue_token_ttl_seconds * 1000),
                str(self._settings.queue_expired_marker_ttl_seconds),
                student_id,
            )
            return self._parse_lua_state(res)
        except RedisError as exc:
            raise AppError(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="Dịch vụ hàng đợi tạm thời không khả dụng.",
            ) from exc

    def verify_ready_token(self, student_id: str, provided_token: str | None) -> None:
        """Enforce `X-Queue-Token` on new `/register` operations when `QUEUE_ENABLED=true`."""
        if not self._settings.queue_enabled:
            return

        if provided_token is None or not provided_token.strip():
            raise AppError(
                status_code=403,
                code=ErrorCode.QUEUE_TOKEN_REQUIRED,
                message="Vui lòng tham gia hàng đợi và gửi kèm X-Queue-Token khi tới lượt.",
            )

        state = self.get_status(student_id)
        if state["status"] != "READY" or not state["queue_token"]:
            raise AppError(
                status_code=403,
                code=ErrorCode.QUEUE_TOKEN_INVALID,
                message="X-Queue-Token không hợp lệ hoặc lượt đăng ký đã hết hạn.",
            )

        if not constant_time_equals(str(state["queue_token"]), provided_token.strip()):
            raise AppError(
                status_code=403,
                code=ErrorCode.QUEUE_TOKEN_INVALID,
                message="X-Queue-Token không hợp lệ hoặc không thuộc người dùng hiện tại.",
            )

    def release_user_slot_on_logout(self, student_id: str) -> None:
        """Release user's WAITING/READY slot and promote next FIFO user upon logout."""
        if not self._settings.queue_enabled or self._redis is None:
            return
        try:
            self._redis.eval(
                _RELEASE_LUA,
                len(self.KEYS),
                *self.KEYS,
                str(self._now_ms()),
                str(self._settings.queue_max_ready),
                str(self._settings.queue_token_ttl_seconds * 1000),
                str(self._settings.queue_expired_marker_ttl_seconds),
                student_id,
            )
        except RedisError:
            # Session revocation in PostgreSQL already succeeded; do not mask logout result
            pass

    def ping(self) -> bool:
        if self._redis is None:
            return False
        try:
            return bool(self._redis.ping())
        except RedisError:
            return False
