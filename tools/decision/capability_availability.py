# =====================================
# Titan Tool Decision — Capability Availability
# =====================================

"""Live tool availability from CapabilityCatalog and runtime health (Phase 10B — P10B-103)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.capability_catalog import CapabilityCatalog
from tools.decision.models import CandidateTool
from tools.health_monitor import HealthMonitor
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_capability import ToolCapability
from tools.tool_enums import RiskLevel, ToolHealthState

_BLOCKED_STATES = frozenset({ToolHealthState.OFFLINE, ToolHealthState.DISABLED})

_DEGRADED_PENALTY = 12.0
_VERSION_MISMATCH_PENALTY = 8.0


@dataclass
class CapabilityAvailabilityResolver:
    """Resolve executable tools and ranking adjustments from live runtime state."""

    catalog: CapabilityCatalog
    health_monitor: HealthMonitor
    provider_registry: ProviderRegistry | None = None
    _version_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def resolve_available_tools(self) -> frozenset[str]:
        """Return tool names that are registered and not health-blocked."""
        available: set[str] = set()
        for name in self.catalog.list_names():
            if self.is_tool_available(name):
                available.add(name)
        return frozenset(available)

    def is_tool_available(self, tool_name: str) -> bool:
        """Return True when catalog entry and dependencies pass health gates."""
        capability = self.catalog.get(tool_name)
        if capability is None:
            return False
        return self._effective_health(tool_name, capability) not in _BLOCKED_STATES

    def get_capability(self, tool_name: str) -> ToolCapability | None:
        """Return catalog capability for a tool name."""
        return self.catalog.get(tool_name)

    def resolve_risk_level(self, tool_name: str, *, fallback: RiskLevel = RiskLevel.MEDIUM) -> RiskLevel:
        """Return risk level from runtime capability metadata."""
        capability = self.catalog.get(tool_name)
        if capability is None:
            return fallback
        return capability.risk_level

    def requires_confirmation(self, tool_name: str) -> bool:
        """Return whether live capability metadata requires user confirmation."""
        capability = self.catalog.get(tool_name)
        if capability is None:
            return False
        if capability.requires_confirmation is True:
            return True
        if capability.requires_confirmation is False:
            return False
        return capability.risk_level in {
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        }

    def adjust_candidates(
        self,
        candidates: tuple[CandidateTool, ...],
    ) -> tuple[CandidateTool, ...]:
        """Re-score candidates using provider health and version compatibility."""
        adjusted: list[CandidateTool] = []
        for candidate in candidates:
            capability = self.catalog.get(candidate.tool_name)
            if capability is None:
                continue
            score = candidate.score
            reason = candidate.reason
            health = self._effective_health(candidate.tool_name, capability)
            if health == ToolHealthState.DEGRADED:
                score -= _DEGRADED_PENALTY
                reason = f"{reason}; provider/tool degraded"
            if self._provider_version_mismatch(capability):
                score -= _VERSION_MISMATCH_PENALTY
                reason = f"{reason}; provider version mismatch"
            adjusted.append(
                CandidateTool(
                    tool_name=candidate.tool_name,
                    score=max(score, 0.0),
                    reason=reason,
                ),
            )
        return tuple(sorted(adjusted, key=lambda item: item.score, reverse=True))

    def provider_version(self, tool_name: str) -> str:
        """Return semver for the tool's provider, or empty when unknown."""
        capability = self.catalog.get(tool_name)
        if capability is None or not capability.provider_name:
            return ""
        if self.provider_registry is None:
            return ""
        return self.provider_registry.version_for(capability.provider_name)

    def _effective_health(
        self,
        tool_name: str,
        capability: ToolCapability,
    ) -> ToolHealthState:
        tool_state = self.health_monitor.get_tool_health(tool_name, capability=capability)
        if tool_state in _BLOCKED_STATES:
            return tool_state

        if capability.provider_name:
            provider_state = self.health_monitor.get_provider_health(capability.provider_name)
            if provider_state in _BLOCKED_STATES:
                return provider_state
            if provider_state == ToolHealthState.DEGRADED and tool_state == ToolHealthState.UNKNOWN:
                return ToolHealthState.DEGRADED

        return tool_state

    def _provider_version_mismatch(self, capability: ToolCapability) -> bool:
        if not capability.provider_name or self.provider_registry is None:
            return False
        provider = self.provider_registry.get(capability.provider_name)
        if provider is None:
            return False
        return not provider.version_info.is_compatible_with_runtime(
            self.provider_registry.runtime_version,
        )
