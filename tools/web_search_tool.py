# =====================================
# Titan Web Search Tool (Provider Abstraction)
# =====================================

"""Web search tool with pluggable provider — no external API yet (Phase 9 — P9-080)."""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import (
    StubWebSearchProvider,
    WebSearchProvider,
)
from tools.tool_result import ToolResult


class WebSearchTool(BaseTool):
    """Web search via injectable provider abstraction."""

    def __init__(
        self,
        provider: WebSearchProvider | None = None,
        *,
        registry: ProviderRegistry | None = None,
    ) -> None:
        if provider is not None:
            self._provider = provider
        elif registry is not None:
            resolved = registry.get("web_search")
            if isinstance(resolved, WebSearchProvider):
                self._provider = resolved
            else:
                self._provider = StubWebSearchProvider()
        else:
            self._provider = StubWebSearchProvider()

    @property
    def provider(self) -> WebSearchProvider:
        """Return the active web search provider."""
        return self._provider

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_search",
            description=(
                "Recherche web via provider abstrait "
                f"(provider actuel : {self._provider.name})."
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    param_type="string",
                    description="Requête de recherche.",
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        query = str(params.get("query", "")).strip()
        if not query:
            return self._result(success=False, error="Requête de recherche vide.")

        response = self._provider.search(query)
        if not response.success:
            return self._result(success=False, error=response.error)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=response.format_for_agent(),
            source=f"web_search/{response.provider}",
        )
