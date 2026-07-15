# =====================================
# Titan Web Search Tool (Provider Abstraction)
# =====================================

"""Web search tool with pluggable provider — no external API yet (Phase 9 — P9-080)."""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.health_monitor import HealthMonitor
from tools.providers.provider_executor import (
    ProviderExecutionContext,
    ProviderExecutor,
    provider_outcome_metadata,
)
from tools.providers.provider_fallback_policy import format_fallback_user_notice
from tools.providers.provider_registry import ProviderRegistry
from tools.providers.web_search_provider import (
    SearchResponse,
    StubWebSearchProvider,
    WebSearchProvider,
)
from tools.tool_enums import ExecutionMode
from tools.tool_result import ToolResult


class WebSearchTool(BaseTool):
    """Web search via ProviderExecutor — registry-authoritative (P10B-201)."""

    def __init__(
        self,
        provider: WebSearchProvider | None = None,
        *,
        registry: ProviderRegistry | None = None,
        provider_executor: ProviderExecutor | None = None,
    ) -> None:
        self._legacy_provider = provider
        self._executor = provider_executor
        if self._executor is None and registry is not None:
            self._executor = ProviderExecutor(
                registry=registry,
                health_monitor=HealthMonitor(),
            )
        elif self._executor is None and provider is None:
            self._legacy_provider = StubWebSearchProvider()

    @property
    def provider(self) -> WebSearchProvider:
        """Return active provider for backward-compatible inspection."""
        if self._legacy_provider is not None:
            return self._legacy_provider
        if self._executor is not None:
            resolved = self._executor.registry.get("web_search")
            if isinstance(resolved, WebSearchProvider):
                return resolved
        return StubWebSearchProvider()

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_search",
            description=(
                "Recherche web via provider abstrait "
                f"(provider actuel : {self.provider.provider_id})."
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

        if self._legacy_provider is not None and self._executor is None:
            response = self._legacy_provider.search(query)
            if not response.success:
                return self._result(success=False, error=response.error)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=response.format_for_agent(),
                source=f"web_search/{response.provider}",
            )

        if self._executor is None:
            return self._result(
                success=False,
                error="ProviderExecutor non configuré — exécution impossible.",
            )

        exec_params = dict(params)
        exec_params["query"] = query
        ctx_meta = exec_params.pop("_execution_context", {}) or {}
        if not isinstance(ctx_meta, dict):
            ctx_meta = {}

        ctx = ProviderExecutionContext.from_tool_metadata(
            action="search",
            params=exec_params,
            tool_name=self.name,
            ctx_meta=ctx_meta,
        )
        outcome = self._executor.execute(
            "search",
            exec_params,
            capability="web_search",
            context=ctx,
            execution_mode=ctx.execution_mode,
        )

        if outcome.no_capability or outcome.provider_unavailable:
            metadata = provider_outcome_metadata(outcome)
            notice = format_fallback_user_notice(
                outcome,
                fallback_decision=str(ctx_meta.get("fallback_decision", "")),
            )
            if notice:
                metadata["fallback_notice"] = notice
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=outcome.error,
                source="provider_executor",
                metadata=metadata,
            )

        if not outcome.success:
            return self._result(success=False, error=outcome.error)

        response = outcome.data
        if not isinstance(response, SearchResponse):
            return self._result(success=False, error="Réponse provider invalide.")

        metadata = provider_outcome_metadata(outcome)
        notice = format_fallback_user_notice(
            outcome,
            fallback_decision=str(ctx_meta.get("fallback_decision", "")),
        )
        if notice:
            metadata["fallback_notice"] = notice

        body = response.format_for_agent()
        if notice:
            body = f"{notice}\n\n{body}"

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=body,
            source=f"web_search/{outcome.provider_id}",
            metadata=metadata,
        )
