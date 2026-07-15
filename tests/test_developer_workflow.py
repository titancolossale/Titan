# =====================================
# Titan Developer Workflow Tests
# =====================================

"""Unit tests for Developer Workflow V1 — plan-only development assistance."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.developer_workflow import (
    DeveloperWorkflow,
    DeveloperWorkflowPlan,
    WorkflowIntent,
)
from brain.llm import LLM
from brain.workspace_awareness import WorkspaceAwareness
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager


def _write(path: Path, content: str = "# note\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path, *, name: str = "demo") -> Path:
    project = root / name
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", f"# {name}\n")
    _write(project / "CHANGELOG.md", "# Changelog\n")
    (project / "core").mkdir()
    _write(project / "core" / "__init__.py", "")
    _write(project / "core" / "engine.py", "VALUE = 1\n")
    (project / "brain").mkdir()
    _write(project / "brain" / "__init__.py", "")
    _write(project / "brain" / "think.py", "def think():\n    return True\n")
    (project / "tests").mkdir()
    _write(project / "tests" / "test_engine.py", "def test_engine():\n    assert True\n")
    _write(project / "tests" / "test_think.py", "def test_think():\n    assert True\n")
    (project / "docs").mkdir()
    _write(project / "docs" / "ARCHITECTURE.md", "# Architecture\n")
    return project


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
def context_manager(
    tmp_path: Path,
    mission_manager: MissionManager,
) -> ContextManager:
    state = StateManager(file_path=tmp_path / "titan_state.json")
    return ContextManager(state_manager=state, mission_manager=mission_manager)


def _build_workflow(
    tmp_path: Path,
    project: Path,
    *,
    mission_manager: MissionManager | None = None,
    memory_service: MemoryService | None = None,
    context_manager: ContextManager | None = None,
) -> DeveloperWorkflow:
    mission = mission_manager or MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = memory_service or MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    if context_manager is None:
        state = StateManager(file_path=tmp_path / "titan_state.json")
        context_manager = ContextManager(state_manager=state, mission_manager=mission)
    awareness = WorkspaceAwareness(
        workspace_root=project,
        mission_manager=mission,
        memory_service=memory,
        context_manager=context_manager,
    )
    from brain.executive_function import ExecutiveFunction

    executive = ExecutiveFunction(
        mission_manager=mission,
        memory_service=memory,
        context_manager=context_manager,
        workspace_awareness=awareness,
    )
    return DeveloperWorkflow(
        workspace_awareness=awareness,
        executive_function=executive,
        mission_manager=mission,
        memory_service=memory,
        context_manager=context_manager,
    )


def _build_brain(tmp_path: Path, workspace_root: Path | None = None) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    state = StateManager(file_path=tmp_path / "titan_state.json")
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    memory = MemoryService(
        short_term=MemoryManager(),
        long_term=LongTermMemory(file_path=tmp_path / "long_term_memory.json"),
    )
    root = workspace_root or tmp_path
    return Brain(
        agent_manager=AgentManager(memory_service=memory),
        context_manager=ContextManager(state_manager=state, mission_manager=mission),
        state_manager=state,
        mission_manager=mission,
        memory_service=memory,
        tool_manager=ToolManager(project_root=root),
        llm=mock_llm,
    )


def test_workspace_aware_planning(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="DevFlow")
    workflow = _build_workflow(tmp_path, project)

    plan = workflow.plan("Continue Titan development")

    assert isinstance(plan, DeveloperWorkflowPlan)
    assert plan.intent == WorkflowIntent.CONTINUE_DEVELOPMENT
    assert plan.goal
    assert "DevFlow" in plan.context_summary or "Python" in plan.context_summary
    assert plan.relevant_files or plan.recommended_tools
    assert plan.risk_level == RiskLevel.MEDIUM
    assert plan.requires_confirmation is True
    assert plan.to_dict()["intent"] == "continue_development"


def test_relevant_file_detection(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="FileDetect")
    workflow = _build_workflow(tmp_path, project)
    snapshot = workflow._workspace_awareness.refresh(
        open_files=["brain/think.py", "core/engine.py"],
    )

    plan = workflow.plan(
        "Continue development on the brain package",
        workspace=snapshot,
    )

    joined = " ".join(plan.relevant_files).lower().replace("\\", "/")
    assert "brain" in joined or "think.py" in joined
    assert plan.relevant_files


def test_test_recommendation(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="TestRec")
    workflow = _build_workflow(tmp_path, project)

    plan = workflow.plan("Run the relevant tests")

    assert plan.intent == WorkflowIntent.RUN_TESTS
    assert plan.test_plan
    assert any("pytest" in cmd for cmd in plan.recommended_commands)
    assert "terminal" in plan.recommended_tools
    assert plan.risk_level == RiskLevel.LOW
    assert plan.requires_confirmation is False


def test_git_related_request(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="GitFlow")
    workflow = _build_workflow(tmp_path, project)

    plan = workflow.plan("Check what changed")

    assert plan.intent == WorkflowIntent.CHECK_CHANGES
    assert any("git status" in cmd for cmd in plan.recommended_commands)
    assert any("git diff" in cmd for cmd in plan.recommended_commands)
    assert "terminal" in plan.recommended_tools or "github" in plan.recommended_tools
    assert plan.risk_level == RiskLevel.SAFE
    assert plan.requires_confirmation is False


def test_mission_related_request(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_python_project(tmp_path, name="MissionFlow")
    mission_manager.runtime.create_mission(
        "Brain package hardening",
        "Improve brain module reliability and tests",
        ["Audit brain modules", "Add regression tests"],
        priority=MissionPriority.HIGH,
    )
    workflow = _build_workflow(
        tmp_path,
        project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )

    plan = workflow.plan("Prepare the next implementation sprint")

    assert plan.intent == WorkflowIntent.PREPARE_SPRINT
    assert plan.mission_context is not None
    assert "Brain" in plan.mission_context or "hardening" in plan.mission_context.lower()
    assert plan.next_steps
    assert plan.risk_level == RiskLevel.MEDIUM
    assert plan.requires_confirmation is True


def test_risk_level_classification(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="RiskFlow")
    workflow = _build_workflow(tmp_path, project)

    safe = workflow.plan("Summarize the current codebase state")
    medium = workflow.plan("Find what needs to be fixed")
    high = workflow.plan("Deploy to production and git push")

    assert safe.intent == WorkflowIntent.SUMMARIZE_CODEBASE
    assert safe.risk_level == RiskLevel.SAFE
    assert safe.requires_confirmation is False

    assert medium.intent == WorkflowIntent.FIND_FIXES
    assert medium.risk_level == RiskLevel.MEDIUM
    assert medium.requires_confirmation is True

    assert high.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert high.requires_confirmation is True


def test_plan_does_not_execute_or_mutate_missions(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_python_project(tmp_path, name="Readonly")
    mission = mission_manager.runtime.create_mission(
        "Stable mission",
        "Must not change during planning",
        ["Step one"],
        priority=MissionPriority.NORMAL,
    )
    before_state = mission.state
    workflow = _build_workflow(
        tmp_path,
        project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )

    plan = workflow.plan("Continue Titan development")

    after = mission_manager.runtime.get_mission(mission.id)
    assert after is not None
    assert after.state == before_state
    assert plan.recommended_commands  # advisory only
    assert "Do not execute" in " ".join(plan.next_steps) or any(
        "approval" in step.lower() for step in plan.next_steps
    )


def test_brain_integration(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="BrainDev")
    brain = _build_brain(tmp_path, workspace_root=project)
    brain.create_mission(
        "Developer workflow mission",
        "Ship developer workflow planning",
        ["Plan", "Test", "Document"],
    )

    plan = brain.plan_development_workflow("Continue Titan development")

    assert isinstance(plan, DeveloperWorkflowPlan)
    assert plan.intent == WorkflowIntent.CONTINUE_DEVELOPMENT
    assert plan.goal
    assert plan.context_summary
    assert isinstance(plan.relevant_files, tuple)
    assert isinstance(plan.recommended_tools, tuple)
    assert isinstance(plan.recommended_commands, tuple)
    assert isinstance(plan.test_plan, tuple)
    assert isinstance(plan.risk_level, RiskLevel)
    assert isinstance(plan.next_steps, tuple)
    assert isinstance(plan.requires_confirmation, bool)
    assert plan.format_for_prompt().startswith("DEVELOPER WORKFLOW PLAN")
    assert brain.developer_workflow is not None
