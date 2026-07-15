# =====================================
# Titan Provider Metadata
# =====================================

"""Provider capability metadata for registry inspection and dashboards (P10B-202)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from tools.provider_version import ProviderHealth
from tools.providers.base_provider import BaseProvider
from tools.tool_enums import ExecutionMode, ToolHealthState


@dataclass(frozen=True)
class ProviderMetadata:
    """Complete metadata descriptor for a registered provider."""

    provider_name: str
    version: str
    capabilities: tuple[str, ...]
    health: ToolHealthState
    execution_mode: str
    supported_actions: tuple[str, ...]
    health_message: str = ""
    min_runtime_version: str = ""
    supported_execution_modes: tuple[str, ...] = ()
    credential_status: str = ""
    configured: bool = True
    enabled: bool = True

    def to_dict(self) -> dict:
        """Serialize for dashboards, logs, and API export."""
        return asdict(self)

    @classmethod
    def from_provider(
        cls,
        provider: BaseProvider,
        *,
        health: ProviderHealth | None = None,
        default_execution_mode: ExecutionMode = ExecutionMode.LIVE,
        credential_status: str = "",
        configured: bool = True,
        enabled: bool = True,
    ) -> ProviderMetadata:
        """Build metadata from a live provider instance and optional health probe."""
        info = provider.version_info
        probed = health or provider.health_check()
        modes = sorted(m.value for m in info.compatible_modes)
        return cls(
            provider_name=provider.provider_id,
            version=info.version,
            capabilities=tuple(sorted(provider.capabilities())),
            health=probed.state,
            execution_mode=default_execution_mode.value,
            supported_actions=tuple(sorted(provider.supported_actions())),
            health_message=probed.message,
            min_runtime_version=info.min_runtime_version,
            supported_execution_modes=tuple(modes),
            credential_status=credential_status,
            configured=configured,
            enabled=enabled,
        )
