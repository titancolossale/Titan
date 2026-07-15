# =====================================
# Titan Executive Function Tests
# =====================================

"""Unit tests for Executive Function V1 — read-only mission priority analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.executive_function import ExecutiveFunction
from brain.llm import LLM
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority, MissionState
from core.mission_runtime import MissionRuntime
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


@pytest.fixture
def runtime(tmp_path: Path) -> MissionRuntime:
    return MissionRuntime(file_path=tmp_path / "titan_mission.json")


@pytest.fixture
def mission_manager(tmp_path: Path) -> MissionManager:
    return MissionManager(file_path=tmp_path / "titan_mission.json")


@pytest.fixture
def memory_service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )


@pytest.fixture
def executive(
    mission_manager: MissionManager,
    memory_service: MemoryService,
) -> ExecutiveFunction:
    state = StateManager(
        file_path=mission_manager.runtime.file_path.parent / "titan_state.json"
    )
    context = ContextManager(
        state_manager=state,
        mission_manager=mission_manager,
    )
    return ExecutiveFunction(
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context,
    )


def _build_brain(tmp_path: Path) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=tmp_path),
        llm=mock_llm,
    )


def test_mission_ranking_by_priority(executive: ExecutiveFunction) -> None:
    runtime = executive._mission_manager.runtime
    low = runtime.create_mission(
        "Low Mission",
        "Low objective",
        ["A"],
        priority=MissionPriority.LOW,
    )
    high = runtime.create_mission(
        "High Mission",
        "High objective",
        ["B"],
        priority=MissionPriority.HIGH,
    )
    critical = runtime.create_mission(
        "Critical Mission",
        "Critical objective",
        ["C"],
        priority=MissionPriority.CRITICAL,
    )
    # Keep focus on low so ranking is not confused with current-focus bias.
    runtime.resume_mission(low.id)

    evaluation = executive.evaluate_missions("status check")
    ranked_ids = [item.mission_id for item in evaluation.ranked_missions]

    assert ranked_ids[0] == critical.id
    assert high.id in ranked_ids
    assert low.id in ranked_ids
    assert evaluation.ranked_missions[0].priority_score > evaluation.ranked_missions[-1].priority_score


def test_blocked_mission_surfaces(executive: ExecutiveFunction) -> None:
    runtime = executive._mission_manager.runtime
    running = runtime.create_mission(
        "Running Work",
        "Keep going",
        ["Step"],
        priority=MissionPriority.NORMAL,
    )
    runtime.update_mission(running.id, state=MissionState.RUNNING)

    blocked = runtime.create_mission(
        "Blocked Work",
        "Needs unblock",
        ["Step"],
        priority=MissionPriority.NORMAL,
    )
    runtime.update_mission(blocked.id, state=MissionState.RUNNING)
    runtime.on_tool_execution_complete(
        mission_id=blocked.id,
        success=False,
        summary_message="Execution failed.",
        completed_tool_steps=0,
        failed_tool_steps=1,
    )
    runtime.resume_mission(running.id)

    evaluation = executive.evaluate_missions("help with blocked work")
    blocked_eval = next(
        item for item in evaluation.ranked_missions if item.mission_id == blocked.id
    )

    assert blocked_eval.is_blocked is True
    assert blocked.id in {item.mission_id for item in evaluation.blocked_missions}
    assert evaluation.ranked_missions[0].mission_id == blocked.id
    assert evaluation.recommendation.should_switch is True
    assert evaluation.recommendation.recommended_mission_id == blocked.id


def test_completed_mission_ignored(executive: ExecutiveFunction) -> None:
    runtime = executive._mission_manager.runtime
    active = runtime.create_mission("Active", "Still open", ["A"])
    done = runtime.create_mission("Done", "Finished", ["B"])
    runtime.complete_mission(done.id)

    evaluation = executive.evaluate_missions("what next")
    ranked_ids = {item.mission_id for item in evaluation.ranked_missions}

    assert active.id in ranked_ids
    assert done.id not in ranked_ids
    assert all(item.state != MissionState.COMPLETED for item in evaluation.ranked_missions)


def test_priority_tie_broken_by_relevance_and_age(
    executive: ExecutiveFunction,
) -> None:
    runtime = executive._mission_manager.runtime
    now = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

    older = runtime.create_mission(
        "Vault Cleanup",
        "Organize notes",
        ["Search"],
        priority=MissionPriority.NORMAL,
    )
    newer = runtime.create_mission(
        "Trading Bot",
        "Automate NQ trading strategy",
        ["Backtest"],
        priority=MissionPriority.NORMAL,
    )

    document = runtime.get_document()
    older_created = (now - timedelta(hours=72)).isoformat()
    newer_created = (now - timedelta(hours=1)).isoformat()
    document["missions"][older.id]["created_at"] = older_created
    document["missions"][older.id]["updated_at"] = older_created
    document["missions"][newer.id]["created_at"] = newer_created
    document["missions"][newer.id]["updated_at"] = newer_created
    runtime._document = document
    runtime._save_document()

    # Equal priority/state: older mission ranks first when the request is neutral.
    age_eval = executive.evaluate_missions("status update", now=now)
    assert age_eval.ranked_missions[0].mission_id == older.id

    # Same priority: user-request relevance breaks the tie toward trading.
    relevance_eval = executive.evaluate_missions(
        "Continue the trading bot NQ strategy",
        now=now,
    )
    assert relevance_eval.ranked_missions[0].mission_id == newer.id
    assert relevance_eval.ranked_missions[0].relevance > (
        relevance_eval.ranked_missions[1].relevance
    )


def test_recommendation_generation(executive: ExecutiveFunction) -> None:
    runtime = executive._mission_manager.runtime
    first = runtime.create_mission(
        "First Focus",
        "Initial work",
        ["A"],
        priority=MissionPriority.LOW,
    )
    second = runtime.create_mission(
        "Second Focus",
        "Urgent trading research",
        ["B"],
        priority=MissionPriority.CRITICAL,
    )
    runtime.resume_mission(first.id)

    recommendation = executive.recommend_focus("urgent trading research")

    assert recommendation.recommended_mission_id == second.id
    assert recommendation.recommended_title == "Second Focus"
    assert recommendation.current_mission_id == first.id
    assert recommendation.should_switch is True
    assert recommendation.priority_score > 0
    assert "switch" in recommendation.reasoning.lower() or "Switching" in recommendation.reasoning


def test_idle_mission_detected(executive: ExecutiveFunction) -> None:
    runtime = executive._mission_manager.runtime
    now = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    mission = runtime.create_mission(
        "Stalled",
        "Waiting forever",
        ["A"],
        priority=MissionPriority.NORMAL,
    )
    runtime.update_mission(mission.id, state=MissionState.WAITING)

    document = runtime.get_document()
    stale = (now - timedelta(hours=30)).isoformat()
    document["missions"][mission.id]["updated_at"] = stale
    document["missions"][mission.id]["created_at"] = stale
    runtime._document = document
    runtime._save_document()

    evaluation = executive.evaluate_missions("anything", now=now)
    idle = next(item for item in evaluation.ranked_missions if item.mission_id == mission.id)

    assert idle.is_idle is True
    assert mission.id in {item.mission_id for item in evaluation.idle_missions}


def test_brain_integration(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    low = brain.create_mission(
        "Keep Focus",
        "Stay here",
        ["A"],
        priority=MissionPriority.LOW,
    )
    high = brain.create_mission(
        "Needs Attention",
        "Trading research",
        ["B"],
        priority=MissionPriority.CRITICAL,
    )
    brain.resume_mission(low.id)

    focus = brain.get_current_focus()
    assert focus is not None
    assert focus.id == low.id

    evaluation = brain.evaluate_missions("trading research")
    assert evaluation.current_mission is not None
    assert evaluation.current_mission.id == low.id
    assert evaluation.ranked_missions
    assert evaluation.recommended_next_mission is not None
    assert evaluation.recommended_next_mission.mission_id == high.id
    assert evaluation.reasoning

    recommendation = brain.recommend_focus("trading research")
    assert recommendation.recommended_mission_id == high.id
    assert recommendation.should_switch is True

    # Read-only: evaluate/recommend must not change active focus.
    assert brain.get_current_focus().id == low.id

    thoughts = brain.generate_thoughts("trading research")
    executive_obs = [
        obs for obs in thoughts.observations if obs.source == "executive_function"
    ]
    assert executive_obs
    executive_thoughts = [
        thought for thought in thoughts.thoughts if thought.source == "executive_function"
    ]
    assert executive_thoughts


def test_evaluate_missions_empty(executive: ExecutiveFunction) -> None:
    evaluation = executive.evaluate_missions("hello")

    assert evaluation.current_mission is None
    assert evaluation.ranked_missions == ()
    assert evaluation.recommendation.recommended_mission_id is None
    assert evaluation.recommendation.should_switch is False
    assert "No active missions" in evaluation.reasoning
