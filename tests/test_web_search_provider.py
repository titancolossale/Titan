# =====================================
# Titan Web Search Provider Tests
# =====================================

"""Tests for Phase 9 web search abstraction (P9-080)."""

from __future__ import annotations

from tools.web_search_provider import StubWebSearchProvider
from tools.web_search_tool import WebSearchTool


def test_stub_provider_returns_empty_results() -> None:
    """Stub provider succeeds with zero results — no external API."""
    provider = StubWebSearchProvider()
    response = provider.search("Titan AI")

    assert response.success is True
    assert response.results == []
    assert response.provider == "stub"


def test_web_search_tool_uses_provider() -> None:
    """Tool delegates to injected provider."""
    tool = WebSearchTool(provider=StubWebSearchProvider())
    result = tool.run(query="test query")

    assert result.success is True
    assert "stub" in result.source
