# =====================================
# Titan Web Search Provider (Reference)
# =====================================

"""Reference provider implementation — stub until external API phase (P10A-025)."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field

from tools.provider_version import ProviderHealth, ProviderVersionInfo
from tools.providers.base_provider import BaseProvider
from tools.providers.provider_context import ProviderContext
from tools.providers.provider_health_resolver import resolve_provider_health
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
    failure_reason: str = ""
    latency_ms: float = 0.0

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

    def capabilities(self) -> frozenset[str]:
        return frozenset({"web_search"})

    def supported_actions(self) -> frozenset[str]:
        return frozenset({"search"})

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        """Execute search and return structured results."""

    def news(self, query: str, *, max_results: int = 5, **kwargs: object) -> SearchResponse:
        """Execute news search; unsupported providers return a structured failure."""
        _ = kwargs
        return SearchResponse(
            query=query,
            provider=self.provider_id,
            success=False,
            error="Action news non supportée par ce provider.",
        )

    @property
    def name(self) -> str:
        """Backward-compatible alias for provider_id."""
        return self.provider_id


class StubWebSearchProvider(WebSearchProvider):
    """Local stub — returns empty results until external API integration."""

    def __init__(self, *, context: ProviderContext | None = None) -> None:
        self.context = context

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _STUB_VERSION

    def health_check(self) -> ProviderHealth:
        default = ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="Stub web search — aucune API externe configurée.",
        )
        return resolve_provider_health(
            self.provider_id,
            context=self.context,
            default_health=default,
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


_FALLBACK_VERSION = ProviderVersionInfo(
    provider_id="web_search_fallback",
    version="0.1.0",
    min_runtime_version="0.10.0",
    api_version=None,
    compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
)


class FallbackWebSearchProvider(WebSearchProvider):
    """Secondary web search provider for fallback routing tests (P10B-204)."""

    @property
    def provider_id(self) -> str:
        return "web_search_fallback"

    @property
    def version_info(self) -> ProviderVersionInfo:
        return _FALLBACK_VERSION

    def capabilities(self) -> frozenset[str]:
        return frozenset({"web_search"})

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="Fallback web search stub.",
        )

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        _ = max_results
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title=f"Fallback result for {query}",
                    url="https://example.com/fallback",
                    snippet="Résultat via provider fallback.",
                    source="fallback",
                ),
            ],
            provider="web_search_fallback",
            success=True,
            error="",
        )


class FailingWebSearchProvider(WebSearchProvider):
    """Provider that always fails execution — used for fallback tests."""

    @property
    def provider_id(self) -> str:
        return "web_search_failing"

    @property
    def version_info(self) -> ProviderVersionInfo:
        return ProviderVersionInfo(
            provider_id="web_search_failing",
            version="0.1.0",
            min_runtime_version="0.10.0",
            compatible_modes=frozenset({ExecutionMode.LIVE, ExecutionMode.MOCK}),
        )

    def capabilities(self) -> frozenset[str]:
        return frozenset({"web_search"})

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            state=ToolHealthState.ONLINE,
            message="Failing provider — simulates runtime failure.",
        )

    def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        _ = max_results
        return SearchResponse(
            query=query,
            provider="web_search_failing",
            success=False,
            error="Simulated provider failure.",
        )
