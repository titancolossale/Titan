# =====================================
# Titan Code Intelligence Tests
# =====================================

"""Unit tests for Code Intelligence V1 — semantic code analysis only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.code_intelligence import (
    CallGraph,
    ClassSummary,
    CodeIntelligence,
    FunctionSummary,
    ModuleSummary,
    SymbolLocation,
    UnusedCandidate,
)
from brain.llm import LLM
from brain.workspace_awareness import WorkspaceAwareness
from context.context_manager import ContextManager
from core.mission_manager import MissionManager
from core.state_manager import StateManager
from memory.long_term_memory import LongTermMemory
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from tools.tool_manager import ToolManager


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_code_sample(root: Path) -> Path:
    """Small Python package with classes, calls, and an unused helper."""
    project = root / "CodeSample"
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")

    pkg = project / "sample"
    pkg.mkdir()
    _write(pkg / "__init__.py", "")

    _write(
        pkg / "planner.py",
        '''\
"""Planner module for execution plans."""

from sample.runtime import RuntimeEngine


class ToolExecutionPlan:
    """Structured plan for tool execution."""

    def __init__(self, steps: list[str]) -> None:
        self.steps = steps

    def validate(self) -> bool:
        """Return True when the plan has steps."""
        return bool(self.steps)


class ToolManager:
    """Facade that runs execution plans."""

    def __init__(self, engine: RuntimeEngine) -> None:
        self.engine = engine

    def execute(self, plan: ToolExecutionPlan) -> str:
        """Execute a validated plan via the runtime engine."""
        if not plan.validate():
            return "empty"
        return self.engine.run(plan)


def execute_request(message: str, manager: ToolManager) -> str:
    """Build a plan and execute it through ToolManager."""
    plan = ToolExecutionPlan([message])
    return manager.execute(plan)


def _orphan_helper(x: int) -> int:
    """Private helper never called."""
    return x + 1
''',
    )

    _write(
        pkg / "runtime.py",
        '''\
"""Runtime engine."""


class RuntimeEngine:
    """Runs plans."""

    def run(self, plan) -> str:
        """Run all plan steps."""
        return "|".join(plan.steps)


def unused_public() -> None:
    """Public function with no callers."""
    return None
''',
    )

    _write(
        pkg / "brain_like.py",
        '''\
"""Brain-like conductor."""

from sample.planner import ToolManager, execute_request


class Brain:
    """Central orchestrator."""

    def __init__(self, manager: ToolManager) -> None:
        self.manager = manager

    def think(self, message: str) -> str:
        """Single cognitive entry point."""
        return execute_request(message, self.manager)
''',
    )
    return project


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    return _make_code_sample(tmp_path)


@pytest.fixture
def intelligence(sample_project: Path) -> CodeIntelligence:
    awareness = WorkspaceAwareness(workspace_root=sample_project)
    return CodeIntelligence(workspace_awareness=awareness)


def _build_brain(tmp_path: Path, workspace_root: Path) -> Brain:
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
        tool_manager=ToolManager(project_root=workspace_root),
        llm=mock_llm,
    )


# --- function explanation -------------------------------------------------


def test_function_explanation(intelligence: CodeIntelligence) -> None:
    summary = intelligence.explain_function("execute_request")

    assert isinstance(summary, FunctionSummary)
    assert summary.name == "execute_request"
    assert summary.file_path.endswith("planner.py")
    assert "plan" in summary.purpose.lower() or "ToolManager" in summary.purpose
    assert "message" in summary.parameters
    assert summary.confidence >= 0.5
    assert summary.format_for_prompt().startswith("FUNCTION:")

    think = intelligence.explain_function("Brain.think")
    assert think.name == "think"
    assert think.is_method
    assert think.class_name == "Brain"
    assert "execute_request" in think.calls or any(
        "execute_request" in c for c in think.calls
    )


# --- class explanation ----------------------------------------------------


def test_class_explanation(intelligence: CodeIntelligence) -> None:
    summary = intelligence.explain_class("ToolManager")

    assert isinstance(summary, ClassSummary)
    assert summary.name == "ToolManager"
    assert "execute" in summary.methods
    assert summary.confidence >= 0.5
    assert "Facade" in summary.purpose or "execute" in summary.purpose.lower()
    assert summary.format_for_prompt().startswith("CLASS:")

    plan = intelligence.explain_class("ToolExecutionPlan")
    assert plan.name == "ToolExecutionPlan"
    assert "validate" in plan.methods


# --- call graph -----------------------------------------------------------


def test_call_graph(intelligence: CodeIntelligence) -> None:
    graph = intelligence.find_callers("execute")

    assert isinstance(graph, CallGraph)
    assert graph.root
    assert graph.format_for_prompt().startswith("CALL GRAPH")
    # execute_request calls manager.execute → static callee "execute"
    # and/or Brain.think → execute_request chain
    assert len(graph.callers) >= 1 or "execute" in graph.root.lower()

    req_graph = intelligence.find_callers("execute_request")
    caller_names = " ".join(c.qualified_name for c in req_graph.callers)
    assert "think" in caller_names or any(
        "think" in c.qualified_name for c in req_graph.callers
    )


# --- symbol lookup --------------------------------------------------------


def test_symbol_lookup(intelligence: CodeIntelligence) -> None:
    locs = intelligence.find_symbol("ToolExecutionPlan")

    assert locs
    assert all(isinstance(loc, SymbolLocation) for loc in locs)
    assert any(loc.kind == "class" for loc in locs)
    assert any("planner.py" in loc.file_path for loc in locs)

    execute_locs = intelligence.find_symbol("execute_request")
    assert any(loc.kind == "function" for loc in execute_locs)


# --- module summary -------------------------------------------------------


def test_module_summary(intelligence: CodeIntelligence) -> None:
    summary = intelligence.summarize_module("planner.py")

    assert isinstance(summary, ModuleSummary)
    assert "ToolManager" in summary.classes
    assert "execute_request" in summary.functions
    assert summary.class_count >= 2
    assert summary.function_count >= 1
    assert summary.imports
    assert summary.format_for_prompt().startswith("MODULE SUMMARY:")

    by_path = intelligence.summarize_module("sample/planner.py")
    assert "ToolManager" in by_path.classes


# --- unused detection -----------------------------------------------------


def test_unused_detection(intelligence: CodeIntelligence) -> None:
    candidates = intelligence.find_unused_candidates()

    assert isinstance(candidates, tuple)
    assert all(isinstance(c, UnusedCandidate) for c in candidates)
    names = {c.name for c in candidates}
    assert "_orphan_helper" in names or "unused_public" in names
    # Used entry points should not dominate as high-confidence unused
    high = [c for c in candidates if c.name == "execute_request" and c.confidence >= 0.5]
    assert not high


# --- modification impact --------------------------------------------------


def test_modification_impact(intelligence: CodeIntelligence) -> None:
    impact = intelligence.estimate_modification_impact("execute_request")
    assert impact["target"]
    assert impact["kind"] == "function"
    assert impact["caller_count"] >= 1
    assert impact["impact"] in {"low", "medium", "high", "unknown"}


# --- analysis-only / empty queries ----------------------------------------


def test_empty_queries(intelligence: CodeIntelligence) -> None:
    assert intelligence.explain_function("").confidence == 0.0
    assert intelligence.explain_class("").confidence == 0.0
    assert intelligence.find_symbol("") == ()
    assert intelligence.find_callers("").root == ""
    assert intelligence.summarize_module("").confidence == 0.0


# --- brain integration ----------------------------------------------------


def test_brain_integration(tmp_path: Path, sample_project: Path) -> None:
    brain = _build_brain(tmp_path, sample_project)

    assert isinstance(brain.code_intelligence, CodeIntelligence)

    fn = brain.explain_function("execute_request")
    assert isinstance(fn, FunctionSummary)
    assert fn.name == "execute_request"

    cls = brain.explain_class("ToolManager")
    assert isinstance(cls, ClassSummary)
    assert cls.name == "ToolManager"

    locs = brain.find_symbol("ToolExecutionPlan")
    assert locs

    graph = brain.find_callers("execute_request")
    assert isinstance(graph, CallGraph)

    unused = brain.find_unused_candidates()
    assert isinstance(unused, tuple)

    mod = brain.summarize_module("sample/planner.py")
    assert isinstance(mod, ModuleSummary)
    assert "ToolManager" in mod.classes
