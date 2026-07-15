# =====================================
# Titan Tool Decision — Tool Need Detector
# =====================================

"""Determine whether a user request requires tool execution (Phase 10B — P10B-003)."""

from __future__ import annotations

import re

from tools.decision.intent import Intent
from tools.decision.models import IntentClassification, ToolNeedAssessment

_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini|pdf|docx?)",
    re.IGNORECASE,
)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

_EXPLICIT_TOOL_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.WEB_SEARCH,
        Intent.FILE,
        Intent.FILE_LIST,
        Intent.FILE_SEARCH,
        Intent.FILE_READ,
        Intent.FILE_METADATA,
        Intent.WORKSPACE_EXPLAIN,
        Intent.SYSTEM,
        Intent.CALENDAR,
        Intent.GITHUB,
        Intent.OBSIDIAN,
        Intent.BROWSER,
    },
)

_NO_TOOL_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.GENERAL_CHAT,
        Intent.MEMORY,
        Intent.WORKSPACE_MODIFY,
    },
)


class ToolNeedDetector:
    """Decide if external tool invocation is warranted for a message."""

    def assess(
        self,
        message: str,
        classification: IntentClassification,
    ) -> ToolNeedAssessment:
        """Return whether a tool is required and why."""
        lowered = message.lower().strip()
        intent = classification.intent

        if intent in _NO_TOOL_INTENTS:
            return ToolNeedAssessment(
                tool_required=False,
                reason=f"Intent {intent.value} is handled without external tools",
            )

        if intent == Intent.UNKNOWN and classification.confidence < 0.5:
            return ToolNeedAssessment(
                tool_required=False,
                reason="Unknown intent with low confidence — direct answer preferred",
            )

        if intent in _EXPLICIT_TOOL_INTENTS:
            return ToolNeedAssessment(
                tool_required=True,
                reason=f"Intent {intent.value} requires an external capability",
            )

        if intent == Intent.CODING:
            if _has_executable_code(message, lowered):
                return ToolNeedAssessment(
                    tool_required=True,
                    reason="Coding intent with executable code block or python directive",
                )
            return ToolNeedAssessment(
                tool_required=False,
                reason="Coding discussion without explicit execution request",
            )

        if intent == Intent.TRADING:
            return ToolNeedAssessment(
                tool_required=True,
                reason="Trading intent implies market data or execution capability",
            )

        if intent == Intent.EMAIL:
            return ToolNeedAssessment(
                tool_required=True,
                reason="Email intent implies outbound mail capability",
            )

        if intent == Intent.DOCUMENT:
            if _PATH_PATTERN.search(message):
                return ToolNeedAssessment(
                    tool_required=True,
                    reason="Document intent with identifiable file path",
                )
            return ToolNeedAssessment(
                tool_required=False,
                reason="Document intent without actionable file target",
            )

        return ToolNeedAssessment(
            tool_required=False,
            reason="No tool invocation signals detected",
        )


def _has_executable_code(message: str, lowered: str) -> bool:
    if _CODE_BLOCK_PATTERN.search(message):
        return True
    exec_keywords = (
        "exécute python",
        "execute python",
        "run python",
        "python:",
        "exec python",
        "lance ce code",
    )
    return any(keyword in lowered for keyword in exec_keywords)
