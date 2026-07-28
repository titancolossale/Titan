# =====================================
# Titan Goal Matcher
# =====================================

"""Automatic goal matching for Phase 16.3 switching.

Scores a user request against known goals using name, aliases, keywords,
description (semantic overlap), contained project names, and recent summaries.
Never creates goals — callers only switch among existing ones via
``GoalManager.resume_goal``.

Performance: a single scan of the goal list; no duplicated matching passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.goal_models import Goal

# Switch only when confidence clears this bar (aligned with project matching).
HIGH_CONFIDENCE = 0.85

# Require a clear winner unless the top hit is an exact name/alias match.
_MIN_MARGIN = 0.12

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]{2,}", re.IGNORECASE)
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "onto", "into",
    "sur", "avec", "pour", "dans", "une", "des", "les", "mon", "mes",
    "projet", "project", "mission", "goal", "objectif", "work", "travail",
    "continue", "continuer", "reprendre", "resume", "on", "le", "la",
    "du", "de",
})


@dataclass(frozen=True)
class GoalMatchResult:
    """Outcome of matching a user message against known goals."""

    matched: bool
    confidence: float
    goal_id: str | None
    goal_name: str | None
    reason: str
    should_switch: bool
    signals: tuple[str, ...] = ()


def match_goal(
    message: str,
    goals: Sequence[Goal],
    *,
    projects_by_goal: Mapping[str, Sequence[Any]] | None = None,
    summaries_by_goal: Mapping[str, str] | None = None,
    active_goal_id: str | None = None,
    high_confidence: float = HIGH_CONFIDENCE,
) -> GoalMatchResult:
    """Score *message* against *goals* and decide whether to switch.

    Never invents a goal. Returns ``matched=False`` when confidence is low
    or when no eligible candidate exists. Performs a single scoring pass.
    """
    text = (message or "").strip()
    if not text:
        return GoalMatchResult(
            matched=False,
            confidence=0.0,
            goal_id=None,
            goal_name=None,
            reason="empty_message",
            should_switch=False,
        )

    candidates = [
        item
        for item in goals
        if item.status not in {"ARCHIVED", "COMPLETED"}
    ]
    if not candidates:
        return GoalMatchResult(
            matched=False,
            confidence=0.0,
            goal_id=None,
            goal_name=None,
            reason="no_goals",
            should_switch=False,
        )

    lowered = text.casefold()
    message_tokens = _tokens(lowered)
    projects_map = projects_by_goal or {}
    summaries_map = summaries_by_goal or {}

    scored: list[tuple[float, Goal, tuple[str, ...]]] = []
    for goal in candidates:
        score, signals = _score_goal(
            lowered,
            message_tokens,
            goal,
            projects=projects_map.get(goal.id, ()),
            summary=summaries_map.get(goal.id),
        )
        if score > 0.0:
            scored.append((score, goal, signals))

    if not scored:
        return GoalMatchResult(
            matched=False,
            confidence=0.0,
            goal_id=None,
            goal_name=None,
            reason="no_signal",
            should_switch=False,
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_goal, best_signals = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    exact = "exact_name" in best_signals or "exact_alias" in best_signals
    margin_ok = exact or (best_score - second_score) >= _MIN_MARGIN

    if best_score < high_confidence or not margin_ok:
        return GoalMatchResult(
            matched=False,
            confidence=round(best_score, 3),
            goal_id=best_goal.id,
            goal_name=best_goal.name,
            reason="low_confidence" if best_score < high_confidence else "ambiguous",
            should_switch=False,
            signals=best_signals,
        )

    already_active = active_goal_id is not None and best_goal.id == active_goal_id
    return GoalMatchResult(
        matched=True,
        confidence=round(min(best_score, 1.0), 3),
        goal_id=best_goal.id,
        goal_name=best_goal.name,
        reason="already_active" if already_active else "switch",
        should_switch=not already_active,
        signals=best_signals,
    )


def _score_goal(
    lowered: str,
    message_tokens: set[str],
    goal: Goal,
    *,
    projects: Sequence[Any],
    summary: str | None,
) -> tuple[float, tuple[str, ...]]:
    signals: list[str] = []
    score = 0.0

    name = (goal.name or "").strip()
    name_cf = name.casefold()
    if name_cf and (name_cf == lowered or _contains_phrase(lowered, name_cf)):
        score = max(score, 1.0)
        signals.append("exact_name")

    for alias in goal.aliases:
        alias_cf = str(alias).strip().casefold()
        if alias_cf and (alias_cf == lowered or _contains_phrase(lowered, alias_cf)):
            score = max(score, 0.97)
            signals.append("exact_alias")
            break

    name_tokens = _tokens(name_cf)
    if name_tokens:
        coverage = len(name_tokens & message_tokens) / len(name_tokens)
        if coverage >= 0.67:
            score = max(score, 0.7 + 0.25 * coverage)
            signals.append("name_tokens")

    keyword_hits = 0
    for keyword in goal.keywords:
        kw = str(keyword).strip().casefold()
        if kw and (kw in message_tokens or _contains_phrase(lowered, kw)):
            keyword_hits += 1
    if keyword_hits:
        score = max(score, min(0.7 + 0.1 * keyword_hits, 0.95))
        signals.append("keywords")

    # Semantic similarity via description token overlap (no embedding API).
    desc_tokens = _tokens((goal.description or "").casefold()) - _STOPWORDS
    if desc_tokens and message_tokens:
        overlap = len(desc_tokens & message_tokens) / max(len(desc_tokens), 1)
        if overlap >= 0.4:
            score = max(score, 0.55 + 0.3 * overlap)
            signals.append("semantic")

    project_score = _score_project_names(message_tokens, lowered, projects)
    if project_score > 0.0:
        score = max(score, project_score)
        signals.append("project_names")

    if summary:
        summary_tokens = _tokens(summary.casefold()) - _STOPWORDS
        if summary_tokens and message_tokens:
            meaningful = summary_tokens & message_tokens
            if meaningful:
                coverage = len(meaningful) / len(summary_tokens)
                if coverage >= 0.25 or len(meaningful) >= 2:
                    score = max(score, min(0.6 + 0.15 * len(meaningful), 0.88))
                    signals.append("summary")

    return round(min(score, 1.0), 3), tuple(dict.fromkeys(signals))


def _score_project_names(
    message_tokens: set[str],
    lowered: str,
    projects: Sequence[Any],
) -> float:
    best = 0.0
    for project in list(projects)[:8]:
        name = ""
        if isinstance(project, Mapping):
            name = str(project.get("name") or "")
        else:
            name = str(getattr(project, "name", "") or "")
        name_cf = name.strip().casefold()
        if not name_cf:
            continue
        if _contains_phrase(lowered, name_cf):
            best = max(best, 0.92)
            continue
        name_tokens = _tokens(name_cf) - _STOPWORDS
        if not name_tokens:
            continue
        coverage = len(name_tokens & message_tokens) / len(name_tokens)
        if coverage >= 0.75:
            best = max(best, 0.7 + 0.2 * coverage)
    return best


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(text or "")}


def _contains_phrase(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    if " " in needle or "-" in needle:
        return needle in haystack
    return needle in _tokens(haystack)
