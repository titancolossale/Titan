# =====================================
# Titan Mission Progress & Resume Tests
# =====================================

"""Phase 14.4 — mission progress persists and resumes across think cycles."""

from __future__ import annotations

import logging
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import MissionContext, ThinkContext
from brain.prompt_builder import PromptBuilder
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority
from core.state_manager import StateManager, WorkspaceState


def _seed_active_mission(brain: Brain, **overrides: Any) -> None:
    payload = {
        "active_mission": "Progress Resume",
        "active_mission_id": "mission-14-4",
        "active_mission_title": "Progress Resume",
        "active_mission_status": "RUNNING",
        "active_mission_progress": 25.0,
        "active_mission_priority": MissionPriority.HIGH.value,
        "active_mission_stage": "Wire progress",
        "active_mission_last_completed_step": "Foundation",
        "active_mission_last_summary": "Earlier progress note",
        "active_mission_progress_updated_at": "2026-01-01T00:00:00+00:00",
        "active_mission_current_objective": "Wire progress",
    }
    payload.update(overrides)
    brain.state_manager.update(**payload)


def _paired_brain(brain: Brain) -> MissionManager:
    """Bind MissionManager to the Brain StateManager for mirrored lifecycle."""
    brain.mission_manager.bind_state_manager(brain.state_manager)
    return brain.mission_manager


def test_mission_progress_persists_after_think(brain: Brain) -> None:
    """Successful think must stamp resume fields onto WorkspaceState and persist."""
    _seed_active_mission(brain)

    brain.think("Continue la mission")

    snap = brain.state_manager.snapshot()
    assert snap.active_mission_id == "mission-14-4"
    assert snap.active_mission_stage == "Wire progress"
    assert snap.active_mission_progress == 25.0
    assert snap.active_mission_last_completed_step == "Foundation"
    assert snap.active_mission_current_objective == "Wire progress"
    assert snap.active_mission_last_summary
    assert "Réponse de test." in (snap.active_mission_last_summary or "")
    assert snap.active_mission_progress_updated_at is not None
    assert snap.active_mission_progress_updated_at != "2026-01-01T00:00:00+00:00"

    on_disk = brain.state_manager.load()
    assert on_disk.active_mission_last_summary == snap.active_mission_last_summary
    assert on_disk.active_mission_progress_updated_at == (
        snap.active_mission_progress_updated_at
    )


def test_resume_survives_multiple_think_cycles(brain: Brain) -> None:
    """Resume fields from cycle N must load into ThinkContext on cycle N+1."""
    _seed_active_mission(brain)

    brain.think("Premier cycle")
    first = brain.state_manager.snapshot()
    first_summary = first.active_mission_last_summary
    first_updated = first.active_mission_progress_updated_at
    assert first_summary
    assert first_updated

    brain.llm.ask.return_value = "Deuxième réponse de reprise."
    brain.think("Deuxième cycle")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.mission_context is not None
    # Second cycle must have loaded first-cycle resume before updating again.
    assert "MISSION RESUME" in ctx.prompt
    assert "Wire progress" in ctx.prompt
    assert "Previous Progress" in ctx.prompt
    assert "25.0" in ctx.prompt
    assert "Foundation" in ctx.prompt

    snap = brain.state_manager.snapshot()
    assert snap.active_mission_last_summary
    assert "Deuxième réponse" in (snap.active_mission_last_summary or "")
    assert snap.active_mission_progress_updated_at != first_updated


def test_prompt_includes_mission_resume() -> None:
    """PromptBuilder must attach Mission Resume labels when a mission is active."""
    mission_context = MissionContext(
        active_mission="Ship Phase 14.4",
        status="RUNNING",
        progress=50.0,
        priority="HIGH",
        stage="Resume tests",
        last_completed_step="Awareness",
        last_summary="Awareness done",
        progress_updated_at="2026-07-27T12:00:00+00:00",
        current_objective="Resume tests",
    )
    ctx = ThinkContext(
        user_message="Continue.",
        mission_context=mission_context,
        state={},
        mission={},
    )
    prompt = PromptBuilder().build(ctx)

    assert "MISSION RESUME" in prompt
    assert "Mission Resume" in prompt
    assert "Current Stage" in prompt
    assert "Resume tests" in prompt
    assert "Previous Progress" in prompt
    assert "50.0" in prompt
    assert "Last Completed Step" in prompt
    assert "Awareness" in prompt
    assert "Current Objective" in prompt


def test_no_mission_unchanged_prompt_behavior() -> None:
    """Without an active mission, resume section must not appear."""
    baseline = ThinkContext(user_message="Bonjour", state={}, mission={})
    without = ThinkContext(
        user_message="Bonjour",
        state={},
        mission={},
        mission_context=None,
    )
    builder = PromptBuilder()
    assert builder.build(baseline) == builder.build(without)
    assert "MISSION RESUME" not in builder.build(without)
    assert "Mission Resume" not in builder.build(without)
    assert "Current Stage" not in builder.build(without)


