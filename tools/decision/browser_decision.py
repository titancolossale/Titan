# =====================================
# Titan Browser Decision Layer
# =====================================

"""Decide when and how Titan uses the Browser connector (Phase 13.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tools.connectors.browser_connector import BrowserConnector

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+",
    re.IGNORECASE,
)

_BROWSER_SIGNALS = (
    "navigateur",
    "browser",
    "page web",
    "webpage",
    "site web",
    "website",
)

_OPEN_KEYWORDS = (
    "ouvre la page",
    "ouvre le site",
    "open page",
    "open webpage",
    "open the page",
    "open website",
    "va sur",
    "go to",
    "navigate to",
    "navigue vers",
    "visite",
    "visit ",
)

_READ_KEYWORDS = (
    "lis la page",
    "lis cette page",
    "lire la page",
    "lire cette page",
    "read page",
    "read the page",
    "read this page",
    "contenu de la page",
    "page content",
    "affiche la page",
    "show page",
)

_EXTRACT_KEYWORDS = (
    "extrait le texte",
    "extract text",
    "texte visible",
    "visible text",
    "extraire le texte",
)

_SCROLL_KEYWORDS = (
    "fais défiler",
    "fais defiler",
    "défiler la page",
    "defiler la page",
    "défiler",
    "defiler",
    "scroll la page",
    "scroll page",
    "scroll ",
)

_SCREENSHOT_KEYWORDS = (
    "capture d'écran",
    "capture d ecran",
    "capture ecran",
    "prends une capture",
    "prend une capture",
    "take screenshot",
    "screenshot",
)


_COMPARE_KEYWORDS = (
    "compare les sources",
    "compare ces sources",
    "compare les pages",
    "compare ces pages",
    "compare multiple",
    "compare sources",
    "comparer les sources",
    "comparer ces sources",
)

_SEARCH_KEYWORDS = (
    "recherche sur le web",
    "recherche web",
    "recherche en ligne",
    "cherche sur le web",
    "cherche en ligne",
    "trouve des infos",
    "trouve des informations",
    "informations sur",
    "information sur",
    "search the web",
    "search for",
    "web search",
    "look up",
    "find information",
)

_RESEARCH_KEYWORDS = (
    "article sur",
    "articles sur",
    "lire un article",
    "read article",
    "analyse les sources",
    "analyse web",
    "explique-moi",
    "explique moi",
    "qu'est-ce que",
    "quest-ce que",
    "c'est quoi",
)


class BrowserDecision(str, Enum):
    """Outcome of the Browser decision layer."""

    OPEN_PAGE = "open_page"
    NAVIGATE = "navigate"
    READ_PAGE = "read_page"
    EXTRACT_TEXT = "extract_text"
    SCROLL_PAGE = "scroll_page"
    TAKE_SCREENSHOT = "take_screenshot"
    RESEARCH_WEB = "research_web"
    COMPARE_SOURCES = "compare_sources"
    READ_ARTICLE = "read_article"
    DO_NOT_USE_BROWSER = "do_not_use_browser"


@dataclass(frozen=True)
class BrowserDecisionResult:
    """Structured Browser routing decision."""

    decision: BrowserDecision
    reason: str
    url: str = ""
    tool_params: tuple[tuple[str, object], ...] = ()

    def tool_params_dict(self) -> dict[str, object]:
        """Return params suitable for ToolRequest."""
        return dict(self.tool_params)


class BrowserDecisionEngine:
    """Map natural language requests to Browser connector actions."""

    def __init__(self, connector: BrowserConnector | None = None) -> None:
        self._connector = connector or BrowserConnector(enabled=True)

    def decide(self, message: str) -> BrowserDecisionResult:
        """Return the Browser action Titan should take for *message*."""
        lowered = message.lower().strip()
        url = self._extract_url(message)
        urls = self._extract_urls(message)

        if any(kw in lowered for kw in _COMPARE_KEYWORDS) and len(urls) >= 2:
            return self._compare_result(
                "Comparaison de plusieurs sources web demandée.",
                urls,
            )

        if any(kw in lowered for kw in _SEARCH_KEYWORDS) and not url:
            query = self._extract_search_query(message)
            return self._research_result(
                "Recherche web cognitive demandée.",
                query,
            )

        if any(kw in lowered for kw in _RESEARCH_KEYWORDS) and not url:
            query = self._extract_search_query(message)
            if query:
                return self._research_result(
                    "Exploration web et lecture d'articles demandée.",
                    query,
                )

        if url and any(
            kw in lowered
            for kw in ("article", "lire l'article", "read article", "analyse cette page")
        ):
            return self._article_result(
                "Lecture d'article web demandée.",
                url,
            )

        if any(kw in lowered for kw in _EXTRACT_KEYWORDS):
            if url:
                return self._url_result(
                    BrowserDecision.EXTRACT_TEXT,
                    "Extraction de texte visible demandée.",
                    url,
                )
            return self._session_result(
                BrowserDecision.EXTRACT_TEXT,
                "Extraction du texte visible de la page active.",
            )

        if any(kw in lowered for kw in _READ_KEYWORDS):
            if url:
                return self._url_result(
                    BrowserDecision.READ_PAGE,
                    "Lecture de page web demandée.",
                    url,
                )
            return self._session_result(
                BrowserDecision.READ_PAGE,
                "Lecture de la page active.",
            )

        if any(kw in lowered for kw in _SCROLL_KEYWORDS):
            return self._session_result(
                BrowserDecision.SCROLL_PAGE,
                "Défilement de la page demandé.",
            )

        if any(kw in lowered for kw in _SCREENSHOT_KEYWORDS):
            return self._session_result(
                BrowserDecision.TAKE_SCREENSHOT,
                "Capture d'écran demandée.",
            )

        if any(kw in lowered for kw in _OPEN_KEYWORDS):
            action = BrowserDecision.NAVIGATE if "navig" in lowered else BrowserDecision.OPEN_PAGE
            return self._url_result(
                action,
                "Ouverture ou navigation vers une page web demandée.",
                url,
            )

        has_browser_signal = any(signal in lowered for signal in _BROWSER_SIGNALS)
        if url and (has_browser_signal or self._looks_like_page_request(lowered)):
            return self._url_result(
                BrowserDecision.OPEN_PAGE,
                "URL web détectée avec intention de consultation.",
                url,
            )

        if has_browser_signal and not url:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason="Intention navigateur détectée mais aucune URL fournie.",
            )

        return BrowserDecisionResult(
            decision=BrowserDecision.DO_NOT_USE_BROWSER,
            reason="Aucune action navigateur pertinente pour ce message.",
        )

    def _looks_like_page_request(self, lowered: str) -> bool:
        return any(
            token in lowered
            for token in ("http://", "https://", "www.", ".com", ".org", ".fr")
        )

    def _extract_url(self, message: str) -> str:
        match = _URL_PATTERN.search(message)
        return match.group(0).rstrip(".,);]") if match else ""

    def _extract_urls(self, message: str) -> list[str]:
        return [
            match.group(0).rstrip(".,);]")
            for match in _URL_PATTERN.finditer(message)
        ]

    def _extract_search_query(self, message: str) -> str:
        from tools.browser_intelligence import BrowserIntelligenceService

        return BrowserIntelligenceService.extract_query(message)

    def _research_result(self, reason: str, query: str) -> BrowserDecisionResult:
        if not query.strip():
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason=f"{reason} Requête manquante.",
            )
        if not self._connector.is_configured:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason="Connecteur Browser désactivé ou non configuré.",
            )
        return BrowserDecisionResult(
            decision=BrowserDecision.RESEARCH_WEB,
            reason=reason,
            tool_params=(
                ("action", "research_web"),
                ("query", query.strip()),
            ),
        )

    def _compare_result(self, reason: str, urls: list[str]) -> BrowserDecisionResult:
        if not self._connector.is_configured:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason="Connecteur Browser désactivé ou non configuré.",
            )
        return BrowserDecisionResult(
            decision=BrowserDecision.COMPARE_SOURCES,
            reason=reason,
            tool_params=(
                ("action", "compare_sources"),
                ("urls", urls[:5]),
            ),
        )

    def _article_result(self, reason: str, url: str) -> BrowserDecisionResult:
        if not url:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason=f"{reason} URL manquante.",
            )
        if not self._connector.is_configured:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason="Connecteur Browser désactivé ou non configuré.",
            )
        return BrowserDecisionResult(
            decision=BrowserDecision.READ_ARTICLE,
            reason=reason,
            url=url,
            tool_params=(
                ("action", "read_article"),
                ("url", url),
            ),
        )

    def _url_result(
        self,
        decision: BrowserDecision,
        reason: str,
        url: str,
    ) -> BrowserDecisionResult:
        if not url:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason=f"{reason} URL manquante.",
            )
        if not self._connector.is_configured:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason="Connecteur Browser désactivé ou non configuré.",
            )
        action = decision.value
        return BrowserDecisionResult(
            decision=decision,
            reason=reason,
            url=url,
            tool_params=(("action", action), ("url", url)),
        )

    def _session_result(
        self,
        decision: BrowserDecision,
        reason: str,
    ) -> BrowserDecisionResult:
        if not self._connector.is_configured:
            return BrowserDecisionResult(
                decision=BrowserDecision.DO_NOT_USE_BROWSER,
                reason="Connecteur Browser désactivé ou non configuré.",
            )
        return BrowserDecisionResult(
            decision=decision,
            reason=reason,
            tool_params=(("action", decision.value),),
        )
