# =====================================
# Titan Tool Health Monitor
# =====================================

"""Aggregates tool and provider health for pre-execution gating (Phase 10A — P10A-012)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.exceptions import ToolHealthError
from tools.tool_capability import ToolCapability
from tools.tool_enums import ToolHealthState

_BLOCKED_PROVIDER_STATES = frozenset({
    ToolHealthState.OFFLINE,
    ToolHealthState.DISABLED,
    ToolHealthState.MISCONFIGURED,
    ToolHealthState.MISSING_CREDENTIALS,
})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class HealthCheckResult:
    """Outcome of a pre-execution health assertion."""

    state: ToolHealthState
    allowed: bool
    message: str = ""


@dataclass
class HealthMonitor:
    """Track per-tool and per-provider health with offline→online cooldown."""

    offline_cooldown_seconds: float = 30.0
    _tool_states: dict[str, ToolHealthState] = field(default_factory=dict)
    _provider_states: dict[str, ToolHealthState] = field(default_factory=dict)
    _offline_since: dict[str, datetime] = field(default_factory=dict)

    def set_tool_health(self, tool_name: str, state: ToolHealthState) -> None:
        """Set explicit health for a tool; hysteresis delays OFFLINE→ONLINE."""
        previous = self._tool_states.get(tool_name)
        key = f"tool:{tool_name}"
        if (
            state == ToolHealthState.ONLINE
            and previous == ToolHealthState.OFFLINE
            and not self._cooldown_elapsed(key)
        ):
            return
        self._tool_states[tool_name] = state
        if state == ToolHealthState.OFFLINE:
            if previous != ToolHealthState.OFFLINE:
                self._offline_since[key] = _utc_now()
        elif key in self._offline_since:
            del self._offline_since[key]

    def set_provider_health(self, provider_id: str, state: ToolHealthState) -> None:
        """Set explicit health for a provider; hysteresis delays OFFLINE→ONLINE."""
        previous = self._provider_states.get(provider_id)
        key = f"provider:{provider_id}"
        if (
            state == ToolHealthState.ONLINE
            and previous == ToolHealthState.OFFLINE
            and not self._cooldown_elapsed(key)
        ):
            return
        self._provider_states[provider_id] = state
        if state == ToolHealthState.OFFLINE:
            if previous != ToolHealthState.OFFLINE:
                self._offline_since[key] = _utc_now()
        elif key in self._offline_since:
            del self._offline_since[key]

    def get_tool_health(
        self,
        tool_name: str,
        *,
        capability: ToolCapability | None = None,
    ) -> ToolHealthState:
        """Resolve effective tool health using override then monitor state."""
        if capability is not None and capability.health_state != ToolHealthState.UNKNOWN:
            return capability.health_state
        return self._tool_states.get(tool_name, ToolHealthState.UNKNOWN)

    def get_provider_health(self, provider_id: str) -> ToolHealthState:
        """Return provider health, defaulting to UNKNOWN."""
        return self._provider_states.get(provider_id, ToolHealthState.UNKNOWN)

    def health_lookup(self, ref_type: str, ref_id: str) -> ToolHealthState:
        """Lookup health for dependency graph checks."""
        if ref_type == "tool":
            return self.get_tool_health(ref_id)
        if ref_type == "provider":
            return self.get_provider_health(ref_id)
        if ref_type == "service":
            return ToolHealthState.ONLINE
        return ToolHealthState.UNKNOWN

    def assert_ready(
        self,
        tool_name: str,
        capability: ToolCapability,
    ) -> HealthCheckResult:
        """Verify tool health allows execution; raises ToolHealthError when blocked."""
        state = self.get_tool_health(tool_name, capability=capability)

        if capability.provider_name:
            provider_state = self.get_provider_health(capability.provider_name)
            if provider_state in _BLOCKED_PROVIDER_STATES:
                state = provider_state
            elif provider_state == ToolHealthState.DEGRADED and state == ToolHealthState.UNKNOWN:
                state = ToolHealthState.DEGRADED

        if state == ToolHealthState.OFFLINE:
            raise ToolHealthError(f"Outil {tool_name!r} indisponible (hors ligne).")

        if state == ToolHealthState.DISABLED:
            raise ToolHealthError(f"Outil {tool_name!r} désactivé par politique.")

        if state == ToolHealthState.MISCONFIGURED:
            raise ToolHealthError(f"Outil {tool_name!r} mal configuré.")

        if state == ToolHealthState.MISSING_CREDENTIALS:
            raise ToolHealthError(
                f"Outil {tool_name!r} indisponible — credentials manquantes."
            )

        if state == ToolHealthState.DEGRADED:
            return HealthCheckResult(
                state=state,
                allowed=True,
                message=f"Outil {tool_name!r} en mode dégradé.",
            )

        return HealthCheckResult(state=state, allowed=True)

    def _cooldown_elapsed(self, key: str) -> bool:
        """Return True when offline→online hysteresis cooldown has passed."""
        since = self._offline_since.get(key)
        if since is None:
            return True
        elapsed = (_utc_now() - since).total_seconds()
        return elapsed >= self.offline_cooldown_seconds
