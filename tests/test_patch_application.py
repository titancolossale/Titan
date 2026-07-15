# =====================================
# Titan Patch Application Tests
# =====================================

"""Tests for Phase 12 Batch 1 — User-Confirmed Patch Application (P12-001–P12-006)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_manager import AgentManager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision import Intent, ToolDecisionEngine
from tools.decision.models import (
    ToolDecisionReport,
    enrich_modification_decision_context,
    enrich_patch_application_decision_context,
)
from tools.decision.modification_models import FileChangeSpec, ModificationPlan, PatchPreview
from tools.decision.patch_application_engine import PatchApplicationEngine
from tools.decision.patch_confirmation_gate import (
    PatchConfirmationGate,
    get_patch_confirmation_gate,
    is_valid_patch_confirmation,
)
from tools.decision.patch_preview import generate_unified_diff
from tools.decision.patch_utils import apply_unified_diff
from tools.decision.workspace_modification_planner import WorkspaceModificationPlanner
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager


@pytest.fixture(autouse=True)
def clear_patch_gate() -> None:
    get_patch_confirmation_gate().clear()


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "titan_project"
    root.mkdir()
    for rel in (
        "tools/tool_manager.py",
        "tools/providers/defaults.py",
        "memory/memory_classifier.py",
        "memory/memory_retriever.py",
        "core/titan.py",
        "tests/test_memory_classifier.py",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# stub {rel}\n", encoding="utf-8")
    return root


@pytest.fixture
def engine(project_root: Path) -> PatchApplicationEngine:
    return PatchApplicationEngine(project_root=project_root)


@pytest.fixture
def gate() -> PatchConfirmationGate:
    return get_patch_confirmation_gate()


@pytest.fixture
def simple_plan(project_root: Path) -> ModificationPlan:
    target = "memory/memory_classifier.py"
    original = (project_root / target).read_text(encoding="utf-8")
    proposed = original + "# patched\n"
    preview = generate_unified_diff(
        target,
        original=original,
        proposed=proposed,
        change_type="modify",
    )
    return ModificationPlan(
        objective="Test patch",
        modification_type="fix_bug",
        files_to_modify=(
            FileChangeSpec(target, "test", "add marker"),
        ),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=("Apply patch",),
        estimated_risk=RiskLevel.MEDIUM,
        confidence=0.9,
        patch_previews=(preview,),
    )


@pytest.fixture
def create_plan(project_root: Path) -> ModificationPlan:
    path = "tools/new_helper.py"
    content = "# new helper\n\ndef helper():\n    return True\n"
    preview = generate_unified_diff(
        path,
        original="",
        proposed=content,
        change_type="create",
    )
    return ModificationPlan(
        objective="Create helper",
        modification_type="add_capability",
        files_to_modify=(),
        files_to_create=(
            FileChangeSpec(path, "new module", "create helper"),
        ),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=("Create file",),
        estimated_risk=RiskLevel.LOW,
        confidence=0.9,
        patch_previews=(preview,),
    )


def _make_multi_file_plan(project_root: Path) -> ModificationPlan:
    first = "memory/memory_classifier.py"
    second = "memory/memory_retriever.py"
    previews = []
    for path in (first, second):
        original = (project_root / path).read_text(encoding="utf-8")
        proposed = original + f"# patch {path}\n"
        previews.append(
            generate_unified_diff(
                path,
                original=original,
                proposed=proposed,
                change_type="modify",
            ),
        )
    return ModificationPlan(
        objective="Multi patch",
        modification_type="fix_bug",
        files_to_modify=(
            FileChangeSpec(first, "a", "a"),
            FileChangeSpec(second, "b", "b"),
        ),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=("Apply",),
        estimated_risk=RiskLevel.MEDIUM,
        confidence=0.9,
        patch_previews=tuple(previews),
    )


# ---------------------------------------------------------------------------
# P12-002 — Confirmation gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "approve",
        "approved",
        "confirm",
        "apply patch",
        "applique le patch",
        "vas-y applique",
        "  Approve.  ",
    ],
)
def test_valid_confirmations(message: str) -> None:
    assert is_valid_patch_confirmation(message) is True


@pytest.mark.parametrize(
    "message",
    ["yes", "ok", "go ahead", "oui", "confirme", "apply", "approved patch"],
)
def test_invalid_confirmations_rejected(message: str) -> None:
    assert is_valid_patch_confirmation(message) is False


def test_patch_not_applied_without_confirmation(
    engine: PatchApplicationEngine,
    simple_plan: ModificationPlan,
) -> None:
    result = engine.apply(
        simple_plan,
        confirmed=False,
        confirmation_message="",
        confirmation_token="tok-1",
    )
    assert result.applied is False
    assert result.errors


def test_patch_not_applied_with_invalid_confirmation(
    engine: PatchApplicationEngine,
    simple_plan: ModificationPlan,
    project_root: Path,
) -> None:
    before = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    result = engine.apply(
        simple_plan,
        confirmed=True,
        confirmation_message="yes please",
        confirmation_token="tok-2",
    )
    assert result.applied is False
    after = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    assert before == after


def test_patch_applied_with_confirmation(
    engine: PatchApplicationEngine,
    simple_plan: ModificationPlan,
    project_root: Path,
) -> None:
    result = engine.apply(
        simple_plan,
        confirmed=True,
        confirmation_message="approve",
        confirmation_token="tok-3",
    )
    assert result.applied is True
    assert "memory/memory_classifier.py" in result.files_modified
    content = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    assert "# patched" in content


# ---------------------------------------------------------------------------
# P12-003 — Safety rules
# ---------------------------------------------------------------------------


def test_path_traversal_blocked(engine: PatchApplicationEngine) -> None:
    preview = PatchPreview(
        path="../outside.py",
        change_type="create",
        unified_diff="--- a/../outside.py\n+++ b/../outside.py\n@@ -0,0 +1,1 @@\n+hack\n",
    )
    plan = ModificationPlan(
        objective="bad",
        modification_type="fix_bug",
        files_to_modify=(),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=(),
        estimated_risk=RiskLevel.HIGH,
        confidence=0.5,
        patch_previews=(preview,),
    )
    result = engine.apply(
        plan,
        confirmed=True,
        confirmation_message="confirm",
        confirmation_token="tok-4",
    )
    assert result.applied is False
    assert any("traversée" in err.lower() or "hors workspace" in err.lower() for err in result.errors)


def test_env_modification_blocked(engine: PatchApplicationEngine, project_root: Path) -> None:
    env_path = project_root / ".env"
    env_path.write_text("SECRET=1\n", encoding="utf-8")
    preview = generate_unified_diff(
        ".env",
        original="SECRET=1\n",
        proposed="SECRET=2\n",
        change_type="modify",
    )
    plan = ModificationPlan(
        objective="bad env",
        modification_type="fix_bug",
        files_to_modify=(FileChangeSpec(".env", "bad", "bad"),),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=(),
        estimated_risk=RiskLevel.CRITICAL,
        confidence=0.5,
        patch_previews=(preview,),
    )
    result = engine.apply(
        plan,
        confirmed=True,
        confirmation_message="approve",
        confirmation_token="tok-5",
    )
    assert result.applied is False
    assert env_path.read_text(encoding="utf-8") == "SECRET=1\n"


def test_binary_write_blocked(engine: PatchApplicationEngine, project_root: Path) -> None:
    binary_path = project_root / "assets" / "image.bin"
    binary_path.parent.mkdir(parents=True)
    binary_path.write_bytes(b"\x00binary")
    preview = PatchPreview(
        path="assets/image.bin",
        change_type="modify",
        unified_diff="--- a/assets/image.bin\n+++ b/assets/image.bin\n@@ -1 +1 @@\n+binary\n",
    )
    plan = ModificationPlan(
        objective="binary",
        modification_type="fix_bug",
        files_to_modify=(FileChangeSpec("assets/image.bin", "bad", "bad"),),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=(),
        estimated_risk=RiskLevel.HIGH,
        confidence=0.5,
        patch_previews=(preview,),
    )
    result = engine.apply(
        plan,
        confirmed=True,
        confirmation_message="confirm",
        confirmation_token="tok-6",
    )
    assert result.applied is False


def test_delete_operations_blocked(engine: PatchApplicationEngine, simple_plan: ModificationPlan) -> None:
    plan = ModificationPlan(
        objective=simple_plan.objective,
        modification_type=simple_plan.modification_type,
        files_to_modify=simple_plan.files_to_modify,
        files_to_create=simple_plan.files_to_create,
        files_to_delete=("memory/memory_classifier.py",),
        dependency_graph={},
        implementation_steps=simple_plan.implementation_steps,
        estimated_risk=simple_plan.estimated_risk,
        confidence=simple_plan.confidence,
        patch_previews=simple_plan.patch_previews,
    )
    result = engine.apply(
        plan,
        confirmed=True,
        confirmation_message="approve",
        confirmation_token="tok-7",
    )
    assert result.applied is False
    assert any("suppression" in err.lower() for err in result.errors)


def test_high_risk_files_emit_warnings(
    engine: PatchApplicationEngine,
    project_root: Path,
) -> None:
    target = "core/titan.py"
    original = (project_root / target).read_text(encoding="utf-8")
    proposed = original + "# risky\n"
    preview = generate_unified_diff(target, original=original, proposed=proposed)
    plan = ModificationPlan(
        objective="risky",
        modification_type="add_command",
        files_to_modify=(FileChangeSpec(target, "cmd", "cmd"),),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=(),
        estimated_risk=RiskLevel.CRITICAL,
        confidence=0.8,
        patch_previews=(preview,),
    )
    result = engine.apply(
        plan,
        confirmed=True,
        confirmation_message="apply patch",
        confirmation_token="tok-8",
    )
    assert result.applied is True
    assert any("core/titan.py" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# P12-005 — Rollback and file handling
# ---------------------------------------------------------------------------


def test_rollback_on_failure(engine: PatchApplicationEngine, project_root: Path) -> None:
    plan = _make_multi_file_plan(project_root)
    original_first = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    original_second = (project_root / "memory/memory_retriever.py").read_text(encoding="utf-8")

    with patch.object(
        engine,
        "_apply_preview",
        side_effect=[("modified", "# patched\n"), ValueError("boom")],
    ):
        result = engine.apply(
            plan,
            confirmed=True,
            confirmation_message="confirm",
            confirmation_token="tok-9",
        )

    assert result.applied is False
    assert result.rollback_available is True
    assert (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8") == original_first
    assert (project_root / "memory/memory_retriever.py").read_text(encoding="utf-8") == original_second


def test_created_file_handling(
    engine: PatchApplicationEngine,
    create_plan: ModificationPlan,
    project_root: Path,
) -> None:
    target = project_root / "tools/new_helper.py"
    assert not target.is_file()
    result = engine.apply(
        create_plan,
        confirmed=True,
        confirmation_message="approve",
        confirmation_token="tok-10",
    )
    assert result.applied is True
    assert "tools/new_helper.py" in result.files_created
    assert target.is_file()
    assert "def helper" in target.read_text(encoding="utf-8")


def test_modified_file_handling(
    engine: PatchApplicationEngine,
    simple_plan: ModificationPlan,
) -> None:
    result = engine.apply(
        simple_plan,
        confirmed=True,
        confirmation_message="confirm",
        confirmation_token="tok-11",
    )
    assert result.applied is True
    assert result.files_modified == ("memory/memory_classifier.py",)
    assert result.files_created == ()


def test_apply_unified_diff_roundtrip() -> None:
    original = "alpha\nbeta\n"
    proposed = "alpha\ngamma\nbeta\n"
    diff = generate_unified_diff("sample.py", original=original, proposed=proposed).unified_diff
    applied = apply_unified_diff(original, diff)
    assert applied == proposed


# ---------------------------------------------------------------------------
# P12-006 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_patch_fields_enriched(simple_plan: ModificationPlan) -> None:
    from tools.decision.patch_models import PatchApplicationResult

    base = enrich_modification_decision_context(
        ToolDecisionReport(
            intent=Intent.WORKSPACE_MODIFY,
            confidence=0.9,
            tool_required=False,
            candidate_tools=(),
            selected_tool=None,
            decision_reason="plan",
            risk_level=RiskLevel.MEDIUM,
            confirmation_required=True,
        ),
        simple_plan,
    )
    assert base.patch_application_requested is True
    assert base.confirmation_required is True

    patch_result = PatchApplicationResult(
        applied=True,
        files_modified=("memory/memory_classifier.py",),
        files_created=(),
        files_skipped=(),
        errors=(),
        rollback_available=True,
        confirmation_token="abc",
        risk_level=RiskLevel.MEDIUM,
    )
    enriched = enrich_patch_application_decision_context(
        base,
        patch_result,
        confirmation_received=True,
    )
    assert enriched.patch_application_requested is True
    assert enriched.confirmation_received is True
    assert enriched.patch_applied is True
    assert enriched.files_modified == ("memory/memory_classifier.py",)
    assert enriched.rollback_available is True
    assert enriched.confirmation_token == "abc"
    data = enriched.to_dict()
    assert data["patch_applied"] is True
    assert data["patch_application_result"]["applied"] is True


def test_reasoning_patch_confirmation_flow(
    project_root: Path,
    gate: PatchConfirmationGate,
) -> None:
    reasoning = Reasoning(project_root=project_root)
    plan_analysis = reasoning.analyze("Corrige ce bug dans memory/memory_classifier.py")
    assert plan_analysis["decision_report"].patch_application_requested is True
    assert plan_analysis["decision_report"].confirmation_token

    before = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    confirm_analysis = reasoning.analyze("approve")
    report = confirm_analysis["decision_report"]
    assert report.confirmation_received is True
    assert report.patch_applied is True
    after = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    assert after != before
    assert gate.get_latest() is None


@pytest.fixture
def coordinator(project_root: Path, mock_agent_llm: MagicMock) -> ExecutionCoordinator:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    return ExecutionCoordinator(
        orchestrator,
        dispatcher,
        reasoning=Reasoning(project_root=project_root),
    )


def test_coordinator_patch_application_end_to_end(coordinator: ExecutionCoordinator) -> None:
    plan_result = coordinator.execute("Corrige ce bug dans memory/memory_classifier.py")
    assert plan_result.decision_report is not None
    assert plan_result.decision_report.confirmation_required is True
    assert "Confirmation requise" in plan_result.tool_results_text or (
        "aucune écriture" in plan_result.tool_results_text.lower()
    )

    apply_result = coordinator.execute("confirm")
    assert apply_result.decision_report is not None
    assert apply_result.decision_report.patch_applied is True
    assert "Fichiers modifiés" in apply_result.tool_results_text


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_regression_modification_planning_still_read_only(
    planner: WorkspaceModificationPlanner,
    project_root: Path,
) -> None:
    before = (project_root / "tools/tool_manager.py").read_text(encoding="utf-8")
    planner.plan("Ajoute une nouvelle capacité audit")
    after = (project_root / "tools/tool_manager.py").read_text(encoding="utf-8")
    assert before == after


@pytest.fixture
def planner(project_root: Path) -> WorkspaceModificationPlanner:
    return WorkspaceModificationPlanner(project_root=project_root)


def test_regression_workspace_explain(engine_decision: ToolDecisionEngine) -> None:
    report = engine_decision.decide("Explique config/settings.py")
    assert report.intent == Intent.WORKSPACE_EXPLAIN


@pytest.fixture
def engine_decision() -> ToolDecisionEngine:
    return ToolDecisionEngine()
