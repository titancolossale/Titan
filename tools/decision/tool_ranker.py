# =====================================
# Titan Tool Decision — Tool Ranker
# =====================================

"""Rank candidate tools by intent affinity and message signals (Phase 10B — P10B-004)."""

from __future__ import annotations

import re

from tools.decision.intent import Intent
from tools.decision.models import CandidateTool, IntentClassification

_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini|pdf|docx?)",
    re.IGNORECASE,
)

_LIST_KEYWORDS = (
    "liste",
    "list ",
    "montre les fichiers",
    "show files",
)
_SEARCH_KEYWORDS = (
    "trouve",
    "find",
    "cherche",
    "search",
    "locate",
    "look for",
)
_READ_KEYWORDS = (
    "lire",
    "read",
    "affiche",
    "show",
    "open",
    "ouvre",
    "contenu",
)
_WRITE_KEYWORDS = (
    "écris",
    "ecri",
    "write",
    "crée",
    "cree",
    "create",
)

_INTENT_BASE_SCORES: dict[Intent, tuple[tuple[str, float, str], ...]] = {
    Intent.WEB_SEARCH: (("web_search", 98.0, "Primary web search capability"),),
    Intent.SYSTEM: (("time", 95.0, "Datetime system tool"),),
    Intent.CALENDAR: (("calendar", 95.0, "Calendar scheduling tool"),),
    Intent.CODING: (
        ("python_exec", 92.0, "Python execution for code runs"),
        ("file_read", 44.0, "Secondary: inspect project files"),
    ),
    Intent.FILE: (
        ("file_read", 90.0, "File read operation"),
        ("file_write", 85.0, "File write operation"),
    ),
    Intent.FILE_LIST: (("file_read", 93.0, "List files in directory"),),
    Intent.FILE_SEARCH: (("file_read", 93.0, "Search project files"),),
    Intent.FILE_READ: (("file_read", 95.0, "Read file contents"),),
    Intent.FILE_METADATA: (("file_read", 91.0, "File metadata lookup"),),
    Intent.WORKSPACE_EXPLAIN: (("file_read", 96.0, "Workspace file read and explanation"),),
    Intent.GITHUB: (("github", 96.0, "GitHub API read operations"),),
    Intent.OBSIDIAN: (("obsidian", 96.0, "Obsidian vault read and maintain"),),
    Intent.BROWSER: (("browser", 96.0, "Browser page read and inspect"),),
    Intent.DOCUMENT: (
        ("file_read", 75.0, "Document read via file tool"),
        ("web_search", 30.0, "Fallback: search for document info"),
    ),
    Intent.TRADING: (("trading", 95.0, "Trading read and execute"),),
    Intent.EMAIL: (("email", 95.0, "Email read and manage"),),
    Intent.MEMORY: (),
    Intent.GENERAL_CHAT: (),
    Intent.UNKNOWN: (),
}


class ToolRanker:
    """Produce ordered candidate tool list filtered to available tools."""

    def rank(
        self,
        message: str,
        classification: IntentClassification,
        *,
        available_tools: frozenset[str],
    ) -> tuple[CandidateTool, ...]:
        """Return candidates sorted by descending score."""
        lowered = message.lower()
        intent = classification.intent
        base_entries = _INTENT_BASE_SCORES.get(intent, ())

        candidates: dict[str, CandidateTool] = {}
        for tool_name, base_score, reason in base_entries:
            if tool_name not in available_tools:
                continue
            candidates[tool_name] = CandidateTool(
                tool_name=tool_name,
                score=base_score,
                reason=reason,
            )

        self._apply_message_boosts(message, lowered, intent, available_tools, candidates)

        ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
        return tuple(ranked)

    def _apply_message_boosts(
        self,
        message: str,
        lowered: str,
        intent: Intent,
        available_tools: frozenset[str],
        candidates: dict[str, CandidateTool],
    ) -> None:
        """Adjust scores using message-specific signals."""
        has_path = _PATH_PATTERN.search(message) is not None

        file_intents = {
            Intent.FILE,
            Intent.FILE_LIST,
            Intent.FILE_SEARCH,
            Intent.FILE_READ,
            Intent.FILE_METADATA,
            Intent.DOCUMENT,
        }
        if intent in file_intents and has_path:
            if any(kw in lowered for kw in _READ_KEYWORDS):
                self._boost(candidates, "file_read", 96.0, "Read keyword + file path", available_tools)
            if any(kw in lowered for kw in _WRITE_KEYWORDS):
                self._boost(candidates, "file_write", 96.0, "Write keyword + file path", available_tools)

        if intent == Intent.FILE_LIST:
            self._boost(candidates, "file_read", 97.0, "File list intent", available_tools)
        if intent == Intent.FILE_SEARCH:
            self._boost(candidates, "file_read", 97.0, "File search intent", available_tools)
        if intent == Intent.FILE_READ:
            self._boost(candidates, "file_read", 98.0, "File read intent", available_tools)
        if intent == Intent.FILE_METADATA:
            self._boost(candidates, "file_read", 96.0, "File metadata intent", available_tools)
        if intent == Intent.WORKSPACE_EXPLAIN:
            self._boost(
                candidates,
                "file_read",
                98.0,
                "Workspace explanation intent",
                available_tools,
            )

        if intent == Intent.GITHUB and "github" in available_tools:
            self._boost(
                candidates,
                "github",
                98.0,
                "GitHub intent match",
                available_tools,
            )

        if intent == Intent.OBSIDIAN and "obsidian" in available_tools:
            self._boost(
                candidates,
                "obsidian",
                98.0,
                "Obsidian vault intent match",
                available_tools,
            )

        if intent == Intent.BROWSER and "browser" in available_tools:
            self._boost(
                candidates,
                "browser",
                98.0,
                "Browser page intent match",
                available_tools,
            )

        if intent == Intent.CALENDAR and "calendar" in available_tools:
            self._boost(
                candidates,
                "calendar",
                98.0,
                "Calendar scheduling intent match",
                available_tools,
            )

        if intent == Intent.EMAIL and "email" in available_tools:
            self._boost(
                candidates,
                "email",
                98.0,
                "Email intent match",
                available_tools,
            )

        if intent == Intent.TRADING and "trading" in available_tools:
            self._boost(
                candidates,
                "trading",
                98.0,
                "Trading intent match",
                available_tools,
            )

        if intent == Intent.WEB_SEARCH and "web_search" in available_tools:
            self._boost(
                candidates,
                "web_search",
                98.0,
                "Explicit search phrasing",
                available_tools,
            )

        if intent == Intent.SYSTEM and any(
            kw in lowered for kw in ("heure", "time", "date", "datetime")
        ):
            self._boost(candidates, "time", 97.0, "Datetime keywords", available_tools)

    def _boost(
        self,
        candidates: dict[str, CandidateTool],
        tool_name: str,
        score: float,
        reason: str,
        available_tools: frozenset[str],
    ) -> None:
        if tool_name not in available_tools:
            return
        existing = candidates.get(tool_name)
        if existing is None or score > existing.score:
            candidates[tool_name] = CandidateTool(
                tool_name=tool_name,
                score=score,
                reason=reason,
            )
