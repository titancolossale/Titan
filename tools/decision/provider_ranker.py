# =====================================
# Titan Tool Decision — Provider Ranker
# =====================================

"""Rank provider backends by intent, health, and capability availability (P10B-702)."""

from __future__ import annotations

import re

from config.settings import TITAN_TOOL_DEFAULT_EXECUTION_MODE
from tools.decision.intent import Intent
from tools.decision.models import CandidateProvider, IntentClassification
from tools.health_monitor import HealthMonitor
from tools.providers.provider_configuration import ProviderConfigurationStore
from tools.providers.provider_performance_model import ProviderPerformanceModel
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_enums import ExecutionMode, ToolHealthState

_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini|pdf|docx?)",
    re.IGNORECASE,
)

_BLOCKED_STATES = frozenset({
    ToolHealthState.OFFLINE,
    ToolHealthState.DISABLED,
    ToolHealthState.MISCONFIGURED,
    ToolHealthState.MISSING_CREDENTIALS,
})

_HEALTH_SCORE: dict[ToolHealthState, float] = {
    ToolHealthState.ONLINE: 30.0,
    ToolHealthState.DEGRADED: 12.0,
    ToolHealthState.UNKNOWN: 6.0,
    ToolHealthState.OFFLINE: 0.0,
    ToolHealthState.DISABLED: 0.0,
    ToolHealthState.MISCONFIGURED: 0.0,
    ToolHealthState.MISSING_CREDENTIALS: 0.0,
}

_TOOL_CAPABILITY: dict[str, str] = {
    "file_read": "file_system",
    "file_write": "file_system",
    "web_search": "web_search",
    "github": "github",
}

_TOOL_DEFAULT_PROVIDER: dict[str, str] = {
    "file_read": "file_system",
    "file_write": "file_system",
    "web_search": "brave_search",
    "github": "github",
}

_PROVIDER_INTENT_BASE: dict[str, dict[Intent, float]] = {
    "file_system": {
        Intent.FILE: 92.0,
        Intent.DOCUMENT: 88.0,
        Intent.CODING: 35.0,
    },
    "brave_search": {
        Intent.WEB_SEARCH: 95.0,
        Intent.GENERAL_CHAT: 20.0,
    },
    "web_search": {
        Intent.WEB_SEARCH: 55.0,
    },
    "github": {
        Intent.GITHUB: 96.0,
        Intent.CODING: 40.0,
    },
}

_FIND_KEYWORDS = ("find", "locate", "search for", "trouve", "cherche", "look for")
_READ_KEYWORDS = ("lire", "read", "affiche", "show", "open", "ouvre", "contenu")
_GITHUB_KEYWORDS = (
    "commit",
    "commits",
    "pull request",
    "pull requests",
    "github",
    "repository",
    "repo ",
    "issue",
    "issues",
    "branch",
    "branches",
)
_NEWS_KEYWORDS = ("news", "actualité", "actualites", "latest", "dernières", "dernieres")


def _parse_execution_mode(value: str) -> ExecutionMode:
    try:
        return ExecutionMode(value.lower())
    except ValueError:
        return ExecutionMode.LIVE


