# =====================================
# Titan Login Rate Limiter
# =====================================

"""Brute-force protection for the private login endpoint."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Final

DEFAULT_MAX_FAILURES: Final[int] = 5
DEFAULT_WINDOW_SECONDS: Final[int] = 900  # 15 minutes
DEFAULT_LOCKOUT_SECONDS: Final[int] = 900  # 15 minutes


@dataclass
class _AttemptBucket:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginRateLimiter:
    """Track failed login attempts by client key (typically IP)."""

    def __init__(
        self,
        *,
        max_failures: int = DEFAULT_MAX_FAILURES,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        lockout_seconds: int = DEFAULT_LOCKOUT_SECONDS,
    ) -> None:
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._buckets: dict[str, _AttemptBucket] = {}
        self._lock = threading.Lock()

    def is_locked(self, key: str) -> bool:
        """Return True when ``key`` is currently locked out."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return False
            if bucket.locked_until > now:
                return True
            if bucket.locked_until and bucket.locked_until <= now:
                bucket.locked_until = 0.0
                bucket.failures.clear()
            return False

    def register_failure(self, key: str) -> None:
        """Record a failed attempt and lock when the threshold is reached."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, _AttemptBucket())
            cutoff = now - self._window_seconds
            bucket.failures = [ts for ts in bucket.failures if ts >= cutoff]
            bucket.failures.append(now)
            if len(bucket.failures) >= self._max_failures:
                bucket.locked_until = now + self._lockout_seconds
                bucket.failures.clear()

    def register_success(self, key: str) -> None:
        """Clear failure history after a successful login."""
        with self._lock:
            self._buckets.pop(key, None)

    def reset(self) -> None:
        """Clear all buckets (tests only)."""
        with self._lock:
            self._buckets.clear()


_rate_limiter = LoginRateLimiter()


def get_login_rate_limiter() -> LoginRateLimiter:
    """Return the process-wide login rate limiter."""
    return _rate_limiter


def reset_login_rate_limiter() -> None:
    """Clear rate-limiter state (tests only)."""
    _rate_limiter.reset()
