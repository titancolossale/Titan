# =====================================
# Titan Provider Failure Types
# =====================================

"""Structured provider failure reasons for graceful degradation (P10B-403)."""

from __future__ import annotations

from enum import Enum

from tools.tool_enums import ToolHealthState


class ProviderFailureReason(str, Enum):
    """Canonical failure categories for external provider calls."""

    OFFLINE = "offline"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    INVALID_KEY = "invalid_key"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


_FAILURE_HEALTH: dict[ProviderFailureReason, ToolHealthState] = {
    ProviderFailureReason.OFFLINE: ToolHealthState.OFFLINE,
    ProviderFailureReason.TIMEOUT: ToolHealthState.DEGRADED,
    ProviderFailureReason.RATE_LIMIT: ToolHealthState.DEGRADED,
    ProviderFailureReason.INVALID_KEY: ToolHealthState.MISCONFIGURED,
    ProviderFailureReason.NETWORK_ERROR: ToolHealthState.DEGRADED,
    ProviderFailureReason.UNKNOWN: ToolHealthState.DEGRADED,
}


def health_state_for_failure(reason: ProviderFailureReason) -> ToolHealthState:
    """Map a provider failure reason to a HealthMonitor state."""
    return _FAILURE_HEALTH.get(reason, ToolHealthState.DEGRADED)
