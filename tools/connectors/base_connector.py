# =====================================
# Titan Base External Connector
# =====================================

"""Abstract connector contract for user-owned external systems (Phase 12.5 — P125-002)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConnectorResult:
    """Structured outcome from a connector operation."""

    success: bool
    action: str
    data: str = ""
    error: str = ""
    target_path: str = ""

    def format_for_tool(self) -> str:
        """Format connector output for ToolResult.data."""
        if not self.success:
            return self.error
        return self.data


class BaseExternalConnector(ABC):
    """Reusable base for external tool connectors backed by a bounded root path."""

    def __init__(
        self,
        vault_root: Path | None,
        *,
        enabled: bool = True,
    ) -> None:
        self._vault_root = vault_root.resolve() if vault_root else None
        self._enabled = enabled

    @property
    @abstractmethod
    def connector_id(self) -> str:
        """Stable connector identifier (e.g. obsidian)."""

    @property
    def vault_root(self) -> Path | None:
        """Configured vault root, if any."""
        return self._vault_root

    @property
    def is_configured(self) -> bool:
        """Return True when the connector is enabled and the vault exists."""
        if not self._enabled:
            return False
        if self._vault_root is None:
            return False
        return self._vault_root.is_dir()

    @abstractmethod
    def supported_actions(self) -> frozenset[str]:
        """Return action names this connector implements."""

    def configuration_error(self) -> str:
        """Return a French error when the connector is not ready."""
        if not self._enabled:
            return f"Connecteur {self.connector_id!r} désactivé."
        if self._vault_root is None or not str(self._vault_root).strip():
            return (
                f"Connecteur {self.connector_id!r} non configuré : "
                "définissez le chemin du vault."
            )
        return f"Vault introuvable : {self._vault_root}"

    def health_check(self) -> tuple[bool, str]:
        """Probe connector readiness without mutating external state."""
        if self.is_configured:
            return True, f"Vault accessible : {self._vault_root}"
        return False, self.configuration_error()

    def execute(self, action: str, params: dict) -> ConnectorResult:
        """Dispatch *action* to the connector implementation."""
        if action not in self.supported_actions():
            return ConnectorResult(
                success=False,
                action=action,
                error=f"Action non supportée : {action!r}",
            )
        if not self.is_configured:
            return ConnectorResult(
                success=False,
                action=action,
                error=self.configuration_error(),
            )
        return self._execute_action(action, params)

    @abstractmethod
    def _execute_action(self, action: str, params: dict) -> ConnectorResult:
        """Run a validated action against the configured vault."""
