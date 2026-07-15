# =====================================
# Titan File System Provider Tests
# =====================================

"""Tests for Phase 10B Batch 5 — FileSystemProvider (P10B-501–P10B-506)."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.reasoning import Reasoning
from tools.decision.execution_context import enrich_decision_report_from_result
from tools.decision.intent import Intent
from tools.decision.models import ToolDecisionReport, enrich_file_decision_context
from tools.decision.tool_decision_engine import ToolDecisionEngine
from tools.file_read_tool import FileReadTool
from tools.file_write_tool import FileWriteTool
from tools.health_monitor import HealthMonitor
from tools.providers.file_system_provider import LocalFileSystemProvider
from tools.providers.provider_executor import ProviderExecutor
from tools.providers.provider_registry import ProviderRegistry
from tools.tool_enums import ExecutionMode, RiskLevel
from tools.tool_manager import ToolManager
from tools.tool_run_models import ToolExecutionContext, ToolRunStatus


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Isolated project tree for filesystem provider tests."""
    (project_root := tmp_path / "workspace").mkdir()
    (project_root / "subdir").mkdir()
    (project_root / "sample.txt").write_text("hello titan", encoding="utf-8")
    (project_root / "subdir" / "nested.py").write_text("x = 1", encoding="utf-8")
    return project_root


@pytest.fixture
def fs_registry(project_root: Path) -> ProviderRegistry:
    registry = ProviderRegistry(runtime_version="0.10.0")
    registry.register(LocalFileSystemProvider(project_root))
    return registry


@pytest.fixture
def fs_executor(fs_registry: ProviderRegistry) -> ProviderExecutor:
    return ProviderExecutor(registry=fs_registry, health_monitor=HealthMonitor())


def test_read_file_success(fs_executor: ProviderExecutor) -> None:
    """P10B-502: read_file returns file content."""
    outcome = fs_executor.execute(
        "read_file",
        {"path": "sample.txt", "execution_mode": ExecutionMode.LIVE.value},
        capability="file_system",
    )
    assert outcome.success
    assert outcome.provider_id == "file_system"
    assert outcome.data.data == "hello titan"


def test_list_directory(fs_executor: ProviderExecutor) -> None:
    """P10B-502: list_directory returns entry names."""
    outcome = fs_executor.execute(
        "list_directory",
        {"path": ".", "execution_mode": ExecutionMode.LIVE.value},
        capability="file_system",
    )
    assert outcome.success
    assert "sample.txt" in outcome.data.data
    assert "subdir" in outcome.data.data


def test_file_exists(fs_executor: ProviderExecutor) -> None:
    """P10B-502: file_exists reports presence."""
    outcome = fs_executor.execute(
        "file_exists",
        {"path": "sample.txt", "execution_mode": ExecutionMode.LIVE.value},
        capability="file_system",
    )
    assert outcome.success
    assert outcome.data.data["exists"] is True


def test_search_files(fs_executor: ProviderExecutor) -> None:
    """P10B-502: search_files finds matches under allowed root."""
    outcome = fs_executor.execute(
        "search_files",
        {
            "directory": ".",
            "pattern": "*.py",
            "execution_mode": ExecutionMode.LIVE.value,
        },
        capability="file_system",
    )
    assert outcome.success
    assert any("nested.py" in match for match in outcome.data.data)


def test_get_metadata(fs_executor: ProviderExecutor) -> None:
    """P10B-502: get_metadata returns structured file info."""
    outcome = fs_executor.execute(
        "get_metadata",
        {"path": "sample.txt", "execution_mode": ExecutionMode.LIVE.value},
        capability="file_system",
    )
    assert outcome.success
    metadata = outcome.data.data
    assert metadata["exists"] is True
    assert metadata["is_file"] is True
    assert metadata["size_bytes"] > 0


def test_path_traversal_blocked(fs_executor: ProviderExecutor) -> None:
    """P10B-503: paths outside project root are rejected."""
    outcome = fs_executor.execute(
        "read_file",
        {"path": "../../etc/passwd", "execution_mode": ExecutionMode.LIVE.value},
        capability="file_system",
    )
    assert not outcome.success
    assert outcome.error
    assert "refusé" in outcome.error.lower() or "autorisé" in outcome.error.lower()


def test_write_blocked_in_simulation(
    fs_executor: ProviderExecutor,
    project_root: Path,
) -> None:
    """P10B-504: SIMULATION mode does not modify disk."""
    target = project_root / "simulated.txt"
    outcome = fs_executor.execute(
        "write_file",
        {
            "path": "simulated.txt",
            "content": "secret",
            "dry_run": False,
            "execution_mode": ExecutionMode.SIMULATION.value,
        },
        capability="file_system",
    )
    assert outcome.success
    assert outcome.data.simulated is True
    assert not target.exists()


def test_write_blocked_in_mock(
    fs_executor: ProviderExecutor,
    project_root: Path,
) -> None:
    """P10B-504: MOCK mode does not modify disk."""
    target = project_root / "mock.txt"
    outcome = fs_executor.execute(
        "write_file",
        {
            "path": "mock.txt",
            "content": "secret",
            "dry_run": False,
            "execution_mode": ExecutionMode.MOCK.value,
        },
        capability="file_system",
    )
    assert outcome.success
    assert outcome.data.simulated is True
    assert not target.exists()


def test_write_file_live_persists(
    fs_executor: ProviderExecutor,
    project_root: Path,
) -> None:
    """P10B-502: LIVE write persists when not simulated."""
    outcome = fs_executor.execute(
        "write_file",
        {
            "path": "live.txt",
            "content": "persisted",
            "dry_run": False,
            "execution_mode": ExecutionMode.LIVE.value,
        },
        capability="file_system",
    )
    assert outcome.success
    assert not outcome.data.simulated
    assert (project_root / "live.txt").read_text(encoding="utf-8") == "persisted"


