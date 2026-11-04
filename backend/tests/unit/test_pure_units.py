"""Pure unit tests (no external database required)."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from app.core.clock import Clock, format_utc_z, utc_now
from app.core.logging import redact_dict
from app.core.security import (
    generate_opaque_token,
    generate_pkce_pair,
    hash_password,
    hash_token,
    verify_password,
)
from app.repositories.course_class_repo import escape_like_literal
from app.repositories.idempotency_repo import compute_advisory_lock_id
from app.services.idempotency_service import compute_request_fingerprint

pytestmark = pytest.mark.unit


def test_argon2id_password_hashing_and_no_trim() -> None:
    pw = "Demo@123456"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2id$")
    assert pw not in hashed
    assert verify_password(pw, hashed) is True
    # Whitespace around password must NOT be trimmed
    assert verify_password(" Demo@123456", hashed) is False
    assert verify_password("Demo@123456 ", hashed) is False
    # Missing user (None hash) runs dummy verification and returns False
    assert verify_password(pw, None) is False


def test_opaque_token_entropy_and_sha256_hashing() -> None:
    t1 = generate_opaque_token(32)
    t2 = generate_opaque_token(32)
    assert t1 != t2
    assert len(t1) >= 43  # 32 bytes base64url without padding = 43 chars
    assert len(hash_token(t1)) == 64
    assert hash_token(t1) == hash_token(t1)
    assert hash_token(t1) != hash_token(t2)
    with pytest.raises(ValueError):
        generate_opaque_token(16)


def test_pkce_s256_pair_conforms_to_rfc7636() -> None:
    verifier, challenge = generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
    assert challenge == expected_challenge


def test_canonical_fingerprint_invariance_and_sensitivity() -> None:
    fp1 = compute_request_fingerprint(
        "post",
        "/api/v1/register",
        {"student_id": "SV0001", "course_class_id": "LHP001"},
    )
    fp2 = compute_request_fingerprint(
        "POST",
        "/api/v1/register",
        {"course_class_id": "LHP001", "student_id": "SV0001"},
    )
    assert fp1 == fp2

    # Different body value -> different fingerprint
    fp_diff_body = compute_request_fingerprint(
        "POST",
        "/api/v1/register",
        {"student_id": "SV0001", "course_class_id": "LHP002"},
    )
    assert fp1 != fp_diff_body

    # Different path or method -> different fingerprint
    fp_del_1 = compute_request_fingerprint(
        "DELETE", "/api/v1/registrations/4d0ce29e-9e4d-4e0a-8a92-f776fe905001", None
    )
    fp_del_2 = compute_request_fingerprint(
        "DELETE", "/api/v1/registrations/4d0ce29e-9e4d-4e0a-8a92-f776fe905002", None
    )
    assert fp_del_1 != fp_del_2


def test_deterministic_advisory_lock_id() -> None:
    key = "7f9c2b10-53a4-4f1b-9c8a-2a1e9f0c1234"
    id1 = compute_advisory_lock_id(10, key)
    id2 = compute_advisory_lock_id(10, key.upper())
    id_other_user = compute_advisory_lock_id(11, key)
    assert id1 == id2
    assert id1 != id_other_user
    assert -(2**63) <= id1 <= (2**63 - 1)


def test_escape_like_literal_prevents_wildcard_injection() -> None:
    raw = r"100%_test\class"
    escaped = escape_like_literal(raw)
    assert escaped == r"100\%\_test\\class"


def test_controllable_utc_clock_and_z_formatting() -> None:
    fixed = datetime(2026, 11, 1, 8, 30, 0, tzinfo=UTC)
    with Clock.override(fixed):
        assert utc_now() == fixed
        assert format_utc_z(utc_now()) == "2026-11-01T08:30:00Z"
        with Clock.advance(timedelta(hours=2)):
            assert format_utc_z(utc_now()) == "2026-11-01T10:30:00Z"
        assert format_utc_z(utc_now()) == "2026-11-01T08:30:00Z"


def test_log_redaction_strips_all_secrets() -> None:
    sample = {
        "student_id": "SV0001",
        "password": "secret",
        "Authorization": "Bearer abc",
        "X-Queue-Token": "qtok",
        "nested": {
            "refresh_token": "rtok",
            "exchange_code": "ex123",
            "state": "st123",
            "code": "authcode",
            "safe": 42,
        },
    }
    redacted = redact_dict(sample)
    assert redacted["student_id"] == "SV0001"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["X-Queue-Token"] == "[REDACTED]"
    assert redacted["nested"]["refresh_token"] == "[REDACTED]"
    assert redacted["nested"]["exchange_code"] == "[REDACTED]"
    assert redacted["nested"]["state"] == "[REDACTED]"
    assert redacted["nested"]["code"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == 42
