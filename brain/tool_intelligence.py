# =====================================
# Titan Tool Intelligence
# =====================================

"""Metadata-driven tool selection and execution planning for Titan Brain."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.actions.action import Action
from core.tools.base_tool import BaseTool
from core.tools.capability_models import CapabilityRecord
from core.tools.capability_registry import (
    CapabilityRegistry,
    CapabilityRegistrySummary,
    CapabilitySearchResult,
)
from core.tools.tool_loader import ToolLoader
from core.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

CORE_TOOLS_DIR = Path(__file__).resolve().parents[1] / "core" / "tools"

_CONVERSATION_PATTERNS = (
    r"^(hi|hello|hey|bonjour|salut|coucou|yo|thanks|thank you|merci)\b",
    r"^(how are you|comment (?:vas|ça va))",
)
_COMPARE_PATTERNS = (
    r"\bcompare\b",
    r"\bcomparer\b",
    r"\bversus\b",
    r"\bvs\.?\b",
    r"\bwith\b.+\band\b",
    r"\bavec\b.+\bet\b",
)
_READ_VERBS = frozenset({
    "read", "lire", "open", "ouvrir", "show", "afficher", "get", "fetch",
    "retrieve", "consulter", "view", "voir",
})
_LIST_VERBS = frozenset({"list", "lister", "lister", "enumerate"})
_WRITE_VERBS = frozenset({
    "write", "create", "edit", "update", "append", "delete", "remove",
    "écrire", "créer", "modifier", "ajouter", "supprimer",
})
_WEB_HINTS = frozenset({
    "http", "https", "url", "website", "web", "page", "documentation", "docs",
    "doc", "api", "fastapi", "site", "internet", "online", "www",
})
_NOTE_HINTS = frozenset({
    "note", "notes", "vault", "obsidian", "markdown", "journal", "folder",
})
_PYTHON_HINTS = frozenset({
    "python", "py", "snippet", "script", "code", "execute", "run", "syntax",
    "format", "interpreter", "runtime", "exécute", "exécuter",
})
_GITHUB_HINTS = frozenset({
    "github", "repo", "repos", "repository", "repositories", "commit", "commits",
    "branch", "branches", "pull", "pr", "clone", "readme", "sha", "vcs", "git",
    "implemented", "implementation", "symbol",
})
_TERMINAL_HINTS = frozenset({
    "terminal", "shell", "command", "cmd", "cli", "console",
    "pytest", "unittest",
    "npm", "npx", "uv",
})
_STOPWORDS = frozenset({
    "a", "an", "the", "my", "me", "i", "to", "for", "of", "in", "on", "at",
    "is", "it", "and", "or", "with", "from", "this", "that", "please",
    "le", "la", "les", "un", "une", "de", "du", "des", "mon", "ma", "mes",
    "et", "ou", "avec", "pour", "dans", "sur", "ce", "cette",
})
_CATEGORY_ORDER = {
    "notes": 0,
    "web": 1,
    "shell": 2,
    "vcs": 3,
    "runtime": 4,
    "demo": 5,
}
_LOCAL_GIT_PATTERN = re.compile(
    r"\bgit\s+(?:status|diff|log|branch|add|commit|push|pull|checkout|stash|show)\b",
    re.IGNORECASE,
)
_PYTEST_PATTERN = re.compile(r"\bpytest\b|\brun\s+tests?\b|\bunit\s+tests?\b", re.IGNORECASE)
_NPM_PATTERN = re.compile(r"\bnpm\b|\bnpx\b", re.IGNORECASE)
_UV_PATTERN = re.compile(r"\buv\s+(?:sync|run|pip|add|remove|lock)\b|\buv\s+sync\b", re.IGNORECASE)
_QUOTED_COMMAND_PATTERN = re.compile(r"""["']([^"']+)["']""")
_REPO_PATTERN = re.compile(
    r"\b(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)\b"
)
_README_PATTERN = re.compile(r"\breadme(?:\.md)?\b", re.IGNORECASE)
_CODE_LOCATION_PATTERN = re.compile(
    r"\b(?:find|where|locate)\b.+\b(?:implemented|implementation|defined|definition)\b"
    r"|\b(?:implemented|implementation)\b",
    re.IGNORECASE,
)
_MIN_TOOL_SCORE = 0.12
_SELECTION_RATIO = 0.55
_AMBIGUITY_GAP = 0.08
_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


class ToolIntent(str, Enum):
    """High-level intent classification for tool routing."""

    CONVERSATION = "conversation"
    READ = "read"
    SEARCH = "search"
    COMPARE = "compare"
    WRITE = "write"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlannedAction:
    """A single action step within a tool execution plan."""

    tool_id: str
    action_id: str
    reason: str
    confidence: float
    parameters: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "action_id": self.action_id,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class SelectedTool:
    """A tool selected for execution with ranked actions."""

    tool_id: str
    tool_name: str
    category: str
    confidence: float
    reason: str
    actions: tuple[PlannedAction, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True)
class ToolExecutionPlan:
    """Structured execution plan produced by ToolIntelligence — no side effects."""

    request: str
    intent: ToolIntent
    intent_summary: str
    selected_tools: tuple[SelectedTool, ...]
    execution_order: tuple[str, ...]
    confidence: float
    requires_tools: bool
    reasoning_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "intent": self.intent.value,
            "intent_summary": self.intent_summary,
            "selected_tools": [tool.to_dict() for tool in self.selected_tools],
            "execution_order": list(self.execution_order),
            "confidence": round(self.confidence, 3),
            "requires_tools": self.requires_tools,
            "reasoning_summary": self.reasoning_summary,
        }


@dataclass(frozen=True)
class _ToolProfile:
    """Runtime index built from registry metadata — never hardcodes tool ids."""

    tool: BaseTool
    tokens: frozenset[str]
    category_tokens: frozenset[str]
    capability_tokens: frozenset[str]
    action_profiles: tuple[tuple[Action, frozenset[str]], ...]


class ToolIntelligence:
    """Select relevant tools and actions from natural language using registry metadata."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self._registry = tool_registry
        self._capability_registry = (
            capability_registry
            or tool_registry.capability_registry
            or CapabilityRegistry(strict_validation=False)
        )
        if tool_registry.capability_registry is None:
            tool_registry.attach_capability_registry(self._capability_registry)
        self._profiles = self._build_profiles()

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def capability_registry(self) -> CapabilityRegistry:
        return self._capability_registry

    def list_capabilities(self) -> list[CapabilityRecord]:
        """Return all installed tool capability records."""
        return self._capability_registry.list_tools()

    def search_capabilities(
        self,
        query: str,
        *,
        exact: bool = False,
    ) -> list[CapabilitySearchResult]:
        """Search installed tools by metadata, tags, capabilities, and actions."""
        return self._capability_registry.search(query, exact=exact)

    def find_tools_for_task(self, task: str) -> list[CapabilitySearchResult]:
        """Rank tools likely useful for a natural-language task description."""
        if not task.strip():
            return []
        search_hits = self._capability_registry.search(task)
        if search_hits:
            return search_hits

        plan = self.plan(task)
        if not plan.selected_tools:
            return []

        results: list[CapabilitySearchResult] = []
        for selected in plan.selected_tools:
            record = self._capability_registry.get_tool(selected.tool_id)
            if record is None:
                continue
            results.append(
                CapabilitySearchResult(
                    record=record,
                    score=selected.confidence,
                    matched_fields=("task_plan",),
                )
            )
        return results

    def describe_tool(self, name: str) -> CapabilityRecord | None:
        """Return full metadata for a tool by id or display name."""
        normalized = name.strip().lower()
        direct = self._capability_registry.get_tool(name)
        if direct is not None:
            return direct
        for record in self._capability_registry.list_tools():
            if record.display_name.lower() == normalized:
                return record
        matches = self._capability_registry.search(name, exact=True)
        return matches[0].record if matches else None

    def summarize_installed_tools(self) -> CapabilityRegistrySummary:
        """Return an aggregate summary of installed tools."""
        return self._capability_registry.summarize()

    def plan(self, request: str) -> ToolExecutionPlan:
        """Analyze *request* and return a metadata-driven execution plan."""
        message = request.strip()
        tokens = _tokenize(message)
        tool_scores = self._score_tools(tokens, message)
        intent = self._classify_intent(message, tokens, tool_scores)
        selected = self._select_tools(message, tokens, intent, tool_scores)
        execution_order = self._execution_order(selected, intent)
        confidence = self._plan_confidence(selected, tool_scores, intent)
        requires_tools = bool(selected)
        intent_summary = self._intent_summary(intent, selected)
        reasoning_summary = self._reasoning_summary(intent, selected, tool_scores)

        plan = ToolExecutionPlan(
            request=message,
            intent=intent,
            intent_summary=intent_summary,
            selected_tools=tuple(selected),
            execution_order=execution_order,
            confidence=confidence,
            requires_tools=requires_tools,
            reasoning_summary=reasoning_summary,
        )
        self._log_plan(plan, tool_scores)
        return plan

    def refresh(self) -> None:
        """Rebuild metadata profiles after registry changes."""
        for tool in self._registry.list_tools():
            if self._capability_registry.get_tool(tool.id) is not None:
                self._capability_registry.refresh_tool(tool)
        self._profiles = self._build_profiles()

    def _build_profiles(self) -> tuple[_ToolProfile, ...]:
        profiles: list[_ToolProfile] = []
        for tool in self._registry.list_enabled_tools():
            action_profiles: list[tuple[Action, frozenset[str]]] = []
            for action in tool.list_actions():
                action_profiles.append((action, _action_tokens(action)))
            corpus = _tool_tokens(tool)
            profiles.append(
                _ToolProfile(
                    tool=tool,
                    tokens=corpus,
                    category_tokens=_tokenize(tool.category),
                    capability_tokens=_merge_tokens(tool.capabilities),
                    action_profiles=tuple(action_profiles),
                )
            )
        return tuple(profiles)

    def _score_tools(
        self,
        tokens: frozenset[str],
        message: str,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        message_lower = message.lower()
        has_web_signal = bool(tokens & _WEB_HINTS) or bool(_URL_PATTERN.search(message))
        has_note_signal = bool(tokens & _NOTE_HINTS) or bool(
            re.search(r"\b(?:my|mes|mon|ma)\s+\w+", message_lower)
        )
        has_python_signal = bool(tokens & _PYTHON_HINTS) or "python" in message_lower
        has_remote_github_signal = (
            "github" in message_lower
            or "github.com" in message_lower
            or bool(_REPO_PATTERN.search(message))
            or bool(_CODE_LOCATION_PATTERN.search(message))
        )
        has_github_signal = (
            has_remote_github_signal
            or (
                bool(tokens & _GITHUB_HINTS)
                and not bool(_LOCAL_GIT_PATTERN.search(message))
                and "pytest" not in message_lower
            )
        )
        has_terminal_signal = (
            bool(tokens & _TERMINAL_HINTS)
            or bool(_LOCAL_GIT_PATTERN.search(message))
            or bool(_PYTEST_PATTERN.search(message))
            or bool(_NPM_PATTERN.search(message))
            or bool(_UV_PATTERN.search(message))
            or "terminal" in message_lower
            or "shell" in message_lower
        )
        # Prefer Terminal for local git / pytest / npm / uv over GitHub API or Python sandbox.
        local_dev_signal = (
            bool(_LOCAL_GIT_PATTERN.search(message))
            or bool(_PYTEST_PATTERN.search(message))
            or bool(_NPM_PATTERN.search(message))
            or bool(_UV_PATTERN.search(message))
            or any(token in tokens for token in ("pytest", "npm", "uv", "npx"))
        )
        for profile in self._profiles:
            score = 0.0
            overlap = len(tokens & profile.tokens)
            score += overlap * 0.18
            score += len(tokens & profile.category_tokens) * 0.25
            score += len(tokens & profile.capability_tokens) * 0.15

            if tokens & _NOTE_HINTS and profile.tool.category == "notes":
                score += 0.35
            if tokens & _WEB_HINTS and profile.tool.category == "web":
                score += 0.35
            if tokens & _PYTHON_HINTS and profile.tool.category == "runtime":
                score += 0.35
            if tokens & _GITHUB_HINTS and profile.tool.category == "vcs":
                score += 0.35
            if tokens & _TERMINAL_HINTS and profile.tool.category == "shell":
                score += 0.35
            if _URL_PATTERN.search(message) and profile.tool.category == "web":
                score += 0.5

            if has_github_signal and not has_note_signal and not local_dev_signal:
                if profile.tool.category == "vcs":
                    score += 0.3
                elif profile.tool.category in {"notes", "web", "demo", "shell"}:
                    score *= 0.4
            if has_web_signal and not has_note_signal and not has_python_signal and not has_github_signal and not has_terminal_signal:
                if profile.tool.category == "web":
                    score += 0.2
                elif profile.tool.category == "notes":
                    score *= 0.45
            if has_note_signal and not has_web_signal and not has_python_signal and not has_github_signal and not has_terminal_signal:
                if profile.tool.category == "notes":
                    score += 0.2
                elif profile.tool.category == "web":
                    score *= 0.45
            if has_python_signal and not has_github_signal and not local_dev_signal:
                if profile.tool.category == "runtime":
                    score += 0.25
                elif profile.tool.category in {"notes", "web", "demo", "vcs", "shell"}:
                    score *= 0.4
            if local_dev_signal:
                if profile.tool.category == "shell":
                    score += 0.45
                elif profile.tool.category in {"vcs", "runtime", "demo"}:
                    score *= 0.35
            elif has_terminal_signal and not has_note_signal and not has_web_signal:
                if profile.tool.category == "shell":
                    score += 0.35
                elif profile.tool.category in {"notes", "web", "demo"}:
                    score *= 0.45
            if profile.tool.category == "demo":
                score *= 0.35

            for action, action_tokens in profile.action_profiles:
                action_overlap = len(tokens & action_tokens)
                if action_overlap:
                    score += action_overlap * 0.08
                capability = str(action.metadata.get("capability", ""))
                if capability and any(part in message_lower for part in capability.split("_")):
                    score += 0.1

            if any(verb in tokens for verb in _READ_VERBS):
                if any("read" in cap or "fetch" in cap or "extract" in cap
                       for cap in profile.tool.capabilities):
                    score += 0.12
            if any(verb in tokens for verb in _LIST_VERBS):
                if any("list" in cap for cap in profile.tool.capabilities):
                    score += 0.12

            # Apply after action scoring so metadata overlap cannot re-boost Terminal
            # into compare/read slots meant for notes/web tools.
            if (
                profile.tool.category == "shell"
                and not local_dev_signal
                and (has_note_signal or has_web_signal)
            ):
                score *= 0.15

            scores[profile.tool.id] = min(score, 1.0)
        return scores

    def _classify_intent(
        self,
        message: str,
        tokens: frozenset[str],
        tool_scores: dict[str, float],
    ) -> ToolIntent:
        lowered = message.lower()
        if _is_conversation(message, tool_scores):
            return ToolIntent.CONVERSATION
        if any(re.search(pattern, lowered) for pattern in _COMPARE_PATTERNS):
            ranked = sorted(tool_scores.values(), reverse=True)
            if len(ranked) >= 2 and ranked[1] >= _MIN_TOOL_SCORE:
                return ToolIntent.COMPARE
        if any(verb in tokens for verb in _WRITE_VERBS):
            return ToolIntent.WRITE
        if any(verb in tokens for verb in _LIST_VERBS):
            return ToolIntent.SEARCH
        if any(verb in tokens for verb in _READ_VERBS):
            return ToolIntent.READ
        if max(tool_scores.values(), default=0.0) >= _MIN_TOOL_SCORE:
            return ToolIntent.READ
        if (
            tokens & _WEB_HINTS
            or tokens & _NOTE_HINTS
            or tokens & _PYTHON_HINTS
            or tokens & _GITHUB_HINTS
            or tokens & _TERMINAL_HINTS
        ):
            return ToolIntent.READ
        return ToolIntent.UNKNOWN

    def _select_tools(
        self,
        message: str,
        tokens: frozenset[str],
        intent: ToolIntent,
        tool_scores: dict[str, float],
    ) -> list[SelectedTool]:
        if intent == ToolIntent.CONVERSATION:
            return []

        ranked_ids = sorted(tool_scores, key=lambda tid: tool_scores[tid], reverse=True)
        if not ranked_ids or tool_scores[ranked_ids[0]] < _MIN_TOOL_SCORE:
            return []

        top_score = tool_scores[ranked_ids[0]]
        chosen_ids: list[str] = [ranked_ids[0]]

        if intent == ToolIntent.COMPARE:
            categories_seen = {self._registry.get_tool(ranked_ids[0]).category}
            for tool_id in ranked_ids[1:]:
                tool = self._registry.get_tool(tool_id)
                if tool is None:
                    continue
                if tool_scores[tool_id] < _MIN_TOOL_SCORE:
                    continue
                if tool.category in categories_seen:
                    continue
                chosen_ids.append(tool_id)
                categories_seen.add(tool.category)
                if len(chosen_ids) >= 2:
                    break
        elif intent == ToolIntent.UNKNOWN:
            for tool_id in ranked_ids[1:]:
                score = tool_scores[tool_id]
                gap = top_score - score
                if score >= _MIN_TOOL_SCORE and gap <= _AMBIGUITY_GAP:
                    chosen_ids.append(tool_id)
                if len(chosen_ids) >= 2:
                    break

        selected: list[SelectedTool] = []
        for tool_id in chosen_ids:
            tool = self._registry.get_tool(tool_id)
            if tool is None:
                continue
            profile = self._profile_for(tool_id)
            if profile is None:
                continue
            actions = self._select_actions(profile, message, tokens, intent)
            reason = self._tool_reason(tool, tool_scores[tool_id], intent)
            selected.append(
                SelectedTool(
                    tool_id=tool.id,
                    tool_name=tool.name,
                    category=tool.category,
                    confidence=round(tool_scores[tool_id], 3),
                    reason=reason,
                    actions=tuple(actions),
                )
            )
        return selected

    def _select_actions(
        self,
        profile: _ToolProfile,
        message: str,
        tokens: frozenset[str],
        intent: ToolIntent,
    ) -> list[PlannedAction]:
        if not profile.action_profiles:
            return []

        scored: list[tuple[float, Action, str]] = []
        for action, action_tokens in profile.action_profiles:
            score = len(tokens & action_tokens) * 0.2
            action_id_lower = action.id.lower()
            capability = str(action.metadata.get("capability", "")).lower()

            if intent in {ToolIntent.READ, ToolIntent.COMPARE, ToolIntent.UNKNOWN}:
                if "read" in action_id_lower or "read" in capability:
                    score += 0.45
                elif "extract" in action_id_lower or "fetch" in action_id_lower:
                    score += 0.35
                elif "open" in action_id_lower:
                    score += 0.25
            if intent == ToolIntent.SEARCH and "list" in action_id_lower:
                score += 0.45
            if intent == ToolIntent.WRITE:
                if any(k in action_id_lower for k in ("create", "edit", "append", "replace", "delete")):
                    score += 0.4

            if "url" in action.parameters and (_URL_PATTERN.search(message) or tokens & _WEB_HINTS):
                score += 0.3
            if profile.tool.category == "notes" and any(k in action_id_lower for k in ("read", "list")):
                score += 0.15
            if profile.tool.category == "vcs":
                if "commit" in tokens and "commit" in action_id_lower:
                    score += 0.45
                if "readme" in tokens and action_id_lower == "read_file":
                    score += 0.5
                if any(k in tokens for k in ("search", "find", "where", "implement", "implemented")) and (
                    "search" in action_id_lower
                ):
                    score += 0.45
                if "branch" in tokens and "branch" in action_id_lower:
                    score += 0.4
                if any(k in tokens for k in ("repo", "repos", "repository", "repositories")) and (
                    "list_repositories" in action_id_lower or "repository_metadata" in action_id_lower
                ):
                    score += 0.35
            if profile.tool.category == "shell":
                if (
                    "pytest" in tokens or "test" in tokens or "tests" in tokens
                    or bool(_PYTEST_PATTERN.search(message))
                ) and "pytest" in action_id_lower:
                    score += 0.55
                if ("git" in tokens or bool(_LOCAL_GIT_PATTERN.search(message))) and (
                    "git" in action_id_lower
                ):
                    score += 0.55
                if ("npm" in tokens or "npx" in tokens or bool(_NPM_PATTERN.search(message))) and (
                    "npm" in action_id_lower
                ):
                    score += 0.55
                if ("uv" in tokens or bool(_UV_PATTERN.search(message))) and "uv" in action_id_lower:
                    score += 0.55
                if "python" in tokens and "python" in action_id_lower:
                    score += 0.35
                if any(k in tokens for k in ("command", "shell", "terminal", "cmd")) and (
                    action_id_lower == "run_command"
                ):
                    score += 0.4

            reason = f"Action '{action.name}' matches request intent ({intent.value})."
            scored.append((score, action, reason))

        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] <= 0.0:
            fallback_action = profile.action_profiles[0][0]
            return [
                PlannedAction(
                    tool_id=profile.tool.id,
                    action_id=fallback_action.id,
                    reason=(
                        f"Default action '{fallback_action.name}' selected from "
                        f"{profile.tool.name} metadata."
                    ),
                    confidence=0.35,
                    parameters=self._infer_parameters(fallback_action, message, tokens),
                )
            ]

        best_score, best_action, best_reason = scored[0]
        confidence = min(0.95, max(0.35, best_score))
        return [
            PlannedAction(
                tool_id=profile.tool.id,
                action_id=best_action.id,
                reason=best_reason,
                confidence=confidence,
                parameters=self._infer_parameters(best_action, message, tokens),
            )
        ]

    def _infer_parameters(
        self,
        action: Action,
        message: str,
        tokens: frozenset[str],
    ) -> dict[str, object]:
        params: dict[str, object] = {}
        schema = action.parameters or {}

        url_match = _URL_PATTERN.search(message)
        if url_match and "url" in schema:
            params["url"] = url_match.group(0)

        repo_match = _REPO_PATTERN.search(message)
        if repo_match:
            if "owner" in schema:
                params["owner"] = repo_match.group("owner")
            if "repo" in schema:
                params["repo"] = repo_match.group("repo")
            if "repository" in schema and "owner" not in params:
                params["repository"] = (
                    f"{repo_match.group('owner')}/{repo_match.group('repo')}"
                )

        if "path" in schema or "relative_path" in schema:
            if _README_PATTERN.search(message) and "path" in schema:
                params["path"] = "README.md"
            else:
                path_hint = _extract_note_path_hint(message, tokens)
                if path_hint:
                    key = "path" if "path" in schema else "relative_path"
                    params[key] = path_hint

        if "query" in schema and "query" not in params:
            query = _extract_query_hint(message)
            if query:
                # Strip owner/repo shorthand so search focuses on the symbol.
                if repo_match:
                    query = query.replace(repo_match.group(0), " ").strip()
                if query:
                    params["query"] = query

        # Terminal action parameter inference.
        if action.tool_id == "terminal":
            params.update(_infer_terminal_parameters(action, message))

        return params

    def _execution_order(
        self,
        selected: list[SelectedTool],
        intent: ToolIntent,
    ) -> tuple[str, ...]:
        if not selected:
            return ()
        if intent == ToolIntent.COMPARE and len(selected) > 1:
            ordered = sorted(
                selected,
                key=lambda item: (
                    _CATEGORY_ORDER.get(item.category, 99),
                    -item.confidence,
                ),
            )
            return tuple(item.tool_id for item in ordered)
        ordered = sorted(selected, key=lambda item: (-item.confidence, item.tool_id))
        return tuple(item.tool_id for item in ordered)

    def _plan_confidence(
        self,
        selected: list[SelectedTool],
        tool_scores: dict[str, float],
        intent: ToolIntent,
    ) -> float:
        if intent == ToolIntent.CONVERSATION:
            return 0.92
        if not selected:
            return 0.25 if intent == ToolIntent.UNKNOWN else 0.35

        confidences = [item.confidence for item in selected]
        base = sum(confidences) / len(confidences)

        ranked = sorted(tool_scores.values(), reverse=True)
        if len(ranked) >= 2 and ranked[0] - ranked[1] < _AMBIGUITY_GAP:
            base *= 0.75

        if intent == ToolIntent.COMPARE and len(selected) >= 2:
            base = min(0.9, base + 0.05)

        return round(min(0.98, max(0.2, base)), 3)

    def _profile_for(self, tool_id: str) -> _ToolProfile | None:
        for profile in self._profiles:
            if profile.tool.id == tool_id:
                return profile
        return None

    @staticmethod
    def _tool_reason(tool: BaseTool, score: float, intent: ToolIntent) -> str:
        caps = ", ".join(tool.capabilities[:4]) or "general capabilities"
        return (
            f"{tool.name} selected ({tool.category}) for {intent.value} intent "
            f"— metadata match score {score:.2f}; capabilities: {caps}."
        )

    @staticmethod
    def _intent_summary(intent: ToolIntent, selected: list[SelectedTool]) -> str:
        if intent == ToolIntent.CONVERSATION:
            return "Conversation-only request; no tool execution required."
        if not selected:
            return f"Intent classified as {intent.value}; no confident tool match."
        names = ", ".join(item.tool_name for item in selected)
        return f"Intent {intent.value}; selected tool(s): {names}."

    @staticmethod
    def _reasoning_summary(
        intent: ToolIntent,
        selected: list[SelectedTool],
        tool_scores: dict[str, float],
    ) -> str:
        if not selected:
            return "No tools met the metadata confidence threshold."
        parts = [
            f"intent={intent.value}",
            f"tools={[item.tool_id for item in selected]}",
        ]
        if tool_scores:
            top = max(tool_scores, key=lambda k: tool_scores[k])
            parts.append(f"top_score={tool_scores[top]:.2f}")
        return "; ".join(parts)

    def _log_plan(self, plan: ToolExecutionPlan, tool_scores: dict[str, float]) -> None:
        logger.info(
            "ToolIntelligence intent=%s confidence=%.3f requires_tools=%s tools=%s order=%s",
            plan.intent.value,
            plan.confidence,
            plan.requires_tools,
            [tool.tool_id for tool in plan.selected_tools],
            list(plan.execution_order),
        )
        logger.info("ToolIntelligence intent_summary: %s", plan.intent_summary)
        logger.debug("ToolIntelligence scores: %s", tool_scores)
        logger.debug("ToolIntelligence plan: %s", plan.to_dict())


