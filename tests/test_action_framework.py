# =====================================
# Titan Action Framework Tests
# =====================================

"""Tests for the universal action execution framework."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.actions import (
    Action,
    ActionAlreadyExistsError,
    ActionDispatcher,
    ActionNotFoundError,
    ActionRegistry,
    ActionResult,
)
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolNotRegisteredError, ToolRegistry
from core.tools.obsidian import (
    ObsidianConfig,
    ObsidianTool,
    PERMISSION_LIST_FOLDERS,
    PERMISSION_LIST_NOTES,
    PERMISSION_READ_NOTE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VAULT = PROJECT_ROOT / "sample_vault"


@pytest.fixture
def permission_manager() -> PermissionManager:
    manager = PermissionManager()
    for permission_id, name in (
        (PERMISSION_READ_NOTE, "Read Note"),
        (PERMISSION_LIST_NOTES, "List Notes"),
        (PERMISSION_LIST_FOLDERS, "List Folders"),
    ):
        manager.register_permission(
            Permission(
                id=permission_id,
                name=name,
                description="Test permission.",
                level=PermissionLevel.SAFE,
            )
        )
    return manager


@pytest.fixture
def action_registry() -> ActionRegistry:
    return ActionRegistry()


@pytest.fixture
def tool_registry(
    permission_manager: PermissionManager,
    action_registry: ActionRegistry,
) -> ToolRegistry:
    registry = ToolRegistry()
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        action_registry=action_registry,
        auto_connect=True,
    )
    registry.register_tool(tool)
    return registry


@pytest.fixture
def dispatcher(
    tool_registry: ToolRegistry,
    action_registry: ActionRegistry,
    permission_manager: PermissionManager,
) -> ActionDispatcher:
    return ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )


def test_action_registration(action_registry: ActionRegistry) -> None:
    action = Action(
        id="read_note",
        name="Read Note",
        description="Read a note.",
        tool_id="obsidian",
        permission_id=PERMISSION_READ_NOTE,
        parameters={"path": {"type": "string"}},
        metadata={"capability": "read_notes"},
    )

    action_registry.register_action(action)

    assert action_registry.action_exists("obsidian", "read_note")
    assert action_registry.get_action("obsidian", "read_note") == action
    assert action_registry.list_actions() == [action]
    assert action_registry.list_actions_by_tool("obsidian") == [action]


def test_action_registration_duplicate_raises(action_registry: ActionRegistry) -> None:
    action = Action(
        id="read_note",
        name="Read Note",
        description="Read a note.",
        tool_id="obsidian",
        permission_id=PERMISSION_READ_NOTE,
    )
    action_registry.register_action(action)

    with pytest.raises(ActionAlreadyExistsError, match="obsidian.read_note"):
        action_registry.register_action(action)


def test_obsidian_tool_registers_actions(action_registry: ActionRegistry) -> None:
    ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        action_registry=action_registry,
    )

    action_ids = {action.id for action in action_registry.list_actions_by_tool("obsidian")}
    assert action_ids == {
        "read_note",
        "list_notes",
        "list_folders",
        "metadata",
        "create_note",
        "edit_note",
        "append_note",
        "replace_note",
        "delete_note",
        "rename_note",
        "move_note",
        "create_folder",
        "delete_folder",
    }


def test_action_listing_from_tool(
    permission_manager: PermissionManager,
    action_registry: ActionRegistry,
) -> None:
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        action_registry=action_registry,
    )

    actions = tool.list_actions()
    assert len(actions) == 13
    assert {action.id for action in actions} == {
        "read_note",
        "list_notes",
        "list_folders",
        "metadata",
        "create_note",
        "edit_note",
        "append_note",
        "replace_note",
        "delete_note",
        "rename_note",
        "move_note",
        "create_folder",
        "delete_folder",
    }


def test_action_metadata(
    permission_manager: PermissionManager,
    action_registry: ActionRegistry,
) -> None:
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        action_registry=action_registry,
    )

    read_action = next(action for action in tool.list_actions() if action.id == "read_note")

    assert read_action.tool_id == "obsidian"
    assert read_action.permission_id == PERMISSION_READ_NOTE
    assert read_action.parameters["path"]["type"] == "string"
    assert read_action.metadata["capability"] == "read_notes"


def test_dispatch_unknown_tool_raises(dispatcher: ActionDispatcher) -> None:
    with pytest.raises(ToolNotRegisteredError, match="missing_tool"):
        dispatcher.dispatch("missing_tool", "read_note", {"path": "welcome.md"})


def test_dispatch_unknown_action_raises(dispatcher: ActionDispatcher) -> None:
    with pytest.raises(ActionNotFoundError, match="obsidian.sync_graph"):
        dispatcher.dispatch("obsidian", "sync_graph", {})


def test_dispatch_permission_denied(
    action_registry: ActionRegistry,
) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_READ_NOTE,
            name="Blocked Read",
            description="Blocked for test.",
            level=PermissionLevel.BLOCKED,
        )
    )
    for permission_id, name in (
        (PERMISSION_LIST_NOTES, "List Notes"),
        (PERMISSION_LIST_FOLDERS, "List Folders"),
    ):
        permission_manager.register_permission(
            Permission(
                id=permission_id,
                name=name,
                description="Allowed.",
                level=PermissionLevel.SAFE,
            )
        )

    tool_registry = ToolRegistry()
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        action_registry=action_registry,
        auto_connect=True,
    )
    tool_registry.register_tool(tool)

    dispatcher = ActionDispatcher(
        tool_registry=tool_registry,
        action_registry=action_registry,
        permission_manager=permission_manager,
    )

    result = dispatcher.dispatch("obsidian", "read_note", {"path": "welcome.md"})

    assert result.success is False
    assert result.errors
    assert result.metadata["permission_id"] == PERMISSION_READ_NOTE


def test_dispatch_successful_read_note(dispatcher: ActionDispatcher) -> None:
    result = dispatcher.dispatch("obsidian", "read_note", {"path": "welcome.md"})

    assert result.success is True
    assert result.execution_time >= 0.0
    assert result.data["action"] == "read_note"
    assert result.data["note"]["relative_path"] == "welcome.md"
    assert result.metadata["tool_id"] == "obsidian"
    assert result.metadata["action_id"] == "read_note"


def test_dispatch_successful_list_notes(dispatcher: ActionDispatcher) -> None:
    result = dispatcher.dispatch("obsidian", "list_notes", {})

    assert result.success is True
    assert result.data["count"] == 3
    assert "welcome.md" in result.data["files"]


def test_dispatch_successful_list_folders(dispatcher: ActionDispatcher) -> None:
    result = dispatcher.dispatch("obsidian", "list_folders", {})

    assert result.success is True
    assert "projects" in result.data["folders"]
    assert "daily" in result.data["folders"]


def test_dispatch_successful_metadata(dispatcher: ActionDispatcher) -> None:
    result = dispatcher.dispatch(
        "obsidian",
        "metadata",
        {"path": "daily/journal.md"},
    )

    assert result.success is True
    assert result.data["metadata"]["relative_path"] == "daily/journal.md"


def test_execute_action_returns_action_result(
    permission_manager: PermissionManager,
) -> None:
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        auto_connect=True,
    )

    result = tool.execute_action("list_notes")

    assert isinstance(result, ActionResult)
    assert result.success is True
    assert result.data["count"] == 3


def test_legacy_execute_still_works(
    permission_manager: PermissionManager,
) -> None:
    tool = ObsidianTool(
        config=ObsidianConfig.for_vault(SAMPLE_VAULT),
        permission_manager=permission_manager,
        auto_connect=True,
    )

    result = tool.execute(action="read_note", path="welcome.md")

    assert result["action"] == "read_note"
    assert result["note"]["relative_path"] == "welcome.md"
