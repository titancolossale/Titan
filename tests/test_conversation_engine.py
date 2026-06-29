# =====================================
# Titan Conversation Engine Tests
# =====================================

"""Tests for Phase 7 conversation engine (P7-060–P7-070)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import (
    CONVERSATION_MAX_STORED_TURNS,
    CONVERSATION_SUMMARIZE_THRESHOLD,
    CONVERSATION_WINDOW_SIZE,
)
from core.conversation_engine import ConversationEngine, TITAN_SPEAKER
from core.conversation_models import ConversationTurn
from memory.memory_service import MemoryService


def test_turn_model_round_trip() -> None:
    """P7-010: ConversationTurn serializes and deserializes cleanly."""
    turn = ConversationTurn(speaker="Nolan", message="Bonjour", user="Nolan")
    restored = ConversationTurn.from_dict(turn.to_dict())

    assert restored.speaker == "Nolan"
    assert restored.message == "Bonjour"
    assert restored.user == "Nolan"
    assert restored.id == turn.id


def test_window_size_limits_prompt_turns() -> None:
    """P7-012: 20 turns stored, prompt window returns only last N."""
    engine = ConversationEngine(window_size=10, persist_sessions=False)
    for index in range(20):
        speaker = "Nolan" if index % 2 == 0 else TITAN_SPEAKER
        engine.add_message(speaker, f"message-{index}", user="Nolan")

    assert engine.turn_count == 20
    window = engine.get_prompt_window()
    assert len(window) == 10
    assert window[0].endswith("message-10")
    assert window[-1].endswith("message-19")


def test_chronological_order_in_prompt_window() -> None:
    """P7-013: formatted window preserves chronological order."""
    engine = ConversationEngine(persist_sessions=False)
    engine.add_user_turn("Nolan", "Première question")
    engine.add_titan_turn("Première réponse", user="Nolan")
    engine.add_user_turn("Nolan", "Deuxième question")

    lines = engine.get_prompt_window(current_message="Deuxième question")

    assert len(lines) == 2
    assert lines[0].startswith("Nolan : Première question")
    assert lines[1].startswith(f"{TITAN_SPEAKER} : Première réponse")


def test_user_attribution_iban_turn_labeled() -> None:
    """P7-012: Ibrahim turns carry correct speaker label."""
    engine = ConversationEngine(persist_sessions=False)
    engine.add_user_turn("Ibrahim", "Salut Titan")

    window = engine.get_window()
    assert window[0].speaker == "Ibrahim"
    assert window[0].user == "Ibrahim"
    lines = engine.get_prompt_window(current_message="Salut Titan")
    assert lines == []


def test_excludes_duplicate_current_user_message() -> None:
    """P7-013: current user message is not duplicated in prompt window."""
    engine = ConversationEngine(persist_sessions=False)
    engine.add_user_turn("Nolan", "Question en cours")

    assert engine.get_prompt_window(current_message="Question en cours") == []


def test_extractive_summarization_archives_old_turns() -> None:
    """P7-014: turns beyond threshold collapse into archived summary."""
    engine = ConversationEngine(
        window_size=5,
        max_stored_turns=10,
        summarize_threshold=5,
        persist_sessions=False,
    )
    for index in range(12):
        speaker = "Nolan" if index % 2 == 0 else TITAN_SPEAKER
        engine.add_message(speaker, f"turn-{index}", user="Nolan")

    assert engine.turn_count == 10
    lines = engine.get_prompt_window()
    assert any("[Résumé de" in line for line in lines)
    assert engine.total_turn_count == 12


def test_empty_history_first_turn() -> None:
    """P7-013: empty history returns no prompt lines without error."""
    engine = ConversationEngine(persist_sessions=False)

    assert engine.get_prompt_window() == []
    assert engine.format_history() == "Aucun historique de conversation."


def test_clear_history_command() -> None:
    """P7-041: /clear removes all turns."""
    engine = ConversationEngine(persist_sessions=False)
    engine.add_user_turn("Nolan", "test")
    response = engine.handle_command("/clear")

    assert response is not None
    assert "effacé" in response.lower()
    assert engine.turn_count == 0


def test_session_status_command() -> None:
    """P7-042: session status reports id and turn counts."""
    engine = ConversationEngine(session_id="abc123", persist_sessions=False)
    engine.add_user_turn("Nolan", "hello")

    status = engine.handle_command("/session")

    assert status is not None
    assert "abc123" in status
    assert "1" in status


def test_session_persistence_round_trip(tmp_path: Path) -> None:
    """P7-040: session file saves and reloads turns."""
    sessions_dir = tmp_path / "sessions"
    engine = ConversationEngine(
        session_id="sess01",
        persist_sessions=True,
        sessions_dir=sessions_dir,
    )
    engine.add_user_turn("Nolan", "Persist me")
    engine.add_titan_turn("Réponse", user="Nolan")

    reloaded = ConversationEngine(
        session_id="sess01",
        persist_sessions=True,
        sessions_dir=sessions_dir,
    )
    assert reloaded.load_session() is True
    assert reloaded.turn_count == 2
    assert reloaded.get_window()[0].message == "Persist me"


def test_memory_summary_hook() -> None:
    """P7-050: session summary available for memory promotion."""
    engine = ConversationEngine(persist_sessions=False)
    engine.add_user_turn("Nolan", "Je préfère Python")
    engine.add_titan_turn("Noté.", user="Nolan")

    summary = engine.get_session_summary_for_memory()

    assert summary is not None
    assert "Python" in summary


def test_settings_defaults() -> None:
    """P7-001: conversation settings have sensible defaults."""
    assert CONVERSATION_WINDOW_SIZE == 10
    assert CONVERSATION_MAX_STORED_TURNS == 50
    assert CONVERSATION_SUMMARIZE_THRESHOLD == 30


def test_memory_service_remembers_conversation_summary(memory_service: MemoryService) -> None:
    """P7-050: MemoryService stores session summary for promotion path."""
    saved = memory_service.remember_conversation_summary(
        "Nolan",
        "Nolan: Je préfère Python | Titan: Noté.",
    )

    assert saved is True
    text = memory_service.handle_command("Nolan", "Montre ma mémoire")
    assert text is not None
    assert "Python" in text


def test_conversation_wrapper_delegates() -> None:
    """P7-020: legacy Conversation class delegates to ConversationEngine."""
    from core.conversation import Conversation

    conv = Conversation(persist_sessions=False)
    conv.add_message("Ibrahim", "Salut")
    conv.add_message(TITAN_SPEAKER, "Bonjour Ibrahim")

    assert conv.turn_count == 2
    assert "Ibrahim" in conv.format_history()
