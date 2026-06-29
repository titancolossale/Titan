# =====================================
# Titan MemoryRetriever Tests
# =====================================

"""Baseline regression tests for MemoryRetriever keyword relevance filtering."""

from __future__ import annotations

import pytest

from memory.memory_retriever import MemoryRetriever


@pytest.fixture
def retriever() -> MemoryRetriever:
    """Fresh MemoryRetriever instance for each test."""
    return MemoryRetriever()


EMPTY_MEMORY: dict = {
    "users": {},
    "titan": {},
}

NO_MATCH_MEMORY: dict = {
    "users": {
        "Nolan": {
            "notes": ["Algorithmes de trading pour le marché crypto"],
            "preferences": [],
            "projects": [],
        }
    },
    "titan": {},
}


def test_retrieve_empty_memory_returns_default_message(
    retriever: MemoryRetriever,
) -> None:
    """Empty memory dict must yield the French no-match fallback string."""
    result = retriever.retrieve(EMPTY_MEMORY, "Bonjour Titan")

    assert result == "Aucune mémoire pertinente trouvée."


def test_retrieve_matching_user_note_returns_formatted_line(
    retriever: MemoryRetriever,
) -> None:
    """A user note sharing a keyword (>3 chars) with the message must be returned."""
    memory = {
        "users": {
            "Nolan": {
                "notes": ["Je travaille sur le robot de trading"],
                "preferences": [],
                "projects": [],
            }
        },
        "titan": {},
    }

    result = retriever.retrieve(memory, "Comment avance le robot de trading ?")

    assert result == "Nolan note : Je travaille sur le robot de trading"


def test_retrieve_no_keyword_overlap_returns_default_message(
    retriever: MemoryRetriever,
) -> None:
    """Stored notes with no word overlap must not appear in retrieval output."""
    result = retriever.retrieve(
        NO_MATCH_MEMORY,
        "Bonjour, quelle heure est-il ?",
    )

    assert result == "Aucune mémoire pertinente trouvée."


def test_retrieve_user_filter_excludes_other_users(
    retriever: MemoryRetriever,
) -> None:
    """P3-022: user-scoped retrieval must not include other users' notes."""
    memory = {
        "users": {
            "Nolan": {
                "notes": ["Nolan secret trading plan"],
                "preferences": [],
                "projects": [],
                "goals": [],
                "active_projects": [],
            },
            "Ibrahim": {
                "notes": ["Ibrahim secret hobby"],
                "preferences": [],
                "projects": [],
                "goals": [],
                "active_projects": [],
            },
        },
        "titan": {},
    }

    result = retriever.retrieve(memory, "parle-moi du trading", user="Nolan")

    assert "Nolan secret trading plan" in result
    assert "Ibrahim" not in result


@pytest.mark.parametrize(
    ("message", "expected_fragment"),
    [
        (
            "Quelle est la mission de Titan ?",
            "Titan mission : Aider Nolan et Ibrahim à construire leurs projets.",
        ),
        (
            "On en est où sur current_project ?",
            "Titan current_project : Titan",
        ),
    ],
)
def test_retrieve_titan_block_match_by_key_or_value(
    retriever: MemoryRetriever,
    message: str,
    expected_fragment: str,
) -> None:
    """Titan block entries match when message contains a titan key or value."""
    memory = {
        "users": {},
        "titan": {
            "mission": "Aider Nolan et Ibrahim à construire leurs projets.",
            "current_project": "Titan",
        },
    }

    result = retriever.retrieve(memory, message)

    assert expected_fragment in result