def build_default_tool_intelligence(
    *,
    registry: ToolRegistry | None = None,
    capability_registry: CapabilityRegistry | None = None,
    scan_paths: list[Path] | None = None,
) -> ToolIntelligence:
    """Construct ToolIntelligence with tools discovered via ToolLoader."""
    cap_registry = capability_registry or CapabilityRegistry()
    tool_registry = registry or ToolRegistry(capability_registry=cap_registry)
    if registry is not None and tool_registry.capability_registry is None:
        tool_registry.attach_capability_registry(cap_registry)
    paths = scan_paths or [CORE_TOOLS_DIR]
    if not tool_registry.list_tools():
        loader = ToolLoader(tool_registry, scan_paths=paths)
        loader.load()
    return ToolIntelligence(tool_registry, capability_registry=cap_registry)


def _tokenize(text: str) -> frozenset[str]:
    raw = re.findall(r"[a-z0-9_]+", text.lower())
    return frozenset(token for token in raw if token and token not in _STOPWORDS)


def _merge_tokens(values: list[str]) -> frozenset[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokenize(value.replace(".", "_").replace("-", "_")))
    return frozenset(tokens)


def _tool_tokens(tool: BaseTool) -> frozenset[str]:
    parts = [
        tool.id,
        tool.name,
        tool.description,
        tool.category,
        *tool.capabilities,
    ]
    for action in tool.list_actions():
        parts.extend([action.id, action.name, action.description])
        capability = action.metadata.get("capability")
        if capability:
            parts.append(str(capability))
    tokens: set[str] = set()
    for part in parts:
        tokens.update(_tokenize(str(part).replace(".", "_").replace("-", "_")))
    return frozenset(tokens)


