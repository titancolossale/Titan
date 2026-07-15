# =====================================
# Titan Web Memory Activity Formatter
# =====================================

"""Sanitize memory retrieval into user-facing activity records (Phase 17.9)."""

from __future__ import annotations

import re
from typing import Any

from brain.pipeline.context_bundle import ThinkContext
from memory.models import RetrievalResult

# User-facing registry — never expose raw note text, paths, or implementation names.
_MEMORY_SOURCE_PRESENTATION: dict[str, dict[str, Any]] = {
    "conversation": {
        "title": "Conversation précédente",
        "icon": "○",
        "search_line": "Souvenirs de la conversation…",
        "recall_line": "Fil de la conversation…",
        "wave_style": "deep_central",
    },
    "long_term": {
        "title": "Souvenirs permanents",
        "icon": "◈",
        "search_line": "Souvenirs en éveil…",
        "recall_line": "Souvenirs retrouvés…",
        "wave_style": "slow",
    },
    "obsidian": {
        "title": "Notes Obsidian",
        "icon": "◇",
        "search_line": "Consultation des notes…",
        "recall_line": "Notes en mémoire…",
        "wave_style": "geometric",
    },
    "browser": {
        "title": "Recherche navigateur",
        "icon": "◎",
        "search_line": "Parcours récent…",
        "recall_line": "Contexte web…",
        "wave_style": "distributed",
    },
    "calendar": {
        "title": "Agenda",
        "icon": "◷",
        "search_line": "Événements en mémoire…",
        "recall_line": "Rythme du calendrier…",
        "wave_style": "circular",
    },
    "trading": {
        "title": "Marchés",
        "icon": "◆",
        "search_line": "Stratégies en mémoire…",
        "recall_line": "Contexte trading…",
        "wave_style": "sharp",
    },
    "project": {
        "title": "Projet",
        "icon": "◐",
        "search_line": "Contexte du projet…",
        "recall_line": "Projet actif…",
        "wave_style": "default",
    },
}

_CATEGORY_CARD_LABELS: dict[str, str] = {
    "goals": "Objectifs",
    "preferences": "Préférences",
    "projects": "Projets",
    "notes": "Notes personnelles",
    "trading": "Stratégie trading",
    "calendar": "Agenda",
    "browser": "Recherche navigateur",
    "obsidian": "Notes Obsidian",
}

_LABEL_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("objectif projet", "goals"),
    ("apprentissage projet", "notes"),
    ("note projet", "notes"),
    ("projet actif", "projects"),
    ("projet", "projects"),
    ("objectif", "goals"),
    ("préférence", "preferences"),
    ("preference", "preferences"),
    ("note", "notes"),
]


def normalize_memory_source(raw: str) -> str:
    """Map internal source keys to presentation registry keys."""
    if not raw:
        return "long_term"

    key = raw.lower().replace("-", "_")
    if key in _MEMORY_SOURCE_PRESENTATION:
        return key

    if "obsidian" in key or "vault" in key or "note" in key:
        return "obsidian"
    if "browser" in key or "web" in key:
        return "browser"
    if "calendar" in key or "agenda" in key:
        return "calendar"
    if "trad" in key or "market" in key or "orb" in key:
        return "trading"
    if "conversation" in key or "dialogue" in key:
        return "conversation"
    if "project" in key or "projet" in key:
        return "project"
    return "long_term"


def _presentation_for(source: str) -> dict[str, Any]:
    return _MEMORY_SOURCE_PRESENTATION.get(
        normalize_memory_source(source),
        _MEMORY_SOURCE_PRESENTATION["long_term"],
    )


def _format_project_card(project_id: str) -> str:
    """Return a human project label without exposing filesystem paths."""
    name = project_id.strip()
    if not name:
        return "Projet"
    if name.lower() == "titan":
        return "Titan Project"
    if re.search(r"trad|orb|market", name, re.IGNORECASE):
        return f"Stratégie {name}"
    return f"Projet {name}"


def _infer_categories(items: list[str]) -> list[str]:
    """Infer memory categories from formatted item labels — never return raw content."""
    found: list[str] = []
    seen: set[str] = set()

    for item in items:
        item_lower = item.lower()
        for pattern, category in _LABEL_CATEGORY_PATTERNS:
            if pattern in item_lower and category not in seen:
                seen.add(category)
                found.append(category)
                break

        if re.search(r"trad|orb|marché|market", item_lower) and "trading" not in seen:
            seen.add("trading")
            found.append("trading")

    return found


