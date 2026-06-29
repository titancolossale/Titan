# =====================================
# Titan Providers Package
# =====================================

"""Provider layer for external tool backends (Phase 10A — Batch 5)."""

from tools.providers.base_provider import BaseProvider
from tools.providers.calendar_provider import (
    CalendarProvider,
    CalendarResponse,
    StubCalendarProvider,
)
from tools.providers.defaults import register_default_providers
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import (
    SearchResponse,
    SearchResult,
    StubWebSearchProvider,
    WebSearchProvider,
)

__all__ = [
    "BaseProvider",
    "CalendarProvider",
    "CalendarResponse",
    "ProviderRegistry",
    "SearchResponse",
    "SearchResult",
    "StubCalendarProvider",
    "StubWebSearchProvider",
    "WebSearchProvider",
    "register_default_providers",
]
