# =====================================
# Titan Workspace Modification Planning Tests
# =====================================

"""Tests for Phase 11 Batch 3 — Workspace Modification Planning (P11-301–P11-306)."""

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
from tools.decision.models import ToolDecisionReport, enrich_modification_decision_context
from tools.decision.modification_models import (
    ModificationPlan,
    estimate_modification_risk,
)
from tools.decision.modification_param_parser import is_modification_request, parse_modification_params
from tools.decision.patch_preview import generate_unified_diff, read_file_safe
from tools.decision.workspace_modification_planner import WorkspaceModificationPlanner
from tools.tool_enums import RiskLevel
from tools.tool_manager import ToolManager


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
def engine() -> ToolDecisionEngine:
    return ToolDecisionEngine()


@pytest.fixture
def reasoning(project_root: Path) -> Reasoning:
    return Reasoning(project_root=project_root)


@pytest.fixture
def planner(project_root: Path) -> WorkspaceModificationPlanner:
    return WorkspaceModificationPlanner(project_root=project_root)


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


# ---------------------------------------------------------------------------
# P11-301 — WorkspaceModificationPlanner
# ---------------------------------------------------------------------------


def test_add_capability_request(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Ajoute une nouvelle capacité weather")
    assert plan.modification_type == "add_capability"
    assert any("tools/weather_tool.py" == item.path for item in plan.files_to_create)
    assert any(item.path == "tools/tool_manager.py" for item in plan.files_to_modify)
    assert plan.confidence >= 0.5


def test_add_provider_request(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Add a new provider slack")
    assert plan.modification_type == "add_provider"
    assert any("tools/providers/slack_provider.py" in item.path for item in plan.files_to_create)
    assert any(item.path == "tools/providers/defaults.py" for item in plan.files_to_modify)


def test_add_memory_request(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Ajoute une nouvelle mémoire pour les préférences trading")
    assert plan.modification_type == "add_memory"
    paths = plan.affected_files
    assert "memory/memory_classifier.py" in paths
    assert "memory/memory_retriever.py" in paths


def test_fix_bug_request_with_path(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Corrige ce bug dans memory/memory_classifier.py")
    assert plan.modification_type == "fix_bug"
    assert any(item.path == "memory/memory_classifier.py" for item in plan.files_to_modify)


def test_modification_planning_dependency_graph(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Ajoute une nouvelle capacité metrics")
    assert plan.dependency_graph
    for path in plan.affected_files:
        assert path in plan.dependency_graph


def test_modification_planning_no_writes(project_root: Path, planner: WorkspaceModificationPlanner) -> None:
    before = {
        rel: (project_root / rel).read_text(encoding="utf-8")
        for rel in ("tools/tool_manager.py", "memory/memory_classifier.py")
    }
    planner.plan("Ajoute une nouvelle capacité audit")
    after = {
        rel: (project_root / rel).read_text(encoding="utf-8")
        for rel in before
    }
    assert before == after


# ---------------------------------------------------------------------------
# P11-302 / P11-305 — ModificationPlan and risk model
# ---------------------------------------------------------------------------


def test_risk_low_for_empty_plan() -> None:
    assert estimate_modification_risk(
        files_to_modify=(),
        files_to_create=(),
        modification_type="add_comment",
    ) == RiskLevel.LOW


def test_risk_critical_for_core_runtime() -> None:
    from tools.decision.modification_models import FileChangeSpec

    risk = estimate_modification_risk(
        files_to_modify=(
            FileChangeSpec("core/titan.py", "command", "add handler"),
        ),
        files_to_create=(),
        modification_type="add_command",
    )
    assert risk == RiskLevel.CRITICAL


def test_risk_high_for_multiple_files(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Ajoute une nouvelle capacité multi")
    assert plan.estimated_risk in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}
    assert len(plan.affected_files) >= 2


def test_modification_plan_serialization_roundtrip(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Add new provider telemetry")
    restored = ModificationPlan.from_dict(plan.to_dict())
    assert restored.objective == plan.objective
    assert restored.affected_files == plan.affected_files
    assert restored.estimated_risk == plan.estimated_risk


# ---------------------------------------------------------------------------
# P11-303 — Patch preview generation
# ---------------------------------------------------------------------------


def test_patch_preview_unified_diff() -> None:
    preview = generate_unified_diff(
        "example.py",
        original="line one\n",
        proposed="line one\nline two\n",
    )
    assert preview.change_type == "modify"
    assert "--- a/example.py" in preview.unified_diff
    assert "+++ b/example.py" in preview.unified_diff
    assert "+line two" in preview.unified_diff


def test_patch_preview_generated_for_capability_plan(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Ajoute une nouvelle capacité notes")
    assert plan.patch_previews
    tool_preview = next(p for p in plan.patch_previews if p.path.endswith("_tool.py"))
    assert tool_preview.change_type == "create"
    assert "class NotesTool" in tool_preview.unified_diff or "NotesTool" in tool_preview.unified_diff


def test_read_file_safe_missing(project_root: Path) -> None:
    assert read_file_safe(project_root, "missing.py") == ""


# ---------------------------------------------------------------------------
# P11-304 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_modification_fields_enriched(
    engine: ToolDecisionEngine,
    reasoning: Reasoning,
) -> None:
    report = engine.decide("Ajoute une nouvelle capacité search_local")
    assert report.intent == Intent.WORKSPACE_MODIFY
    analysis = reasoning.analyze("Ajoute une nouvelle capacité search_local")
    enriched = analysis["decision_report"]
    assert enriched.confirmation_required is True
    assert enriched.modification_plan is not None
    assert enriched.affected_files
    assert enriched.explanation_mode == "modification_plan"
    assert enriched.workspace_operation == "plan_modification"
    data = enriched.to_dict()
    assert data["modification_plan"]["modification_type"] == "add_capability"
    assert data["affected_files"]


def test_enrich_modification_decision_context_helper(planner: WorkspaceModificationPlanner) -> None:
    plan = planner.plan("Fix this bug in memory/memory_classifier.py")
    base = ToolDecisionReport(
        intent=Intent.WORKSPACE_MODIFY,
        confidence=0.9,
        tool_required=False,
        candidate_tools=(),
        selected_tool=None,
        decision_reason="test",
        risk_level=RiskLevel.MEDIUM,
        confirmation_required=False,
    )
    enriched = enrich_modification_decision_context(base, plan)
    assert enriched.confirmation_required is True
    assert enriched.modification_plan is not None
    assert enriched.affected_files == plan.affected_files
    assert enriched.risk_level == plan.estimated_risk


# ---------------------------------------------------------------------------
# P11-306 — User output via coordinator
# ---------------------------------------------------------------------------


def test_coordinator_returns_modification_plan_text(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute("Ajoute une nouvelle capacité export")
    assert result.decision_report is not None
    assert result.decision_report.confirmation_required is True
    assert "Je recommande de modifier ces fichiers" in result.tool_results_text
    assert "Aucun fichier ne sera modifié" in result.tool_results_text or (
        "aucune écriture" in result.tool_results_text.lower()
    )
    assert result.tool_results == []


def test_explain_extension_point_not_modification(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Où dois-je modifier pour ajouter une nouvelle capacité?")
    assert report.intent == Intent.WORKSPACE_EXPLAIN


def test_is_modification_request_parser() -> None:
    assert is_modification_request("Ajoute une nouvelle capacité")
    assert not is_modification_request("Explique comment fonctionne la mémoire")
    params = parse_modification_params("Add a command status")
    assert params.modification_type == "add_command"


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_regression_workspace_explain_still_works(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Explique config/settings.py")
    assert report.intent == Intent.WORKSPACE_EXPLAIN


def test_regression_time_still_works(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Quelle heure est-il ?")
    assert report.intent == Intent.SYSTEM
    assert report.selected_tool == "time"