def _action_tokens(action: Action) -> frozenset[str]:
    parts = [action.id, action.name, action.description]
    capability = action.metadata.get("capability")
    if capability:
        parts.append(str(capability))
    for param_name, spec in (action.parameters or {}).items():
        parts.append(param_name)
        if isinstance(spec, dict):
            desc = spec.get("description")
            if desc:
                parts.append(str(desc))
    tokens: set[str] = set()
    for part in parts:
        tokens.update(_tokenize(str(part).replace(".", "_").replace("-", "_")))
    return frozenset(tokens)


def _is_conversation(message: str, tool_scores: dict[str, float]) -> bool:
    stripped = message.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if any(re.search(pattern, lowered) for pattern in _CONVERSATION_PATTERNS):
        return max(tool_scores.values(), default=0.0) < _MIN_TOOL_SCORE + 0.05
    if len(_tokenize(stripped)) <= 2 and max(tool_scores.values(), default=0.0) < _MIN_TOOL_SCORE:
        return True
    return False


def _extract_note_path_hint(message: str, tokens: frozenset[str]) -> str | None:
    quoted = re.search(r"['\"]([^'\"]+)['\"]", message)
    if quoted:
        return quoted.group(1).strip()

    lowered = message.lower()
    my_match = re.search(
        r"\b(?:my|mes|mon|ma)\s+([a-z0-9][\w\-./ ]{1,60}?)(?:\s+notes?\b|\s+note\b|$)",
        lowered,
    )
    if my_match:
        return my_match.group(1).strip()

    note_tokens = [token for token in tokens if token not in _NOTE_HINTS and len(token) > 2]
    if note_tokens and tokens & _NOTE_HINTS:
        return note_tokens[0].upper()
    return None


