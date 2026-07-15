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
from tools.providers.credential_manager import CredentialManager
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_health_resolver import reconcile_probe_health
from tools.providers.provider_metadata import ProviderMetadata
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.tool_enums import ExecutionMode, ToolHealthState

_BLOCKED_STATES = frozenset({
    ToolHealthState.OFFLINE,
    ToolHealthState.DISABLED,
    ToolHealthState.MISCONFIGURED,
    ToolHealthState.MISSING_CREDENTIALS,
})

_HEALTH_SCORE: dict[ToolHealthState, float] = {
    ToolHealthState.ONLINE: 100.0,
    ToolHealthState.DEGRADED: 50.0,
    ToolHealthState.UNKNOWN: 25.0,
    ToolHealthState.OFFLINE: 0.0,
    ToolHealthState.DISABLED: 0.0,
    ToolHealthState.MISCONFIGURED: 0.0,
    ToolHealthState.MISSING_CREDENTIALS: 0.0,
}


@dataclass
class ProviderRegistry:
    """Register providers, validate runtime compatibility, and sync health."""

    runtime_version: str = TOOL_RUNTIME_VERSION
    credential_manager: CredentialManager | None = None
    configuration_store: ProviderConfigurationStore | None = None
    _providers: dict[str, BaseProvider] = field(default_factory=dict)

    def attach_bootstrap(
        self,
        credential_manager: CredentialManager,
        configuration_store: ProviderConfigurationStore,
    ) -> None:
        """Attach credential and configuration services for provider bootstrap."""
        self.credential_manager = credential_manager
        self.configuration_store = configuration_store

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
        configuration = (
            self.configuration_store.get(provider_id)
            if self.configuration_store is not None
            else None
        )
        return reconcile_probe_health(
            provider_id,
            health,
            credential_manager=self.credential_manager,
            configuration=configuration,
        )

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

    def get_metadata(
        self,
        provider_id: str,
        *,
        default_execution_mode: ExecutionMode = ExecutionMode.LIVE,
    ) -> ProviderMetadata | None:
        """Return complete metadata for a registered provider."""
        provider = self.get(provider_id)
        if provider is None:
            return None
        health = self.probe(provider_id)
        credential_status = ""
        configured = True
        enabled = True
        if self.credential_manager is not None:
            validation = self.credential_manager.validate(provider_id)
            credential_status = validation.status.value
            configured = validation.configured
        if self.configuration_store is not None:
            config = self.configuration_store.get(provider_id)
            if config is not None:
                enabled = config.enabled
        return ProviderMetadata.from_provider(
            provider,
            health=health,
            default_execution_mode=default_execution_mode,
            credential_status=credential_status,
            configured=configured,
            enabled=enabled,
        )

    def list_metadata(
        self,
        *,
        default_execution_mode: ExecutionMode = ExecutionMode.LIVE,
    ) -> list[ProviderMetadata]:
        """Return metadata for all registered providers."""
        return [
            meta
            for provider_id in self.list_ids()
            if (meta := self.get_metadata(
                provider_id,
                default_execution_mode=default_execution_mode,
            ))
            is not None
        ]

    def list_for_action(self, action: str) -> list[str]:
        """Return provider IDs that support the given action, sorted by id."""
        matching: list[str] = []
        for provider_id in self.list_ids():
            provider = self.get(provider_id)
            if provider is not None and action in provider.supported_actions():
                matching.append(provider_id)
        return matching

    def list_for_capability(self, capability: str) -> list[str]:
        """Return provider IDs that implement the given capability."""
        matching: list[str] = []
        for provider_id in self.list_ids():
            provider = self.get(provider_id)
            if provider is not None and capability in provider.capabilities():
                matching.append(provider_id)
        return matching

    def select_providers(
        self,
        action: str,
        execution_mode: ExecutionMode,
        *,
        capability: str | None = None,
        health_monitor: HealthMonitor | None = None,
        performance_model: ProviderPerformanceModel | None = None,
    ) -> list[tuple[str, float]]:
        """Return ordered (provider_id, score) pairs for fallback routing."""
        if capability:
            candidates = self.list_for_capability(capability)
        else:
            candidates = self.list_for_action(action)

        scored: list[tuple[str, float]] = []
        for provider_id in candidates:
            provider = self.get(provider_id)
            if provider is None:
                continue
            if not provider.supports_execution_mode(execution_mode):
                continue
            health = self.probe(provider_id)
            if health_monitor is not None:
                monitor_state = health_monitor.get_provider_health(provider_id)
                if monitor_state in _BLOCKED_STATES:
                    continue
            if health.state in _BLOCKED_STATES:
                continue
            score = _HEALTH_SCORE.get(health.state, 0.0)
            if action in provider.supported_actions():
                score += 10.0
            if self.configuration_store is not None:
                config = self.configuration_store.get(provider_id)
                if config is not None:
                    score += max(0.0, 200.0 - float(config.priority))
            if performance_model is not None:
                perf_delta, _ = performance_model.ranking_adjustment(provider_id)
                score += perf_delta
            scored.append((provider_id, round(score, 2)))

        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored
