# =====================================
# Titan Workspace Intelligence Tests
# =====================================

"""Tests for Phase 11 — Workspace Intelligence (P11-001–P11-006, P11-101–P11-106)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_manager import AgentManager
from brain.reasoning import Reasoning
from brain.tool_dispatcher import ToolDispatcher
from context.workspace_map import find_area_in_message, files_for_area, get_area, list_areas
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from tools.decision import FallbackAction, Intent, ToolDecisionEngine
from tools.decision.models import ToolDecisionReport, enrich_workspace_decision_context
from tools.decision.search_chain import (
    build_search_query,
    extract_search_results,
    select_strong_matches,
)
from tools.decision.workspace_param_parser import parse_workspace_params
from tools.decision.workspace_planner import plan_workspace_operation, resolve_filename
from tools.health_monitor import HealthMonitor
from tools.providers.file_system_provider import LocalFileSystemProvider
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_manager import ToolManager


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    brain = root / "brain"
    brain.mkdir()
    memory = root / "memory"
    memory.mkdir()
    config = root / "config"
    config.mkdir()
    tools = root / "tools"
    tools.mkdir()
    (brain / "brain.py").write_text(
        "class Brain:\n    def think(self): pass\n",
        encoding="utf-8",
    )
    (brain / "llm.py").write_text("# LLM gateway\n", encoding="utf-8")
    (memory / "long_term_memory.py").write_text(
        "class LongTermMemory:\n    \"\"\"Core durable memory system.\"\"\"\n    pass\n",
        encoding="utf-8",
    )
    (memory / "memory_retriever.py").write_text(
        "class Retriever:\n    pass\n",
        encoding="utf-8",
    )
    (config / "settings.py").write_text("VERSION = '0.10.0'\n", encoding="utf-8")
    (tools / "tool_manager.py").write_text("# tool manager\n", encoding="utf-8")
    (root / "notes.md").write_text("# Notes\nTODO item\n", encoding="utf-8")
    (root / "readme.txt").write_text("duplicate name placeholder\n", encoding="utf-8")
    nested = root / "docs"
    nested.mkdir()
    (nested / "notes.md").write_text("# Other notes\n", encoding="utf-8")
    (root / "Titan_Context.md").write_text(
        "# Titan Context\nProject overview and architecture notes.\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def engine() -> ToolDecisionEngine:
    return ToolDecisionEngine()


@pytest.fixture
def reasoning(project_root: Path) -> Reasoning:
    return Reasoning(project_root=project_root)


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
# P11-003 — Workspace map
# ---------------------------------------------------------------------------


def test_workspace_map_lists_core_areas() -> None:
    areas = list_areas()
    for key in ("brain", "memory", "agents", "tools", "providers", "config", "context", "tests"):
        assert key in areas


def test_workspace_map_resolves_memory_area() -> None:
    assert find_area_in_message("comment fonctionne le système de mémoire") == "memory"
    area = get_area("memory")
    assert area is not None
    assert "memory/long_term_memory.py" in area.key_files


def test_workspace_map_files_for_area(project_root: Path) -> None:
    files = files_for_area("brain", project_root=project_root)
    assert "brain/brain.py" in files


# ---------------------------------------------------------------------------
# P11-001 — Natural-language file read
# ---------------------------------------------------------------------------


def test_read_exact_file_path(engine: ToolDecisionEngine, reasoning: Reasoning) -> None:
    report = engine.decide("Lis config/settings.py et résume-le")
    assert report.intent == Intent.WORKSPACE_EXPLAIN
    analysis = reasoning.analyze("Lis config/settings.py et résume-le")
    assert analysis["needs_tool"]
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["path"] == "config/settings.py"


def test_read_file_found_by_search(project_root: Path) -> None:
    unique, candidates = resolve_filename(project_root, "notes.md")
    assert unique is None
    assert len(candidates) == 2
    plan = plan_workspace_operation(
        "Explique notes.md",
        project_root=project_root,
        confidence=0.9,
    )
    assert plan.ambiguous
    assert len(plan.files_considered) == 2


def test_read_resolved_unique_filename(project_root: Path) -> None:
    unique, candidates = resolve_filename(project_root, "settings.py")
    assert unique == "config/settings.py"
    plan = plan_workspace_operation(
        "Explique settings.py",
        project_root=project_root,
    )
    assert not plan.ambiguous
    assert plan.tool_requests[0].params["path"] == "config/settings.py"


def test_semantic_area_read(reasoning: Reasoning) -> None:
    analysis = reasoning.analyze("Explique-moi comment fonctionne le système de mémoire")
    report = analysis["decision_report"]
    assert report.intent == Intent.WORKSPACE_EXPLAIN
    assert report.explanation_mode == "area_overview"
    assert "memory/" in report.files_considered[0]


# ---------------------------------------------------------------------------
# P11-002 — Workspace explanation mode
# ---------------------------------------------------------------------------


def test_explain_one_file(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute("Explique-moi brain/brain.py")
    assert result.decision_report.explanation_mode == "single_file"
    assert result.tool_results[0].success
    assert "class Brain" in result.tool_results[0].data
    assert "[Mode explication workspace]" in result.tool_results_text


def test_explain_workspace_area(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute("Explique-moi comment fonctionne le système de mémoire")
    assert result.decision_report.workspace_operation == "explain_area"
    assert result.decision_report.explanation_mode == "area_overview"
    assert result.tool_results
    assert any(item.success for item in result.tool_results)


def test_identify_brain_related_files(reasoning: Reasoning) -> None:
    analysis = reasoning.analyze("Quels fichiers contrôlent le Brain?")
    report = analysis["decision_report"]
    assert report.intent == Intent.WORKSPACE_EXPLAIN
    assert report.explanation_mode == "identify_controllers"
    assert any("brain/" in path for path in report.files_considered)


def test_identify_memory_related_files(reasoning: Reasoning) -> None:
    analysis = reasoning.analyze("Which files control memory?")
    report = analysis["decision_report"]
    assert report.explanation_mode == "identify_controllers"
    assert any("memory/" in path for path in report.files_considered)


def test_find_extension_point(reasoning: Reasoning) -> None:
    analysis = reasoning.analyze(
        "Où dois-je modifier le code pour ajouter une nouvelle capacité?"
    )
    report = analysis["decision_report"]
    assert report.workspace_operation == "find_extension_point"
    assert report.explanation_mode == "extension_point"
    assert analysis["needs_tool"]


# ---------------------------------------------------------------------------
# P11-005 — Safety and edge cases
# ---------------------------------------------------------------------------


def test_no_matching_file(project_root: Path) -> None:
    plan = plan_workspace_operation(
        "Explique missing.py",
        project_root=project_root,
    )
    assert plan.tool_requests
    assert plan.tool_requests[0].params["action"] == "search_files"


def test_ambiguous_file_request(reasoning: Reasoning) -> None:
    analysis = reasoning.analyze("Explique-moi ce fichier")
    assert analysis["needs_clarification"]
    assert analysis["decision_report"].fallback_action == FallbackAction.CLARIFICATION


def test_path_traversal_blocked(project_root: Path, reasoning: Reasoning) -> None:
    plan = plan_workspace_operation(
        "Explique ../../etc/passwd",
        project_root=project_root,
    )
    assert plan.ambiguous
    assert "refusé" in plan.ambiguity_reason.lower() or "hors" in plan.ambiguity_reason.lower()


def test_file_write_still_high_risk(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Écris dans notes.md contenu: test")
    if report.selected_tool == "file_write":
        assert report.risk_level == RiskLevel.HIGH
        assert report.confirmation_required is True


# ---------------------------------------------------------------------------
# P11-004 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_workspace_fields_enriched(project_root: Path) -> None:
    plan = plan_workspace_operation(
        "Explique config/settings.py",
        project_root=project_root,
    )
    base = ToolDecisionReport(
        intent=Intent.WORKSPACE_EXPLAIN,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="file_read",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        fallback_action=FallbackAction.EXECUTE_TOOL,
    )
    enriched = enrich_workspace_decision_context(base, plan, execution_mode="live")
    data = enriched.to_dict()
    assert data["workspace_operation"] == "explain_file"
    assert data["explanation_mode"] == "single_file"
    assert data["files_considered"] == ["config/settings.py"]
    assert data["selected_provider"] == "file_system"
    assert data["risk_level"] == RiskLevel.LOW.value
    assert 0.0 <= data["confidence"] <= 1.0


def test_decision_report_files_read_after_execution(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute("Explique config/settings.py")
    assert result.decision_report.files_read
    assert "config/settings.py" in result.decision_report.files_read


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def test_regression_file_list_still_works(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Liste les fichiers Python dans brain/")
    assert report.intent == Intent.FILE_LIST
    assert report.selected_tool == "file_read"


def test_regression_time_still_works(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Quelle heure est-il ?")
    assert report.intent == Intent.SYSTEM
    assert report.selected_tool == "time"


def test_parse_workspace_params_controller_without_area() -> None:
    params = parse_workspace_params("Quels fichiers contrôlent ?")
    assert params.ambiguous


# ---------------------------------------------------------------------------
# P11-101–P11-106 — Search then read chaining
# ---------------------------------------------------------------------------


def test_search_then_read_exact_match(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute("Trouve Titan_Context.md et résume-le")
    report = result.decision_report
    assert report.workspace_operation == "search_then_read"
    assert report.selected_file == "Titan_Context.md"
    assert report.ambiguity_status == "clear"
    assert "Titan_Context.md" in report.files_read
    assert result.tool_results[-1].success
    assert "Titan Context" in result.tool_results[-1].data


def test_search_then_read_semantic_match(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute(
        "Trouve le fichier qui parle du système de mémoire et explique-le"
    )
    report = result.decision_report
    assert report.workspace_operation == "search_then_read"
    assert report.selected_file == "memory/long_term_memory.py"
    assert report.ambiguity_status == "clear"
    assert "memory/long_term_memory.py" in report.files_read
    assert report.search_query
    assert "[Mode explication workspace]" in result.tool_results_text


def test_search_then_read_multiple_matches_clarification(
    coordinator: ExecutionCoordinator,
) -> None:
    result = coordinator.execute("Explique le fichier qui contrôle le Brain")
    report = result.decision_report
    assert report.workspace_operation == "search_then_read"
    assert report.ambiguity_status == "ambiguous"
    assert len(report.files_considered) >= 2
    assert result.tool_results[-1].success is False
    assert "brain/brain.py" in result.tool_results[-1].error


def test_search_then_read_no_match(project_root: Path, coordinator: ExecutionCoordinator) -> None:
    plan = plan_workspace_operation(
        "Trouve missing_unique_xyz.py et explique-le",
        project_root=project_root,
    )
    assert plan.chain_after_search or plan.ambiguity_status == "pending"

    result = coordinator.execute("Trouve missing_unique_xyz.py et explique-le")
    report = result.decision_report
    assert report.ambiguity_status in {"no_match", "pending", "ambiguous"}
    if report.ambiguity_status == "no_match":
        assert any(
            "Aucun fichier correspondant" in (item.error or item.data)
            for item in result.tool_results
        )


def test_search_chain_prior_search_result_read(project_root: Path) -> None:
    params = parse_workspace_params("Trouve orphan_only.py et explique-le")
    query = build_search_query(params)
    (project_root / "orphan_only.py").write_text("unique orphan file\n", encoding="utf-8")
    selection = select_strong_matches(
        ("orphan_only.py",),
        query,
        params,
        project_root,
    )
    assert selection.status == "single_match"
    assert selection.selected_file == "orphan_only.py"


def test_decision_report_search_chain_fields(coordinator: ExecutionCoordinator) -> None:
    result = coordinator.execute("Trouve Titan_Context.md et résume-le")
    data = result.decision_report.to_dict()
    assert data["search_query"]
    assert data["selected_file"] == "Titan_Context.md"
    assert data["explanation_mode"] == "read_and_summarize"
    assert data["ambiguity_status"] == "clear"
    assert data["confidence"] >= 0.0


def test_search_chain_extract_results_from_metadata() -> None:
    from tools.tool_result import ToolResult

    result = ToolResult(
        tool_name="file_read",
        success=True,
        data="Résultats de recherche (1) :\n  - brain/brain.py",
        metadata={
            "file_operation": "search_files",
            "search_results": ["brain/brain.py"],
        },
    )
    assert extract_search_results(result) == ("brain/brain.py",)


def test_search_then_read_path_traversal_blocked(project_root: Path) -> None:
    plan = plan_workspace_operation(
        "Trouve ../../etc/passwd et explique-le",
        project_root=project_root,
    )
    assert plan.ambiguous
    assert "refusé" in plan.ambiguity_reason.lower() or "hors" in plan.ambiguity_reason.lower()
