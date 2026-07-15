# =====================================
# Titan Cognitive Loop Tests
# =====================================

"""Unit tests for Cognitive Loop V1 — cognition without tool execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.brain import Brain
from brain.cognitive_loop import (
    CognitiveLoop,
    CognitiveLoopResult,
    ThoughtPriority,
)
from brain.tool_intelligence import build_default_tool_intelligence
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService

CORE_TOOLS_DIR = Path(__file__).resolve().parents[1] / "core" / "tools"


@pytest.fixture
def memory_service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )


@pytest.fixture
def cognitive_loop(memory_service: MemoryService) -> CognitiveLoop:
    state = StateManager(file_path=memory_service.long_term.file_path.parent / "state.json")
    mission = MissionManager(file_path=memory_service.long_term.file_path.parent / "mission.json")
    context = ContextManager(state_manager=state, mission_manager=mission)
    return CognitiveLoop(
        memory_service=memory_service,
        tool_intelligence=build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR]),
        context_manager=context,
    )


def _summaries(result: CognitiveLoopResult) -> list[str]:
    return [thought.summary for thought in result.thoughts]


def _tool_sets(result: CognitiveLoopResult) -> list[tuple[str, ...]]:
    return [thought.requires_tools for thought in result.thoughts]


def test_conversation_only_greeting(cognitive_loop: CognitiveLoop) -> None:
    result = cognitive_loop.run("Hello")

    assert isinstance(result, CognitiveLoopResult)
    assert any("Conversation only" in summary for summary in _summaries(result))
    assert all("obsidian" not in tools and "browser" not in tools for tools in _tool_sets(result))
    conversation_thought = next(
        thought for thought in result.thoughts if "Conversation only" in thought.summary
    )
    assert conversation_thought.priority == ThoughtPriority.LOW
    assert conversation_thought.confidence >= 0.9
    assert result.recommendations == ()


def test_obsidian_recommendation_for_orr_notes(cognitive_loop: CognitiveLoop) -> None:
    result = cognitive_loop.run("Tell me about my ORR notes")

    assert any("Obsidian" in summary for summary in _summaries(result))
    obsidian_thoughts = [
        thought for thought in result.thoughts if "obsidian" in thought.requires_tools
    ]
    assert obsidian_thoughts
    assert obsidian_thoughts[0].confidence >= 0.35
    assert any(
        rec.requires_tools == ("obsidian",)
        for rec in result.recommendations
    )


def test_browser_recommendation_for_fastapi_docs(cognitive_loop: CognitiveLoop) -> None:
    result = cognitive_loop.run("Explain FastAPI routing from the official documentation")

    assert any("Browser" in summary or "official docs" in summary.lower() for summary in _summaries(result))
    browser_thoughts = [
        thought for thought in result.thoughts if "browser" in thought.requires_tools
    ]
    assert browser_thoughts
    assert browser_thoughts[0].priority in {
        ThoughtPriority.NORMAL,
        ThoughtPriority.HIGH,
        ThoughtPriority.CRITICAL,
    }


def test_mixed_reasoning_compare_notes_and_docs(cognitive_loop: CognitiveLoop) -> None:
    result = cognitive_loop.run("Compare my ORR notes with FastAPI docs")

    summaries = _summaries(result)
    assert any("Obsidian" in summary for summary in summaries)
    assert any(
        "Browser" in summary or "documentation" in summary.lower() for summary in summaries
    )
    compare_thoughts = [
        thought
        for thought in result.thoughts
        if set(thought.requires_tools) == {"obsidian", "browser"}
    ]
    assert compare_thoughts
    assert compare_thoughts[0].priority == ThoughtPriority.HIGH


def test_priority_ordering_critical_before_low(cognitive_loop: CognitiveLoop) -> None:
    memory = cognitive_loop._memory_service.long_term
    memory.write_categorized("Nolan", "projects", "Titan ORR roadmap milestone")
    memory.write_categorized("Nolan", "goals", "Ship Cognitive Loop V1")
    memory.write_categorized("Nolan", "notes", "Review ORR vault notes weekly")

    result = cognitive_loop.run("What should I know about ORR for Titan?")

    priorities = [thought.priority for thought in result.thoughts]
    if ThoughtPriority.CRITICAL in priorities and ThoughtPriority.LOW in priorities:
        assert priorities.index(ThoughtPriority.CRITICAL) < priorities.index(ThoughtPriority.LOW)


def test_memory_influence_boosts_obsidian_confidence(
    cognitive_loop: CognitiveLoop,
) -> None:
    memory = cognitive_loop._memory_service.long_term
    memory.write_categorized("Nolan", "projects", "ORR notes live in Obsidian vault")

    with_memory = cognitive_loop.run("Summarize my ORR notes")
    without_memory = cognitive_loop.run("Summarize xyzzy plugh notes")

    with_conf = max(
        (
            thought.confidence
            for thought in with_memory.thoughts
            if "obsidian" in thought.requires_tools
        ),
        default=0.0,
    )
    without_conf = max(
        (
            thought.confidence
            for thought in without_memory.thoughts
            if "obsidian" in thought.requires_tools
        ),
        default=0.0,
    )
    assert with_conf >= without_conf


def test_no_duplicate_thoughts_for_obsidian_and_memory(cognitive_loop: CognitiveLoop) -> None:
    memory = cognitive_loop._memory_service.long_term
    memory.write_categorized("Nolan", "notes", "ORR design notes in vault")

    result = cognitive_loop.run("Read my ORR notes")

    obsidian_summaries = [
        thought.summary
        for thought in result.thoughts
        if "Obsidian" in thought.summary
    ]
    assert len(obsidian_summaries) == len(set(obsidian_summaries))


def test_session_open_generates_review_thought(
    cognitive_loop: CognitiveLoop,
) -> None:
    cognitive_loop._memory_service.remember_session("Unread Titan project checkpoint")

    result = cognitive_loop.run("")

    assert any("Review latest project notes" in summary for summary in _summaries(result))
    assert any(obs.summary == "Unread session notes detected." for obs in result.observations)


def test_observations_include_sources(cognitive_loop: CognitiveLoop) -> None:
    result = cognitive_loop.run("Hello")

    sources = {observation.source for observation in result.observations}
    assert "message" in sources
    assert "memory" in sources
    assert "tool_intelligence" in sources


def test_result_serializes_to_dict(cognitive_loop: CognitiveLoop) -> None:
    payload = cognitive_loop.run("Hello").to_dict()

    assert payload["message"] == "Hello"
    assert isinstance(payload["observations"], list)
    assert isinstance(payload["thoughts"], list)
    assert isinstance(payload["recommendations"], list)
    if payload["thoughts"]:
        thought = payload["thoughts"][0]
        assert {"id", "source", "priority", "confidence", "summary", "reasoning",
                "recommended_action", "requires_tools", "timestamp"} <= set(thought)


def test_brain_generate_thoughts_api(brain: Brain) -> None:
    result = brain.generate_thoughts("Hello")

    assert isinstance(result, CognitiveLoopResult)
    assert result.message == "Hello"
    assert result.observations
    assert result.thoughts
