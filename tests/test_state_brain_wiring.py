# =====================================
# Titan StateManager ↔ Brain Wiring Tests
# =====================================

"""Phase 13.2 — StateManager connected to Brain.think() lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain.brain import Brain
from brain.pipeline.context_bundle import ThinkContext
from core.state_manager import StateManager, WorkspaceState


def test_workspace_state_loaded_before_pipeline_execution(brain: Brain) -> None:
    """StateManager.load() must run before any pipeline stage sees the context."""
    order: list[str] = []
    original_load = brain.state_manager.load
    original_first = brain.pipeline._stage_knowledge_search

    def tracking_load() -> WorkspaceState:
        order.append("load")
        return original_load()

    def tracking_first_stage(ctx: ThinkContext) -> None:
        order.append("first_stage")
        assert ctx.workspace_state is not None
        assert isinstance(ctx.workspace_state, WorkspaceState)
        original_first(ctx)

    brain.state_manager.load = tracking_load  # type: ignore[method-assign]
    brain.pipeline._stage_knowledge_search = tracking_first_stage  # type: ignore[method-assign]

    brain.think("Bonjour")

    assert order[0] == "load"
    assert order[1] == "first_stage"


def test_workspace_state_survives_whole_brain_request(brain: Brain) -> None:
    """Request-scoped WorkspaceState must remain on ThinkContext through the turn."""
    brain.state_manager.update(
        current_goal="Survivre toute la requête",
        brain_mode="focused",
    )

    brain.think("Bonjour")

    ctx = brain.last_think_context
    assert ctx is not None
    assert ctx.workspace_state is not None
    assert ctx.workspace_state.current_goal == "Survivre toute la requête"
    assert ctx.workspace_state.brain_mode == "focused"
    assert ctx.workspace_state.conversation_state["last_user_message"] == "Bonjour"
    assert ctx.workspace_state.conversation_state["last_titan_response"] == (
        "Réponse de test."
    )


def test_pipeline_stages_receive_same_workspace_state_object(brain: Brain) -> None:
    """Every stage must see the identical WorkspaceState instance (no duplicates)."""
    seen_ids: list[int] = []
    stages = ("knowledge_search", "load_state", "llm_call", "update_state")

    for stage_name in stages:
        original = getattr(brain.pipeline, f"_stage_{stage_name}")

        def make_wrapper(orig: Any) -> Any:
            def wrapper(ctx: ThinkContext) -> None:
                assert ctx.workspace_state is not None
                seen_ids.append(id(ctx.workspace_state))
                orig(ctx)

            return wrapper

        setattr(brain.pipeline, f"_stage_{stage_name}", make_wrapper(original))

    brain.think("Test identité d'objet")

    assert len(seen_ids) == len(stages)
    assert len(set(seen_ids)) == 1
    assert brain.last_think_context is not None
    assert id(brain.last_think_context.workspace_state) == seen_ids[0]


def test_workspace_state_saved_after_brain_finishes(
    brain: Brain,
    tmp_path: Path,
) -> None:
    """Mutations on ctx.workspace_state must be persisted after think() returns.

    Phase 18.1 — ExecutionEngine may update next_action / current_focus from the
    Decision selection; this test stamps a field Execution does not own.
    """
    original_load_state = brain.pipeline._stage_load_state

    def mutate_during_load(ctx: ThinkContext) -> None:
        assert ctx.workspace_state is not None
        ctx.workspace_state.brain_mode = "thinking"
        ctx.workspace_state.progress = "Phase 13.2 wiring"
        ctx.workspace_state.important_decisions = ["persist-marker"]
        original_load_state(ctx)

    brain.pipeline._stage_load_state = mutate_during_load  # type: ignore[method-assign]

    brain.think("Persiste cet état")

    reloaded = StateManager(file_path=tmp_path / "titan_state.json")
    snap = reloaded.snapshot()
    assert snap.brain_mode in ("thinking", "working")
    assert snap.progress == "Phase 13.2 wiring"
    assert "persist-marker" in list(snap.important_decisions or [])
    assert snap.conversation_state["last_user_message"] == "Persiste cet état"
    assert snap.conversation_state["last_titan_response"] == "Réponse de test."


def test_state_load_and_save_diagnostics_emitted(
    brain: Brain,
    caplog: Any,
) -> None:
    """Lightweight STATE_LOAD_* / STATE_SAVE_* diagnostics must be emitted."""
    import logging

    with caplog.at_level(logging.INFO, logger="brain.brain"):
        brain.think("Diagnostics état")

    messages = [record.getMessage() for record in caplog.records]
    assert any(msg.startswith("STATE_LOAD_BEGIN") for msg in messages)
    assert any(msg.startswith("STATE_LOAD_DONE") for msg in messages)
    assert any(msg.startswith("STATE_SAVE_BEGIN") for msg in messages)
    assert any(msg.startswith("STATE_SAVE_DONE") for msg in messages)
