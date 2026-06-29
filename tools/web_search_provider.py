# =====================================
# Titan Web Search Provider
# =====================================

"""Backward-compatible re-exports — prefer tools.providers.web_search_provider."""

from __future__ import annotations

from tools.providers.web_search_provider import (
    SearchResponse,
    SearchResult,
    StubWebSearchProvider,
    WebSearchProvider,
)

__all__ = [
    "SearchResponse",
    "SearchResult",
    "StubWebSearchProvider",
    "WebSearchProvider",
]
