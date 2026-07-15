# =====================================
# Titan Provider Configuration
# =====================================

"""Non-secret provider configuration separate from credentials (Phase 10B — P10B-302)."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import (
    TITAN_BRAVE_SEARCH_ENABLED,
    TITAN_BRAVE_SEARCH_PRIORITY,
    TITAN_BRAVE_SEARCH_RETRY_COUNT,
    TITAN_BRAVE_SEARCH_TIMEOUT_SECONDS,
    TITAN_CALENDAR_ENABLED,
    TITAN_CALENDAR_PRIORITY,
    TITAN_CALENDAR_RETRY_COUNT,
    TITAN_CALENDAR_TIMEOUT_SECONDS,
    TITAN_GITHUB_ENABLED,
    TITAN_GITHUB_PRIORITY,
    TITAN_GITHUB_RETRY_COUNT,
    TITAN_GITHUB_TIMEOUT_SECONDS,
    TITAN_TOOL_DEFAULT_EXECUTION_MODE,
    TITAN_WEB_SEARCH_ENABLED,
    TITAN_WEB_SEARCH_PRIORITY,
    TITAN_WEB_SEARCH_RETRY_COUNT,
    TITAN_WEB_SEARCH_TIMEOUT_SECONDS,
)
from tools.tool_enums import ExecutionMode


def _parse_execution_mode(value: str) -> ExecutionMode:
    try:
        return ExecutionMode(value.lower())
    except ValueError:
        return ExecutionMode.LIVE


@dataclass(frozen=True)
class ProviderConfiguration:
    """Operational settings for a provider — no secrets."""

    provider_id: str
    enabled: bool = True
    priority: int = 100
    timeout_seconds: float = 30.0
    retry_count: int = 2
    execution_mode: ExecutionMode = ExecutionMode.LIVE
    settings: dict[str, object] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Return True when configuration values are internally consistent."""
        return not self.validation_errors()

    def validation_errors(self) -> list[str]:
        """Return human-readable configuration errors."""
        errors: list[str] = []
        if self.timeout_seconds <= 0:
            errors.append("timeout_seconds must be positive")
        if self.retry_count < 0:
            errors.append("retry_count must be non-negative")
        if self.priority < 0:
            errors.append("priority must be non-negative")
        return errors


@dataclass
class ProviderConfigurationStore:
    """Registry of provider configurations loaded at bootstrap."""

    _configs: dict[str, ProviderConfiguration] = field(default_factory=dict)

    @classmethod
    def from_defaults(
        cls,
        default_execution_mode: ExecutionMode | None = None,
    ) -> ProviderConfigurationStore:
        """Build default configurations from settings and environment."""
        mode = default_execution_mode or _parse_execution_mode(
            TITAN_TOOL_DEFAULT_EXECUTION_MODE
        )
        store = cls()
        store.register(
            ProviderConfiguration(
                provider_id="web_search",
                enabled=TITAN_WEB_SEARCH_ENABLED,
                priority=TITAN_WEB_SEARCH_PRIORITY,
                timeout_seconds=TITAN_WEB_SEARCH_TIMEOUT_SECONDS,
                retry_count=TITAN_WEB_SEARCH_RETRY_COUNT,
                execution_mode=mode,
                settings={"stub_mode": True},
            )
        )
        store.register(
            ProviderConfiguration(
                provider_id="brave_search",
                enabled=TITAN_BRAVE_SEARCH_ENABLED,
                priority=TITAN_BRAVE_SEARCH_PRIORITY,
                timeout_seconds=TITAN_BRAVE_SEARCH_TIMEOUT_SECONDS,
                retry_count=TITAN_BRAVE_SEARCH_RETRY_COUNT,
                execution_mode=mode,
                settings={"require_credentials": True},
            )
        )
        store.register(
            ProviderConfiguration(
                provider_id="calendar",
                enabled=TITAN_CALENDAR_ENABLED,
                priority=TITAN_CALENDAR_PRIORITY,
                timeout_seconds=TITAN_CALENDAR_TIMEOUT_SECONDS,
                retry_count=TITAN_CALENDAR_RETRY_COUNT,
                execution_mode=mode,
                settings={"stub_mode": True},
            )
        )
        store.register(
            ProviderConfiguration(
                provider_id="github",
                enabled=TITAN_GITHUB_ENABLED,
                priority=TITAN_GITHUB_PRIORITY,
                timeout_seconds=TITAN_GITHUB_TIMEOUT_SECONDS,
                retry_count=TITAN_GITHUB_RETRY_COUNT,
                execution_mode=mode,
                settings={"require_credentials": True, "read_only": True},
            )
        )
        return store

    def register(self, config: ProviderConfiguration, *, replace: bool = False) -> None:
        """Register configuration for a provider."""
        if config.provider_id in self._configs and not replace:
            raise ValueError(f"Provider configuration already registered: {config.provider_id}")
        self._configs[config.provider_id] = config

    def get(self, provider_id: str) -> ProviderConfiguration | None:
        """Return configuration for a provider or None when unknown."""
        return self._configs.get(provider_id)

    def get_or_default(self, provider_id: str) -> ProviderConfiguration:
        """Return registered configuration or a permissive default."""
        existing = self.get(provider_id)
        if existing is not None:
            return existing
        return ProviderConfiguration(provider_id=provider_id)

    def list_ids(self) -> list[str]:
        """Return sorted provider identifiers with configuration."""
        return sorted(self._configs.keys())
