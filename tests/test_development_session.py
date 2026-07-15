# =====================================
# Titan Development Session Runtime Tests
# =====================================

"""Unit tests for Development Session Runtime V1 — track-only session context."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.development_session import (
    DevelopmentSession,
    DevelopmentSessionRuntime,
    SessionState,
    SessionSummary,
)
from brain.llm import LLM
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager


@pytest.fixture
def session_path(tmp_path: Path) -> Path:
    return tmp_path / "development_sessions.json"


@pytest.fixture
def runtime(session_path: Path) -> DevelopmentSessionRuntime:
    return DevelopmentSessionRuntime(file_path=session_path)


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    brain = Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )
    brain.development_session = DevelopmentSessionRuntime(
        file_path=tmp_path / "development_sessions.json",
        workspace_awareness=brain.workspace_awareness,
        executive_function=brain.executive_function,
        mission_manager=brain.mission_manager,
        memory_service=brain.memory_service,
        context_manager=brain.context_manager,
    )
    return brain


def test_lifecycle_start_update_end(runtime: DevelopmentSessionRuntime) -> None:
    session = runtime.start(
        "Auth refactor",
        pending=["Audit auth module", "Add tests"],
        open_modules=["brain", "core"],
    )
    assert session.state == SessionState.ACTIVE
    assert session.feature == "Auth refactor"
    assert len(session.pending_tasks) == 2
    assert "brain" in session.opened_modules

    updated = runtime.update(
        reviewed_files=["brain/brain.py"],
        add_pending=["Document API"],
        note="Started review",
    )
    assert "brain/brain.py" in updated.reviewed_files
    assert len(updated.pending_tasks) == 3
    assert updated.notes == ["Started review"]

    ended = runtime.end()
    assert ended.state == SessionState.ENDED
    assert ended.ended_at is not None
    assert runtime.get_active() is None


def test_pause_resume_and_double_active_rejected(
    runtime: DevelopmentSessionRuntime,
) -> None:
    first = runtime.start("Feature A")
    paused = runtime.pause()
    assert paused.state == SessionState.PAUSED
    assert runtime.get_active() is None

    resumed = runtime.resume()
    assert resumed.session_id == first.session_id
    assert resumed.state == SessionState.ACTIVE
    assert runtime.get_active() is not None

    with pytest.raises(ValueError, match="Active session already exists"):
        runtime.start("Feature B")

    runtime.pause()
    second = runtime.start("Feature B")
    assert second.feature == "Feature B"
    with pytest.raises(ValueError, match="Cannot resume while session"):
        runtime.resume(first.session_id)


def test_summary_counts_and_narrative(runtime: DevelopmentSessionRuntime) -> None:
    runtime.start("Session summary feature", pending=["Step one"])
    runtime.update(
        decision="Use JSON persistence",
        decision_rationale="Matches MissionRuntime pattern",
        plan={"goal": "Ship runtime", "next_steps": ["Write tests", "Update docs"]},
        patch={"plan_request": "add module", "files": [], "edits": []},
        complete_task="Step one",
    )
    summary = runtime.summarize()
    assert isinstance(summary, SessionSummary)
    assert summary.feature == "Session summary feature"
    assert summary.plans_count == 1
    assert summary.patches_count == 1
    assert summary.completed_count == 1
    assert summary.pending_count >= 2
    assert summary.decisions_count == 1
    assert "Session summary feature" in summary.narrative
    assert "Use JSON persistence" in summary.key_decisions
    assert summary.format_for_prompt().startswith("DEVELOPMENT SESSION SUMMARY")


def test_decisions_and_rejected_ideas(runtime: DevelopmentSessionRuntime) -> None:
    runtime.start("Decision tracking")
    runtime.update(
        decision="Keep track-only policy",
        decision_rationale="No autonomous execution",
        reject_idea="Auto-apply patches",
    )
    session = runtime.get_active()
    assert session is not None
    assert len(session.decisions) == 1
    assert session.decisions[0].statement == "Keep track-only policy"
    assert "Auto-apply patches" in session.rejected_ideas
    summary = runtime.summarize()
    assert summary.rejected_ideas_count == 1


def test_pending_completed_move(runtime: DevelopmentSessionRuntime) -> None:
    runtime.start("Tasks", pending=["Implement runtime", "Wire Brain"])
    session = runtime.update(complete_task="Implement runtime")
    assert len(session.completed_tasks) == 1
    assert session.completed_tasks[0].description == "Implement runtime"
    assert all(t.description != "Implement runtime" for t in session.pending_tasks)
    assert any(t.description == "Wire Brain" for t in session.pending_tasks)


def test_persistence_roundtrip(session_path: Path) -> None:
    runtime = DevelopmentSessionRuntime(file_path=session_path)
    session = runtime.start("Persist me", pending=["Keep context"])
    session_id = session.session_id
    runtime.update(reviewed_files=["docs/ARCHITECTURE.md"])
    runtime.pause()

    reloaded = DevelopmentSessionRuntime(file_path=session_path)
    assert reloaded.get_active() is None
    loaded = reloaded.get_session(session_id)
    assert loaded is not None
    assert loaded.state == SessionState.PAUSED
    assert "docs/ARCHITECTURE.md" in loaded.reviewed_files

    resumed = reloaded.resume(session_id)
    assert resumed.state == SessionState.ACTIVE
    assert reloaded.get_active() is not None


def test_plan_and_patch_stored_as_dicts_only(
    runtime: DevelopmentSessionRuntime,
) -> None:
    runtime.start("Artifacts")
    plan = MagicMock()
    plan.to_dict.return_value = {
        "goal": "Ship",
        "next_steps": ["Test"],
        "risk_level": RiskLevel.MEDIUM.value,
    }
    plan.next_steps = ("Test",)
    plan.implementation_steps = None
    plan.checklist = None

    patch = MagicMock()
    patch.to_dict.return_value = {
        "plan_request": "add file",
        "unified_diff_bundle": "diff --git a/x b/x",
        "files": [{"path": "x.py"}],
    }

    session = runtime.update(plan=plan, patch=patch)
    assert len(session.plans) == 1
    assert isinstance(session.plans[0], dict)
    assert session.plans[0]["goal"] == "Ship"
    assert len(session.patches) == 1
    assert isinstance(session.patches[0], dict)
    assert session.patches[0]["_applied"] is False
    assert any(t.description == "Test" for t in session.pending_tasks)


def test_no_tool_execution_side_effects(runtime: DevelopmentSessionRuntime) -> None:
    tool_spy = MagicMock()
    runtime._workspace_awareness = MagicMock()
    runtime._workspace_awareness.refresh = MagicMock(return_value=MagicMock(
        detected_modules=("brain",),
        open_files=("brain/development_session.py",),
    ))
    runtime.start("No exec", open_modules=["brain"])
    runtime.update(
        plan={"next_steps": ["Do not run tools"]},
        patch={"unified_diff_bundle": "should not be applied"},
    )
    # Runtime must never call a tool manager / executor attribute.
    assert not hasattr(runtime, "tool_manager") or runtime.__dict__.get("tool_manager") is None
    tool_spy.assert_not_called()
    session = runtime.get_active()
    assert session is not None
    assert session.patches[0]["_applied"] is False


def test_brain_integration(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    assert isinstance(brain.development_session, DevelopmentSessionRuntime)

    session = brain.start_development_session(
        "Development Session Runtime",
        pending=["Implement", "Test"],
        open_modules=["brain"],
    )
    assert isinstance(session, DevelopmentSession)
    assert session.state == SessionState.ACTIVE

    brain.update_development_session(
        decision="Track only",
        reviewed_files=["brain/development_session.py"],
        plan={"goal": "Ship V1", "next_steps": ["Document"]},
    )
    active = brain.get_development_session()
    assert active is not None
    assert len(active.decisions) == 1
    assert len(active.plans) == 1

    summary = brain.summarize_development_session()
    assert isinstance(summary, SessionSummary)
    assert summary.plans_count == 1
    assert "Track only" in summary.key_decisions

    paused = brain.pause_development_session()
    assert paused.state == SessionState.PAUSED
    assert brain.get_development_session() is None

    resumed = brain.resume_development_session()
    assert resumed.state == SessionState.ACTIVE

    ended = brain.end_development_session()
    assert ended.state == SessionState.ENDED
    assert brain.get_development_session() is None


def test_record_to_session_flag_on_workflow(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    brain.start_development_session("Hook test")

    # Without flag — no plan recorded
    brain.plan_development_workflow("Summarize the current codebase state")
    active = brain.get_development_session()
    assert active is not None
    assert active.plans == []

    # With flag — plan recorded when session active
    brain.plan_development_workflow(
        "Summarize the current codebase state",
        record_to_session=True,
    )
    active = brain.get_development_session()
    assert active is not None
    assert len(active.plans) == 1
