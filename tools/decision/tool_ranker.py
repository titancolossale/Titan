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
    Intent.DOCUMENT: (
        ("file_read", 75.0, "Document read via file tool"),
        ("web_search", 30.0, "Fallback: search for document info"),
    ),
    Intent.TRADING: (),
    Intent.EMAIL: (),
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

        if intent in {Intent.FILE, Intent.DOCUMENT} and has_path:
            if any(kw in lowered for kw in _READ_KEYWORDS):
                self._boost(candidates, "file_read", 96.0, "Read keyword + file path", available_tools)
            if any(kw in lowered for kw in _WRITE_KEYWORDS):
                self._boost(candidates, "file_write", 96.0, "Write keyword + file path", available_tools)

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
