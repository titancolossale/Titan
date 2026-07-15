# =====================================
# Titan Code Generation Engine Tests
# =====================================

"""Unit tests for Code Generation Engine V1 — proposals only, no writes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.brain import Brain
from brain.code_generation_engine import (
    CodeGenerationEngine,
    GeneratedEdit,
    GeneratedFile,
    GeneratedPatch,
    ReviewItem,
)
from brain.code_modification_planner import (
    AffectedFile,
    AffectedModule,
    ChangeType,
    CodeModificationPlan,
    CodeModificationPlanner,
    ComplexityLevel,
    ImplementationStep,
    RiskAssessment,
    RiskLevel,
    TestingPlan,
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


def _write(path: Path, content: str = "# stub\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fingerprint_tree(root: Path) -> dict[str, str]:
    """Map relative paths → content hashes for mutation detection."""
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _make_project(root: Path) -> Path:
    project = root / "GenProject"
    project.mkdir(parents=True)
    _write(project / "requirements.txt", "pytest\n")
    _write(
        project / "tools" / "tool_manager.py",
        '''# =====================================
# Titan ToolManager
# =====================================

from __future__ import annotations

class ToolManager:
    def _register_defaults(self) -> None:
        self.register(object())

    def register(self, tool: object) -> None:
        pass
''',
    )
    _write(
        project / "core" / "tools" / "browser" / "browser_tool.py",
        '''# Browser tool
class BrowserTool:
    def fetch(self, url: str) -> str:
        return url
''',
    )
    _write(
        project / "tools" / "connectors" / "tradingview_provider.py",
        '''# TradingView provider
class TradingViewProvider:
    def parse(self, payload: str) -> dict:
        return {"raw": payload}
''',
    )
    _write(project / ".env.example", "OPENAI_API_KEY=\n")
    _write(project / "tests" / "test_core_browser_tool.py", "def test_browser():\n    assert True\n")
    return project


def _minimal_plan(
    request: str,
    *,
    change_type: ChangeType = ChangeType.FEATURE,
    files: tuple[AffectedFile, ...] = (),
    approved: bool = True,
    risk: RiskLevel = RiskLevel.MEDIUM,
) -> CodeModificationPlan:
    return CodeModificationPlan(
        request=request,
        change_type=change_type,
        summary=f"Plan for {request}",
        affected_modules=(
            AffectedModule(name="tools", path="tools/", role="tools layer"),
        ),
        affected_files=files,
        implementation_steps=(
            ImplementationStep(
                order=1,
                title="Implement",
                description="Apply proposed changes after review",
                target_files=tuple(f.path for f in files),
            ),
        ),
        risk=RiskAssessment(overall=risk, architectural="test"),
        testing=TestingPlan(unit_tests=("unit smoke",)),
        complexity=ComplexityLevel.MEDIUM,
        estimated_impact="test impact",
        checklist=("review diffs",),
        confidence=0.8,
        approved=approved,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _make_project(tmp_path)


@pytest.fixture
def engine(project: Path) -> CodeGenerationEngine:
    awareness = WorkspaceAwareness(workspace_root=project)
    return CodeGenerationEngine(
        workspace_awareness=awareness,
        project_root=project,
        require_approval=True,
    )


@pytest.fixture
def planner(project: Path) -> CodeModificationPlanner:
    awareness = WorkspaceAwareness(workspace_root=project)
    return CodeModificationPlanner(workspace_awareness=awareness)


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
# Core generation behaviors
# ---------------------------------------------------------------------------


def test_single_file_generation(engine: CodeGenerationEngine) -> None:
    plan = _minimal_plan(
        "Add helper module",
        files=(
            AffectedFile(
                path="tools/helper_tool.py",
                reason="Single new helper",
                classes=("HelperTool",),
                action="create",
            ),
        ),
    )
    patch = engine.generate(plan)

    assert isinstance(patch, GeneratedPatch)
    assert patch.summary.files_created == 1
    assert patch.summary.files_edited == 0
    assert len(patch.files) == 1
    assert patch.files[0].path == "tools/helper_tool.py"
    assert "HelperTool" in patch.files[0].content
    assert "--- a/tools/helper_tool.py" in patch.unified_diff_bundle or patch.files[0].content


def test_multi_file_generation(engine: CodeGenerationEngine) -> None:
    plan = _minimal_plan(
        "Implement Discord integration.",
        files=(
            AffectedFile(
                path="tools/discord_tool.py",
                reason="Discord tool",
                classes=("DiscordTool",),
                action="create",
            ),
            AffectedFile(
                path="tests/test_discord_tool.py",
                reason="Discord tests",
                priority="test",
                action="create",
            ),
            AffectedFile(
                path="tools/tool_manager.py",
                reason="Register DiscordTool",
                classes=("ToolManager",),
                action="modify",
            ),
        ),
    )
    patch = engine.generate(plan)

    assert patch.summary.files_created >= 2
    assert patch.summary.files_edited >= 1
    paths = {f.path for f in patch.files} | {e.path for e in patch.edits}
    assert "tools/discord_tool.py" in paths
    assert "tests/test_discord_tool.py" in paths
    assert "tools/tool_manager.py" in paths


def test_edit_generation(engine: CodeGenerationEngine, project: Path) -> None:
    before = (project / "core/tools/browser/browser_tool.py").read_text(encoding="utf-8")
    plan = _minimal_plan(
        "Refactor Browser Tool.",
        change_type=ChangeType.REFACTOR,
        files=(
            AffectedFile(
                path="core/tools/browser/browser_tool.py",
                reason="Improve Browser Tool structure",
                classes=("BrowserTool",),
                action="modify",
            ),
        ),
    )
    patch = engine.generate(plan)

    assert len(patch.edits) == 1
    edit = patch.edits[0]
    assert isinstance(edit, GeneratedEdit)
    assert edit.path == "core/tools/browser/browser_tool.py"
    assert edit.unified_diff
    assert "CODEGEN PROPOSAL" in edit.proposed_content or edit.proposed_content != before
    # Repository file unchanged
    after = (project / "core/tools/browser/browser_tool.py").read_text(encoding="utf-8")
    assert after == before


def test_new_file_generation(engine: CodeGenerationEngine, project: Path) -> None:
    plan = _minimal_plan(
        "Add Discord integration.",
        files=(
            AffectedFile(
                path="tools/discord_tool.py",
                reason="New Discord tool",
                classes=("DiscordTool",),
                action="create",
            ),
        ),
    )
    patch = engine.generate(plan)

    assert len(patch.files) == 1
    generated = patch.files[0]
    assert isinstance(generated, GeneratedFile)
    assert "class DiscordTool" in generated.content
    assert not (project / "tools/discord_tool.py").exists()


def test_review_generation(engine: CodeGenerationEngine) -> None:
    plan = _minimal_plan(
        "Implement Discord integration.",
        risk=RiskLevel.HIGH,
        files=(
            AffectedFile(
                path="tools/discord_tool.py",
                reason="External connector",
                classes=("DiscordTool",),
                action="create",
            ),
        ),
    )
    patch = engine.generate(plan)

    assert patch.review_items
    assert all(isinstance(item, ReviewItem) for item in patch.review_items)
    severities = {item.severity for item in patch.review_items}
    assert "critical" in severities or "warning" in severities
    assert patch.summary.requires_manual_review is True


def test_unapproved_plan_rejected(engine: CodeGenerationEngine) -> None:
    plan = _minimal_plan(
        "Add Discord integration.",
        approved=False,
        files=(
            AffectedFile(
                path="tools/discord_tool.py",
                reason="Discord",
                action="create",
            ),
        ),
    )
    patch = engine.generate(plan)

    assert patch.summary.files_created == 0
    assert patch.summary.files_edited == 0
    assert patch.confidence == 0.0
    assert any(item.severity == "critical" for item in patch.review_items)


def test_tradingview_and_toolmanager_examples(
    engine: CodeGenerationEngine,
    planner: CodeModificationPlanner,
    project: Path,
) -> None:
    before = _fingerprint_tree(project)

    tv_plan = planner.plan("Generate TradingView connector.").with_approval()
    tv_patch = engine.generate(tv_plan)
    assert tv_patch.edits or tv_patch.files
    tv_paths = [item.path for item in tv_patch.edits] + [item.path for item in tv_patch.files]
    assert any("tradingview" in path for path in tv_paths) or "tradingview" in tv_patch.rationale.lower()

    rename_plan = planner.plan("Rename ToolManager.").with_approval()
    patch = engine.generate(rename_plan)
    assert patch.edits or patch.files
    assert patch.review_items

    assert _fingerprint_tree(project) == before


def test_repository_unchanged_after_generation(
    engine: CodeGenerationEngine,
    project: Path,
) -> None:
    before = _fingerprint_tree(project)
    plan = _minimal_plan(
        "Implement Discord integration.",
        files=(
            AffectedFile(
                path="tools/discord_tool.py",
                reason="Discord",
                classes=("DiscordTool",),
                action="create",
            ),
            AffectedFile(
                path="tools/tool_manager.py",
                reason="Register",
                action="modify",
            ),
            AffectedFile(
                path=".env.example",
                reason="Env docs",
                priority="docs",
                action="modify",
            ),
        ),
    )
    patch = engine.generate(plan)
    assert patch.files or patch.edits
    assert _fingerprint_tree(project) == before


# ---------------------------------------------------------------------------
# Planner → generator and Brain integration
# ---------------------------------------------------------------------------


def test_planner_to_generator_pipeline(
    planner: CodeModificationPlanner,
    engine: CodeGenerationEngine,
    project: Path,
) -> None:
    before = _fingerprint_tree(project)
    plan = planner.plan("Add Discord integration.")
    assert plan.change_type == ChangeType.FEATURE
    assert plan.affected_files

    patch = engine.generate(plan.with_approval())
    assert isinstance(patch, GeneratedPatch)
    assert patch.plan_approved is True
    assert patch.to_dict()["summary"]["files_created"] >= 1
    assert _fingerprint_tree(project) == before


def test_brain_integration(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    before = _fingerprint_tree(project)
    brain = _build_brain(tmp_path, workspace_root=project)

    assert brain.code_generation_engine is not None
    assert brain.code_modification_planner is not None

    plan = brain.plan_code_change("Implement Discord integration.")
    assert isinstance(plan, CodeModificationPlan)
    assert plan.affected_modules

    rejected = brain.generate_code(plan)
    assert rejected.summary.files_created == 0

    patch = brain.generate_code(plan.with_approval())
    assert isinstance(patch, GeneratedPatch)
    assert patch.summary.files_created >= 1
    assert "DiscordTool" in patch.files[0].content or any(
        "discord" in f.path for f in patch.files
    )
    assert patch.format_for_prompt().startswith("CODE GENERATION PROPOSAL")
    assert _fingerprint_tree(project) == before
