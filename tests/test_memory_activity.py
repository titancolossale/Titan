# =====================================
# Titan Memory Activity Tests
# =====================================

"""Tests for Phase 17.9 memory activity formatting."""

from __future__ import annotations

from api.memory_activity import (
    format_memory_activity,
    normalize_memory_source,
    register_memory_source,
)
from brain.pipeline.context_bundle import ThinkContext
from memory.models import RetrievalResult


def test_normalize_memory_source_maps_obsidian() -> None:
    assert normalize_memory_source("obsidian_vault") == "obsidian"
    assert normalize_memory_source("browser_history") == "browser"


def test_format_memory_activity_never_exposes_raw_items() -> None:
    ctx = ThinkContext(
        user_message="Parle-moi du projet Titan",
        active_project="Titan",
        conversation_loaded=True,
        conversation_window=["User: salut", "Titan: bonjour"],
        retrieval_result=RetrievalResult(
            text="Nolan projet : Titan\nNolan note : routine gym",
            items=[
                "Nolan projet : Titan",
                "Nolan note : routine gym",
            ],
            user="Nolan",
        ),
    )

    activity = format_memory_activity(ctx)

    assert len(activity) >= 3
    serialized = str(activity)
    assert "routine gym" not in serialized
    assert "Nolan note" not in serialized
    assert "json" not in serialized.lower()

    recall = next(record for record in activity if record["phase"] == "recall")
    assert recall["has_matches"] is True
    assert recall["match_count"] == 2
    assert "Titan Project" in recall["cards"]
    assert "Conversation précédente" in recall["cards"]


def test_format_memory_activity_empty_when_no_retrieval() -> None:
    ctx = ThinkContext(user_message="Bonjour")
    assert format_memory_activity(ctx) == []


def test_format_memory_activity_no_matches_still_recalls() -> None:
    ctx = ThinkContext(
        user_message="Quelle heure est-il ?",
        retrieval_result=RetrievalResult(
            text="Aucune mémoire pertinente trouvée.",
            items=[],
            user="Nolan",
        ),
    )

    activity = format_memory_activity(ctx)
    recall = next(record for record in activity if record["phase"] == "recall")

    assert recall["has_matches"] is False
    assert recall["match_count"] == 0
    assert recall["cards"] == []


def test_register_memory_source_extends_presentation() -> None:
    register_memory_source(
        "custom_archive",
        {
            "title": "Archives",
            "search_line": "Souvenirs lointains…",
            "wave_style": "slow",
        },
    )
    assert normalize_memory_source("custom_archive") == "custom_archive"
