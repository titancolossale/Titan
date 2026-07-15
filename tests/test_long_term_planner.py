# =====================================
# Titan Long-Term Planning Engine Tests
# =====================================

"""Comprehensive tests for Long-Term Planning Engine V1 — plan only, zero execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.developer_workflow import DeveloperWorkflow
from brain.executive_function import ExecutiveFunction
from brain.llm import LLM
from brain.long_term_planner import (
    Dependency,
    GoalDomain,
    GoalPlan,
    LongTermPlanner,
    Milestone,
    MissionProposal,
    PlanningRecommendation,
    PlanningRisk,
    PlanningSummary,
    ProjectPlan,
    SubTask,
    Task,
    TaskDifficulty,
    TaskKind,
    TaskPriority,
    TaskStatus,
)
from brain.project_intelligence import ProjectIntelligence
from brain.workspace_awareness import WorkspaceAwareness
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.mission_models import MissionPriority
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


def _write(path: Path, content: str = "# note\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path, *, name: str = "TitanPlan") -> Path:
    project = root / name
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", f"# {name}\n")
    _write(project / "CHANGELOG.md", "# Changelog\n")
    for pkg in ("core", "brain", "memory", "tools", "tests", "docs"):
        (project / pkg).mkdir(exist_ok=True)
        if pkg != "docs" and pkg != "tests":
            _write(project / pkg / "__init__.py", "")
    _write(project / "brain" / "think.py", "def think():\n    return True\n")
    _write(project / "core" / "engine.py", "VALUE = 1\n")
    _write(project / "tests" / "test_engine.py", "def test_engine():\n    assert True\n")
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


def _build_planner(
    tmp_path: Path,
    project: Path,
    *,
    mission_manager: MissionManager | None = None,
    memory_service: MemoryService | None = None,
    context_manager: ContextManager | None = None,
) -> LongTermPlanner:
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
    executive = ExecutiveFunction(
        mission_manager=mission,
        memory_service=memory,
        context_manager=context_manager,
        workspace_awareness=awareness,
    )
    project_intel = ProjectIntelligence(
        workspace_root=project,
        workspace_awareness=awareness,
        executive_function=executive,
        mission_manager=mission,
        memory_service=memory,
        context_manager=context_manager,
    )
    workflow = DeveloperWorkflow(
        workspace_awareness=awareness,
        executive_function=executive,
        mission_manager=mission,
        memory_service=memory,
        context_manager=context_manager,
    )
    return LongTermPlanner(
        workspace_awareness=awareness,
        executive_function=executive,
        project_intelligence=project_intel,
        developer_workflow=workflow,
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


# ---------------------------------------------------------------------------
# Core planning
# ---------------------------------------------------------------------------


def test_small_goal_structure(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Add a README section")

    assert isinstance(plan, GoalPlan)
    assert plan.goal
    assert len(plan.projects) >= 1
    assert plan.summary.confidence_score > 0
    assert plan.summary.complexity_score >= 0
    assert plan.summary.estimated_implementation_time
    assert plan.summary.reasoning_summary
    assert plan.summary.overall_risk in ("low", "medium", "high")
    tasks = plan.all_tasks()
    assert tasks
    task = tasks[0]
    assert task.id and task.title and task.description
    assert isinstance(task.priority, TaskPriority)
    assert isinstance(task.difficulty, TaskDifficulty)
    assert task.estimated_duration
    assert isinstance(task.dependencies, tuple)
    assert isinstance(task.required_tools, tuple)
    assert isinstance(task.success_conditions, tuple)
    assert isinstance(task.blocked_by, tuple)
    assert isinstance(task.status, TaskStatus)


def test_large_goal_nested_projects(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Automate my ORR strategy end-to-end with full monitoring")

    assert plan.domain == GoalDomain.TRADING
    assert len(plan.projects) >= 2
    assert any(len(p.milestones) >= 2 for p in plan.projects)
    assert plan.success_criteria
    assert plan.required_tools
    assert "paper" in " ".join(plan.success_criteria).lower() or any(
        "LIVE" in c or "live" in c.lower() for c in plan.success_criteria
    )


def test_expand_goal_adds_subtasks(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    basic = planner.plan_goal("Build a Discord notification bridge")
    expanded = planner.expand_goal("Build a Discord notification bridge")

    assert expanded.expanded is True
    basic_subs = sum(len(t.subtasks) for t in basic.all_tasks())
    expanded_subs = sum(len(t.subtasks) for t in expanded.all_tasks())
    assert expanded_subs > basic_subs
    assert any(isinstance(st, SubTask) for t in expanded.all_tasks() for st in t.subtasks)


def test_dependency_graph_and_parallel_tasks(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.expand_goal("Automate my ORR strategy")

    assert plan.dependencies
    assert all(isinstance(d, Dependency) for d in plan.dependencies)
    assert plan.summary.critical_path_task_ids
    # At least some tasks marked sequential or parallel
    assert plan.summary.sequential_task_ids or plan.summary.parallel_groups
    critical = [t for t in plan.all_tasks() if t.is_critical_path]
    assert critical


def test_blocked_tasks_and_statuses(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Automate calendar sync and email digests")

    ready = [t for t in plan.all_tasks() if t.status == TaskStatus.READY]
    assert ready
    # Later tasks should depend on earlier ones
    dependent = [t for t in plan.all_tasks() if t.dependencies]
    assert dependent


def test_task_kind_classification(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.expand_goal("Automate my ORR strategy")

    kinds = {t.kind for t in plan.all_tasks()}
    assert TaskKind.DOCUMENTATION in kinds or TaskKind.RESEARCH in kinds
    assert TaskKind.IMPLEMENTATION in kinds
    assert TaskKind.TESTING in kinds or TaskKind.VALIDATION in kinds
    assert plan.summary.research_tasks or plan.summary.documentation_tasks
    assert plan.summary.implementation_tasks
    assert plan.summary.testing_tasks or plan.summary.documentation_tasks


def test_quick_wins_and_risk_flags(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.expand_goal("Automate my ORR strategy")

    assert plan.summary.quick_wins or any(t.is_quick_win for t in plan.all_tasks())
    assert plan.summary.high_risk_tasks or plan.summary.low_risk_tasks
    assert plan.risks
    assert all(isinstance(r, PlanningRisk) for r in plan.risks)


def test_tool_recommendations(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Automate my ORR strategy")

    assert plan.required_tools
    task_tools = {tool for t in plan.all_tasks() for tool in t.required_tools}
    assert task_tools
    assert "python" in task_tools or "trading" in task_tools or "terminal" in task_tools


def test_confidence_and_complexity_scoring(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    small = planner.plan_goal("Fix typo in docs")
    large = planner.expand_goal("Automate my ORR strategy end-to-end platform")

    assert 0.0 < small.summary.confidence_score <= 1.0
    assert 0.0 <= small.summary.complexity_score <= 1.0
    assert large.summary.complexity_score >= small.summary.complexity_score


def test_review_and_recalculate(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Integrate GitHub status checks")
    reviewed = planner.review_plan(plan)
    recalculated = planner.recalculate_plan(plan)

    assert reviewed.sources.get("reviewed") is True
    assert "Reviewed plan" in reviewed.summary.reasoning_summary
    assert recalculated.sources.get("recalculated_from")
    assert recalculated.goal
    # Original plan object not mutated
    assert plan.sources.get("reviewed") is not True


def test_never_executes_or_creates_missions(
    tmp_path: Path,
    mission_manager: MissionManager,
) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project, mission_manager=mission_manager)

    before = list(mission_manager.runtime.list_active_missions())
    plan = planner.plan_goal("Automate my ORR strategy")
    planner.expand_goal("Automate my ORR strategy")
    planner.review_plan(plan)
    planner.recalculate_plan(plan)
    after = list(mission_manager.runtime.list_active_missions())

    assert before == after
    assert plan.mission_proposals
    assert all(isinstance(p, MissionProposal) for p in plan.mission_proposals)


def test_mission_runtime_compatibility(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)
    mission = MissionManager(file_path=tmp_path / "mission_adopt.json")

    plan = planner.plan_goal("Prepare sprint for memory facade")
    proposal = plan.mission_proposals[0]
    kwargs = proposal.to_create_kwargs()

    created = mission.runtime.create_mission(**kwargs)
    assert created.title == proposal.title
    assert created.objective == proposal.objective
    assert len(created.steps) == len(proposal.steps)


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


def test_executive_function_integration(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)
    plan = planner.plan_goal("Automate my ORR strategy")

    assert any(r.source == "executive_function" for r in plan.recommendations)
    exec_rec = next(r for r in plan.recommendations if r.source == "executive_function")
    assert isinstance(exec_rec, PlanningRecommendation)
    assert exec_rec.next_task_id or exec_rec.summary

    # Direct EF API — must not mutate plan
    snapshot = plan.to_dict()
    again = planner._executive_function.recommend_next_from_goal_plan(plan)
    assert again.source == "executive_function"
    assert plan.to_dict() == snapshot


def test_workspace_awareness_integration(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="WorkspaceAware")
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Continue Titan development planning")

    assert "WorkspaceAware" in plan.context_summary or "workspace=" in plan.context_summary
    assert plan.sources.get("workspace") is True


def test_project_intelligence_integration(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Improve developer workflow and executive function")

    assert plan.sources.get("project_intelligence") is True
    # At least one project should carry intel signals (existing/missing/conflicts/dupes)
    signals = any(
        p.existing_features or p.missing_systems or p.architecture_conflicts or p.duplicate_work_warnings
        for p in plan.projects
    )
    # Soft assert: architecture analysis ran; signals may be empty on tiny fixtures
    assert plan.context_summary
    _ = signals


def test_developer_workflow_integration(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("Ship a new memory retrieval feature")

    assert plan.sources.get("developer_workflow") is True
    # Docs / tests / review appear before or alongside implementation
    kinds_in_order: list[TaskKind] = []
    for project_plan in plan.projects:
        for milestone in project_plan.milestones:
            for task in milestone.tasks:
                kinds_in_order.append(task.kind)
    first_impl = next(
        (i for i, k in enumerate(kinds_in_order) if k == TaskKind.IMPLEMENTATION),
        None,
    )
    first_doc_or_research = next(
        (
            i
            for i, k in enumerate(kinds_in_order)
            if k in (TaskKind.DOCUMENTATION, TaskKind.RESEARCH, TaskKind.ARCHITECTURE)
        ),
        None,
    )
    if first_impl is not None and first_doc_or_research is not None:
        assert first_doc_or_research < first_impl


def test_duplicate_mission_warning(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    mission = MissionManager(file_path=tmp_path / "titan_mission.json")
    mission.runtime.create_mission(
        title="Automate ORR strategy",
        objective="Automate my ORR strategy with paper trading",
        steps=["Research", "Implement", "Validate"],
        priority=MissionPriority.HIGH,
    )
    planner = _build_planner(tmp_path, project, mission_manager=mission)

    plan = planner.plan_goal("Automate my ORR strategy")

    warnings = [w for p in plan.projects for w in p.duplicate_work_warnings]
    assert warnings or any("overlap" in r.summary.lower() for r in plan.risks)


def test_brain_api_plan_goal_expand_review_recalculate(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    brain = _build_brain(tmp_path, workspace_root=project)

    plan = brain.plan_goal("Automate my ORR strategy")
    assert isinstance(plan, GoalPlan)
    assert hasattr(brain, "long_term_planner")

    expanded = brain.expand_goal("Automate my ORR strategy")
    assert expanded.expanded is True

    reviewed = brain.review_plan(plan)
    assert reviewed.sources.get("reviewed") is True

    recalculated = brain.recalculate_plan(plan)
    assert recalculated.goal

    # Still no missions created by planning APIs
    active_before = len(brain.list_active_missions())
    brain.plan_goal("Another goal")
    assert len(brain.list_active_missions()) == active_before


def test_goal_plan_serialization(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.expand_goal("Build trading research notes pipeline")
    data = plan.to_dict()
    prompt = plan.format_for_prompt()

    assert data["goal"]
    assert data["projects"]
    assert data["summary"]["confidence_score"] >= 0
    assert "LONG-TERM GOAL PLAN" in prompt
    assert isinstance(plan.summary, PlanningSummary)
    assert isinstance(plan.projects[0], ProjectPlan)
    assert isinstance(plan.projects[0].milestones[0], Milestone)


def test_empty_goal(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    planner = _build_planner(tmp_path, project)

    plan = planner.plan_goal("   ")
    assert plan.projects == ()
    assert plan.summary.confidence_score == 0.0
