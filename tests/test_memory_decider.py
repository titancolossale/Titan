# =====================================
# Titan Memory Decider Tests
# =====================================

"""Tests for memory write gating and user resolution (P3-020 / P3-021)."""

from __future__ import annotations

import pytest

from memory.memory_decider import MemoryDecider


@pytest.fixture
def decider() -> MemoryDecider:
    return MemoryDecider()


@pytest.mark.parametrize(
    "message",
    [
        "salut titan",
        "Bonjour, comment vas-tu ?",
        "On avance sur le projet Titan",
    ],
)
def test_should_remember_rejects_casual_messages(
    decider: MemoryDecider,
    message: str,
) -> None:
    """P3-021: over-broad keywords must not trigger auto-save."""
    assert decider.should_remember(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "Souviens-toi que je code en Python",
        "Je préfère travailler le matin",
        "Mon objectif est de finir Titan",
        "remember my stack is FastAPI",
    ],
)
def test_should_remember_accepts_explicit_phrases(
    decider: MemoryDecider,
    message: str,
) -> None:
    """Explicit remember phrases must trigger persistence."""
    assert decider.should_remember(message) is True


def test_resolve_user_prefers_message_subject(decider: MemoryDecider) -> None:
    """P3-020: Ibrahim mentioned in message stores to Ibrahim."""
    assert decider.resolve_user("Ibrahim aime le café", "Nolan") == "Ibrahim"


def test_resolve_user_falls_back_to_session(decider: MemoryDecider) -> None:
    """Session user used when message has no user hint."""
    assert decider.resolve_user("Je préfère le café", "Nolan") == "Nolan"


def test_parse_remember_content_extracts_payload(decider: MemoryDecider) -> None:
    """P3-030: souviens-toi de extracts content."""
    content = decider.parse_remember_content("Souviens-toi de mon numéro 42")

    assert content == "mon numéro 42"


def test_parse_forget_query_extracts_target(decider: MemoryDecider) -> None:
    """P3-030: oublie extracts search query."""
    query = decider.parse_forget_query("Oublie le mot trading")

    assert query == "le mot trading"
