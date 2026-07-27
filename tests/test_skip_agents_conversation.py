# =====================================
# Titan skip_agents Conversation Path Tests
# =====================================

"""Prove conversation/question turns skip agent orchestration and reach the LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.brain import Brain
from brain.natural_language_orchestrator import DetectedIntent, SystemName
from brain.pipeline.context_bundle import ThinkContext
from brain.pipeline.stages import STAGE_ORDER
from brain.prompt_builder import PromptBuilder
from brain.request_deadline import (
    RequestDeadline,
    reset_request_deadline,
    set_request_deadline,
)
from tests.test_natural_language_orchestrator import _build_brain, _make_python_project


@pytest.fixture
def brain(tmp_path: Path) -> Brain:
    project = _make_python_project(tmp_path)
    return _build_brain(tmp_path, project)


@pytest.fixture(autouse=True)
def _clear_deadline() -> None:
    token = set_request_deadline(None)
    yield
    reset_request_deadline(token)


def test_conversation_intent_calls_think_with_skip_agents(brain: Brain) -> None:
    """Non-fast-path conversation still reaches think(skip_agents=True)."""
    with patch.object(brain, "think", return_value="ok") as mock_think:
        # Force complex path so _handle_conversation is used (not chat_fast_path).
        with patch(
            "brain.natural_language_orchestrator.is_simple_conversational_request",
            return_value=False,
        ):
            result = brain.process_request(
                "Bonjour, comment avancer concrètement sur Titan aujourd'hui ?"
            )
    assert result.detected_intent == DetectedIntent.CONVERSATION
    mock_think.assert_called()
    kwargs = mock_think.call_args.kwargs
    assert kwargs.get("skip_agents") is True
    assert (result.artifacts or {}).get("skip_agents") is True


def test_question_intent_calls_think_with_skip_agents(brain: Brain) -> None:
    """Question intent (no tool required) uses skip_agents=True."""
    with patch.object(brain, "think", return_value="Paris") as mock_think:
        result = brain.process_request("What is the capital of France?")
    assert result.detected_intent == DetectedIntent.QUESTION
    mock_think.assert_called()
    assert mock_think.call_args.kwargs.get("skip_agents") is True
    assert (result.artifacts or {}).get("skip_agents") is True


def test_tool_intent_does_not_skip_agents(brain: Brain) -> None:
    """Tool requests keep the normal tool execution path (no skip_agents think)."""
    with patch.object(brain, "think") as mock_think:
        with patch.object(
            brain,
            "execute_request",
            return_value=MagicMock(
                summary_message="Tool done",
                to_dict=lambda: {"ok": True},
            ),
        ):
            with patch.object(
                brain,
                "plan_tool_execution",
                return_value=MagicMock(
                    requires_tools=True,
                    selected_tools=(),
                    to_dict=lambda: {},
                ),
            ):
                result = brain.process_request("Run pytest")
    assert result.detected_intent == DetectedIntent.TOOL_REQUEST
    mock_think.assert_not_called()
    assert (result.artifacts or {}).get("skip_agents") is not True


def test_research_intent_does_not_skip_agents(brain: Brain) -> None:
    """Research intents keep the tool path — agents/tools are not skipped."""
    with patch.object(brain, "think") as mock_think:
        with patch.object(
            brain,
            "execute_request",
            return_value=MagicMock(
                summary_message="Browser search completed",
                to_dict=lambda: {"ok": True},
            ),
        ):
            with patch.object(
                brain,
                "plan_tool_execution",
                return_value=MagicMock(
                    requires_tools=True,
                    selected_tools=(),
                    to_dict=lambda: {},
                ),
            ):
                result = brain.process_request("Search FastAPI docs")
    assert result.detected_intent == DetectedIntent.RESEARCH
    mock_think.assert_not_called()
    assert (result.artifacts or {}).get("skip_agents") is not True


def test_skip_agents_reaches_llm_without_execution_coordinator(brain: Brain) -> None:
    """skip_agents=True skips ExecutionCoordinator but still calls the LLM."""
    deadline = RequestDeadline.start(total_seconds=30, request_id="skip-agents-1")
    token = set_request_deadline(deadline)
    try:
        coord = brain.pipeline.execution_coordinator
        with patch.object(coord, "execute", wraps=coord.execute) as mock_execute:
            response = brain.think("Explique-moi Titan brièvement.", skip_agents=True)
    finally:
        reset_request_deadline(token)
    assert response == "Réponse de test."
    mock_execute.assert_not_called()
    assert brain.llm.ask.call_count == 1
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.skip_agents is True
    assert "execution_coordinate" in brain.pipeline.stage_log
    assert "assemble_prompt" in brain.pipeline.stage_log
    assert "llm_call" in brain.pipeline.stage_log
    assert STAGE_ORDER.index("load_conversation") < STAGE_ORDER.index(
        "execution_coordinate"
    )


def test_skip_agents_keeps_phase_12_2_conversation_context(brain: Brain) -> None:
    """Conversation load + Phase 12.2 prompt sections still run with skip_agents."""
    # Prove pipeline still runs load_conversation before LLM when skipping agents.
    response = brain.think("Tu te souviens de mon projet ?", skip_agents=True)
    assert response == "Réponse de test."
    assert "load_conversation" in brain.pipeline.stage_log
    assert "assemble_prompt" in brain.pipeline.stage_log
    assert "llm_call" in brain.pipeline.stage_log
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.skip_agents is True

    # Prove PromptBuilder still injects Phase 12.2 layers when present on context.
    rich = ThinkContext(
        user_message="suite",
        skip_agents=True,
        conversation_window=["User : Mon projet préféré est Titan."],
        conversation_summary="L'utilisateur construit Titan.",
        pinned_facts_text="- Préfère Python",
    )
    built = PromptBuilder().build(rich)
    assert "CONVERSATION RÉCENTE" in built
    assert "RÉSUMÉ CONVERSATION" in built
    assert "FAITS ÉPINGLÉS" in built
    assert "Préfère Python" in built
    assert "Mon projet préféré est Titan." in built


def test_skip_agents_structured_logs(brain: Brain, caplog: pytest.LogCaptureFixture) -> None:
    """Required CHAT_* logs fire with request_id on the skip_agents path."""
    deadline = RequestDeadline.start(total_seconds=30, request_id="chat-logs-1")
    token = set_request_deadline(deadline)
    try:
        with caplog.at_level(logging.INFO):
            brain.think("Quelle est ta mission ?", skip_agents=True)
    finally:
        reset_request_deadline(token)
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "CHAT_THINK_ENTER" in joined
    assert "skip_agents=True" in joined
    assert "CHAT_THINK_STAGE_ENTER" in joined
    assert "CHAT_EXEC_COORD_SKIPPED reason=skip_agents" in joined
    assert "CHAT_LLM_CALL_ENTER" in joined
    assert "request_id=chat-logs-1" in joined


def test_think_default_does_not_force_skip_agents(brain: Brain) -> None:
    """Direct think() without skip_agents keeps orchestration available."""
    coord = brain.pipeline.execution_coordinator
    with patch.object(
        coord,
        "execute",
        return_value=MagicMock(
            agent_results=[],
            agent_results_text="",
            tool_results=[],
            tool_results_text="",
            decision_report=None,
            cognitive_execution=None,
        ),
    ) as mock_execute:
        # Avoid greeting safety-net that auto-sets skip_agents.
        brain.think("Analyse cette demande non conversationnelle pour le routage.")
    mock_execute.assert_called_once()
    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.skip_agents is False
