# =====================================
# Titan Workspace Awareness Tests
# =====================================

"""Unit tests for Workspace Awareness V1 — contextual workspace snapshots only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.llm import LLM
from brain.workspace_awareness import WorkspaceAwareness, WorkspaceSnapshot
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


def _make_python_project(root: Path, *, name: str = "demo") -> Path:
    project = root / name
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(project / "README.md", f"# {name}\n")
    (project / "core").mkdir()
    _write(project / "core" / "__init__.py", "")
    _write(project / "core" / "engine.py", "VALUE = 1\n")
    (project / "brain").mkdir()
    _write(project / "brain" / "__init__.py", "")
    _write(project / "brain" / "think.py", "def think():\n    return True\n")
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


def test_workspace_creation(
    tmp_path: Path,
    mission_manager: MissionManager,
    memory_service: MemoryService,
    context_manager: ContextManager,
) -> None:
    project = _make_python_project(tmp_path, name="Alpha")
    awareness = WorkspaceAwareness(
        workspace_root=project,
        mission_manager=mission_manager,
        memory_service=memory_service,
        context_manager=context_manager,
    )

    snapshot = awareness.refresh()

    assert isinstance(snapshot, WorkspaceSnapshot)
    assert snapshot.workspace_root == str(project.resolve())
    assert snapshot.current_project
    assert snapshot.project_language == "Python"
    assert "core" in snapshot.detected_modules
    assert "brain" in snapshot.detected_modules
    assert any(path.endswith("README.md") for path in snapshot.documentation_files)
    assert any("ARCHITECTURE.md" in path for path in snapshot.documentation_files)
    assert snapshot.timestamp.tzinfo is not None
    assert "Project" in snapshot.summary


def test_empty_workspace(tmp_path: Path) -> None:
    empty = tmp_path / "missing_workspace"
    awareness = WorkspaceAwareness(workspace_root=empty)

    snapshot = awareness.refresh()

    assert snapshot.detected_modules == ()
    assert snapshot.documentation_files == ()
    assert snapshot.recently_modified_files == ()
    assert snapshot.active_missions == ()
    assert snapshot.project_language == "unknown"
    assert "Empty" in snapshot.summary or "missing" in snapshot.summary.lower()


def test_multiple_projects(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _make_python_project(workspace, name="project_a")
    _make_python_project(workspace, name="project_b")

    awareness = WorkspaceAwareness(workspace_root=workspace)
    snapshot = awareness.refresh(project_id="project_b")

    assert "project_a" in snapshot.projects
    assert "project_b" in snapshot.projects
    assert snapshot.current_project == "project_b"
    assert "core" in snapshot.detected_modules


def test_mission_correlation(
    tmp_path: Path,
    mission_manager: MissionManager,
) -> None:
    project = _make_python_project(tmp_path, name="Titanish")
    mission_manager.runtime.create_mission(
        "Improve brain cognition",
        "Upgrade brain modules and cognitive loop",
        ["Inspect brain", "Add tests"],
        priority=MissionPriority.HIGH,
    )

    awareness = WorkspaceAwareness(
        workspace_root=project,
        mission_manager=mission_manager,
    )
    snapshot = awareness.refresh()

    assert len(snapshot.active_missions) == 1
    assert snapshot.active_missions[0]["title"] == "Improve brain cognition"

    related = awareness.mission_related_files(
        "Improve brain cognition",
        "Upgrade brain modules",
        snapshot=snapshot,
    )
    assert any("brain" in path for path in related)
    assert any(
        item.kind == "mission_related_files" for item in snapshot.recommendations
    )


def test_documentation_detection(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="DocsProj")
    _write(project / "CHANGELOG.md", "## Unreleased\n")
    # Module without matching docs should surface a missing-doc signal when
    # documentation coverage is thin — add an undocumented package.
    (project / "trading").mkdir()
    _write(project / "trading" / "__init__.py", "")
    _write(project / "trading" / "broker.py", "x = 1\n")

    awareness = WorkspaceAwareness(workspace_root=project)
    snapshot = awareness.refresh()

    docs_lower = [path.lower() for path in snapshot.documentation_files]
    assert any(path.endswith("readme.md") for path in docs_lower)
    assert any("changelog.md" in path for path in docs_lower)
    assert any("architecture.md" in path for path in docs_lower)
    assert "trading" in snapshot.detected_modules


def test_open_files_and_git_branch(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="GitProj")
    git_dir = project / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/workspace\n", encoding="utf-8")

    awareness = WorkspaceAwareness(workspace_root=project)
    snapshot = awareness.refresh(
        open_files=[str(project / "brain" / "think.py"), "core/engine.py"],
    )

    assert snapshot.git_branch == "feature/workspace"
    assert any("think.py" in path for path in snapshot.open_files)
    assert "core/engine.py" in snapshot.open_files


def test_get_workspace_caches_until_refresh(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="CacheProj")
    awareness = WorkspaceAwareness(workspace_root=project)

    first = awareness.get_workspace()
    second = awareness.get_workspace()
    assert first is second

    third = awareness.refresh()
    assert third is not first
    assert awareness.get_workspace() is third


def test_brain_integration(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="BrainWS")
    brain = _build_brain(tmp_path, workspace_root=project)

    refreshed = brain.refresh_workspace(open_files=["brain/think.py"])
    cached = brain.get_workspace()

    assert refreshed.current_project
    assert refreshed.project_language == "Python"
    assert "brain" in refreshed.detected_modules
    assert cached is refreshed
    assert any("think.py" in path for path in refreshed.open_files)

    brain.create_mission(
        "Brain workspace mission",
        "Align brain package with workspace awareness",
        ["Map modules", "Write tests"],
    )
    thoughts = brain.generate_thoughts("What should I work on in the brain package?")
    sources = {obs.source for obs in thoughts.observations}
    assert "workspace" in sources
    assert any("workspace" in thought.source for thought in thoughts.thoughts)


def test_format_for_prompt(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="PromptProj")
    awareness = WorkspaceAwareness(workspace_root=project)
    snapshot = awareness.refresh()
    block = snapshot.format_for_prompt()

    assert "WORKSPACE" in block
    assert snapshot.current_project in block
    assert "modules:" in block


def test_snapshot_to_dict_roundtrip_fields(tmp_path: Path) -> None:
    project = _make_python_project(tmp_path, name="DictProj")
    awareness = WorkspaceAwareness(workspace_root=project)
    data = awareness.refresh(now=datetime(2026, 7, 9, tzinfo=timezone.utc)).to_dict()

    assert data["workspace_root"]
    assert data["current_project"]
    assert isinstance(data["open_files"], list)
    assert isinstance(data["recently_modified_files"], list)
    assert isinstance(data["detected_modules"], list)
    assert isinstance(data["documentation_files"], list)
    assert isinstance(data["active_missions"], list)
    assert data["timestamp"].startswith("2026-07-09")
