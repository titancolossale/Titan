# =====================================
# Titan Brain Pipeline Tests
# =====================================

"""Integration smoke tests for Phase 2 think pipeline (P2-024–P2-025)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brain.brain import Brain
from brain.llm import LLM_ERROR_MESSAGE
from brain.pipeline.stages import STAGE_ORDER


def test_pipeline_stage_order_matches_rulebook() -> None:
    """P2-024: pipeline executes stages in canonical rulebook order."""
    assert STAGE_ORDER[0] == "knowledge_search"
    assert STAGE_ORDER[-1] == "update_context"
    assert "session_commands" in STAGE_ORDER
    assert "conversation_commands" in STAGE_ORDER
    assert "mission_commands" in STAGE_ORDER
    assert "load_conversation" in STAGE_ORDER
    assert "memory_commands" in STAGE_ORDER
    assert "assemble_prompt" in STAGE_ORDER
    assert STAGE_ORDER.index("execution_coordinate") < STAGE_ORDER.index("llm_call")
    assert STAGE_ORDER.index("llm_call") < STAGE_ORDER.index("evaluate_mission_step")


def test_brain_think_uses_retrieved_memory_in_llm_prompt(brain: Brain) -> None:
    """P2-022/P2-025: LLM prompt uses retrieved memory, not full JSON dump."""
    brain.memory_service.retrieve = MagicMock(
        return_value=type("R", (), {"text": "Nolan note : préfère Python"})(),
    )
    brain.long_memory.show_memory = MagicMock(
        return_value='{"users": {"Nolan": {"notes": ["secret"]}}}',
    )

    brain.think("Parle-moi de Python")

    prompt_sent = brain.llm.ask.call_args[0][0]
    assert "Nolan note : préfère Python" in prompt_sent
    assert '"users":' not in prompt_sent
    brain.long_memory.show_memory.assert_not_called()


def test_brain_think_skips_llm_for_show_memory_command(brain: Brain) -> None:
    """P3-031: show-memory command returns direct response without LLM call."""
    brain.memory_service.maybe_remember("Nolan", "Je préfère Python")

    result = brain.think("Montre ma mémoire")

    assert "Python" in result
    assert brain.llm.ask.call_count == 0


def test_brain_think_single_llm_call(brain: Brain) -> None:
    """P2-025: exactly one LLM call per think() turn."""
    brain.think("Bonjour Titan")

    assert brain.llm.ask.call_count == 1


def test_brain_think_records_pipeline_stages(brain: Brain) -> None:
    """P2-024: pipeline stage_log matches STAGE_ORDER after run."""
    brain.think("test pipeline")

    assert brain.pipeline.stage_log == list(STAGE_ORDER)


def test_brain_think_returns_llm_response(brain: Brain) -> None:
    """P2-025: think() returns the LLM response string."""
    brain.llm.ask.return_value = "Réponse personnalisée."

    result = brain.think("Question test")

    assert result == "Réponse personnalisée."


def test_brain_think_returns_french_error_on_llm_failure(brain: Brain) -> None:
    """P2-025: LLM failure surfaces French fallback through think()."""
    brain.llm.ask.return_value = LLM_ERROR_MESSAGE

    result = brain.think("Question test")

    assert result == LLM_ERROR_MESSAGE


def test_brain_think_method_is_thin_orchestrator() -> None:
    """P2-021 DoD: think() delegates to pipeline — method body ≤ 5 lines."""
    import inspect

    source = inspect.getsource(Brain.think)
    body_lines = [
        line for line in source.splitlines()[1:]
        if line.strip() and not line.strip().startswith('"""')
    ]
    assert len(body_lines) <= 5


def test_knowledge_reports_settings_version() -> None:
    """P2-023: Knowledge uses VERSION from settings, not hardcoded 0.0.1."""
    from brain.knowledge import Knowledge
    from config.settings import VERSION

    knowledge = Knowledge()
    assert knowledge.search("quelle version") == VERSION


def test_brain_think_skips_llm_for_user_switch_command(brain: Brain) -> None:
    """P4-031: /user command returns direct response without LLM call."""
    result = brain.think("/user Ibrahim")

    assert "Ibrahim" in result
    assert brain.llm.ask.call_count == 0
    assert brain.context_manager.current_user == "Ibrahim"


def test_brain_think_includes_conversation_window_in_prompt(brain: Brain) -> None:
    """P7-030: prior turns appear in CONVERSATION RÉCENTE section."""
    prior_user = "Première question alpha"
    prior_titan = "Première réponse beta"
    current_user = "Deuxième question gamma"
    brain.conversation_engine.add_user_turn("Nolan", prior_user)
    brain.conversation_engine.add_titan_turn(prior_titan, user="Nolan")
    brain.conversation_engine.add_user_turn("Nolan", current_user)

    brain.think(current_user)

    prompt_sent = brain.llm.ask.call_args[0][0]
    conv_start = prompt_sent.index("CONVERSATION RÉCENTE")
    agents_start = prompt_sent.index("RÉSULTATS DES AGENTS")
    conv_section = prompt_sent[conv_start:agents_start]

    assert prior_user in conv_section
    assert prior_titan in conv_section
    assert current_user not in conv_section


def test_brain_think_skips_llm_for_clear_history_command(brain: Brain) -> None:
    """P7-031: /clear returns direct response without LLM call."""
    brain.conversation_engine.add_user_turn("Nolan", "test")

    result = brain.think("/clear")

    assert "effacé" in result.lower()
    assert brain.llm.ask.call_count == 0
    assert brain.conversation_engine.turn_count == 0


def test_brain_think_uses_dynamic_context_from_state(brain: Brain) -> None:
    """P4-032: situational context reflects state, not static defaults."""
    brain.state_manager.update_state("active_project", "Dynamic Project X")
    brain.state_manager.update_state("current_step", "Integration tests")

    brain.think("Bonjour")

    prompt_sent = brain.llm.ask.call_args[0][0]
    assert "Dynamic Project X" in prompt_sent
    assert "Integration tests" in prompt_sent


def test_brain_think_user_switch_affects_memory_retrieval(brain: Brain) -> None:
    """P4-033: after /user Ibrahim, memory retrieval uses Ibrahim scope."""
    brain.memory_service.maybe_remember("Ibrahim", "Je préfère le café")

    brain.think("/user Ibrahim")
    brain.llm.ask.reset_mock()
    result = brain.think("Montre ma mémoire")

    assert "café" in result
    assert brain.llm.ask.call_count == 0
