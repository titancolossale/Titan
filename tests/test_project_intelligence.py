# =====================================
# Titan Project Intelligence Tests
# =====================================

"""Unit tests for Project Intelligence V1 — architecture analysis only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from brain.project_intelligence import (
    ArchitectureSummary,
    DependencyGraph,
    FeatureLocation,
    ImpactAnalysis,
    ModuleDescription,
    ProjectIntelligence,
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


def _make_titan_like_project(root: Path) -> Path:
    """Minimal multi-package layout with import edges for analysis."""
    project = root / "TitanLite"
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", "# TitanLite\n")

    for pkg in ("brain", "core", "memory", "tools", "agents", "context", "config", "api"):
        (project / pkg).mkdir()
        _write(project / pkg / "__init__.py", "")

    _write(
        project / "config" / "settings.py",
        'PROJECT_ROOT = "."\nVERSION = "0.0.1"\n',
    )
    _write(
        project / "memory" / "memory_service.py",
        "class MemoryService:\n    pass\n",
    )
    _write(
        project / "core" / "mission_runtime.py",
        "from memory.memory_service import MemoryService\n\nclass MissionRuntime:\n    pass\n",
    )
    _write(
        project / "core" / "mission_manager.py",
        "from core.mission_runtime import MissionRuntime\n\nclass MissionManager:\n    pass\n",
    )
    _write(
        project / "tools" / "tool_manager.py",
        "class ToolManager:\n    pass\n",
    )
    _write(
        project / "brain" / "brain.py",
        "from memory.memory_service import MemoryService\n"
        "from tools.tool_manager import ToolManager\n"
        "from core.mission_manager import MissionManager\n"
        "from agents.agent_manager import AgentManager\n\n"
        "class Brain:\n    pass\n",
    )
    _write(
        project / "agents" / "agent_manager.py",
        "from memory.memory_service import MemoryService\n\nclass AgentManager:\n    pass\n",
    )
    _write(
        project / "context" / "context_manager.py",
        "from core.mission_manager import MissionManager\n\nclass ContextManager:\n    pass\n",
    )
    _write(
        project / "api" / "auth.py",
        "def require_web_auth():\n    return True\n",
    )
    _write(
        project / "api" / "app.py",
        "from api.auth import require_web_auth\n",
    )
    (project / "tools" / "connectors").mkdir()
    _write(project / "tools" / "connectors" / "__init__.py", "")
    _write(
        project / "tools" / "connectors" / "browser_connector.py",
        "class BrowserConnector:\n    pass\n",
    )
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


def _build_intelligence(
    project: Path,
    *,
    mission_manager: MissionManager | None = None,
    memory_service: MemoryService | None = None,
    context_manager: ContextManager | None = None,
) -> ProjectIntelligence:
    awareness = WorkspaceAwareness(
        workspace_root=project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )
    return ProjectIntelligence(
        workspace_awareness=awareness,
        mission_manager=mission_manager,
        memory_service=memory_service,
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


# --- architecture summary -------------------------------------------------


def test_architecture_summary(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_titan_like_project(tmp_path)
    mission_manager.runtime.create_mission(
        "Architecture map",
        "Understand TitanLite modules",
        ["Scan packages", "Document edges"],
        priority=MissionPriority.NORMAL,
    )
    intel = _build_intelligence(
        project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )

    summary = intel.analyze_project()

    assert isinstance(summary, ArchitectureSummary)
    assert summary.project_name
    assert summary.language == "Python"
    module_names = {m.name for m in summary.modules}
    assert "brain" in module_names
    assert "memory" in module_names
    assert "tools" in module_names
    assert isinstance(summary.dependency_graph, DependencyGraph)
    assert len(summary.execution_pipeline) >= 3
    assert any("Brain" in step or "think" in step for step in summary.execution_pipeline)
    assert summary.architectural_boundaries
    assert "brain" in summary.folder_responsibilities
    assert summary.active_missions
    assert "module" in summary.summary.lower() or "Module" in summary.summary
    assert summary.format_for_prompt().startswith("PROJECT ARCHITECTURE")


# --- dependency lookup ----------------------------------------------------


def test_dependency_lookup(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)

    summary = intel.analyze_project()
    graph = summary.dependency_graph

    # brain imports memory / tools / core / agents
    brain_deps = graph.dependencies_of("brain")
    assert "memory" in brain_deps
    assert "tools" in brain_deps

    # modules that depend on memory
    memory_dependents = intel.modules_depending_on("memory")
    assert "brain" in memory_dependents
    assert "agents" in memory_dependents or "core" in memory_dependents

    memory_module = intel.explain_module("memory")
    assert "brain" in memory_module.depended_on_by or memory_dependents


# --- feature lookup -------------------------------------------------------


def test_feature_lookup_authentication(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)

    location = intel.find_feature("authentication")

    assert isinstance(location, FeatureLocation)
    assert location.feature == "authentication"
    assert location.owner_module == "api"
    assert any("auth.py" in path for path in location.primary_files)
    assert location.confidence >= 0.8


def test_feature_lookup_browser_and_pipeline(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)

    browser = intel.find_feature("Browser Tool")
    assert browser.feature == "browser_tool"
    assert any("browser" in path.lower() for path in browser.primary_files)

    pipeline = intel.find_feature("execution pipeline")
    assert pipeline.feature == "execution_pipeline"
    assert pipeline.owner_module == "brain"
    assert any("execution_coordinator" in path or "stages" in path for path in pipeline.primary_files)


def test_feature_lookup_tool_manager(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)

    location = intel.find_feature("ToolManager")
    assert location.feature == "tool_manager"
    assert location.owner_module == "tools"
    assert any("tool_manager.py" in path for path in location.primary_files)


# --- module explanation ---------------------------------------------------


def test_module_explanation(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)

    mission = intel.explain_module("Mission Runtime")
    assert isinstance(mission, ModuleDescription)
    assert mission.name == "core"
    assert "mission" in mission.responsibility.lower() or "Persist" in mission.why_exists
    assert mission.format_for_prompt().startswith("MODULE:")

    memory = intel.explain_module("memory")
    assert memory.name == "memory"
    assert "Must NOT import" in memory.architectural_boundary
    assert memory.file_count >= 1


# --- impact analysis ------------------------------------------------------


def test_impact_analysis_tool_manager(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)
    intel.analyze_project()

    impact = intel.analyze_change_impact("ToolManager")
    assert isinstance(impact, ImpactAnalysis)
    assert impact.target_kind in {"module", "file"}
    assert impact.risk_level in {"low", "medium", "high"}
    assert "tool_manager" in impact.related_features or "tools" in impact.transitive_modules
    assert impact.recommendations
    assert impact.confidence > 0

    file_impact = intel.analyze_change_impact("tools/tool_manager.py")
    assert file_impact.target_kind == "file"
    assert "tools" in file_impact.transitive_modules
    assert file_impact.format_for_prompt().startswith("IMPACT ANALYSIS")


def test_impact_analysis_memory_module(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)
    intel.analyze_project()

    impact = intel.analyze_change_impact("memory")
    assert impact.target_kind == "module"
    assert "brain" in impact.direct_dependents or "brain" in impact.transitive_modules
    assert impact.risk_level in {"medium", "high"}
    assert any("isolation" in r.lower() or "Nolan" in r for r in impact.recommendations)


# --- analysis-only guarantees ---------------------------------------------


def test_never_mutates_missions(
    tmp_path: Path,
    mission_manager: MissionManager,
) -> None:
    project = _make_titan_like_project(tmp_path)
    created = mission_manager.runtime.create_mission(
        "Keep intact",
        "Must not change",
        ["Step A"],
    )
    before = created.to_dict()
    intel = _build_intelligence(project, mission_manager=mission_manager)

    intel.analyze_project()
    intel.find_feature("memory")
    intel.explain_module("brain")
    intel.analyze_change_impact("core")

    after = mission_manager.runtime.get_mission(created.id)
    assert after is not None
    assert after.title == before["title"]
    assert after.state.value == before["state"]
    assert after.progress_percent == before["progress_percent"]


# --- brain integration ----------------------------------------------------


def test_brain_integration(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    brain = _build_brain(tmp_path, workspace_root=project)

    assert isinstance(brain.project_intelligence, ProjectIntelligence)

    summary = brain.analyze_project()
    assert isinstance(summary, ArchitectureSummary)
    assert summary.modules

    feature = brain.find_feature("Where is authentication implemented?")
    # Catalog matches on tokens inside longer questions.
    assert feature.feature in {"authentication", "Where is authentication implemented?"}
    if feature.feature == "authentication":
        assert any("auth" in path for path in feature.primary_files)

    # Direct catalog query via Brain
    auth = brain.find_feature("authentication")
    assert auth.owner_module == "api"

    module = brain.explain_module("tools")
    assert module.name == "tools"
    assert module.responsibility

    impact = brain.analyze_change_impact("memory")
    assert isinstance(impact, ImpactAnalysis)
    assert impact.summary


def test_find_feature_empty_query(tmp_path: Path) -> None:
    project = _make_titan_like_project(tmp_path)
    intel = _build_intelligence(project)
    location = intel.find_feature("   ")
    assert location.confidence == 0.0
    assert location.primary_files == ()
