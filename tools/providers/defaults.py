# =====================================
# Titan Default Providers
# =====================================

"""Register built-in provider stubs at startup (P10A-027, P10B-304)."""

from __future__ import annotations

from pathlib import Path

from config.settings import PROJECT_ROOT
from tools.providers.brave_search_provider import BraveSearchProvider
from tools.providers.calendar_provider import StubCalendarProvider
from tools.providers.credential_manager import CredentialManager
from tools.providers.file_system_provider import LocalFileSystemProvider
from tools.providers.github_provider import LiveGitHubProvider
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import StubWebSearchProvider


def create_provider_bootstrap(
    env: dict[str, str | None] | None = None,
) -> tuple[CredentialManager, ProviderConfigurationStore]:
    """Create shared credential and configuration services for provider bootstrap."""
    credential_manager = CredentialManager(env=env)
    configuration_store = ProviderConfigurationStore.from_defaults()
    return credential_manager, configuration_store


def register_default_providers(
    registry: ProviderRegistry,
    *,
    credential_manager: CredentialManager | None = None,
    configuration_store: ProviderConfigurationStore | None = None,
    project_root: Path | None = None,
) -> None:
    """Register all Phase 10A provider stubs when not already present."""
    if credential_manager is None or configuration_store is None:
        bootstrap_cm, bootstrap_cs = create_provider_bootstrap()
        credential_manager = credential_manager or bootstrap_cm
        configuration_store = configuration_store or bootstrap_cs

    if registry.credential_manager is None or registry.configuration_store is None:
        registry.attach_bootstrap(credential_manager, configuration_store)

    root = (project_root or PROJECT_ROOT).resolve()
    defaults = (
        LocalFileSystemProvider(
            root,
            context=_context_for("file_system", credential_manager, configuration_store),
        ),
        BraveSearchProvider(
            context=_context_for("brave_search", credential_manager, configuration_store),
        ),
        StubWebSearchProvider(
            context=_context_for("web_search", credential_manager, configuration_store),
        ),
        StubCalendarProvider(
            context=_context_for("calendar", credential_manager, configuration_store),
        ),
        LiveGitHubProvider(
            context=_context_for("github", credential_manager, configuration_store),
        ),
    )
    for provider in defaults:
        existing = registry.get(provider.provider_id)
        if provider.provider_id == "file_system":
            if project_root is not None:
                registry.register(provider, replace=True)
            elif existing is None:
                registry.register(provider)
            continue
        if existing is None:
            registry.register(provider)


def _context_for(
    provider_id: str,
    credential_manager: CredentialManager,
    configuration_store: ProviderConfigurationStore,
) -> ProviderContext:
    """Build injected context for a known default provider."""
    return ProviderContext(
        credential_manager=credential_manager,
        configuration=configuration_store.get_or_default(provider_id),
    )
