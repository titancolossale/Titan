# =====================================
# Titan Tool Intelligence Tests
# =====================================

"""Unit tests for Tool Intelligence V1 — metadata-driven tool selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.tool_intelligence import (
    ToolExecutionPlan,
    ToolIntelligence,
    ToolIntent,
    build_default_tool_intelligence,
)
from core.tools import ToolLoader, ToolRegistry

CORE_TOOLS_DIR = Path(__file__).resolve().parents[1] / "core" / "tools"


@pytest.fixture
def tool_intelligence() -> ToolIntelligence:
    return build_default_tool_intelligence(scan_paths=[CORE_TOOLS_DIR])


def _tool_ids(plan: ToolExecutionPlan) -> list[str]:
    return [tool.tool_id for tool in plan.selected_tools]


def _action_ids(plan: ToolExecutionPlan, tool_id: str) -> list[str]:
    for selected in plan.selected_tools:
        if selected.tool_id == tool_id:
            return [action.action_id for action in selected.actions]
    return []


def test_single_tool_obsidian_read_notes(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Read my ORR notes")

    assert plan.requires_tools is True
    assert plan.intent in {ToolIntent.READ, ToolIntent.SEARCH}
    assert _tool_ids(plan) == ["obsidian"]
    assert "read" in _action_ids(plan, "obsidian")[0]
    assert plan.confidence >= 0.35
    assert plan.execution_order == ("obsidian",)
    assert plan.selected_tools[0].reason


def test_single_tool_browser_documentation(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Read the FastAPI documentation")

    assert plan.requires_tools is True
    assert _tool_ids(plan) == ["browser"]
    browser_actions = _action_ids(plan, "browser")
    assert browser_actions
    assert any(
        action in browser_actions[0]
        for action in ("extract_text", "fetch_html", "open_url", "page_metadata")
    )
    assert plan.confidence >= 0.35
    assert plan.execution_order == ("browser",)


def test_single_tool_github_recent_commits(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Show recent commits on github")

    assert plan.requires_tools is True
    assert "github" in _tool_ids(plan)
    assert _action_ids(plan, "github")[0] == "list_commits"


def test_single_tool_github_readme(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Read README from github repository")

    assert plan.requires_tools is True
    assert "github" in _tool_ids(plan)
    assert _action_ids(plan, "github")[0] == "read_file"


def test_single_tool_github_code_search(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Find where MissionRuntime is implemented on github")

    assert plan.requires_tools is True
    assert "github" in _tool_ids(plan)
    assert _action_ids(plan, "github")[0] == "search_repository"


def test_multiple_tools_compare_notes_and_docs(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Compare my ORR notes with FastAPI docs")

    assert plan.requires_tools is True
    assert plan.intent == ToolIntent.COMPARE
    assert set(_tool_ids(plan)) == {"obsidian", "browser"}
    assert plan.execution_order[0] == "obsidian"
    assert plan.execution_order[1] == "browser"
    assert len(plan.selected_tools) == 2
    assert plan.confidence >= 0.35


def test_no_tool_conversation_greeting(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Hello")

    assert plan.requires_tools is False
    assert plan.intent == ToolIntent.CONVERSATION
    assert plan.selected_tools == ()
    assert plan.execution_order == ()
    assert plan.confidence >= 0.9


def test_unknown_request_low_confidence(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("xyzzy plugh totally ambiguous")

    assert plan.requires_tools is False
    assert plan.intent == ToolIntent.UNKNOWN
    assert plan.confidence <= 0.4


def test_ambiguous_request_may_select_multiple_or_low_confidence(
    tool_intelligence: ToolIntelligence,
) -> None:
    plan = tool_intelligence.plan("Read something from somewhere")

    assert plan.intent in {ToolIntent.READ, ToolIntent.UNKNOWN}
    if plan.requires_tools:
        assert plan.confidence <= 0.85
    else:
        assert plan.confidence <= 0.4


def test_confidence_scoring_reflects_match_strength(
    tool_intelligence: ToolIntelligence,
) -> None:
    strong = tool_intelligence.plan("Read my ORR notes in Obsidian vault")
    weak = tool_intelligence.plan("Read something maybe")

    assert strong.confidence >= weak.confidence
    assert strong.requires_tools is True


def test_tool_ordering_notes_before_web_on_compare(
    tool_intelligence: ToolIntelligence,
) -> None:
    plan = tool_intelligence.plan(
        "Compare my project notes with the FastAPI documentation online"
    )

    assert plan.intent == ToolIntent.COMPARE
    assert plan.execution_order.index("obsidian") < plan.execution_order.index("browser")


def test_plan_includes_action_reasons(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("List notes in my vault")

    if plan.requires_tools:
        for selected in plan.selected_tools:
            assert selected.reason
            for action in selected.actions:
                assert action.reason
                assert 0.0 <= action.confidence <= 1.0


def test_plan_serializes_to_dict(tool_intelligence: ToolIntelligence) -> None:
    plan = tool_intelligence.plan("Read the FastAPI documentation")
    payload = plan.to_dict()

    assert payload["request"] == "Read the FastAPI documentation"
    assert "intent" in payload
    assert "selected_tools" in payload
    assert "execution_order" in payload
    assert "confidence" in payload


def test_refresh_rebuilds_profiles_after_registry_change() -> None:
    registry = ToolRegistry()
    loader = ToolLoader(registry, scan_paths=[CORE_TOOLS_DIR])
    loader.load()
    intelligence = ToolIntelligence(registry)

    before = intelligence.plan("Read my ORR notes")
    assert "obsidian" in _tool_ids(before)

    registry.disable_tool("obsidian")
    intelligence.refresh()
    after = intelligence.plan("Read my ORR notes")

    assert "obsidian" not in _tool_ids(after)


def test_brain_exposes_plan_tool_execution(brain) -> None:
    plan = brain.plan_tool_execution("Hello")

    assert plan.intent == ToolIntent.CONVERSATION
    assert plan.requires_tools is False
