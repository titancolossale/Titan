# =====================================
# Titan Password Security
# =====================================

"""Secure password hashing and verification (Argon2id preferred, bcrypt fallback)."""

from __future__ import annotations

import re
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ARGON2 = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

_MIN_PASSWORD_LENGTH: Final[int] = 14
_WEAK_PASSWORD_MESSAGE: Final[str] = (
    "Le mot de passe doit contenir au moins 14 caractères, "
    "une majuscule, une minuscule, un chiffre et un caractère spécial."
)


def hash_password(password: str) -> str:
    """Return an Argon2id hash for ``password`` (never log the plaintext)."""
    return _ARGON2.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify ``password`` against an Argon2id or bcrypt hash.

    Returns False on mismatch or unsupported/corrupt hashes. Never raises
    credential details to callers.
    """
    if not password or not password_hash:
        return False

    raw = password_hash.strip()
    if raw.startswith("$argon2"):
        try:
            return bool(_ARGON2.verify(raw, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        except Exception:
            return False

    if raw.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
        except ImportError:
            return False
        try:
            return bool(
                bcrypt.checkpw(
                    password.encode("utf-8"),
                    raw.encode("utf-8"),
                )
            )
        except (ValueError, TypeError):
            return False

    return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Return (ok, error_message) for local hash-generation policy."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        return False, _WEAK_PASSWORD_MESSAGE
    if not re.search(r"[A-Z]", password):
        return False, _WEAK_PASSWORD_MESSAGE
    if not re.search(r"[a-z]", password):
        return False, _WEAK_PASSWORD_MESSAGE
    if not re.search(r"[0-9]", password):
        return False, _WEAK_PASSWORD_MESSAGE
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, _WEAK_PASSWORD_MESSAGE
    return True, ""
