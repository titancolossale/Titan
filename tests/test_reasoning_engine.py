# =====================================
# Titan Reasoning Engine Tests
# =====================================

"""Comprehensive tests for Reasoning Engine V1 — analysis only, zero tool execution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.executive_function import ExecutiveFunction
from brain.llm import LLM
from brain.long_term_planner import LongTermPlanner
from brain.reasoning_engine import ReasoningEngine
from brain.reasoning_models import (
    ReasoningDomain,
    ReasoningResult,
    ReasoningUrgency,
)
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


def _make_python_project(root: Path, *, name: str = "TitanReason") -> Path:
    project = root / name
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", f"# {name}\n")
    for pkg in ("core", "brain", "memory", "tools", "tests"):
        (project / pkg).mkdir(exist_ok=True)
        _write(project / pkg / "__init__.py", "")
    _write(
        project / "brain" / "brain.py",
        "class Brain:\n    def think(self):\n        return True\n",
    )
    _write(project / "core" / "engine.py", "VALUE = 1\n")
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


def _build_brain(tmp_path: Path, project: Path | None = None) -> Brain:
    mock_llm = MagicMock(spec=LLM)
    mock_llm.ask.return_value = "Réponse de test."
    root = project or _make_python_project(tmp_path)
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
        tool_manager=ToolManager(project_root=root),
        llm=mock_llm,
    )


def _build_engine(
    tmp_path: Path,
    project: Path,
    *,
    mission_manager: MissionManager | None = None,
    memory_service: MemoryService | None = None,
    context_manager: ContextManager | None = None,
) -> ReasoningEngine:
    """Return a fully wired ReasoningEngine via Brain composition."""
    return _build_brain(tmp_path, project).reasoning_engine


# --- Simple & complex reasoning ---


def test_simple_reasoning_produces_result(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("What is the safest way to implement this feature?")
    assert isinstance(result, ReasoningResult)
    assert result.summary.objective
    assert result.recommendation.strategy
    assert 0.0 <= result.summary.confidence_score <= 1.0
    assert len(result.steps) >= 3


def test_complex_reasoning_decomposes_software_goal(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    engine = _build_engine(tmp_path, project)
    result = engine.reason(
        "Build a new authentication feature with tests and deployment plan"
    )
    assert result.understanding.domain in (
        ReasoningDomain.SOFTWARE,
        ReasoningDomain.PLANNING,
        ReasoningDomain.GENERAL,
    )
    step_titles = {s.title.lower() for s in result.steps}
    assert any("test" in t or "architecture" in t or "dependencies" in t for t in step_titles)


def test_trading_domain_detected(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("Would this affect trading? Analyze the risks.")
    assert result.understanding.domain == ReasoningDomain.TRADING
    assert any("paper" in a.description.lower() for a in result.alternatives)


# --- Alternative generation ---


def test_compare_options_generates_alternatives(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.compare_options("Compare three possible architectures for the API layer")
    assert len(result.alternatives) >= 2
    ranks = [a.rank for a in result.alternatives if a.rank > 0]
    assert ranks == sorted(ranks)


def test_explicit_options_used(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    options = ("Microservices", "Modular monolith", "Serverless")
    result = brain.compare_options("Compare architectures", options=options)
    descriptions = {a.description for a in result.alternatives}
    assert descriptions == set(options)


# --- Risk evaluation ---


def test_risk_evaluation_for_trading(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("Analyze the risks of live trading this strategy")
    assert any("capital" in r.summary.lower() or "paper" in r.mitigation.lower()
               for r in result.risks)


def test_contradiction_request_surfaces_risk(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("Does this contradict my previous decisions?")
    assert any("contradict" in r.summary.lower() for r in result.risks)


# --- Missing information ---


def test_detect_missing_information_short_request(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    questions = brain.detect_missing_information("help")
    assert len(questions) >= 1
    assert any("success" in q.question.lower() for q in questions)


def test_compare_without_options_asks_clarification(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.compare_options("Compare options")
    assert any(q.category == "clarification" for q in result.open_questions) or len(
        result.alternatives
    ) >= 2


# --- Confidence & scoring ---


def test_confidence_scores_in_valid_range(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason(
        "Should I modify the brain module to add structured reasoning capabilities?"
    )
    assert 0.0 <= result.summary.confidence_score <= 1.0
    assert 0.0 <= result.summary.reasoning_quality_score <= 1.0
    assert 0.0 <= result.summary.completeness_score <= 1.0


def test_recommend_strategy_returns_recommendation(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    rec = brain.recommend_strategy("Analyze the risks of refactoring core/engine.py")
    assert rec.strategy
    assert rec.confidence > 0.0


# --- Executive Function integration ---


def test_executive_function_consumes_reasoning_result(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_python_project(tmp_path)
    engine = _build_engine(
        tmp_path,
        project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    executive = ExecutiveFunction(
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    reasoning = engine.reason("Focus on mission priorities for the sprint")
    runtime = mission_manager.runtime
    runtime.create_mission("Sprint A", "Objective A", ["Step 1"], priority=MissionPriority.HIGH)

    evaluation = executive.evaluate_missions(
        "sprint focus",
        reasoning_result=reasoning,
    )
    assert "Reasoning Engine" in evaluation.reasoning
    assert reasoning.recommendation.strategy in evaluation.reasoning


def test_executive_without_reasoning_unchanged(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    executive = ExecutiveFunction(
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    mission_manager.runtime.create_mission("Test", "Obj", ["S"])
    evaluation = executive.evaluate_missions("status")
    assert "Reasoning Engine" not in evaluation.reasoning


# --- Planner integration ---


def test_planner_integration_with_reasoning(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_python_project(tmp_path)
    brain = _build_brain(tmp_path, project)
    plan = brain.plan_goal("Ship authentication feature with tests and documentation")
    assert plan.sources.get("reasoning_engine") is True
    assert "reasoning=" in plan.context_summary or plan.context_summary != "no external context"
    assert any(
        "Reasoning Engine" in r.rationale for r in plan.recommendations
    )


def test_long_term_planner_reasoning_enriches_recommendations(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_python_project(tmp_path)
    engine = _build_engine(
        tmp_path,
        project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    from brain.executive_function import ExecutiveFunction
    from brain.project_intelligence import ProjectIntelligence
    from brain.developer_workflow import DeveloperWorkflow

    awareness = WorkspaceAwareness(
        workspace_root=project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    executive = ExecutiveFunction(
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
        workspace_awareness=awareness,
    )
    project_intel = ProjectIntelligence(
        workspace_awareness=awareness,
        executive_function=executive,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    workflow = DeveloperWorkflow(
        workspace_awareness=awareness,
        executive_function=executive,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    planner = LongTermPlanner(
        workspace_awareness=awareness,
        executive_function=executive,
        project_intelligence=project_intel,
        developer_workflow=workflow,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    reasoning = engine.reason("Plan a multi-week software release")
    plan = planner.plan_goal(
        "Plan a multi-week software release",
        reasoning_result=reasoning,
    )
    assert plan.sources["reasoning_engine"] is True


# --- Serialization ---


def test_reasoning_result_serializable(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("Explain module brain and its dependencies")
    payload = result.to_dict()
    serialized = json.dumps(payload)
    parsed = json.loads(serialized)
    assert parsed["summary"]["domain"]
    assert parsed["recommendation"]["strategy"]
    assert isinstance(parsed["alternatives"], list)
    assert isinstance(parsed["open_questions"], list)


def test_format_for_prompt_non_empty(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("Analyze risks before modifying Brain")
    text = result.format_for_prompt()
    assert "RAISONNEMENT STRUCTURÉ" in text
    assert result.recommendation.strategy in text


# --- Brain APIs ---


def test_brain_evaluate_request_alias(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.evaluate_request("Should I modify this module?")
    assert isinstance(result, ReasoningResult)


def test_brain_reason_about_project(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    brain = _build_brain(tmp_path, project)
    result = brain.reason_about_project("How should we structure the brain layer?")
    assert result.understanding.domain == ReasoningDomain.ARCHITECTURE


# --- Project Intelligence reuse ---


def test_project_intelligence_used_in_context(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    engine = _build_engine(tmp_path, project)
    result = engine.reason("Analyze project architecture for the brain module")
    assert result.context_sources.get("project_intelligence") is True


# --- Code Intelligence reuse ---


def test_code_intelligence_used_for_module_query(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    engine = _build_engine(tmp_path, project)
    result = engine.reason("Explain module brain and summarize class Brain")
    assert result.context_sources.get("code_intelligence") is True


# --- Tool recommendation (no execution) ---


def test_tool_recommendation_without_execution(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    with patch.object(
        brain.tool_execution_engine,
        "execute",
        side_effect=AssertionError("Reasoning must not execute tools"),
    ):
        result = brain.reason("Search the web for Python best practices")
    assert isinstance(result.recommended_tools, tuple)


def test_reasoning_engine_never_calls_tool_execution_engine(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path)
    engine = _build_engine(tmp_path, project)
    with patch(
        "brain.tool_execution_engine.ToolExecutionEngine.execute",
        side_effect=AssertionError("must not execute"),
    ):
        engine.reason("Find tools for file reading and web search")


# --- NLO integration ---


def test_nlo_runs_reasoning_in_awareness(tmp_path: Path) -> None:
    from brain.natural_language_orchestrator import SystemName

    brain = _build_brain(tmp_path)
    result = brain.process_request("What is the safest way to implement caching?")
    assert "reasoning" in result.artifacts
    assert SystemName.REASONING_ENGINE in result.systems_used.invoked


def test_nlo_reasoning_summary_enriched(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.process_request("Compare two approaches for memory retrieval")
    assert "Reasoning:" in result.reasoning_summary or "reasoning" in result.artifacts


# --- Urgency detection ---


def test_urgency_critical_detected(tmp_path: Path) -> None:
    brain = _build_brain(tmp_path)
    result = brain.reason("This is critical — fix the bug immediately")
    assert result.understanding.urgency == ReasoningUrgency.CRITICAL