def test_brain_prompt_omits_resume_when_no_mission(brain: Brain) -> None:
    """End-to-end: idle WorkspaceState leaves prompt without resume section."""
    brain.state_manager.update(
        active_mission=None,
        active_mission_id=None,
        active_mission_title=None,
        active_mission_status=None,
        active_mission_progress=None,
        active_mission_priority=None,
        active_mission_stage=None,
        active_mission_last_completed_step=None,
        active_mission_last_summary=None,
        active_mission_progress_updated_at=None,
        active_mission_current_objective=None,
    )

    brain.think("Simple hello")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.mission_context is None
    assert "MISSION RESUME" not in ctx.prompt
    assert "Mission Resume" not in ctx.prompt


def test_mission_progress_diagnostics_emitted(
    brain: Brain,
    caplog: Any,
) -> None:
    """MISSION_PROGRESS_UPDATED / RESUME_LOADED / RESUME_INJECTED must fire."""
    _seed_active_mission(brain)

    with caplog.at_level(logging.INFO):
        brain.think("Diagnostics progress")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("MISSION_PROGRESS_UPDATED") for msg in messages)
    assert any(msg.startswith("MISSION_RESUME_LOADED") for msg in messages)
    assert any(msg.startswith("MISSION_RESUME_INJECTED") for msg in messages)


def test_no_mission_skips_progress_and_resume_logs(
    brain: Brain,
    caplog: Any,
) -> None:
    """Without an active mission, progress/resume diagnostics must not fire."""
    brain.state_manager.update(
        active_mission=None,
        active_mission_id=None,
        active_mission_title=None,
        active_mission_status=None,
        active_mission_progress=None,
        active_mission_priority=None,
        active_mission_stage=None,
        active_mission_last_completed_step=None,
        active_mission_last_summary=None,
        active_mission_progress_updated_at=None,
        active_mission_current_objective=None,
    )

    with caplog.at_level(logging.INFO):
        brain.think("Pas de mission")

    messages = [record.getMessage() for record in caplog.records]
    assert not any(msg.startswith("MISSION_PROGRESS_UPDATED") for msg in messages)
    assert not any(msg.startswith("MISSION_RESUME_LOADED") for msg in messages)
    assert not any(msg.startswith("MISSION_RESUME_INJECTED") for msg in messages)


def test_progress_update_from_live_mission(brain: Brain) -> None:
    """Paired MissionManager + think cycle must mirror completed step into resume."""
    missions = _paired_brain(brain)
    mission = missions.create_mission(
        title="Live Progress",
        objective="Prove live resume",
        steps=["Alpha", "Beta", "Gamma"],
    )
    missions.complete_current_step()

    brain.think("Avance encore")

    snap = brain.state_manager.snapshot()
    assert snap.active_mission_id == mission.id
    assert snap.active_mission_last_completed_step == "Alpha"
    assert snap.active_mission_stage == "Beta"
    assert snap.active_mission_current_objective == "Beta"
    assert abs(float(snap.active_mission_progress or 0) - (100.0 / 3.0)) < 0.1
    assert snap.active_mission_last_summary
    assert snap.active_mission_progress_updated_at is not None

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.mission_context is not None
    assert ctx.mission_context.last_completed_step == "Alpha"
    assert ctx.mission_context.stage == "Beta"


def test_mission_context_resume_from_workspace() -> None:
    """MissionContext.from_workspace must expose Phase 14.4 resume fields."""
    active = WorkspaceState(
        active_mission="From State",
        active_mission_id="ws-14-4",
        active_mission_title="From State",
        active_mission_status="RUNNING",
        active_mission_progress=40.0,
        active_mission_priority="NORMAL",
        active_mission_stage="Second",
        active_mission_last_completed_step="First",
        active_mission_last_summary="First done",
        active_mission_progress_updated_at="2026-07-27T18:00:00+00:00",
        active_mission_current_objective="Second",
    )
    ctx = MissionContext.from_workspace(active)
    assert ctx is not None
    assert ctx.last_completed_step == "First"
    assert ctx.last_summary == "First done"
    assert ctx.current_objective == "Second"
    assert ctx.progress_updated_at == "2026-07-27T18:00:00+00:00"


def test_single_state_read_write_for_progress(brain: Brain) -> None:
    """Progress/resume must reuse the existing load/save pair (no extra I/O)."""
    _seed_active_mission(brain)
    load_calls = {"n": 0}
    update_calls = {"n": 0}
    original_load = brain.state_manager.load
    original_update = brain.state_manager.update

    def tracking_load() -> WorkspaceState:
        load_calls["n"] += 1
        return original_load()

    def tracking_update(*args: Any, **kwargs: Any) -> WorkspaceState:
        update_calls["n"] += 1
        return original_update(*args, **kwargs)

    brain.state_manager.load = tracking_load  # type: ignore[method-assign]
    brain.state_manager.update = tracking_update  # type: ignore[method-assign]

    brain.think("Compter les I/O")

    assert load_calls["n"] == 1
    assert update_calls["n"] == 1
