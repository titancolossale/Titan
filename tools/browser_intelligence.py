# =====================================
# Titan Browser Intelligence
# =====================================

"""Cognitive web research orchestration — search, read, compare, cite (Phase 23.0).

Browser Intelligence provides information; Brain retains reasoning authority.
Never replaces Titan's decision layer — executes structured research plans only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_models import BrowserResearchResult, BrowserSource

SearchHit = tuple[str, str, str]  # title, url, snippet
SearchFn = Callable[[str, int], list[SearchHit]]

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+",
    re.IGNORECASE,
)

_QUERY_PREFIXES = (
    "recherche sur le web",
    "recherche web",
    "recherche en ligne",
    "cherche sur le web",
    "cherche en ligne",
    "trouve des infos sur",
    "trouve des informations sur",
    "informations sur",
    "information sur",
    "explique-moi",
    "explique moi",
    "qu'est-ce que",
    "quest-ce que",
    "compare les sources sur",
    "compare ",
    "search the web for",
    "search for",
    "find information about",
    "look up",
)

_DEFAULT_MAX_SOURCES = 3
_EXCERPT_MAX_CHARS = 600


class BrowserIntelligenceService:
    """Orchestrate multi-step web research via BrowserConnector."""

    def __init__(
        self,
        connector: BrowserConnector,
        *,
        search_fn: SearchFn | None = None,
        max_sources: int = _DEFAULT_MAX_SOURCES,
    ) -> None:
        self._connector = connector
        self._search_fn = search_fn
        self._max_sources = max(1, min(max_sources, 5))

    @staticmethod
    def extract_urls(message: str) -> list[str]:
        """Return deduplicated http(s) URLs found in *message*."""
        seen: set[str] = set()
        urls: list[str] = []
        for match in _URL_PATTERN.finditer(message):
            url = match.group(0).rstrip(".,);]")
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    @staticmethod
    def extract_query(message: str) -> str:
        """Derive a search query from natural language — never invent missing facts."""
        text = message.strip()
        lowered = text.lower()
        for prefix in _QUERY_PREFIXES:
            if lowered.startswith(prefix):
                text = text[len(prefix) :].strip(" :—-.,?")
                break
        text = _URL_PATTERN.sub("", text).strip(" :—-.,?")
        return text or message.strip()

    def research_web(self, query: str) -> BrowserResearchResult:
        """
        Search the web, open top results, extract excerpts, return citations.

        Falls back to empty sources when search is unavailable — Brain may clarify.
        """
        cleaned = query.strip()
        if not cleaned:
            return BrowserResearchResult(
                query="",
                status="empty_query",
                warnings=("Requête de recherche vide.",),
            )

        if not self._connector.is_configured:
            return BrowserResearchResult(
                query=cleaned,
                status="browser_unavailable",
                warnings=("Connecteur Browser désactivé ou non configuré.",),
            )

        hits: list[SearchHit] = []
        warnings: list[str] = []
        if self._search_fn is not None:
            try:
                hits = self._search_fn(cleaned, self._max_sources)
            except Exception as exc:
                warnings.append(f"Recherche web indisponible : {exc}")
        else:
            warnings.append("Recherche web non configurée — ouverture directe impossible.")

        if not hits:
            return BrowserResearchResult(
                query=cleaned,
                status="no_results",
                warnings=tuple(warnings) or ("Aucun résultat de recherche.",),
            )

        sources = self._read_hits(hits, warnings)
        status = "ok" if sources else "read_failed"
        return BrowserResearchResult(
            query=cleaned,
            sources=tuple(sources),
            status=status,
            warnings=tuple(warnings),
        )

    def compare_sources(self, urls: list[str]) -> BrowserResearchResult:
        """Read and extract structured excerpts from multiple URLs for comparison."""
        cleaned = [url.strip() for url in urls if url.strip()]
        if len(cleaned) < 2:
            return BrowserResearchResult(
                query="comparaison",
                status="insufficient_urls",
                warnings=("Au moins deux URLs sont requises pour comparer des sources.",),
            )

        if not self._connector.is_configured:
            return BrowserResearchResult(
                query="comparaison",
                status="browser_unavailable",
                warnings=("Connecteur Browser désactivé ou non configuré.",),
            )

        hits = [
            (f"Source {index + 1}", url, "")
            for index, url in enumerate(cleaned[: self._max_sources])
        ]
        warnings: list[str] = []
        sources = self._read_hits(hits, warnings)
        return BrowserResearchResult(
            query="comparaison de sources",
            sources=tuple(sources),
            status="ok" if sources else "read_failed",
            warnings=tuple(warnings),
        )

    def read_article(self, url: str) -> BrowserResearchResult:
        """Open a single page and return structured excerpt with citation."""
        if not url.strip():
            return BrowserResearchResult(
                query="",
                status="empty_url",
                warnings=("URL manquante.",),
            )

        if not self._connector.is_configured:
            return BrowserResearchResult(
                query=url,
                status="browser_unavailable",
                warnings=("Connecteur Browser désactivé ou non configuré.",),
            )

        warnings: list[str] = []
        sources = self._read_hits([(url, url, "")], warnings)
        return BrowserResearchResult(
            query=url,
            sources=tuple(sources),
            status="ok" if sources else "read_failed",
            warnings=tuple(warnings),
        )

    def _read_hits(
        self,
        hits: list[SearchHit],
        warnings: list[str],
    ) -> list[BrowserSource]:
        """Open each hit URL and collect structured excerpts."""
        sources: list[BrowserSource] = []
        for index, hit in enumerate(hits[: self._max_sources], start=1):
            title, url, snippet = hit
            outcome = self._connector.execute(
                "open_page",
                {"action": "open_page", "url": url},
            )
            if not outcome.success:
                warnings.append(f"Lecture impossible : {title or url}")
                continue

            page_title = title or url
            excerpt = snippet
            try:
                import json

                payload = json.loads(outcome.data or "{}")
                page_title = str(payload.get("page_title") or title or url).strip()
                page_text = str(payload.get("page_text") or "").strip()
                if page_text:
                    excerpt = page_text[:_EXCERPT_MAX_CHARS]
                elif not excerpt:
                    excerpt = str(payload.get("url") or url)
            except (json.JSONDecodeError, TypeError, AttributeError):
                if outcome.data:
                    excerpt = str(outcome.data)[:_EXCERPT_MAX_CHARS]

            sources.append(
                BrowserSource(
                    title=page_title,
                    url=url,
                    excerpt=excerpt,
                    index=index,
                ),
            )
        return sources


def default_search_fn(tool_manager: Any) -> SearchFn | None:
    """Build a search callable from ToolManager or ToolRegistry web_search tool."""
    registry = getattr(tool_manager, "registry", tool_manager)
    if registry is None or not hasattr(registry, "get"):
        return None

    web_search = registry.get("web_search")
    if web_search is None:
        return None

    def _search(query: str, max_results: int) -> list[SearchHit]:
        result = web_search.run(query=query)
        if not result.success:
            return []

        from tools.providers.web_search_provider import SearchResponse

        hits: list[SearchHit] = []
        if isinstance(result.data, str):
            for line in result.data.splitlines():
                if line.strip().startswith("http"):
                    hits.append(("Résultat", line.strip(), ""))
            return hits[:max_results]

        metadata = result.metadata or {}
        raw_results = metadata.get("results")
        if isinstance(raw_results, list):
            for item in raw_results[:max_results]:
                if isinstance(item, dict):
                    hits.append(
                        (
                            str(item.get("title", "Résultat")),
                            str(item.get("url", "")),
                            str(item.get("snippet", "")),
                        ),
                    )
            return [h for h in hits if h[1]]

        return _parse_search_text(result.data or "", max_results)

    return _search


def _parse_search_text(text: str, max_results: int) -> list[SearchHit]:
    """Parse formatted web search output into structured hits."""
    hits: list[SearchHit] = []
    current_title = ""
    current_url = ""
    current_snippet = ""

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0].isdigit() and ". " in stripped[:4]:
            if current_url:
                hits.append((current_title, current_url, current_snippet))
            current_title = stripped.split(". ", 1)[-1].strip()
            current_url = ""
            current_snippet = ""
        elif stripped.lower().startswith("url :"):
            current_url = stripped.split(":", 1)[-1].strip()
        elif stripped.lower().startswith("extrait :"):
            current_snippet = stripped.split(":", 1)[-1].strip()

    if current_url:
        hits.append((current_title, current_url, current_snippet))

    return hits[:max_results]