def _build_memory_cards(ctx: ThinkContext, result: RetrievalResult) -> list[str]:
    """Build sanitized floating card labels — thematic only, no note content."""
    cards: list[str] = []
    seen: set[str] = set()

    def add_card(label: str) -> None:
        if label and label not in seen and len(cards) < 4:
            seen.add(label)
            cards.append(label)

    if ctx.active_project:
        add_card(_format_project_card(ctx.active_project))

    if ctx.conversation_loaded:
        add_card("Conversation précédente")

    for title in ctx.obsidian_note_titles:
        add_card(f"Note · {title}")

    for label in ctx.browser_source_labels:
        add_card(f"Source · {label}")

    for category in _infer_categories(result.items):
        add_card(_CATEGORY_CARD_LABELS.get(category, "Souvenirs"))

    if result.has_matches and not cards:
        add_card("Souvenirs pertinents")

    if ctx.obsidian_consulted and not ctx.obsidian_note_titles and not cards:
        add_card("Notes Obsidian")

    if ctx.browser_exploring and not ctx.browser_source_labels and not cards:
        add_card("Exploration web")

    return cards


def _active_sources(ctx: ThinkContext) -> list[str]:
    """Determine which memory sources participated in this think turn."""
    sources: list[str] = []
    if ctx.conversation_loaded:
        sources.append("conversation")
    if ctx.active_project:
        sources.append("project")
    if ctx.obsidian_consulted:
        sources.append("obsidian")
    if ctx.browser_exploring:
        sources.append("browser")
    sources.append("long_term")
    return sources


def format_memory_activity(ctx: ThinkContext | None) -> list[dict[str, Any]]:
    """
    Convert think context retrieval metadata into sanitized activity records.

    Returns user-facing dicts only — no note text, embeddings, or internal paths.
    """
    if ctx is None or ctx.retrieval_result is None:
        return []

    result = ctx.retrieval_result
    cards = _build_memory_cards(ctx, result)
    sources = _active_sources(ctx)
    records: list[dict[str, Any]] = []

    for index, source in enumerate(sources):
        presentation = _presentation_for(source)
        records.append(
            {
                "run_id": f"mem-search-{source}-{index}",
                "source": normalize_memory_source(source),
                "phase": "search",
                "title": presentation["title"],
                "icon": presentation["icon"],
                "status_line": presentation["search_line"],
                "wave_style": presentation["wave_style"],
                "state": "running",
            }
        )

    if ctx.obsidian_consulted:
        obsidian_presentation = _presentation_for("obsidian")
        obsidian_cards = [
            f"Note · {title}" for title in ctx.obsidian_note_titles[:4]
        ] or ["Notes Obsidian"]
        records.append(
            {
                "run_id": "mem-recall-obsidian",
                "source": "obsidian",
                "phase": "recall",
                "title": obsidian_presentation["title"],
                "icon": obsidian_presentation["icon"],
                "status_line": obsidian_presentation["recall_line"],
                "wave_style": obsidian_presentation["wave_style"],
                "cards": obsidian_cards,
                "match_count": len(ctx.obsidian_note_titles),
                "has_matches": bool(ctx.obsidian_note_titles),
                "state": "running",
            }
        )

    if ctx.browser_exploring:
        browser_presentation = _presentation_for("browser")
        browser_cards = [
            f"Source · {label}" for label in ctx.browser_source_labels[:4]
        ] or ["Exploration web"]
        records.append(
            {
                "run_id": "mem-recall-browser",
                "source": "browser",
                "phase": "recall",
                "title": browser_presentation["title"],
                "icon": browser_presentation["icon"],
                "status_line": browser_presentation["recall_line"],
                "wave_style": browser_presentation["wave_style"],
                "cards": browser_cards,
                "match_count": len(ctx.browser_source_labels),
                "has_matches": bool(ctx.browser_source_labels),
                "state": "running",
            }
        )

    recall_presentation = _presentation_for("long_term")
    records.append(
        {
            "run_id": "mem-recall",
            "source": "long_term",
            "phase": "recall",
            "title": recall_presentation["title"],
            "icon": recall_presentation["icon"],
            "status_line": (
                recall_presentation["recall_line"]
                if result.has_matches
                else "Aucun souvenir précis pour l'instant…"
            ),
            "wave_style": recall_presentation["wave_style"] if result.has_matches else "central",
            "cards": cards,
            "match_count": len(result.items),
            "has_matches": result.has_matches,
            "state": "running",
        }
    )

    records.append(
        {
            "run_id": "mem-complete",
            "source": "long_term",
            "phase": "complete",
            "title": recall_presentation["title"],
            "icon": recall_presentation["icon"],
            "status_line": "Souvenirs intégrés.",
            "wave_style": recall_presentation["wave_style"],
            "state": "complete",
            "success": True,
        }
    )

    return records


def register_memory_source(key: str, definition: dict[str, Any]) -> None:
    """Register a future memory source for automatic UI presentation."""
    normalized = key.lower().replace("-", "_")
    base = dict(_MEMORY_SOURCE_PRESENTATION.get("long_term", {}))
    base.update(definition)
    _MEMORY_SOURCE_PRESENTATION[normalized] = base