class ProviderRanker:
    """Rank provider candidates for a selected tool and user message."""

    def __init__(
        self,
        *,
        performance_model: ProviderPerformanceModel | None = None,
    ) -> None:
        self.performance_model = performance_model

    def rank(
        self,
        message: str,
        classification: IntentClassification,
        *,
        selected_tool: str,
        provider_registry: ProviderRegistry | None = None,
        health_monitor: HealthMonitor | None = None,
        execution_mode: ExecutionMode | None = None,
        configuration_store: ProviderConfigurationStore | None = None,
    ) -> tuple[CandidateProvider, ...]:
        """Return providers sorted by descending composite score."""
        capability = _TOOL_CAPABILITY.get(selected_tool)
        if capability is None:
            return ()

        mode = execution_mode or _parse_execution_mode(TITAN_TOOL_DEFAULT_EXECUTION_MODE)
        provider_ids = self._resolve_provider_ids(
            capability,
            selected_tool,
            provider_registry,
        )

        candidates: list[CandidateProvider] = []
        for provider_id in provider_ids:
            candidate = self._score_provider(
                message,
                classification,
                provider_id=provider_id,
                capability=capability,
                selected_tool=selected_tool,
                provider_registry=provider_registry,
                health_monitor=health_monitor,
                execution_mode=mode,
                configuration_store=configuration_store,
            )
            if candidate is not None:
                candidates.append(candidate)

        return tuple(sorted(candidates, key=lambda item: item.score, reverse=True))

    def _resolve_provider_ids(
        self,
        capability: str,
        selected_tool: str,
        provider_registry: ProviderRegistry | None,
    ) -> tuple[str, ...]:
        if provider_registry is not None:
            ids = provider_registry.list_for_capability(capability)
            if ids:
                return tuple(ids)
        default = _TOOL_DEFAULT_PROVIDER.get(selected_tool)
        if default:
            return (default,)
        return ()

    def _score_provider(
        self,
        message: str,
        classification: IntentClassification,
        *,
        provider_id: str,
        capability: str,
        selected_tool: str,
        provider_registry: ProviderRegistry | None,
        health_monitor: HealthMonitor | None,
        execution_mode: ExecutionMode,
        configuration_store: ProviderConfigurationStore | None,
    ) -> CandidateProvider | None:
        provider = provider_registry.get(provider_id) if provider_registry else None

        if provider is not None and not provider.supports_execution_mode(execution_mode):
            return None

        health_state = self._resolve_health(
            provider_id,
            provider_registry,
            health_monitor,
        )
        if health_state in _BLOCKED_STATES:
            return None

        lowered = message.lower()
        intent = classification.intent
        score = _PROVIDER_INTENT_BASE.get(provider_id, {}).get(intent, 25.0)
        reason_parts = [f"Intent {intent.value} → {provider_id}"]

        score += classification.confidence * 15.0
        score += _HEALTH_SCORE.get(health_state, 0.0)
        reason_parts.append(f"health={health_state.value}")

        if configuration_store is not None:
            config = configuration_store.get(provider_id)
            if config is not None and not config.enabled:
                return None
            if config is not None:
                score += max(0.0, 20.0 - float(config.priority) / 10.0)

        score, signal_reason = self._apply_message_signals(
            lowered,
            message,
            provider_id,
            selected_tool,
            score,
        )
        if signal_reason:
            reason_parts.append(signal_reason)

        if provider is not None:
            actions = provider.supported_actions()
            if actions and selected_tool == "github":
                score += 5.0
            if capability in provider.capabilities():
                score += 8.0

        if self.performance_model is not None:
            perf_delta, perf_reason = self.performance_model.ranking_adjustment(provider_id)
            if perf_delta:
                score += perf_delta
            if perf_reason:
                reason_parts.append(perf_reason)

        final_score = round(max(score, 0.0), 2)
        return CandidateProvider(
            provider_id=provider_id,
            score=final_score,
            reason="; ".join(reason_parts),
            capability=capability,
            health_state=health_state.value,
        )

    def _resolve_health(
        self,
        provider_id: str,
        provider_registry: ProviderRegistry | None,
        health_monitor: HealthMonitor | None,
    ) -> ToolHealthState:
        if health_monitor is not None:
            state = health_monitor.get_provider_health(provider_id)
            if state != ToolHealthState.UNKNOWN:
                return state
        if provider_registry is not None:
            health = provider_registry.probe(provider_id)
            return health.state
        return ToolHealthState.UNKNOWN

    def _apply_message_signals(
        self,
        lowered: str,
        message: str,
        provider_id: str,
        selected_tool: str,
        score: float,
    ) -> tuple[float, str]:
        has_path = _PATH_PATTERN.search(message) is not None

        if provider_id == "file_system" and selected_tool.startswith("file_"):
            if has_path and any(kw in lowered for kw in _FIND_KEYWORDS + _READ_KEYWORDS):
                return score + 18.0, "File path + find/read signal"
            if has_path:
                return score + 12.0, "File path detected"

        if provider_id == "brave_search" and selected_tool == "web_search":
            if any(kw in lowered for kw in _NEWS_KEYWORDS):
                return score + 15.0, "News/search signal favors Brave"
            return score + 8.0, "Web search capability"

        if provider_id == "web_search" and selected_tool == "web_search":
            return score + 2.0, "Stub web search fallback"

        if provider_id == "github" and selected_tool == "github":
            if any(kw in lowered for kw in _GITHUB_KEYWORDS):
                return score + 20.0, "GitHub operation keywords"
            return score + 5.0, "GitHub tool selected"

        return score, ""
