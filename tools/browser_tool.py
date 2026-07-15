# =====================================
# Titan Browser Tool
# =====================================

"""Browser web interaction tool — read and controlled interaction (Phase 13.3)."""

from __future__ import annotations

from config.settings import TITAN_BROWSER_ENABLED, TITAN_BROWSER_TIMEOUT_SECONDS
from tools.base_tool import BaseTool, ToolParameter, ToolSchema
from tools.browser_intelligence import BrowserIntelligenceService, default_search_fn
from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_permissions import (
    BROWSER_AUTO_ALLOWED_ACTIONS,
    BROWSER_CONFIRMATION_REQUIRED_ACTIONS,
)
from tools.tool_result import ToolResult

_INTELLIGENCE_ACTIONS = frozenset({
    "research_web",
    "compare_sources",
    "read_article",
})

_SUPPORTED_ACTIONS = (
    BROWSER_AUTO_ALLOWED_ACTIONS
    | BROWSER_CONFIRMATION_REQUIRED_ACTIONS
    | _INTELLIGENCE_ACTIONS
    - {
        "search_public",
        "download_file",
        "download",
        "upload_file",
        "upload",
        "submit_form",
        "submit",
        "login",
    }
)

_BROWSER_TOOL_DESCRIPTION = (
    "Capacité cognitive d'exploration web de Titan (Phase 23.0). "
    "Recherche le web, ouvre des pages, lit des articles, compare des sources, "
    "extrait des informations structurées et retourne des citations. "
    "Le Brain synthétise — le navigateur fournit l'information seulement. "
    "Actions : research_web, compare_sources, read_article, open_page, navigate, "
    "read_page, extract_text, scroll_page, take_screenshot. "
    "Les actions interactives nécessitent confirmed=true."
)


class BrowserTool(BaseTool):
    """Read and interact with web pages through the Browser connector."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        connector: BrowserConnector | None = None,
        intelligence: BrowserIntelligenceService | None = None,
        search_fn=None,
    ) -> None:
        is_enabled = TITAN_BROWSER_ENABLED if enabled is None else enabled
        resolved_timeout = (
            TITAN_BROWSER_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._connector = connector or BrowserConnector(
            enabled=is_enabled,
            timeout_seconds=resolved_timeout,
        )
        self._intelligence = intelligence or BrowserIntelligenceService(
            self._connector,
            search_fn=search_fn,
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="browser",
            description=_BROWSER_TOOL_DESCRIPTION,
            parameters=[
                ToolParameter(
                    name="action",
                    param_type="string",
                    description=(
                        "Action navigateur : research_web, compare_sources, read_article, "
                        "open_page, navigate, read_page, extract_text, click_element, "
                        "type_text, select_option, scroll_page, go_back, open_new_tab, "
                        "close_tab, wait_for_element, take_screenshot."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="query",
                    param_type="string",
                    description="Requête de recherche web (action research_web).",
                    required=False,
                ),
                ToolParameter(
                    name="urls",
                    param_type="array",
                    description="Liste d'URLs à comparer (action compare_sources).",
                    required=False,
                ),
                ToolParameter(
                    name="url",
                    param_type="string",
                    description="URL http(s) de la page à ouvrir ou lire.",
                    required=False,
                ),
                ToolParameter(
                    name="selector",
                    param_type="string",
                    description="Sélecteur CSS pour clic, saisie, sélection ou attente.",
                    required=False,
                ),
                ToolParameter(
                    name="text",
                    param_type="string",
                    description="Texte à saisir (action type_text).",
                    required=False,
                ),
                ToolParameter(
                    name="value",
                    param_type="string",
                    description="Valeur à sélectionner (action select_option).",
                    required=False,
                ),
                ToolParameter(
                    name="confirmed",
                    param_type="boolean",
                    description="Confirmation utilisateur pour actions interactives.",
                    required=False,
                ),
            ],
        )

    def run(self, **params: object) -> ToolResult:
        action = str(params.get("action", "")).strip()
        if not action:
            return self._result(success=False, error="Paramètre action requis.")
        if action not in _SUPPORTED_ACTIONS:
            return self._result(
                success=False,
                error=f"Action non supportée : {action!r}",
            )

        exec_params = {
            key: value
            for key, value in params.items()
            if not str(key).startswith("_")
        }
        if action in _INTELLIGENCE_ACTIONS:
            return self._run_intelligence(action, exec_params)

        outcome = self._connector.execute(action, exec_params)
        metadata = {
            "connector": self._connector.connector_id,
            "action": action,
            "target_url": outcome.target_path,
            "browser_configured": self._connector.is_configured,
            "session_started": self._connector.session.started,
        }
        return ToolResult(
            tool_name=self.name,
            success=outcome.success,
            data=outcome.format_for_tool(),
            error=outcome.error if not outcome.success else "",
            source="browser",
            metadata=metadata,
        )

    def _run_intelligence(self, action: str, params: dict[str, object]) -> ToolResult:
        """Execute Browser Intelligence research actions (Phase 23.0)."""
        if action == "research_web":
            query = str(params.get("query", "")).strip()
            result = self._intelligence.research_web(query)
        elif action == "compare_sources":
            raw_urls = params.get("urls") or []
            if isinstance(raw_urls, str):
                urls = [part.strip() for part in raw_urls.split(",") if part.strip()]
            else:
                urls = [str(item).strip() for item in raw_urls if str(item).strip()]
            result = self._intelligence.compare_sources(urls)
        elif action == "read_article":
            url = str(params.get("url", "")).strip()
            result = self._intelligence.read_article(url)
        else:
            return self._result(success=False, error=f"Action intelligence inconnue : {action!r}")

        sources = [source.to_dict() for source in result.sources]
        metadata = {
            "connector": self._connector.connector_id,
            "action": action,
            "browser_configured": self._connector.is_configured,
            "session_started": self._connector.session.started,
            "exploration": True,
            "sources": sources,
            "citations": [source.citation_label() for source in result.sources],
            "query": result.query,
            "research_status": result.status,
        }
        success = result.status in {"ok"} or bool(result.sources)
        return ToolResult(
            tool_name=self.name,
            success=success,
            data=result.format_for_tool(),
            error="" if success else ", ".join(result.warnings) or "Exploration échouée.",
            source="browser",
            metadata=metadata,
        )

    def wire_search_from_manager(self, tool_manager: object) -> None:
        """Attach web search when ToolManager is available (composition root hook)."""
        search_fn = default_search_fn(tool_manager)
        if search_fn is not None:
            self._intelligence = BrowserIntelligenceService(
                self._connector,
                search_fn=search_fn,
            )
