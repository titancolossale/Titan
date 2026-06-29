# =====================================
# Titan Provider Registry
# =====================================

"""Central registry for tool providers with versioning and health probes (P10A-024)."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import TOOL_RUNTIME_VERSION
from core.exceptions import ProviderVersionIncompatible
from tools.health_monitor import HealthMonitor
from tools.provider_version import ProviderHealth
from tools.providers.base_provider import BaseProvider
from tools.tool_enums import ToolHealthState


@dataclass
class ProviderRegistry:
    """Register providers, validate runtime compatibility, and sync health."""

    runtime_version: str = TOOL_RUNTIME_VERSION
    _providers: dict[str, BaseProvider] = field(default_factory=dict)

    def register(self, provider: BaseProvider, *, replace: bool = False) -> None:
        """Register a provider after runtime version validation.

        Raises:
            ProviderVersionIncompatible: when min_runtime_version exceeds runtime.
            ValueError: on duplicate registration or provider_id mismatch.
        """
        provider_id = provider.provider_id
        info = provider.version_info

        if info.provider_id != provider_id:
            raise ValueError(
                f"provider_id mismatch: {provider_id!r} vs {info.provider_id!r}"
            )

        if not info.is_compatible_with_runtime(self.runtime_version):
            raise ProviderVersionIncompatible(
                f"Provider {provider_id!r} requiert runtime "
                f"{info.min_runtime_version}, actuel {self.runtime_version}."
            )

        if provider_id in self._providers and not replace:
            raise ValueError(f"Provider already registered: {provider_id}")

        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> BaseProvider | None:
        """Return a registered provider or None."""
        return self._providers.get(provider_id)

    def list_ids(self) -> list[str]:
        """Return sorted registered provider identifiers."""
        return sorted(self._providers.keys())

    def probe(self, provider_id: str) -> ProviderHealth:
        """Run health_check for a registered provider."""
        provider = self._providers.get(provider_id)
        if provider is None:
            return ProviderHealth(
                state=ToolHealthState.OFFLINE,
                message=f"Provider inconnu : {provider_id}",
            )

        health = provider.health_check()
        if not provider.version_info.is_compatible_with_runtime(self.runtime_version):
            return ProviderHealth(
                state=ToolHealthState.DEGRADED,
                message=(
                    f"Version runtime {self.runtime_version} incompatible "
                    f"avec min {provider.version_info.min_runtime_version}."
                ),
            )
        return health

    def probe_all(self) -> dict[str, ProviderHealth]:
        """Probe every registered provider."""
        return {provider_id: self.probe(provider_id) for provider_id in self.list_ids()}

    def sync_health(self, health_monitor: HealthMonitor) -> dict[str, ProviderHealth]:
        """Probe providers and push states into the health monitor."""
        results: dict[str, ProviderHealth] = {}
        for provider_id in self.list_ids():
            health = self.probe(provider_id)
            health_monitor.set_provider_health(provider_id, health.state)
            results[provider_id] = health
        return results

    def version_for(self, provider_id: str) -> str:
        """Return semver string for audit logging, or empty when unknown."""
        provider = self.get(provider_id)
        if provider is None:
            return ""
        return provider.version_info.version
