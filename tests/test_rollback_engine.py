# =====================================
# Titan Rollback Engine Tests
# =====================================

"""Tests for Phase 12 Batch 2 — Persistent Rollback Engine (P12B2-001–P12B2-006)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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
    enrich_patch_application_decision_context,
    enrich_rollback_decision_context,
)
from tools.decision.modification_models import FileChangeSpec, ModificationPlan
from tools.decision.patch_application_engine import PatchApplicationEngine
from tools.decision.patch_confirmation_gate import get_patch_confirmation_gate
from tools.decision.patch_preview import generate_unified_diff
from tools.decision.rollback_command_parser import parse_rollback_command
from tools.decision.rollback_confirmation_gate import (
    get_rollback_confirmation_gate,
    is_valid_rollback_confirmation,
)
from tools.decision.rollback_manager import RollbackManager, clear_rollback_managers, get_rollback_manager
from tools.decision.rollback_models import RollbackResult
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager


@pytest.fixture(autouse=True)
def clear_gates() -> None:
    get_patch_confirmation_gate().clear()
    get_rollback_confirmation_gate().clear()
    clear_rollback_managers()


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "titan_project"
    root.mkdir()
    (root / "data").mkdir()
    for rel in (
        "memory/memory_classifier.py",
        "memory/memory_retriever.py",
        "tools/new_helper.py",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# stub {rel}\n", encoding="utf-8")
    return root


@pytest.fixture
def rollback_path(project_root: Path) -> Path:
    return project_root / "data" / "rollback_history.json"


@pytest.fixture
def rollback_manager(project_root: Path, rollback_path: Path) -> RollbackManager:
    return get_rollback_manager(project_root, file_path=rollback_path, persist=True)


@pytest.fixture
def engine(project_root: Path, rollback_manager: RollbackManager) -> PatchApplicationEngine:
    return PatchApplicationEngine(
        project_root=project_root,
        rollback_manager=rollback_manager,
    )


def _modify_plan(project_root: Path, target: str, marker: str) -> ModificationPlan:
    original = (project_root / target).read_text(encoding="utf-8")
    proposed = original + marker
    preview = generate_unified_diff(
        target,
        original=original,
        proposed=proposed,
        change_type="modify",
    )
    return ModificationPlan(
        objective=f"Patch {target}",
        modification_type="fix_bug",
        files_to_modify=(FileChangeSpec(target, "test", marker),),
        files_to_create=(),
        files_to_delete=(),
        dependency_graph={},
        implementation_steps=("Apply",),
        estimated_risk=RiskLevel.MEDIUM,
        confidence=0.9,
        patch_previews=(preview,),
    )


def _apply(engine: PatchApplicationEngine, plan: ModificationPlan, token: str) -> None:
    result = engine.apply(
        plan,
        confirmed=True,
        confirmation_message="approve",
        confirmation_token=token,
        patch_id=token,
    )
    assert result.applied is True
    assert result.rollback_id is not None


# ---------------------------------------------------------------------------
# P12B2-001 / P12B2-002 — RollbackManager snapshots
# ---------------------------------------------------------------------------


def test_successful_patch_creates_persisted_snapshot(
    engine: PatchApplicationEngine,
    rollback_manager: RollbackManager,
    rollback_path: Path,
    project_root: Path,
) -> None:
    target = "memory/memory_classifier.py"
    before = (project_root / target).read_text(encoding="utf-8")
    _apply(engine, _modify_plan(project_root, target, "# v1\n"), "patch-1")

    assert rollback_path.is_file()
    assert rollback_manager.history_size() == 1
    snapshot = rollback_manager.get_latest_snapshot()
    assert snapshot is not None
    assert snapshot.patch_id == "patch-1"
    assert snapshot.confirmation_token == "patch-1"
    assert target in snapshot.files_modified
    assert snapshot.file_snapshots[0].original_content == before
    assert "# v1" in (snapshot.file_snapshots[0].new_content or "")


def test_successful_rollback_restores_files(
    engine: PatchApplicationEngine,
    rollback_manager: RollbackManager,
    project_root: Path,
) -> None:
    target = "memory/memory_classifier.py"
    before = (project_root / target).read_text(encoding="utf-8")
    _apply(engine, _modify_plan(project_root, target, "# v1\n"), "patch-1")
    snapshot = rollback_manager.get_latest_snapshot()
    assert snapshot is not None

    result = rollback_manager.restore(snapshot.rollback_id, confirmed=True)
    assert result.applied is True
    assert target in result.files_restored
    assert (project_root / target).read_text(encoding="utf-8") == before


def test_multiple_rollbacks_restore_sequential_versions(
    engine: PatchApplicationEngine,
    rollback_manager: RollbackManager,
    project_root: Path,
) -> None:
    target = "memory/memory_classifier.py"
    original = (project_root / target).read_text(encoding="utf-8")
    _apply(engine, _modify_plan(project_root, target, "# v1\n"), "patch-1")
    first_id = rollback_manager.get_latest_snapshot().rollback_id
    _apply(engine, _modify_plan(project_root, target, "# v2\n"), "patch-2")
    second_id = rollback_manager.get_latest_snapshot().rollback_id

    assert first_id != second_id
    assert rollback_manager.history_size() == 2

    undo_second = rollback_manager.restore(second_id, confirmed=True)
    assert undo_second.applied is True
    content_after_second_undo = (project_root / target).read_text(encoding="utf-8")
    assert "# v2" not in content_after_second_undo
    assert "# v1" in content_after_second_undo

    undo_first = rollback_manager.restore(first_id, confirmed=True)
    assert undo_first.applied is True
    assert (project_root / target).read_text(encoding="utf-8") == original


def test_rollback_invalid_id(rollback_manager: RollbackManager) -> None:
    result = rollback_manager.restore("deadbeef0000", confirmed=True)
    assert result.applied is False
    assert any("introuvable" in err.lower() for err in result.errors)


def test_rollback_without_history(rollback_manager: RollbackManager) -> None:
    assert rollback_manager.history_size() == 0
    result = rollback_manager.restore("anything", confirmed=False)
    assert result.applied is False
    assert any("confirmation" in err.lower() for err in result.errors)


def test_rollback_confirmation_required(rollback_manager: RollbackManager) -> None:
    rollback_manager.record_snapshot(
        patch_id="p1",
        confirmation_token="tok",
        risk_level=RiskLevel.LOW,
        files_modified=("memory/memory_classifier.py",),
        files_created=(),
        file_contents={
            "memory/memory_classifier.py": ("original", "new"),
        },
    )
    snapshot = rollback_manager.get_latest_snapshot()
    assert snapshot is not None
    result = rollback_manager.restore(snapshot.rollback_id, confirmed=False)
    assert result.applied is False


def test_rollback_audit_preserved_after_restore(
    engine: PatchApplicationEngine,
    rollback_manager: RollbackManager,
    project_root: Path,
) -> None:
    _apply(engine, _modify_plan(project_root, "memory/memory_classifier.py", "# v1\n"), "patch-1")
    snapshot = rollback_manager.get_latest_snapshot()
    assert snapshot is not None
    before_audit = len(rollback_manager.audit_entries())
    rollback_manager.restore(snapshot.rollback_id, confirmed=True)
    after_audit = rollback_manager.audit_entries()

    assert len(after_audit) > before_audit
    assert rollback_manager.history_size() == 1
    assert any(entry.event == "rollback_applied" for entry in after_audit)
    assert any(entry.event == "snapshot_created" for entry in after_audit)


def test_rollback_blocks_path_outside_workspace(
    rollback_manager: RollbackManager,
    project_root: Path,
) -> None:
    rollback_manager.record_snapshot(
        patch_id="bad",
        confirmation_token="tok",
        risk_level=RiskLevel.HIGH,
        files_modified=("../outside.py",),
        files_created=(),
        file_contents={
            "../outside.py": ("old", "new"),
        },
    )
    snapshot = rollback_manager.get_latest_snapshot()
    assert snapshot is not None
    result = rollback_manager.restore(snapshot.rollback_id, confirmed=True)
    assert result.applied is False


# ---------------------------------------------------------------------------
# P12B2-003 — Commands and reasoning flow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    ["rollback", "undo", "restore previous patch", "restore patch abcdef012345"],
)
def test_parse_rollback_commands(message: str) -> None:
    cmd = parse_rollback_command(message)
    assert cmd is not None
    if "abcdef012345" in message:
        assert cmd.target_rollback_id == "abcdef012345"
    else:
        assert cmd.target_rollback_id is None


@pytest.mark.parametrize(
    "message",
    [
        "confirm rollback",
        "confirme rollback",
        "approve rollback",
    ],
)
def test_valid_rollback_confirmations(message: str) -> None:
    assert is_valid_rollback_confirmation(message) is True


def test_reasoning_undo_then_confirm_flow(
    project_root: Path,
    rollback_path: Path,
) -> None:
    reasoning = Reasoning(project_root=project_root)
    plan_analysis = reasoning.analyze("Corrige ce bug dans memory/memory_classifier.py")
    assert plan_analysis["decision_report"].patch_application_requested is True

    before = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    apply_analysis = reasoning.analyze("approve")
    assert apply_analysis["decision_report"].patch_applied is True
    after_patch = (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8")
    assert after_patch != before

    undo_analysis = reasoning.analyze("undo")
    assert undo_analysis["confirmation_required"] is True
    assert undo_analysis["decision_report"].rollback_id is not None

    confirm_analysis = reasoning.analyze("confirm rollback")
    report = confirm_analysis["decision_report"]
    assert report.rollback_applied is True
    assert (project_root / "memory/memory_classifier.py").read_text(encoding="utf-8") == before


def test_restore_patch_by_id_command(
    engine: PatchApplicationEngine,
    project_root: Path,
) -> None:
    reasoning = Reasoning(project_root=project_root)
    _apply(engine, _modify_plan(project_root, "memory/memory_classifier.py", "# v1\n"), "patch-1")
    rollback_id = get_rollback_manager(project_root).get_latest_snapshot().rollback_id

    request = reasoning.analyze(f"restore patch {rollback_id}")
    assert request["decision_report"].rollback_id == rollback_id

    result = reasoning.analyze("confirm rollback")
    assert result["decision_report"].rollback_applied is True


# ---------------------------------------------------------------------------
# P12B2-005 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_rollback_fields_enriched() -> None:
    rollback_result = RollbackResult(
        applied=True,
        rollback_id="rb-123",
        files_restored=("memory/memory_classifier.py",),
        files_removed=(),
        errors=(),
        rollback_history_size=2,
    )
    base = ToolDecisionReport(
        intent=Intent.WORKSPACE_MODIFY,
        confidence=0.9,
        tool_required=False,
        candidate_tools=(),
        selected_tool=None,
        decision_reason="rollback",
        risk_level=RiskLevel.MEDIUM,
        confirmation_required=False,
    )
    enriched = enrich_rollback_decision_context(
        base,
        rollback_result,
        confirmation_received=True,
        rollback_history_size=2,
    )
    assert enriched.rollback_applied is True
    assert enriched.rollback_id == "rb-123"
    assert enriched.rollback_history_size == 2
    assert enriched.rollback_available is True
    data = enriched.to_dict()
    assert data["rollback_applied"] is True
    assert data["rollback_id"] == "rb-123"


def test_decision_report_patch_fields_include_rollback_id(
    project_root: Path,
    engine: PatchApplicationEngine,
) -> None:
    from tools.decision.patch_models import PatchApplicationResult

    result = engine.apply(
        _modify_plan(project_root, "memory/memory_classifier.py", "# x\n"),
        confirmed=True,
        confirmation_message="approve",
        confirmation_token="tok",
        patch_id="tok",
    )
    base = ToolDecisionReport(
        intent=Intent.WORKSPACE_MODIFY,
        confidence=0.9,
        tool_required=False,
        candidate_tools=(),
        selected_tool=None,
        decision_reason="patch",
        risk_level=RiskLevel.MEDIUM,
        confirmation_required=False,
    )
    enriched = enrich_patch_application_decision_context(
        base,
        result,
        confirmation_received=True,
        rollback_history_size=1,
    )
    assert enriched.rollback_id == result.rollback_id
    assert enriched.rollback_history_size == 1


def test_decision_report_from_dict_legacy_defaults() -> None:
    data = {
        "intent": "general_chat",
        "confidence": 0.5,
        "tool_required": False,
        "candidate_tools": [],
        "selected_tool": None,
        "decision_reason": "legacy",
        "risk_level": "safe",
        "confirmation_required": False,
    }
    report = ToolDecisionReport.from_dict(data)
    assert report.rollback_id is None
    assert report.rollback_history_size == 0
    assert report.rollback_applied is False


# ---------------------------------------------------------------------------
# P12B2-006 — ToolRuntime exposure
# ---------------------------------------------------------------------------


def test_tool_runtime_exposes_rollback_history(
    project_root: Path,
    engine: PatchApplicationEngine,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    _apply(engine, _modify_plan(project_root, "memory/memory_classifier.py", "# v1\n"), "patch-1")

    history = manager.get_rollback_history()
    assert len(history) == 1
    assert history[0]["rollback_id"]
    assert manager.rollback_history_size() == 1


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


def test_coordinator_rollback_end_to_end(coordinator: ExecutionCoordinator) -> None:
    coordinator.execute("Corrige ce bug dans memory/memory_classifier.py")
    coordinator.execute("confirm")
    undo_result = coordinator.execute("undo")
    assert undo_result.decision_report is not None
    assert undo_result.decision_report.confirmation_required is True

    restore_result = coordinator.execute("confirm rollback")
    assert restore_result.decision_report is not None
    assert restore_result.decision_report.rollback_applied is True
    assert "Rollback" in restore_result.tool_results_text


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_regression_patch_application_still_works(engine: PatchApplicationEngine, project_root: Path) -> None:
    result = engine.apply(
        _modify_plan(project_root, "memory/memory_classifier.py", "# ok\n"),
        confirmed=True,
        confirmation_message="approve",
        confirmation_token="regression",
    )
    assert result.applied is True
    assert result.rollback_available is True


def test_regression_workspace_explain(engine_decision: ToolDecisionEngine) -> None:
    report = engine_decision.decide("Explique config/settings.py")
    assert report.intent == Intent.WORKSPACE_EXPLAIN


@pytest.fixture
def engine_decision() -> ToolDecisionEngine:
    return ToolDecisionEngine()
