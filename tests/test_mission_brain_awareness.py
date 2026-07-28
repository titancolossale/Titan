# =====================================
# Titan Mission Awareness Inside Brain Tests
# =====================================

"""Phase 14.3 — Brain loads active mission from WorkspaceState once per think()."""

from __future__ import annotations

import logging
from typing import Any

from agents.agent_context import AgentContext
from brain.brain import Brain
from brain.pipeline.context_bundle import MissionContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.mission_models import MissionPriority
from core.state_manager import WorkspaceState


def _seed_active_mission(brain: Brain) -> None:
    brain.state_manager.update(
        active_mission="Mission Awareness",
        active_mission_id="mission-14-3",
        active_mission_title="Mission Awareness",
        active_mission_status="RUNNING",
        active_mission_progress=0.4,
        active_mission_priority=MissionPriority.HIGH.value,
        active_mission_stage="Wire ThinkContext",
    )


def test_brain_loads_active_mission_into_think_context(brain: Brain) -> None:
    """Brain.think() must load WorkspaceState mission fields into ThinkContext."""
    _seed_active_mission(brain)

    brain.think("Quelle est la mission active ?")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.active_mission_title == "Mission Awareness"
    assert ctx.mission_context is not None
    assert ctx.mission_context.active_mission == "Mission Awareness"
    assert ctx.mission_context.status == "RUNNING"
    assert ctx.mission_context.progress == 0.4
    assert ctx.mission_context.priority == "HIGH"
    assert ctx.mission_context.stage == "Wire ThinkContext"


def test_mission_context_shared_across_pipeline_stages(brain: Brain) -> None:
    """Every stage must see the same mission_context object (no duplicated lookups).

    Phase 14.4 may refresh mission_context after a successful response so resume
    fields match WorkspaceState; identity is required only through reasoning stages.
    """
    _seed_active_mission(brain)
    seen_ids: list[int] = []
    stages = ("knowledge_search", "load_state", "assemble_prompt", "llm_call")

    for stage_name in stages:
        original = getattr(brain.pipeline, f"_stage_{stage_name}")

        def make_wrapper(orig: Any) -> Any:
            def wrapper(ctx: ThinkContext) -> None:
                assert ctx.mission_context is not None
                seen_ids.append(id(ctx.mission_context))
                orig(ctx)

            return wrapper

        setattr(brain.pipeline, f"_stage_{stage_name}", make_wrapper(original))

    brain.think("Vérifier le partage du contexte mission")

    assert len(seen_ids) == len(stages)
    assert len(set(seen_ids)) == 1
    assert brain.last_think_context is not None
    assert brain.last_think_context.mission_context is not None
    assert (
        brain.last_think_context.mission_context.active_mission == "Mission Awareness"
    )


def test_prompt_builder_includes_mission_section() -> None:
    """Prompt assembly must include the concise Current Mission block when active."""
    mission_context = MissionContext(
        active_mission="Ship Phase 14.3",
        status="RUNNING",
        progress=0.5,
        priority="HIGH",
        stage="Tests",
    )
    ctx = ThinkContext(
        user_message="Continue.",
        mission_context=mission_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)

    assert "CONTEXTE MISSION" in prompt
    assert "Active Mission:" in prompt
    assert "Ship Phase 14.3" in prompt
    assert "Status:" in prompt
    assert "RUNNING" in prompt
    assert "Progress:" in prompt
    assert "0.5" in prompt
    assert "Priority:" in prompt
    assert "HIGH" in prompt
    assert "Stage:" in prompt
    assert "Tests" in prompt
    assert "Mission Queue Count:" in prompt
    assert "Paused Mission Count:" in prompt


def test_prompt_unchanged_when_no_active_mission() -> None:
    """Without an active mission, the concise mission section must not appear."""
    baseline = ThinkContext(user_message="Bonjour", state={}, mission={})
    without = ThinkContext(
        user_message="Bonjour",
        state={},
        mission={},
        mission_context=None,
    )
    builder = PromptBuilder()
    assert builder.build(baseline) == builder.build(without)
    assert "CONTEXTE MISSION" not in builder.build(without)
    assert "Active Mission:" not in builder.build(without)
    assert "Current Mission:" not in builder.build(without)