def _extract_query_hint(message: str) -> str | None:
    cleaned = message.strip()
    if len(cleaned) >= 3:
        return cleaned
    return None


def _infer_terminal_parameters(action: Action, message: str) -> dict[str, object]:
    """Infer Terminal action parameters from a natural-language request."""
    params: dict[str, object] = {}
    schema = action.parameters or {}
    action_id = action.id.lower()
    lowered = message.lower().strip()

    quoted = _QUOTED_COMMAND_PATTERN.search(message)
    quoted_text = quoted.group(1).strip() if quoted else ""

    if action_id == "run_command" and "command" in schema:
        if quoted_text:
            params["command"] = quoted_text
        else:
            # Strip leading verbs: "run echo hello" → "echo hello"
            command = re.sub(
                r"^(?:please\s+)?(?:run|execute|executer|exécuter)\s+",
                "",
                lowered,
                flags=re.IGNORECASE,
            ).strip()
            if command:
                params["command"] = command
        return params

    if "args" not in schema:
        return params

    if action_id == "run_git":
        if quoted_text.lower().startswith("git "):
            params["args"] = quoted_text[4:].strip()
        elif quoted_text:
            params["args"] = quoted_text
        else:
            match = re.search(
                r"\bgit\s+(.+)$",
                message.strip(),
                flags=re.IGNORECASE,
            )
            if match:
                params["args"] = match.group(1).strip()
            elif "status" in lowered:
                params["args"] = "status"
            elif "diff" in lowered:
                params["args"] = "diff"
            elif "log" in lowered:
                params["args"] = "log --oneline -20"
        return params

    if action_id == "run_pytest":
        if quoted_text.lower().startswith("pytest "):
            params["args"] = quoted_text[7:].strip()
        elif quoted_text:
            params["args"] = quoted_text
        else:
            match = re.search(r"\bpytest\s+(.+)$", message.strip(), flags=re.IGNORECASE)
            if match:
                params["args"] = match.group(1).strip()
            else:
                params["args"] = "tests/"
        return params

    if action_id == "run_npm":
        if quoted_text.lower().startswith("npm "):
            params["args"] = quoted_text[4:].strip()
        elif quoted_text:
            params["args"] = quoted_text
        else:
            match = re.search(r"\bnpm\s+(.+)$", message.strip(), flags=re.IGNORECASE)
            if match:
                params["args"] = match.group(1).strip()
        return params

    if action_id == "run_uv":
        if quoted_text.lower().startswith("uv "):
            params["args"] = quoted_text[3:].strip()
        elif quoted_text:
            params["args"] = quoted_text
        else:
            match = re.search(r"\buv\s+(.+)$", message.strip(), flags=re.IGNORECASE)
            if match:
                params["args"] = match.group(1).strip()
            elif "sync" in lowered:
                params["args"] = "sync"
        return params

    if action_id == "run_python":
        if quoted_text.lower().startswith("python "):
            params["args"] = quoted_text[7:].strip()
        elif quoted_text:
            params["args"] = quoted_text
        else:
            match = re.search(
                r"\b(?:python3?|py)\s+(.+)$",
                message.strip(),
                flags=re.IGNORECASE,
            )
            if match:
                params["args"] = match.group(1).strip()
        return params

    return params
