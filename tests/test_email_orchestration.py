# =====================================
# Titan Email Orchestration Tests
# =====================================

"""Planner and orchestrator integration tests for Email connector (Phase 15.1)."""

from __future__ import annotations

import json

from tools.natural_language_planner import NaturalLanguagePlanner
from tools.orchestration_models import InterpretedToolRequest, OrchestrationStatus
from tools.permission_manager import PermissionLevel, PermissionManager
from tools.tool_manager import ToolManager
from tools.tool_orchestrator import ToolOrchestrator
from tools.tool_result import ToolRequest


def _email_analysis(*, action: str, query: str = "") -> dict:
    params: dict = {"action": action}
    if query:
        params["query"] = query
    return {
        "tool_requests": [ToolRequest("email", params)],
        "needs_tool": True,
    }


def test_planner_assigns_auto_allowed_for_list_emails() -> None:
    planner = NaturalLanguagePlanner()
    analysis = _email_analysis(action="list_emails")
    result = planner.plan("Liste mes emails", analysis)
    assert result.steps
    step = result.steps[0]
    assert step.required_tool == "email"
    assert step.selected_action == "list_emails"
    assert step.required_permission == PermissionLevel.AUTO_ALLOWED


def test_planner_assigns_confirmation_for_send_email() -> None:
    planner = NaturalLanguagePlanner()
    analysis = _email_analysis(action="send_email")
    result = planner.plan("Envoie un email", analysis)
    step = result.steps[0]
    assert step.selected_action == "send_email"
    assert step.required_permission == PermissionLevel.CONFIRMATION_REQUIRED


def test_orchestrator_routes_email_list_action() -> None:
    tool_manager = ToolManager(use_runtime_v2=False)
    orchestrator = ToolOrchestrator(tool_manager)
    result = orchestrator.orchestrate(
        InterpretedToolRequest(
            tool_name="email",
            params={"action": "list_emails"},
        ),
        execute=True,
    )

    assert result.orchestration_status == OrchestrationStatus.COMPLETED
    assert result.selected_tool == "email"
    assert result.result is not None
    payload = json.loads(result.result.data)
    assert payload["emails"]


def test_permission_manager_email_action_resolution() -> None:
    manager = PermissionManager()
    read_result = manager.evaluate("email", "read_email")
    send_result = manager.evaluate("email", "send_email", confirmed=False)
    assert read_result.level == PermissionLevel.AUTO_ALLOWED
    assert send_result.level == PermissionLevel.CONFIRMATION_REQUIRED


def test_orchestrate_plan_email_search() -> None:
    tool_manager = ToolManager(use_runtime_v2=False)
    orchestrator = ToolOrchestrator(tool_manager)
    planner = NaturalLanguagePlanner()

    analysis = _email_analysis(action="search_emails", query="Titan")
    plan_result = planner.plan("Cherche Titan dans mes emails", analysis)
    results = orchestrator.orchestrate_plan(
        plan_result,
        message="Cherche Titan dans mes emails",
    )

    assert len(results) == 1
    assert results[0].orchestration_status == OrchestrationStatus.COMPLETED
    assert results[0].selected_tool == "email"
