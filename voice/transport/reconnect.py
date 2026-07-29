# =====================================
# Titan Transport Reconnect Policy
# =====================================

"""Backoff + jitter for automatic transport recovery (Phase 20.6)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from voice.transport.base import TransportConfig


@dataclass(frozen=True)
class ReconnectPolicy:
    """Decides whether and how long to wait before reconnect."""

    max_attempts: int = 5
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.15

    @classmethod
    def from_config(cls, config: TransportConfig) -> ReconnectPolicy:
        return cls(
            max_attempts=config.max_reconnect_attempts,
            base_delay_seconds=config.reconnect_base_delay_seconds,
            max_delay_seconds=config.reconnect_max_delay_seconds,
            jitter_ratio=config.reconnect_jitter_ratio,
        )

    def should_retry(self, attempt: int) -> bool:
        return 0 <= attempt < self.max_attempts

    def delay_for_attempt(self, attempt: int) -> float:
        return compute_backoff_seconds(
            attempt,
            base_delay_seconds=self.base_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
            jitter_ratio=self.jitter_ratio,
        )


def compute_backoff_seconds(
    attempt: int,
    *,
    base_delay_seconds: float = 0.25,
    max_delay_seconds: float = 8.0,
    jitter_ratio: float = 0.15,
) -> float:
    """Exponential backoff with bounded jitter."""
    exponent = max(0, attempt)
    delay = min(max_delay_seconds, base_delay_seconds * (2**exponent))
    if jitter_ratio <= 0:
        return delay
    span = delay * jitter_ratio
    return max(0.0, delay + random.uniform(-span, span))
