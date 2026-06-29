# =====================================
# Titan Tool Usage Quotas
# =====================================

"""Optional usage limits and quota tracking (Phase 10A — P10A-006)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class UsageQuota:
    """Optional invocation limits for a tool or caller."""

    max_invocations: int | None = None
    max_invocations_per_day: int | None = None
    max_concurrent: int | None = None
    window_seconds: int = 86400


@dataclass
class QuotaUsage:
    """Mutable quota consumption counters for one tool."""

    invocations_in_window: int = 0
    window_started_at: str | None = None
    daily_count: int = 0
    daily_reset_at: str | None = None
    concurrent_active: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize quota counters for persistence."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuotaUsage:
        """Restore quota counters from persisted JSON."""
        return cls(
            invocations_in_window=int(data.get("invocations_in_window", 0)),
            window_started_at=data.get("window_started_at"),
            daily_count=int(data.get("daily_count", 0)),
            daily_reset_at=data.get("daily_reset_at"),
            concurrent_active=int(data.get("concurrent_active", 0)),
        )


@dataclass(frozen=True)
class QuotaCheckResult:
    """Outcome of a pre-execution quota check."""

    allowed: bool
    reason: str = ""


@dataclass
class QuotaTracker:
    """In-memory quota tracker with optional persistence (Batch 4)."""

    enabled: bool = False
    _usage: dict[str, QuotaUsage] = field(default_factory=dict)

    def _get_usage(self, tool_name: str) -> QuotaUsage:
        if tool_name not in self._usage:
            self._usage[tool_name] = QuotaUsage()
        return self._usage[tool_name]

    def check(self, tool_name: str, quota: UsageQuota | None) -> QuotaCheckResult:
        """Return whether invocation is within quota limits."""
        if not self.enabled or quota is None:
            return QuotaCheckResult(allowed=True)

        usage = self._get_usage(tool_name)
        now = _utc_now()

        if quota.max_concurrent is not None and usage.concurrent_active >= quota.max_concurrent:
            return QuotaCheckResult(
                allowed=False,
                reason="Limite d'exécutions simultanées atteinte",
            )

        if quota.max_invocations_per_day is not None:
            reset_at = usage.daily_reset_at
            if reset_at is None or now >= datetime.fromisoformat(reset_at):
                usage.daily_count = 0
                usage.daily_reset_at = (now + timedelta(days=1)).replace(
                    microsecond=0
                ).isoformat()
            if usage.daily_count >= quota.max_invocations_per_day:
                return QuotaCheckResult(
                    allowed=False,
                    reason="Quota journalier atteint",
                )

        if quota.max_invocations is not None:
            window_start = usage.window_started_at
            window_end = None
            if window_start is not None:
                window_end = datetime.fromisoformat(window_start) + timedelta(
                    seconds=quota.window_seconds
                )
            if window_start is None or (window_end and now >= window_end):
                usage.invocations_in_window = 0
                usage.window_started_at = _utc_now_iso()
            if usage.invocations_in_window >= quota.max_invocations:
                return QuotaCheckResult(
                    allowed=False,
                    reason="Quota de fenêtre atteint",
                )

        return QuotaCheckResult(allowed=True)

    def record_start(self, tool_name: str) -> None:
        """Increment concurrent counter when a run starts."""
        self._get_usage(tool_name).concurrent_active += 1

    def record_finish(self, tool_name: str, quota: UsageQuota | None) -> None:
        """Decrement concurrent counter and increment invocation counts."""
        usage = self._get_usage(tool_name)
        usage.concurrent_active = max(0, usage.concurrent_active - 1)
        if not self.enabled or quota is None:
            return
        usage.invocations_in_window += 1
        usage.daily_count += 1

    def usage_snapshot(self) -> dict[str, dict]:
        """Export quota counters for persistence."""
        return {name: usage.to_dict() for name, usage in self._usage.items()}

    def load_snapshot(self, snapshot: dict[str, dict]) -> None:
        """Restore quota counters from a persisted snapshot."""
        for name, data in snapshot.items():
            self._usage[name] = QuotaUsage.from_dict(data)

    def remaining_daily(self, tool_name: str, quota: UsageQuota | None) -> int | None:
        """Return remaining daily invocations when a daily quota is configured."""
        if quota is None or quota.max_invocations_per_day is None:
            return None
        usage = self._get_usage(tool_name)
        return max(0, quota.max_invocations_per_day - usage.daily_count)
