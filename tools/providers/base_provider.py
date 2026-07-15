# =====================================
# Titan Base Provider
# =====================================

"""Abstract provider contract for the Phase 10A provider layer (P10A-023)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.tool_enums import ExecutionMode


class BaseProvider(ABC):
    """Contract for external capability backends wired through tools."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider identifier used by tools and dependency graph."""

    @property
    @abstractmethod
    def version_info(self) -> ProviderVersionInfo:
        """Version and compatibility metadata for registration validation."""

    @abstractmethod
    def health_check(self) -> ProviderHealth:
        """Probe operational readiness; no side effects beyond the probe."""

    def supports_execution_mode(self, mode: ExecutionMode) -> bool:
        """Return True when the provider supports the requested execution mode."""
        return self.version_info.supports_mode(mode)

    def capabilities(self) -> frozenset[str]:
        """Return capability identifiers this provider implements."""
        return frozenset({self.provider_id})

    def supported_actions(self) -> frozenset[str]:
        """Return action names this provider can execute."""
        return frozenset()