def test_brain_prompt_attaches_mission_from_workspace(brain: Brain) -> None:
    """End-to-end: WorkspaceState mission reaches the assembled LLM prompt."""
    _seed_active_mission(brain)

    brain.think("Avance sur la mission")

    ctx = brain.last_think_context
    assert ctx is not None
    assert "CONTEXTE MISSION" in ctx.prompt
    assert "Mission Awareness" in ctx.prompt
    assert "Wire ThinkContext" in ctx.prompt


def test_brain_prompt_omits_mission_when_workspace_has_none(brain: Brain) -> None:
    """End-to-end: no active WorkspaceState mission leaves prompt without section."""
    brain.state_manager.update(
        active_mission=None,
        active_mission_id=None,
        active_mission_title=None,
        active_mission_status=None,
        active_mission_progress=None,
        active_mission_priority=None,
        active_mission_stage=None,
    )

    brain.think("Simple hello")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.mission_context is None
    assert "CONTEXTE MISSION" not in ctx.prompt
    assert "Current Mission:" not in ctx.prompt


def test_mission_awareness_diagnostics_emitted(
    brain: Brain,
    caplog: Any,
) -> None:
    """MISSION_CONTEXT_* / MISSION_PROMPT_ATTACHED diagnostics must fire."""
    _seed_active_mission(brain)

    with caplog.at_level(logging.INFO):
        brain.think("Diagnostics mission")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("MISSION_CONTEXT_LOADED") for msg in messages)
    assert any(msg.startswith("MISSION_CONTEXT_INJECTED") for msg in messages)
    assert any(msg.startswith("MISSION_PROMPT_ATTACHED") for msg in messages)


def test_no_mission_skips_prompt_attached_log(
    brain: Brain,
    caplog: Any,
) -> None:
    """Without an active mission, MISSION_PROMPT_ATTACHED must not fire."""
    brain.state_manager.update(
        active_mission=None,
        active_mission_id=None,
        active_mission_title=None,
        active_mission_status=None,
        active_mission_progress=None,
        active_mission_priority=None,
        active_mission_stage=None,
    )

    with caplog.at_level(logging.INFO):
        brain.think("Pas de mission")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("MISSION_CONTEXT_LOADED") for msg in messages)
    assert any(msg.startswith("MISSION_CONTEXT_INJECTED") for msg in messages)
    assert not any(msg.startswith("MISSION_PROMPT_ATTACHED") for msg in messages)


def test_agent_context_receives_mission_context(brain: Brain) -> None:
    """Subsystems built from ThinkContext must receive the shared mission slice."""
    _seed_active_mission(brain)
    brain.think("Partager aux agents")
    ctx = brain.last_think_context
    assert ctx is not None

    agent_ctx = AgentContext.from_think_context(ctx, task="Inspect mission")
    assert agent_ctx.mission_context["active_mission"] == "Mission Awareness"
    assert agent_ctx.mission_context["status"] == "RUNNING"
    assert agent_ctx.mission_context["priority"] == "HIGH"
    assert agent_ctx.mission_context["stage"] == "Wire ThinkContext"


def test_mission_context_from_workspace_helper() -> None:
    """MissionContext.from_workspace must read only WorkspaceState fields."""
    empty = WorkspaceState()
    assert MissionContext.from_workspace(empty) is None
    assert MissionContext.from_workspace(None) is None

    active = WorkspaceState(
        active_mission="From State",
        active_mission_id="ws-1",
        active_mission_title="From State",
        active_mission_status="READY",
        active_mission_progress=0.0,
        active_mission_priority="NORMAL",
        active_mission_stage="First step",
    )
    ctx = MissionContext.from_workspace(active)
    assert ctx is not None
    assert ctx.active_mission == "From State"
    assert ctx.stage == "First step"
