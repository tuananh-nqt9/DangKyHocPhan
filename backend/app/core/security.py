"""Cryptographic helpers: Argon2id password hashing, CSPRNG opaque tokens, SHA-256, PKCE S256."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id configured with OWASP-recommended interactive parameters
_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# Precomputed dummy hash so missing-user login still runs Argon2id verification
# to prevent user-enumeration via timing side-channel.
_DUMMY_PASSWORD_HASH = _password_hasher.hash("DummyPassword@NotUsedInLab123!")


def hash_password(plain_password: str) -> str:
    """Hash a password with Argon2id without trimming."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    """Verify plaintext password against Argon2id hash in constant-ish time."""
    target_hash = password_hash if password_hash is not None else _DUMMY_PASSWORD_HASH
    try:
        matched = _password_hasher.verify(target_hash, plain_password)
        return matched and (password_hash is not None)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_opaque_token(nbytes: int = 32) -> str:
    """Generate a high-entropy URL-safe opaque token (>= 32 bytes raw entropy)."""
    if nbytes < 32:
        raise ValueError("Entropy token phải tối thiểu 32 byte.")
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """Compute hex-encoded SHA-256 digest of an opaque token / code."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def generate_pkce_pair() -> tuple[str, str]:
    """Generate RFC 7636 PKCE (code_verifier, S256 code_challenge)."""
    code_verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge
