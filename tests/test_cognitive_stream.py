# =====================================
# Titan Cognitive Stream Tests
# =====================================

"""Tests for Phase E9 live cognitive streaming."""

from __future__ import annotations

from unittest.mock import MagicMock

from api.stream_service import handle_chat_stream
from brain.cognitive_stream import (
    COGNITIVE_EVENT_TYPES,
    CognitiveStreamEmitter,
    intent_label,
)
from core.titan import Titan
from tools.tool_manager import ToolManager
from api.titan_service import reset_titan, set_titan


def test_cognitive_event_types_complete() -> None:
    expected = {
        "thinking_started",
        "intent_detected",
        "memory_lookup",
        "memory_hit",
        "memory_miss",
        "obsidian_lookup",
        "tool_selection",
        "tool_execution",
        "reasoning",
        "planning",
        "verification",
        "response_building",
        "response_ready",
        "thinking_finished",
    }
    assert set(COGNITIVE_EVENT_TYPES) == expected


def test_emitter_tracks_pipeline_state() -> None:
    events: list[tuple[str, dict]] = []

    emitter = CognitiveStreamEmitter(lambda t, d: events.append((t, d)))
    emitter.start_thinking(message="Hello", user="Nolan")
    emitter.emit("memory_lookup", {"label": "Recherche…"})
    emitter.emit("memory_hit", {"label": "Trouvé", "has_matches": True})
    emitter.finish_thinking()

    assert emitter.thinking is False
    assert emitter.current_stage is None
    assert len(emitter.stage_history) >= 3
    assert "memory_lookup" in emitter.pipeline
    assert events[0][0] == "thinking_started"
    assert events[-1][0] == "thinking_finished"


def test_intent_label_sanitized() -> None:
    assert intent_label("general_chat") == "Conversation générale"
    assert intent_label("obsidian") == "Obsidian"
    assert intent_label("file_read") == "Lecture de fichier"


def test_handle_chat_stream_emits_live_pipeline_events(tmp_path) -> None:
    """Integration — real think() path streams memory and intent events."""
    reset_titan()
    tool_manager = ToolManager(project_root=tmp_path)
    titan = Titan()
    titan.tools = tool_manager
    titan.brain.tool_manager = tool_manager
    mock_llm = MagicMock()
    mock_llm.ask.return_value = "Réponse de test."
    titan.brain.llm = mock_llm
    set_titan(titan)

    events: list[str] = []

    def capture(event_type: str, data: dict) -> None:
        events.append(event_type)

    handle_chat_stream("Bonjour Titan", emit=capture)

    assert "thinking_started" in events
    assert "memory_lookup" in events
    assert "thinking_finished" in events
    assert any(e in events for e in ("memory_hit", "memory_miss"))
    reset_titan()
