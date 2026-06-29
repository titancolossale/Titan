# =====================================
# Titan Web Search Provider (Reference)
# =====================================

"""Reference provider implementation — stub until external API phase (P10A-025)."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field

from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.base_provider import BaseProvider
from tools.tool_enums import ExecutionMode, ToolHealthState


@dataclass(frozen=True)
class SearchResult:
    """One web search hit."""

    title: str
    url: str
    snippet: str
    source: str = "stub"


@dataclass
class SearchResponse:
    """Structured search response for agents and tools."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    provider: str = "stub"
    success: bool = True
    error: str = ""

    def format_for_agent(self) -> str:
        """Format results with citations for agent consumption."""
        if not self.success:
            return f"Recherche échouée : {self.error}"
        if not self.results:
            return f"Aucun résultat pour : {self.query}"
        lines = [f"Résultats pour « {self.query} » :"]
        for index, hit in enumerate(self.results, start=1):
            lines.append(f"{index}. {hit.title}")
            lines.append(f"   URL : {hit.url}")
            lines.append(f"   Extrait : {hit.snippet}")
        return "\n".join(lines)


_STUB_VERSION = ProviderVersionInfo(
    provider_id="web_search",
    version="0.1.0",
    min_runtime_version="0.10.0",
    api_version=None,
    compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
)


class WebSearchProvider(BaseProvider):
    """Contract for web search backends."""

    @property
    def provider_id(self) -> str:
        return "web_search"

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        """Execute search and return structured results."""

    @property
    def name(self) -> str:
        """Backward-compatible alias for provider_id."""
        return self.provider_id


class StubWebSearchProvider(WebSearchProvider):
    """Local stub — returns empty results until external API integration."""

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _STUB_VERSION

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="Stub web search — aucune API externe configurée.",
        )

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        _ = max_results
        return SearchResponse(
            query=query,
            results=[],
            provider="stub",
            success=True,
            error="",
        )
