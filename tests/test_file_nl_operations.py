# =====================================
# Titan File NL Operations Tests
# =====================================

"""Tests for Phase 10B Batch 15 — Natural Language File List/Search (P10B-1501–P10B-1506)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.reasoning import Reasoning
from core.execution_coordinator import ExecutionCoordinator
from core.task_manager import TaskManager
from core.task_orchestrator import TaskOrchestrator
from agents.agent_manager import AgentManager
from brain.tool_dispatcher import ToolDispatcher
from tools.decision import FallbackAction, Intent, ToolDecisionEngine
from tools.decision.file_param_parser import parse_file_params, params_to_tool_dict
from tools.decision.models import ToolDecisionReport, enrich_file_decision_context
from tools.providers.file_system_provider import LocalFileSystemProvider
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.health_monitor import HealthMonitor
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_manager import ToolManager


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    brain = root / "brain"
    brain.mkdir()
    (brain / "brain.py").write_text("# brain module", encoding="utf-8")
    (brain / "helper.py").write_text("x = 1", encoding="utf-8")
    (root / "Titan_Context.md").write_text("# Titan\nTradingView integration", encoding="utf-8")
    (root / "notes.md").write_text("# Notes\nTODO: refactor", encoding="utf-8")
    (root / "readme.txt").write_text("plain text", encoding="utf-8")
    return root


@pytest.fixture
def fs_executor(project_root: Path) -> ProviderExecutor:
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(LocalFileSystemProvider(project_root))
    return ProviderExecutor(registry=registry, health_monitor=HealthMonitor())


@pytest.fixture
def engine() -> ToolDecisionEngine:
    return ToolDecisionEngine()


# ---------------------------------------------------------------------------
# P10B-1501 — Intent classification
# ---------------------------------------------------------------------------


def test_intent_file_list(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Liste les fichiers Python dans brain/")
    assert report.intent == Intent.FILE_LIST
    assert report.selected_tool == "file_read"
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL


def test_intent_file_search_by_filename(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Cherche Titan_Context.md")
    assert report.intent == Intent.FILE_SEARCH
    assert report.selected_tool == "file_read"


def test_intent_file_search_by_keyword(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Trouve les fichiers qui parlent de TradingView")
    assert report.intent == Intent.FILE_SEARCH


def test_intent_file_read(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Lire le fichier config/settings.py")
    assert report.intent == Intent.FILE_READ
    assert report.confidence >= 0.8


def test_intent_file_metadata(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Métadonnées du fichier notes.md")
    assert report.intent == Intent.FILE_METADATA


# ---------------------------------------------------------------------------
# P10B-1503 — Parameter parsing
# ---------------------------------------------------------------------------


def test_parse_list_python_in_directory() -> None:
    params = parse_file_params("Liste les fichiers Python dans brain/", Intent.FILE_LIST)
    assert params.operation == "list_directory"
    assert params.directory == "brain"
    assert params.extension == "py"
    assert not params.ambiguous


def test_parse_list_markdown_project() -> None:
    params = parse_file_params("Liste les fichiers markdown du projet", Intent.FILE_LIST)
    assert params.directory == "."
    assert params.extension == "md"


def test_parse_search_filename() -> None:
    params = parse_file_params("Cherche Titan_Context.md", Intent.FILE_SEARCH)
    assert params.operation == "search_files"
    assert params.filename == "Titan_Context.md"


def test_parse_search_keyword() -> None:
    params = parse_file_params(
        "Trouve les fichiers qui parlent de TradingView",
        Intent.FILE_SEARCH,
    )
    assert params.keyword == "TradingView"
    assert params.operation == "search_files"


def test_parse_search_todo_keyword() -> None:
    params = parse_file_params("Trouve les TODO dans les fichiers", Intent.FILE_SEARCH)
    assert params.keyword == "TODO"


def test_parse_recursive_search() -> None:
    params = parse_file_params("Cherche récursivement *.py", Intent.FILE_SEARCH)
    assert params.recursive is True


def test_parse_ambiguous_search() -> None:
    params = parse_file_params("Trouve des fichiers", Intent.FILE_SEARCH)
    assert params.ambiguous is True


def test_params_to_tool_dict_list() -> None:
    params = parse_file_params("Liste les fichiers Python dans brain/", Intent.FILE_LIST)
    payload = params_to_tool_dict(params)
    assert payload["action"] == "list_directory"
    assert payload["path"] == "brain"
    assert payload["extension"] == "py"


def test_params_to_tool_dict_search() -> None:
    params = parse_file_params("Cherche Titan_Context.md", Intent.FILE_SEARCH)
    payload = params_to_tool_dict(params)
    assert payload["action"] == "search_files"
    assert "Titan_Context.md" in payload["pattern"]


# ---------------------------------------------------------------------------
# P10B-1504 — DecisionReport enrichment
# ---------------------------------------------------------------------------


def test_decision_report_file_fields_enriched() -> None:
    params = parse_file_params("Liste les fichiers markdown du projet", Intent.FILE_LIST)
    base = ToolDecisionReport(
        intent=Intent.FILE_LIST,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="file_read",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        fallback_action=FallbackAction.EXECUTE_TOOL,
    )
    enriched = enrich_file_decision_context(
        base,
        execution_mode="live",
        file_operation=params.operation,
        directory=params.directory,
        filename=params.filename,
        extension=params.extension,
        keyword=params.keyword,
        recursive=params.recursive,
    )
    assert enriched.file_operation == "list_directory"
    assert enriched.directory == "."
    assert enriched.extension == "md"
    assert enriched.selected_provider == "file_system"
    assert enriched.execution_mode == "live"
    assert enriched.risk_level == RiskLevel.LOW
    assert enriched.confirmation_required is False
    data = enriched.to_dict()
    assert data["file_operation"] == "list_directory"
    assert data["directory"] == "."
    assert data["extension"] == "md"


# ---------------------------------------------------------------------------
# P10B-1502 / P10B-1505 — End-to-end through Brain pipeline
# ---------------------------------------------------------------------------


def test_list_python_files_e2e(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Liste les fichiers Python dans brain/")
    assert result.decision_report is not None
    assert result.decision_report.intent == Intent.FILE_LIST
    assert result.decision_report.file_operation == "list_directory"
    assert result.decision_report.selected_provider == "file_system"
    assert result.tool_results
    assert result.tool_results[0].success
    assert "brain.py" in result.tool_results[0].data
    assert "helper.py" in result.tool_results[0].data


def test_search_by_filename_e2e(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Cherche Titan_Context.md")
    assert result.decision_report.intent == Intent.FILE_SEARCH
    assert result.tool_results[0].success
    assert "Titan_Context.md" in result.tool_results[0].data


def test_search_by_keyword_e2e(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Trouve les fichiers qui parlent de TradingView")
    assert result.tool_results[0].success
    assert "Titan_Context.md" in result.tool_results[0].data


def test_search_todo_e2e(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Trouve les TODO dans les fichiers")
    assert result.tool_results[0].success
    assert "notes.md" in result.tool_results[0].data


def test_list_markdown_e2e(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Liste les fichiers markdown du projet")
    assert result.tool_results[0].success
    assert "Titan_Context.md" in result.tool_results[0].data
    assert "notes.md" in result.tool_results[0].data
    assert "readme.txt" not in result.tool_results[0].data


def test_no_results_clear_message(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Cherche fichier_inexistant_xyz.md")
    assert result.tool_results[0].success
    assert "Aucun fichier" in result.tool_results[0].data


def test_ambiguous_request_clarification(
    mock_agent_llm: MagicMock,
    tmp_path: Path,
) -> None:
    manager = ToolManager(project_root=tmp_path, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Trouve des fichiers")
    assert result.decision_report.fallback_action == FallbackAction.CLARIFICATION
    assert result.tool_results
    assert "Clarification requise" in result.tool_results[0].error


def test_path_traversal_blocked_e2e(
    project_root: Path,
    mock_agent_llm: MagicMock,
) -> None:
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    dispatcher = ToolDispatcher(manager)
    agent_manager = AgentManager(agent_llm=mock_agent_llm)
    orchestrator = TaskOrchestrator(TaskManager(agent_manager), agent_manager)
    orchestrator.task_manager.create_tasks = MagicMock(return_value=[])
    coordinator = ExecutionCoordinator(orchestrator, dispatcher, reasoning=Reasoning())
    result = coordinator.execute("Cherche ../../etc/passwd")
    assert not result.tool_results[0].success


def test_file_write_still_high_risk(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Écris dans le fichier notes.txt contenu: hello")
    if report.selected_tool == "file_write":
        assert report.risk_level == RiskLevel.HIGH
        assert report.confirmation_required is True


def test_recursive_search_provider(
    fs_executor: ProviderExecutor,
    project_root: Path,
) -> None:
    outcome = fs_executor.execute(
        "search_files",
        {
            "directory": ".",
            "pattern": "*.py",
            "recursive": True,
            "execution_mode": ExecutionMode.LIVE.value,
        },
        capability="file_system",
    )
    assert outcome.success
    assert any("brain.py" in match for match in outcome.data.data)


def test_reasoning_file_read_regression() -> None:
    analysis = Reasoning().analyze("Lire le fichier config/settings.py")
    report = analysis["decision_report"]
    assert report.intent == Intent.FILE_READ
    if report.selected_tool == "file_read":
        assert report.file_operation == "read_file"


def test_brain_tool_routing_find_file_regression(engine: ToolDecisionEngine) -> None:
    report = engine.decide("Find Titan_Context.md")
    assert report.intent == Intent.FILE_SEARCH
    assert report.selected_tool == "file_read"
    assert report.selected_provider == "file_system"
