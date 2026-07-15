# =====================================
# Titan Trading Orchestration Tests
# =====================================

"""Planner and orchestrator integration tests for Trading connector (Phase 16.1)."""

from __future__ import annotations

import json

from tools.natural_language_planner import NaturalLanguagePlanner
from tools.orchestration_models import InterpretedToolRequest, OrchestrationStatus
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest


def _trading_analysis(*, action: str, symbol: str = "") -> dict:
    params: dict = {"action": action}
    if symbol:
        params["symbol"] = symbol
    return {
        "tool_requests": [ToolRequest("trading", params)],
        "needs_tool": True,
    }


def test_planner_assigns_auto_allowed_for_get_positions() -> None:
    planner = NaturalLanguagePlanner()
    analysis = _trading_analysis(action="get_positions")
    result = planner.plan("Montre mes positions", analysis)
    assert result.steps
    step = result.steps[0]
    assert step.required_tool == "trading"
    assert step.selected_action == "get_positions"
    assert step.required_permission == PermissionLevel.AUTO_ALLOWED


def test_planner_assigns_confirmation_for_place_order() -> None:
    planner = NaturalLanguagePlanner()
    analysis = _trading_analysis(action="place_order", symbol="NQ")
    result = planner.plan("Place un ordre NQ", analysis)
    step = result.steps[0]
    assert step.selected_action == "place_order"
    assert step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED


def test_orchestrator_routes_trading_get_price() -> None:
    tool_manager = ToolManager(use_runtime_v2=False)
    orchestrator = ToolOrchestrator(tool_manager)
    result = orchestrator.orchestrate(
        InterpretedToolRequest(
            tool_name="trading",
            params={"action": "get_price", "symbol": "NQ"},
        ),
        execute=True,
    )

    assert result.orchestration_status == OrchestrationStatus.COMPLETED
    assert result.selected_tool == "trading"
    assert result.result is not None
    payload = json.loads(result.result.data)
    assert payload["symbol"] == "NQ"
    assert payload["last_price"] is not None


def test_permission_manager_trading_action_resolution() -> None:
    manager = PermissionManager()
    read_result = manager.evaluate("trading", "get_balance")
    order_result = manager.evaluate("trading", "place_order", confirmed=False)
    blocked_result = manager.evaluate("trading", "reset_account")
    assert read_result.level == PermissionLevel.AUTO_ALLOWED
    assert order_result.level == PermissionLevel.CONFIRMATION_REQUIRED
    assert blocked_result.level == PermissionLevel.BLOCKED


def test_orchestrate_plan_trading_positions() -> None:
    tool_manager = ToolManager(use_runtime_v2=False)
    orchestrator = ToolOrchestrator(tool_manager)
    planner = NaturalLanguagePlanner()

    analysis = _trading_analysis(action="get_positions")
    plan_result = planner.plan("Montre mes positions NQ", analysis)
    results = orchestrator.orchestrate_plan(
        plan_result,
        message="Montre mes positions NQ",
    )

    assert len(results) == 1
    assert results[0].orchestration_status == OrchestrationStatus.COMPLETED
    assert results[0].selected_tool == "trading"