def test_write_file_confirmation_required_via_runtime(project_root: Path) -> None:
    """P10B-504: file_write requires confirmation in LIVE runtime."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    ctx = ToolExecutionContext(
        caller="coding",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.LIVE,
    )
    outcome = manager.runtime.invoke(
        "file_write",
        {"path": "confirmed.txt", "content": "data", "dry_run": False},
        ctx,
    )
    assert outcome.status == ToolRunStatus.PENDING_CONFIRMATION
    assert outcome.confirmation_request is not None


def test_file_read_no_confirmation_in_live(project_root: Path) -> None:
    """P10B-504: reads proceed without confirmation in LIVE."""
    manager = ToolManager(project_root=project_root, use_runtime_v2=True)
    (project_root / "read.txt").write_text("content", encoding="utf-8")
    ctx = ToolExecutionContext(
        caller="coding",
        user="Nolan",
        session_id="s1",
        turn_id="t1",
        execution_mode=ExecutionMode.LIVE,
    )
    outcome = manager.runtime.invoke("file_read", {"path": "read.txt"}, ctx)
    assert outcome.status == ToolRunStatus.COMPLETED
    assert outcome.result is not None
    assert outcome.result.success


def test_decision_report_file_fields() -> None:
    """P10B-505: DecisionReport includes filesystem metadata."""
    report = ToolDecisionReport(
        intent=Intent.FILE,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="file_write",
        decision_reason="test",
        risk_level=RiskLevel.HIGH,
        confirmation_required=True,
    )
    enriched = enrich_file_decision_context(
        report,
        target_path="config/settings.py",
        execution_mode="live",
    )
    assert enriched.selected_provider == "file_system"
    assert enriched.file_operation == "write_file"
    assert enriched.target_path == "config/settings.py"
    assert enriched.execution_mode == "live"
    assert enriched.risk_level == RiskLevel.HIGH
    assert enriched.confirmation_required is True


def test_decision_report_enriched_from_tool_result() -> None:
    """P10B-505: Provider execution enriches filesystem fields on DecisionReport."""
    report = ToolDecisionReport(
        intent=Intent.FILE,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="file_read",
        decision_reason="test",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
    )
    enriched = enrich_decision_report_from_result(
        report,
        {
            "provider_id": "file_system",
            "provider_score": 100.0,
            "provider_health": "online",
            "provider_version": "1.0.0",
            "execution_path": ["file_system"],
            "duration_ms": 2.5,
            "file_operation": "read_file",
            "target_path": "sample.txt",
            "execution_mode": "live",
        },
    )
    assert enriched is not None
    assert enriched.selected_provider == "file_system"
    assert enriched.file_operation == "read_file"
    assert enriched.target_path == "sample.txt"
    assert enriched.execution_mode == "live"


def test_legacy_file_read_without_executor(project_root: Path) -> None:
    """Backward compatibility: FileReadTool works without ProviderExecutor."""
    tool = FileReadTool(project_root)
    result = tool.run(path="sample.txt")
    assert result.success
    assert result.data == "hello titan"


def test_legacy_file_write_dry_run_without_executor(project_root: Path) -> None:
    """Backward compatibility: FileWriteTool dry-run without ProviderExecutor."""
    tool = FileWriteTool(project_root)
    target = project_root / "legacy.txt"
    result = tool.run(path="legacy.txt", content="nope")
    assert result.success
    assert "[dry-run]" in result.data
    assert not target.exists()


def test_file_read_tool_via_provider(
    fs_executor: ProviderExecutor,
    project_root: Path,
) -> None:
    """P10B-501: FileReadTool routes through ProviderExecutor."""
    tool = FileReadTool(project_root, provider_executor=fs_executor)
    result = tool.run(
        path="sample.txt",
        _execution_context={"execution_mode": ExecutionMode.LIVE.value},
    )
    assert result.success
    assert result.metadata.get("provider_id") == "file_system"
    assert result.metadata.get("file_operation") == "read_file"


def test_decision_engine_file_write_high_risk() -> None:
    """P10B-503: file_write classified as HIGH risk."""
    report = ToolDecisionEngine().decide(
        "Écris dans le fichier notes.txt contenu: hello",
    )
    if report.selected_tool == "file_write":
        assert report.risk_level == RiskLevel.HIGH
        assert report.confirmation_required is True


def test_reasoning_enriches_file_decision_report() -> None:
    """P10B-505: Reasoning attaches filesystem context to decision report."""
    analysis = Reasoning().analyze("Lire le fichier config/settings.py")
    report = analysis["decision_report"]
    if report.selected_tool == "file_read":
        assert report.file_operation == "read_file"
        assert report.selected_provider == "file_system"
        assert report.target_path == "config/settings.py"


def test_provider_metadata_registered(fs_registry: ProviderRegistry) -> None:
    """P10B-501: file_system provider exposes metadata via registry."""
    meta = fs_registry.get_metadata("file_system")
    assert meta is not None
    assert "file_system" in meta.capabilities
    assert "read_file" in meta.supported_actions
    assert "write_file" in meta.supported_actions


def test_regression_suite_imports() -> None:
    """Regression: filesystem provider module imports cleanly."""
    from tools.providers.file_system_provider import FileSystemProvider, LocalFileSystemProvider

    assert issubclass(LocalFileSystemProvider, FileSystemProvider)
