# =====================================
# Titan Tool Status Formatter
# =====================================

"""Format tool and provider health for Brain prompt injection (Phase 10A — P10A-026)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.capability_catalog import CapabilityCatalog
from tools.health_monitor import HealthMonitor
from tools.provider_version import ProviderHealth
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_capability import ToolCapability
from tools.tool_enums import ToolHealthState


@dataclass
class ToolStatusSnapshot:
    """Aggregated health view for prompt assembly."""

    provider_health: dict[str, ProviderHealth] = field(default_factory=dict)
    tool_health: dict[str, ToolHealthState] = field(default_factory=dict)
    capabilities: dict[str, ToolCapability] = field(default_factory=dict)


class ToolStatusFormatter:
    """Build French prompt blocks from runtime health and capability metadata."""

    @staticmethod
    def probe_snapshot(
        provider_registry: ProviderRegistry,
        health_monitor: HealthMonitor,
        catalog: CapabilityCatalog,
    ) -> ToolStatusSnapshot:
        """Probe providers and collect effective tool health for the current turn."""
        provider_health = provider_registry.sync_health(health_monitor)
        tool_health: dict[str, ToolHealthState] = {}
        capabilities: dict[str, ToolCapability] = {}
        for name in catalog.list_names():
            cap = catalog.get(name)
            if cap is None:
                continue
            capabilities[name] = cap
            tool_health[name] = health_monitor.get_tool_health(name, capability=cap)
        return ToolStatusSnapshot(
            provider_health=provider_health,
            tool_health=tool_health,
            capabilities=capabilities,
        )

    @classmethod
    def format_for_prompt(cls, snapshot: ToolStatusSnapshot, *, provider_registry: ProviderRegistry) -> str:
        """Render provider and tool status as a compact French block."""
        if not snapshot.provider_health and not snapshot.capabilities:
            return "Aucune capacité outil enregistrée."

        lines: list[str] = []

        if snapshot.provider_health:
            lines.append("Providers :")
            for provider_id in sorted(snapshot.provider_health):
                health = snapshot.provider_health[provider_id]
                version = provider_registry.version_for(provider_id)
                version_suffix = f" v{version}" if version else ""
                message = f" — {health.message}" if health.message else ""
                lines.append(
                    f"  - {provider_id}{version_suffix} : "
                    f"{health.state.value}{message}"
                )

        if snapshot.capabilities:
            lines.append("Outils (capability-first) :")
            for name in sorted(snapshot.capabilities):
                cap = snapshot.capabilities[name]
                state = snapshot.tool_health.get(name, ToolHealthState.UNKNOWN)
                provider = cap.provider_name or "local"
                lines.append(
                    f"  - {name} [{cap.risk_level.value}, {state.value}, "
                    f"provider={provider}]"
                )

        return "\n".join(lines)
