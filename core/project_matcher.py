# =====================================
# Titan Project Matcher
# =====================================

"""Automatic project matching for Phase 15.3 switching.

Scores a user request against known projects using name, aliases, description,
keywords, recent mission titles, and recent summaries. Never creates projects —
callers only switch among existing ones via ``ProjectManager.resume_project``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.project_models import Project

# Switch only when confidence clears this bar (aligned with state evolution).
HIGH_CONFIDENCE = 0.85

# Require a clear winner unless the top hit is an exact name/alias match.
_MIN_MARGIN = 0.12

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]{2,}", re.IGNORECASE)
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "onto", "into",
    "sur", "avec", "pour", "dans", "une", "des", "les", "mon", "mes",
    "projet", "project", "mission", "work", "travail", "continue",
    "continuer", "reprendre", "resume", "on", "le", "la", "du", "de",
})


@dataclass(frozen=True)
class ProjectMatchResult:
    """Outcome of matching a user message against known projects."""

    matched: bool
    confidence: float
    project_id: str | None
    project_name: str | None
    reason: str
    should_switch: bool
    signals: tuple[str, ...] = ()


def match_project(
    message: str,
    projects: Sequence[Project],
    *,
    missions_by_project: Mapping[str, Sequence[Any]] | None = None,
    summaries_by_project: Mapping[str, str] | None = None,
    active_project_id: str | None = None,
    high_confidence: float = HIGH_CONFIDENCE,
) -> ProjectMatchResult:
    """Score *message* against *projects* and decide whether to switch.

    Never invents a project. Returns ``matched=False`` when confidence is low
    or when no eligible candidate exists.
    """
    text = (message or "").strip()
    if not text:
        return ProjectMatchResult(
            matched=False,
            confidence=0.0,
            project_id=None,
            project_name=None,
            reason="empty_message",
            should_switch=False,
        )

    candidates = [
        item
        for item in projects
        if item.status not in {"ARCHIVED", "COMPLETED"}
    ]
    if not candidates:
        return ProjectMatchResult(
            matched=False,
            confidence=0.0,
            project_id=None,
            project_name=None,
            reason="no_projects",
            should_switch=False,
        )

    lowered = text.casefold()
    message_tokens = _tokens(lowered)
    missions_map = missions_by_project or {}
    summaries_map = summaries_by_project or {}

    scored: list[tuple[float, Project, tuple[str, ...]]] = []
    for project in candidates:
        score, signals = _score_project(
            lowered,
            message_tokens,
            project,
            missions=missions_map.get(project.id, ()),
            summary=summaries_map.get(project.id),
        )
        if score > 0.0:
            scored.append((score, project, signals))

    if not scored:
        return ProjectMatchResult(
            matched=False,
            confidence=0.0,
            project_id=None,
            project_name=None,
            reason="no_signal",
            should_switch=False,
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_project, best_signals = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    exact = "exact_name" in best_signals or "exact_alias" in best_signals
    margin_ok = exact or (best_score - second_score) >= _MIN_MARGIN

    if best_score < high_confidence or not margin_ok:
        return ProjectMatchResult(
            matched=False,
            confidence=round(best_score, 3),
            project_id=best_project.id,
            project_name=best_project.name,
            reason="low_confidence" if best_score < high_confidence else "ambiguous",
            should_switch=False,
            signals=best_signals,
        )

    already_active = active_project_id is not None and best_project.id == active_project_id
    return ProjectMatchResult(
        matched=True,
        confidence=round(min(best_score, 1.0), 3),
        project_id=best_project.id,
        project_name=best_project.name,
        reason="already_active" if already_active else "switch",
        should_switch=not already_active,
        signals=best_signals,
    )


def _score_project(
    lowered: str,
    message_tokens: set[str],
    project: Project,
    *,
    missions: Sequence[Any],
    summary: str | None,
) -> tuple[float, tuple[str, ...]]:
    signals: list[str] = []
    score = 0.0

    name = (project.name or "").strip()
    name_cf = name.casefold()
    if name_cf and (name_cf == lowered or _contains_phrase(lowered, name_cf)):
        score = max(score, 1.0)
        signals.append("exact_name")

    for alias in project.aliases:
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
    for keyword in project.keywords:
        kw = str(keyword).strip().casefold()
        if kw and (kw in message_tokens or _contains_phrase(lowered, kw)):
            keyword_hits += 1
    if keyword_hits:
        score = max(score, min(0.7 + 0.1 * keyword_hits, 0.95))
        signals.append("keywords")

    desc_tokens = _tokens((project.description or "").casefold())
    if desc_tokens and message_tokens:
        overlap = len(desc_tokens & message_tokens) / max(len(desc_tokens), 1)
        if overlap >= 0.4:
            score = max(score, 0.55 + 0.3 * overlap)
            signals.append("description")

    mission_score = _score_mission_titles(message_tokens, lowered, missions)
    if mission_score > 0.0:
        score = max(score, mission_score)
        signals.append("mission_titles")

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


def _score_mission_titles(
    message_tokens: set[str],
    lowered: str,
    missions: Sequence[Any],
) -> float:
    best = 0.0
    # Prefer recent missions — list is typically newest-first from managers.
    for mission in list(missions)[:8]:
        title = ""
        if isinstance(mission, Mapping):
            title = str(mission.get("title") or "")
        else:
            title = str(getattr(mission, "title", "") or "")
        title_cf = title.strip().casefold()
        if not title_cf:
            continue
        if _contains_phrase(lowered, title_cf):
            best = max(best, 0.92)
            continue
        title_tokens = _tokens(title_cf) - _STOPWORDS
        if not title_tokens:
            continue
        coverage = len(title_tokens & message_tokens) / len(title_tokens)
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
    # Whole-token match for single-word names/aliases.
    return needle in _tokens(haystack)
