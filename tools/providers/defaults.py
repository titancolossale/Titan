# =====================================
# Titan Default Providers
# =====================================

"""Register built-in provider stubs at startup (P10A-027)."""

from __future__ import annotations

from tools.providers.calendar_provider import StubCalendarProvider
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import StubWebSearchProvider


def register_default_providers(registry: ProviderRegistry) -> None:
    """Register all Phase 10A provider stubs when not already present."""
    defaults = (
        StubWebSearchProvider(),
        StubCalendarProvider(),
    )
    for provider in defaults:
        if registry.get(provider.provider_id) is None:
            registry.register(provider)
