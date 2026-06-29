# =====================================
# Titan Web Agent Tests
# =====================================

"""Tests for Phase 9 web agent (P9-081)."""

from __future__ import annotations

from agents.agent_context import AgentContext
from agents.web_agent import WebAgent
from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.tool_enums import ExecutionMode, ToolHealthState
from tools.web_search_provider import SearchResponse, SearchResult, WebSearchProvider


class _MockProvider(WebSearchProvider):
    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def name(self) -> str:
        return "mock"

    @property
    def version_info(self) -> ProviderVersionInfo:
        return ProviderVersionInfo(
            provider_id="mock",
            version="0.0.0",
            min_runtime_version="0.10.0",
            compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
        )

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(state=ToolHealthState.ONLINE)

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title="Titan Docs",
                    url="https://example.com/titan",
                    snippet="Architecture overview",
                    source="mock",
                ),
            ],
            provider="mock",
        )


def test_web_agent_returns_cited_results() -> None:
    """Web agent formats provider results with citation metadata."""
    agent = WebAgent(provider=_MockProvider())
    result = agent.execute(
        "recherche architecture Titan",
        AgentContext(user_message="recherche architecture Titan", task="recherche architecture Titan"),
    )

    assert result.confidence >= 0.5
    assert "example.com" in result.result
    assert "mock" in result.summary
