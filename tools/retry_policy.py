# =====================================
# Titan Tool Retry Policy
# =====================================

"""Retry decisions for transient tool failures (Phase 10A — P10A-017)."""

from __future__ import annotations

from dataclasses import dataclass

from tools.tool_result import ToolResult

_TRANSIENT_MARKERS = (
    "timeout",
    "temporarily",
    "rate limit",
    "connexion",
    "connection",
    "unavailable",
    "indisponible",
)


@dataclass
class RetryPolicy:
    """Simple exponential backoff retry policy for sync execution."""

    base_delay_seconds: float = 0.1
    max_delay_seconds: float = 2.0

    def should_retry(
        self,
        attempt: int,
        max_retries: int,
        result: ToolResult,
    ) -> bool:
        """Return True when another attempt is warranted."""
        if result.success:
            return False
        if attempt >= max_retries:
            return False
        error_lower = result.error.lower()
        if not error_lower:
            return False
        return any(marker in error_lower for marker in _TRANSIENT_MARKERS)

    def delay_seconds(self, attempt: int) -> float:
        """Compute backoff delay for the given attempt (1-based)."""
        delay = self.base_delay_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)
