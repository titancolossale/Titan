# =====================================
# Titan Tool Execution Engine Tests
# =====================================

"""Unit tests for Tool Execution Engine V1."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.tool_execution_engine import (
    ToolExecutionEngine,
    build_core_tool_runtime,
    sync_action_runtime,
)
from brain.tool_intelligence import (
    PlannedAction,
    SelectedTool,
    ToolExecutionPlan,
    ToolIntent,
)
from core.actions import Action, ActionDispatcher, ActionRegistry, ActionResult
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import BaseTool, ToolRegistry
from core.tools.obsidian import (
    ObsidianConfig,
    ObsidianTool,
    PERMISSION_LIST_NOTES,
    PERMISSION_READ_NOTE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_TOOLS_DIR = PROJECT_ROOT / "core" / "tools"
SAMPLE_VAULT = PROJECT_ROOT / "sample_vault"


@pytest.fixture
def core_runtime():
    return build_core_tool_runtime(scan_paths=[CORE_TOOLS_DIR])


@pytest.fixture
def engine(core_runtime) -> ToolExecutionEngine:
    return core_runtime.engine


def _planned_action(
    tool_id: str,
    action_id: str,
    **parameters: object,
) -> PlannedAction:
    return PlannedAction(
        tool_id=tool_id,
        action_id=action_id,
        reason="Test planned action.",
        confidence=0.9,
        parameters=dict(parameters),
    )


def _selected_tool(
    tool_id: str,
    name: str,
    category: str,
    actions: list[PlannedAction],
) -> SelectedTool:
    return SelectedTool(
        tool_id=tool_id,
        tool_name=name,
        category=category,
        confidence=0.9,
        reason="Selected for test.",
        actions=tuple(actions),
    )


def _make_plan(
    request: str,
    *,
    selected_tools: tuple[SelectedTool, ...],
    execution_order: tuple[str, ...],
    intent: ToolIntent = ToolIntent.READ,
    requires_tools: bool = True,
) -> ToolExecutionPlan:
    return ToolExecutionPlan(
        request=request,
        intent=intent,
        intent_summary="Test plan.",
        selected_tools=selected_tools,
        execution_order=execution_order,
        confidence=0.9,
        requires_tools=requires_tools,
        reasoning_summary="test",
    )


def test_single_tool_execution(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "List notes",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "list_notes")],
            ),
        ),
        execution_order=("obsidian",),
    )

    result = engine.execute(plan)

    assert result.success is True
    assert len(result.completed_steps) == 1
    assert result.completed_steps[0].tool_id == "obsidian"
    assert result.completed_steps[0].action_id == "list_notes"
    assert result.tool_outputs["obsidian"]["count"] == 3
    assert result.execution_duration >= 0.0
    assert result.messages


def test_multiple_tools_execution(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "Compare notes and calculate",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "list_notes")],
            ),
            _selected_tool(
                "fake_calculator",
                "Fake Calculator",
                "utility",
                [_planned_action("fake_calculator", "add", left=2, right=3)],
            ),
        ),
        execution_order=("obsidian", "fake_calculator"),
        intent=ToolIntent.COMPARE,
    )

    result = engine.execute(plan)

    assert result.success is True
    assert len(result.completed_steps) == 2
    assert [step.tool_id for step in result.completed_steps] == [
        "obsidian",
        "fake_calculator",
    ]
    assert result.tool_outputs["fake_calculator"]["result"] == 5.0


def test_empty_plan(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "Hello",
        selected_tools=(),
        execution_order=(),
        intent=ToolIntent.CONVERSATION,
        requires_tools=False,
    )

    result = engine.execute(plan)

    assert result.success is True
    assert result.completed_steps == ()
    assert result.failed_steps == ()
    assert result.tool_outputs == {}
    assert result.summary_message


def test_tool_failure_stops_dependent_actions_in_block() -> None:
    class FailThenEchoTool(BaseTool):
        @property
        def id(self) -> str:
            return "fail_tool"

        @property
        def name(self) -> str:
            return "Fail Tool"

        @property
        def description(self) -> str:
            return "Fails on demand."

        @property
        def version(self) -> str:
            return "0.1.0"

        @property
        def category(self) -> str:
            return "demo"

        @property
        def requires_confirmation(self) -> bool:
            return False

        @property
        def capabilities(self) -> list[str]:
            return ["demo.fail", "demo.echo"]

        def list_actions(self) -> list[Action]:
            return [
                Action(
                    id="fail",
                    name="Fail",
                    description="Always fail.",
                    tool_id=self.id,
                    permission_id="fail_tool.fail",
                ),
                Action(
                    id="echo",
                    name="Echo",
                    description="Should be skipped.",
                    tool_id=self.id,
                    permission_id="fail_tool.echo",
                ),
            ]

        def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
            if action_id == "fail":
                return ActionResult(success=False, message="boom", errors=["boom"])
            return ActionResult(success=True, data={"echo": "ok"})

        def execute(self, **kwargs: object) -> object:
            return None

    registry = ToolRegistry()
    registry.register_tool(FailThenEchoTool())
    action_registry = ActionRegistry()
    permission_manager = PermissionManager()
    sync_action_runtime(registry, action_registry, permission_manager)
    engine = ToolExecutionEngine(
        ActionDispatcher(registry, action_registry, permission_manager)
    )

    plan = _make_plan(
        "Fail",
        selected_tools=(
            _selected_tool(
                "fail_tool",
                "Fail Tool",
                "demo",
                [
                    _planned_action("fail_tool", "fail"),
                    _planned_action("fail_tool", "echo"),
                ],
            ),
        ),
        execution_order=("fail_tool",),
    )

    result = engine.execute(plan)

    assert result.success is False
    assert len(result.failed_steps) == 1
    assert len(result.skipped_steps) == 1
    assert result.skipped_steps[0].action_id == "echo"


def test_permission_denied_records_failure() -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_READ_NOTE,
            name="Blocked Read",
            description="Blocked.",
            level=PermissionLevel.BLOCKED,
        )
    )
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        action_registry=action_registry,
        auto_connect=True,
    )
    tool_registry.register_tool(tool)
    for perm in permission_manager.list_permissions():
        if not permission_manager.permission_exists(perm.id):
            permission_manager.register_permission(perm)
    sync_action_runtime(tool_registry, action_registry, permission_manager)

    engine = ToolExecutionEngine(
        ActionDispatcher(tool_registry, action_registry, permission_manager)
    )
    plan = _make_plan(
        "Read note",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "read_note", path="welcome.md")],
            ),
        ),
        execution_order=("obsidian",),
    )

    result = engine.execute(plan)

    assert result.success is False
    assert len(result.failed_steps) == 1
    assert result.failed_steps[0].result.errors
    assert "permission" in result.failed_steps[0].result.message.lower()


def test_unknown_tool_stops_execution(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "Missing tool",
        selected_tools=(),
        execution_order=("missing_tool",),
        intent=ToolIntent.UNKNOWN,
    )

    result = engine.execute(plan)

    assert result.success is False
    assert result.stopped_early is True
    assert len(result.failed_steps) == 1
    assert result.failed_steps[0].tool_id == "missing_tool"


def test_execution_ordering(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "Compare",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "list_notes")],
            ),
            _selected_tool(
                "fake_calculator",
                "Fake Calculator",
                "utility",
                [_planned_action("fake_calculator", "subtract", left=5, right=2)],
            ),
        ),
        execution_order=("obsidian", "fake_calculator"),
        intent=ToolIntent.COMPARE,
    )

    result = engine.execute(plan)

    assert [step.tool_id for step in result.completed_steps] == [
        "obsidian",
        "fake_calculator",
    ]
    assert [step.block_index for step in result.completed_steps] == [0, 1]


def test_compare_continues_after_independent_block_failure() -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_READ_NOTE,
            name="Blocked Read",
            description="Blocked.",
            level=PermissionLevel.BLOCKED,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_LIST_NOTES,
            name="List Notes",
            description="Allowed.",
            level=PermissionLevel.SAFE,
        )
    )
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    obsidian = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        action_registry=action_registry,
        auto_connect=True,
    )
    tool_registry.register_tool(obsidian)

    from core.tools.fake_calculator_tool import FakeCalculatorTool

    tool_registry.register_tool(FakeCalculatorTool())
    sync_action_runtime(tool_registry, action_registry, permission_manager)

    engine = ToolExecutionEngine(
        ActionDispatcher(tool_registry, action_registry, permission_manager)
    )
    plan = _make_plan(
        "Compare note and math",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "read_note", path="welcome.md")],
            ),
            _selected_tool(
                "fake_calculator",
                "Fake Calculator",
                "utility",
                [_planned_action("fake_calculator", "add", left=1, right=1)],
            ),
        ),
        execution_order=("obsidian", "fake_calculator"),
        intent=ToolIntent.COMPARE,
    )

    result = engine.execute(plan)

    assert len(result.failed_steps) == 1
    assert len(result.completed_steps) == 1
    assert result.completed_steps[0].tool_id == "fake_calculator"
    assert result.stopped_early is False


def test_aggregation_collects_outputs_and_messages(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "Read welcome",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "read_note", path="welcome.md")],
            ),
        ),
        execution_order=("obsidian",),
    )

    result = engine.execute(plan)

    assert "obsidian" in result.tool_outputs
    assert result.tool_outputs["obsidian"]["note"]["relative_path"] == "welcome.md"
    assert any("obsidian" in message for message in result.messages)
    assert result.summary_message


def test_result_serializes_to_dict(engine: ToolExecutionEngine) -> None:
    plan = _make_plan(
        "List",
        selected_tools=(
            _selected_tool(
                "obsidian",
                "Obsidian",
                "notes",
                [_planned_action("obsidian", "list_notes")],
            ),
        ),
        execution_order=("obsidian",),
    )

    payload = engine.execute(plan).to_dict()

    assert payload["success"] is True
    assert payload["completed_steps"]
    assert "execution_duration" in payload
    assert "tool_outputs" in payload


def test_brain_execute_request(brain) -> None:
    result = brain.execute_request("Hello")

    assert result.request == "Hello"
    assert result.plan.intent == ToolIntent.CONVERSATION
    assert result.execution.success is True
    assert result.success is True


def test_brain_execute_request_runs_obsidian_when_planned(brain) -> None:
    result = brain.execute_request("List notes in my vault")

    if result.plan.requires_tools and "obsidian" in result.plan.execution_order:
        assert any(
            step.tool_id == "obsidian"
            for step in result.execution.completed_steps
        ) or result.execution.failed_steps
