# =====================================
# Titan Tool Orchestrator Tests
# =====================================

"""Tests for Phase 12.6 Batch 1 — ToolOrchestrator (P126-005)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.decision.intent import Intent
from tools.decision.models import ToolDecisionReport
from tools.decision.obsidian_decision import ObsidianDecision
from tools.orchestration_models import (
    InterpretedToolRequest,
    OrchestrationStatus,
    ToolOrchestrationResult,
)
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest, ToolResult
from tools.tool_enums import RiskLevel


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
    return tmp_path


@pytest.fixture
def tool_manager(project_root: Path) -> ToolManager:
    return ToolManager(project_root=project_root, use_runtime_v2=True)


@pytest.fixture
def orchestrator(tool_manager: ToolManager) -> ToolOrchestrator:
    return ToolOrchestrator(tool_manager)


def _obsidian_report() -> ToolDecisionReport:
    return ToolDecisionReport(
        intent=Intent.OBSIDIAN,
        confidence=0.9,
        tool_required=True,
        candidate_tools=(),
        selected_tool="obsidian",
        decision_reason="Obsidian search",
        risk_level=RiskLevel.LOW,
        confirmation_required=False,
        obsidian_decision=ObsidianDecision.SEARCH_NOTES.value,
        obsidian_action="search_notes",
    )


def test_orchestrator_routes_obsidian_action(orchestrator: ToolOrchestrator) -> None:
    """P126-005: orchestrator routes Obsidian search with auto-allowed permission."""
    request = InterpretedToolRequest(
        tool_name="obsidian",
        params={"action": "search_notes", "query": "titan"},
    )
    result = orchestrator.orchestrate(
        request,
        decision_report=_obsidian_report(),
        execute=False,
    )

    assert result.selected_tool == "obsidian"
    assert result.selected_action == "search_notes"
    assert result.permission_level == PermissionLevel.AUTO_ALLOWED
    assert result.orchestration_status == OrchestrationStatus.SKIPPED


def test_orchestrator_blocks_unsafe_action(orchestrator: ToolOrchestrator) -> None:
    """P126-005: orchestrator blocks unsafe filesystem actions."""
    request = InterpretedToolRequest(
        tool_name="file_read",
        params={"action": "delete_file", "path": "readme.txt"},
    )
    result = orchestrator.orchestrate(request, execute=True)

    assert result.orchestration_status == OrchestrationStatus.BLOCKED
    assert result.permission_level == PermissionLevel.BLOCKED
    assert result.executed is False
    assert result.result is not None
    assert result.result.success is False


def test_orchestrator_pending_confirmation_for_delete(
    orchestrator: ToolOrchestrator,
) -> None:
    """P126-005: orchestrator returns pending confirmation for delete."""
    request = InterpretedToolRequest(
        tool_name="obsidian",
        params={"action": "delete_note", "path": "notes/old.md"},
    )
    result = orchestrator.orchestrate(request)

    assert result.orchestration_status == OrchestrationStatus.PENDING_CONFIRMATION
    assert result.confirmation_required is True
    assert result.executed is False


def test_orchestrator_no_unrelated_tools_started(
    orchestrator: ToolOrchestrator,
) -> None:
    """P126-005: only requested tools are invoked."""
    runtime = orchestrator.tool_manager.runtime
    assert runtime is not None

    from tools.tool_run_models import ToolRunOutcome, ToolRunStatus

    invoke_mock = MagicMock(
        return_value=ToolRunOutcome(
            run_id="test-run",
            status=ToolRunStatus.COMPLETED,
            result=ToolResult(tool_name="obsidian", success=True, data="ok"),
        ),
    )
    runtime.invoke = invoke_mock
    runtime.outcome_to_result = MagicMock(
        return_value=ToolResult(tool_name="obsidian", success=True, data="ok"),
    )

    requests = [
        ToolRequest("obsidian", {"action": "search_notes", "query": "titan"}),
    ]
    results = orchestrator.orchestrate_requests(
        requests,
        decision_report=_obsidian_report(),
    )

    assert len(results) == 1
    assert results[0].selected_tool == "obsidian"
    assert invoke_mock.call_count == 1
    assert invoke_mock.call_args.args[0] == "obsidian"
    assert invoke_mock.call_args.args[1]["action"] == "search_notes"


def test_orchestration_results_to_tool_results_blocked(
    orchestrator: ToolOrchestrator,
) -> None:
    """P126-005: blocked orchestration produces ToolResult for Brain."""
    blocked = ToolOrchestrationResult(
        orchestration_status=OrchestrationStatus.BLOCKED,
        selected_tool="file_read",
        selected_action="delete_file",
        permission_level=PermissionLevel.BLOCKED,
        executed=False,
        confirmation_required=False,
        reason="blocked",
        result=ToolResult(
            tool_name="file_read",
            success=False,
            error="blocked",
        ),
    )
    tool_results = orchestrator.orchestration_results_to_tool_results([blocked])
    assert len(tool_results) == 1
    assert tool_results[0].success is False


def test_orchestrate_requests_respects_permission_manager(
    tool_manager: ToolManager,
) -> None:
    """P126-005: orchestrator uses PermissionManager before execution."""
    permission_manager = PermissionManager()
    orchestrator = ToolOrchestrator(
        tool_manager,
        permission_manager=permission_manager,
    )
    request = InterpretedToolRequest(
        tool_name="file_read",
        params={"action": "read_file", "path": "readme.txt"},
    )
    result = orchestrator.orchestrate(request, execute=False)

    assert result.permission_level == PermissionLevel.AUTO_ALLOWED
    assert result.orchestration_status == OrchestrationStatus.SKIPPED
    assert result.executed is False
