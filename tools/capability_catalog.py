# =====================================
# Titan Capability Catalog
# =====================================

"""Registry of tool capability metadata for the Phase 10A runtime (P10A-011)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.tool_capability import ToolCapability


@dataclass
class CapabilityCatalog:
    """In-memory catalog of ToolCapability descriptors keyed by tool name."""

    _capabilities: dict[str, ToolCapability] = field(default_factory=dict)

    def register(self, capability: ToolCapability) -> None:
        """Register a capability; duplicate names raise ValueError."""
        if capability.name in self._capabilities:
            raise ValueError(f"Capability already registered: {capability.name}")
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> ToolCapability | None:
        """Return capability for a tool name, or None if unknown."""
        return self._capabilities.get(name)

    def list_names(self) -> list[str]:
        """Return sorted registered tool names."""
        return sorted(self._capabilities.keys())

    def export(self, *, metrics_snapshot: dict[str, dict] | None = None) -> dict:
        """Export capabilities for dashboards; optional metrics merged by tool name."""
        metrics_snapshot = metrics_snapshot or {}
        exported: dict[str, dict] = {}
        for name, cap in self._capabilities.items():
            entry = {
                "name": cap.name,
                "description": cap.description,
                "invocation_mode": cap.invocation_mode.value,
                "execution_mode": cap.execution_mode.value,
                "supported_execution_modes": sorted(
                    m.value for m in cap.supported_execution_modes
                ),
                "risk_level": cap.risk_level.value,
                "health_state": cap.health_state.value,
                "provider_name": cap.provider_name,
                "tags": sorted(cap.tags),
            }
            if name in metrics_snapshot:
                entry["metrics"] = metrics_snapshot[name]
            exported[name] = entry
        return exported

    def export_with_providers(
        self,
        *,
        metrics_snapshot: dict[str, dict] | None = None,
        provider_versions: dict[str, str] | None = None,
    ) -> dict:
        """Export capabilities with optional provider version metadata."""
        exported = self.export(metrics_snapshot=metrics_snapshot)
        if not provider_versions:
            return exported
        for name, cap in self._capabilities.items():
            if cap.provider_name and cap.provider_name in provider_versions:
                exported[name]["provider_version"] = provider_versions[cap.provider_name]
        return exported
