# =====================================
# Titan Reasoning System
# =====================================

"""Intent analysis with tool-request heuristics (Phase 6 — P6-032; Phase 10B — P10B bridge)."""

from __future__ import annotations

import re

from config.settings import TITAN_TOOL_DECISION_ENGINE
from tools.decision.capability_availability import CapabilityAvailabilityResolver
from tools.decision.models import FallbackAction
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.tool_result import ToolRequest

_TIME_KEYWORDS = (
    "heure",
    "quelle heure",
    "what time",
    "current time",
    "datetime",
    "date et heure",
    "quelle date",
)
_READ_KEYWORDS = (
    "lire le fichier",
    "lire fichier",
    "read file",
    "contenu du fichier",
    "affiche le fichier",
    "ouvre le fichier",
    "show file",
    "open file",
)
_WRITE_KEYWORDS = (
    "écris dans",
    "ecrire dans",
    "write file",
    "crée le fichier",
    "cree le fichier",
    "create file",
    "écrire le fichier",
)
_PYTHON_KEYWORDS = (
    "exécute python",
    "execute python",
    "run python",
    "python:",
    "exec python",
    "lance ce code",
)
_WEB_KEYWORDS = (
    "recherche web",
    "web search",
    "cherche sur internet",
    "google ",
)
_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini)",
    re.IGNORECASE,
)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class Reasoning:
    """Analyze user messages and emit structured tool requests when needed."""

    def __init__(
        self,
        *,
        decision_engine: ToolDecisionEngine | None = None,
        use_decision_engine: bool | None = None,
    ) -> None:
        self.decision_engine = decision_engine or ToolDecisionEngine()
        self._use_decision_engine = (
            TITAN_TOOL_DECISION_ENGINE
            if use_decision_engine is None
            else use_decision_engine
        )

    def analyze(
        self,
        message: str,
        *,
        available_tools: frozenset[str] | None = None,
        availability_resolver: CapabilityAvailabilityResolver | None = None,
    ) -> dict:
        """Return analysis dict with tool requests for Brain executor."""
        if self._use_decision_engine:
            return self._analyze_with_decision_engine(
                message,
                available_tools=available_tools,
                availability_resolver=availability_resolver,
            )
        return self._analyze_legacy(message)

    def _analyze_with_decision_engine(
        self,
        message: str,
        *,
        available_tools: frozenset[str] | None = None,
        availability_resolver: CapabilityAvailabilityResolver | None = None,
    ) -> dict:
        report = self.decision_engine.decide(
            message,
            available_tools=available_tools,
            availability_resolver=availability_resolver,
        )
        tool_requests: list[ToolRequest] = []

        if report.fallback_action == FallbackAction.EXECUTE_TOOL and report.selected_tool:
            params = _build_tool_params(message, report.selected_tool)
            tool_requests.append(ToolRequest(report.selected_tool, params))

        return {
            "message": message,
            "goal": "Comprendre la demande de l'utilisateur",
            "needs_memory": report.intent.value == "memory",
            "needs_tool": report.tool_required and bool(tool_requests),
            "needs_clarification": report.fallback_action == FallbackAction.NO_CAPABILITY,
            "tool_requests": tool_requests,
            "decision_report": report,
            "fallback_action": report.fallback_action.value,
            "confirmation_required": report.confirmation_required,
        }

    def _analyze_legacy(self, message: str) -> dict:
        """Phase 6 keyword path preserved for opt-out regression safety."""
        lowered = message.lower()
        tool_requests: list[ToolRequest] = []

        if _matches_any(lowered, _TIME_KEYWORDS):
            tool_requests.append(ToolRequest("time", {}))

        file_path = _extract_path(message)
        if file_path and _matches_any(lowered, _READ_KEYWORDS):
            tool_requests.append(ToolRequest("file_read", {"path": file_path}))

        if file_path and _matches_any(lowered, _WRITE_KEYWORDS):
            content = _extract_write_content(message)
            tool_requests.append(
                ToolRequest(
                    "file_write",
                    {"path": file_path, "content": content},
                ),
            )

        code = _extract_python_code(message)
        if code and _matches_any(lowered, _PYTHON_KEYWORDS):
            tool_requests.append(ToolRequest("python_exec", {"code": code}))

        if _matches_any(lowered, _WEB_KEYWORDS):
            query = message.strip()
            tool_requests.append(ToolRequest("web_search", {"query": query}))

        return {
            "message": message,
            "goal": "Comprendre la demande de l'utilisateur",
            "needs_memory": False,
            "needs_tool": bool(tool_requests),
            "needs_clarification": False,
            "tool_requests": tool_requests,
        }


def _build_tool_params(message: str, tool_name: str) -> dict:
    """Map selected tool name to invocation parameters from the message."""
    if tool_name == "time":
        return {}
    if tool_name == "web_search":
        return {"query": message.strip()}
    if tool_name == "calendar":
        return {"query": message.strip()}
    if tool_name == "file_read":
        path = _extract_path(message)
        return {"path": path or ""}
    if tool_name == "file_write":
        path = _extract_path(message)
        return {"path": path or "", "content": _extract_write_content(message)}
    if tool_name == "python_exec":
        code = _extract_python_code(message)
        return {"code": code or ""}
    return {}


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_path(message: str) -> str | None:
    match = _PATH_PATTERN.search(message)
    return match.group(0) if match else None


def _extract_write_content(message: str) -> str:
    marker = "contenu:"
    lowered = message.lower()
    if marker in lowered:
        idx = lowered.index(marker)
        return message[idx + len(marker) :].strip()
    return ""


def _extract_python_code(message: str) -> str | None:
    block = _CODE_BLOCK_PATTERN.search(message)
    if block:
        return block.group(1).strip()
    if "python:" in message.lower():
        _, _, tail = message.partition(":")
        stripped = tail.strip()
        return stripped or None
    return None
