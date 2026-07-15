# =====================================
# Titan Obsidian Write Operations Tests
# =====================================

"""Comprehensive tests for Obsidian vault write operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.actions import ActionDispatcher
from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools import ToolRegistry
from core.tools.obsidian import (
    ObsidianClient,
    ObsidianConfig,
    ObsidianFolderNotEmptyError,
    ObsidianFolderNotFoundError,
    ObsidianInvalidPathError,
    ObsidianNoteExistsError,
    ObsidianNoteNotFoundError,
    ObsidianPathTraversalError,
    ObsidianPermissionDeniedError,
    ObsidianTool,
    PERMISSION_CREATE_NOTE,
    PERMISSION_DELETE_FOLDER,
    PERMISSION_DELETE_NOTE,
    PERMISSION_EDIT_NOTE,
    PERMISSION_MANAGE_FOLDERS,
    PERMISSION_READ_NOTE,
    VAULT_BACKUP_DIR,
)
from core.actions import ActionRegistry


@pytest.fixture
def write_vault(tmp_path: Path) -> Path:
    """Create an isolated vault with a starter note."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "starter.md").write_text("# Starter\n\nOriginal body.\n", encoding="utf-8")
    (vault / "projects").mkdir()
    (vault / "projects" / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    return vault


@pytest.fixture
def write_config(write_vault: Path) -> ObsidianConfig:
    return ObsidianConfig.for_vault(write_vault)


@pytest.fixture
def write_client(write_config: ObsidianConfig) -> ObsidianClient:
    client = ObsidianClient(write_config)
    client.connect()
    yield client
    client.disconnect()


def _register_write_permissions(manager: PermissionManager) -> None:
    """Register write permissions as SAFE so tests can execute mutations."""
    permissions = (
        (PERMISSION_READ_NOTE, "Read"),
        (PERMISSION_CREATE_NOTE, "Create"),
        (PERMISSION_EDIT_NOTE, "Edit"),
        (PERMISSION_DELETE_NOTE, "Delete Note"),
        (PERMISSION_MANAGE_FOLDERS, "Manage Folders"),
        (PERMISSION_DELETE_FOLDER, "Delete Folder"),
    )
    for permission_id, name in permissions:
        manager.register_permission(
            Permission(
                id=permission_id,
                name=name,
                description="Test permission.",
                level=PermissionLevel.SAFE,
            )
        )


@pytest.fixture
def write_tool(write_config: ObsidianConfig) -> ObsidianTool:
    permission_manager = PermissionManager()
    _register_write_permissions(permission_manager)
    tool = ObsidianTool(
        config=write_config,
        permission_manager=permission_manager,
        auto_connect=True,
    )
    yield tool
    tool.disconnect()


def test_create_note(write_client: ObsidianClient) -> None:
    note = write_client.create_note("ideas/new-idea.md", "# Idea\n")

    assert note.relative_path == "ideas/new-idea.md"
    assert note.content == "# Idea\n"
    assert write_client.note_exists("ideas/new-idea.md")


def test_create_note_already_exists(write_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianNoteExistsError):
        write_client.create_note("starter.md", "duplicate")


def test_edit_note_overwrite(write_client: ObsidianClient) -> None:
    note = write_client.edit_note("starter.md", "# Updated\n\nNew body.")

    assert "Updated" in note.content
    assert "New body." in note.content
    backups = list((write_client.vault_root / VAULT_BACKUP_DIR).iterdir())
    assert len(backups) == 1


def test_append_note(write_client: ObsidianClient) -> None:
    note = write_client.append_note("starter.md", "Appended line.")

    assert "Original body." in note.content
    assert "Appended line." in note.content


def test_replace_note_selected_text(write_client: ObsidianClient) -> None:
    note = write_client.replace_note(
        "starter.md",
        search="Original body.",
        replacement="Replaced body.",
    )

    assert "Replaced body." in note.content
    assert "Original body." not in note.content
    backups = list((write_client.vault_root / VAULT_BACKUP_DIR).iterdir())
    assert len(backups) == 1


def test_replace_note_missing_search_raises(write_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianInvalidPathError):
        write_client.replace_note(
            "starter.md",
            search="missing text",
            replacement="x",
        )


def test_rename_note(write_client: ObsidianClient) -> None:
    result = write_client.rename_note("starter.md", "renamed-starter.md")

    assert result["source_path"] == "starter.md"
    assert result["destination_path"] == "renamed-starter.md"
    assert write_client.note_exists("renamed-starter.md")
    assert not write_client.note_exists("starter.md")
    assert (write_client.vault_root / VAULT_BACKUP_DIR).exists()


def test_move_note(write_client: ObsidianClient) -> None:
    result = write_client.move_note("projects/alpha.md", "archive")

    assert result["destination_path"] == "archive/alpha.md"
    assert write_client.note_exists("archive/alpha.md")
    assert not write_client.note_exists("projects/alpha.md")


def test_delete_note(write_client: ObsidianClient) -> None:
    result = write_client.delete_note("projects/alpha.md")

    assert result["deleted"] is True
    assert result["backup_path"].startswith(f"{VAULT_BACKUP_DIR}/")
    assert not write_client.note_exists("projects/alpha.md")


def test_create_folder(write_client: ObsidianClient) -> None:
    result = write_client.create_folder("inbox/drafts")

    assert result["created"] is True
    assert result["folder_path"] == "inbox/drafts"
    assert (write_client.vault_root / "inbox" / "drafts").is_dir()


def test_delete_folder(write_client: ObsidianClient) -> None:
    write_client.create_folder("temp-empty")
    result = write_client.delete_folder("temp-empty")

    assert result["deleted"] is True
    assert result["backup_path"].startswith(f"{VAULT_BACKUP_DIR}/")
    assert not (write_client.vault_root / "temp-empty").exists()


def test_delete_non_empty_folder_raises(write_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianFolderNotEmptyError):
        write_client.delete_folder("projects")


def test_delete_missing_folder_raises(write_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianFolderNotFoundError):
        write_client.delete_folder("missing-folder")


def test_missing_note_raises(write_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianNoteNotFoundError):
        write_client.edit_note("missing.md", "content")


def test_invalid_path_traversal_blocked(write_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianPathTraversalError):
        write_client.create_note("../escape.md", "bad")

    with pytest.raises(ObsidianPathTraversalError):
        write_client.normalize_relative_path("C:/outside/path.md")


def test_tool_execute_create_note(write_tool: ObsidianTool) -> None:
    result = write_tool.execute(
        action="create_note",
        path="notes/test.md",
        content="# Test\n",
    )

    assert result["created"] is True
    assert result["note"]["relative_path"] == "notes/test.md"


def test_tool_execute_append_note(write_tool: ObsidianTool) -> None:
    result = write_tool.execute(
        action="append_note",
        path="starter.md",
        content="Extra paragraph.",
    )

    assert "Extra paragraph." in result["note"]["content"]


def test_tool_execute_replace_note(write_tool: ObsidianTool) -> None:
    result = write_tool.execute(
        action="replace_note",
        path="starter.md",
        search="Original body.",
        replacement="Changed body.",
    )

    assert result["replacement"] == "Changed body."


def test_tool_execute_rename_and_move(write_tool: ObsidianTool) -> None:
    rename = write_tool.execute(
        action="rename_note",
        path="starter.md",
        new_path="daily/starter.md",
    )
    assert rename["destination_path"] == "daily/starter.md"

    move = write_tool.execute(
        action="move_note",
        path="daily/starter.md",
        folder="archive",
    )
    assert move["destination_path"] == "archive/starter.md"


def test_tool_execute_delete_note(write_tool: ObsidianTool) -> None:
    write_tool.execute(action="create_note", path="temp.md", content="temp")
    result = write_tool.execute(action="delete_note", path="temp.md")

    assert result["deleted"] is True
    assert result["backup_path"].startswith(f"{VAULT_BACKUP_DIR}/")


def test_tool_execute_folder_operations(write_tool: ObsidianTool) -> None:
    created = write_tool.execute(action="create_folder", folder="scratch")
    assert created["folder_path"] == "scratch"

    deleted = write_tool.execute(action="delete_folder", folder="scratch")
    assert deleted["deleted"] is True


def test_permission_denied_for_create_note(write_config: ObsidianConfig) -> None:
    permission_manager = PermissionManager()
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_CREATE_NOTE,
            name="Blocked Create",
            description="Blocked.",
            level=PermissionLevel.BLOCKED,
        )
    )
    tool = ObsidianTool(
        config=write_config,
        permission_manager=permission_manager,
        auto_connect=True,
    )

    with pytest.raises(ObsidianPermissionDeniedError):
        tool.execute(action="create_note", path="blocked.md", content="x")


def test_permission_denied_for_delete_note(write_config: ObsidianConfig) -> None:
    permission_manager = PermissionManager()
    _register_write_permissions(permission_manager)
    permission_manager.remove_permission(PERMISSION_DELETE_NOTE)
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_DELETE_NOTE,
            name="Blocked Delete",
            description="Blocked.",
            level=PermissionLevel.BLOCKED,
        )
    )
    tool = ObsidianTool(
        config=write_config,
        permission_manager=permission_manager,
        auto_connect=True,
    )

    with pytest.raises(ObsidianPermissionDeniedError):
        tool.execute(action="delete_note", path="starter.md")


def test_dispatcher_write_action_returns_action_result(
    write_config: ObsidianConfig,
) -> None:
    permission_manager = PermissionManager()
    _register_write_permissions(permission_manager)
    action_registry = ActionRegistry()
    tool_registry = ToolRegistry()
    tool = ObsidianTool(
        config=write_config,
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

    result = dispatcher.dispatch(
        "obsidian",
        "create_note",
        {"path": "dispatcher.md", "content": "# Dispatch\n"},
    )

    assert result.success is True
    assert result.data["note"]["relative_path"] == "dispatcher.md"


def test_backup_created_before_destructive_replace(write_tool: ObsidianTool) -> None:
    write_tool.execute(
        action="replace_note",
        path="starter.md",
        search="Original body.",
        replacement="Backup check.",
    )

    backup_dir = write_tool.client.vault_root / VAULT_BACKUP_DIR
    backups = list(backup_dir.glob("*starter.md"))
    assert backups


def test_symlink_escape_blocked(write_vault: Path, write_config: ObsidianConfig) -> None:
    outside = write_vault.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    link_path = write_vault / "escape-link.md"
    try:
        link_path.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is not supported in this environment.")

    client = ObsidianClient(write_config)
    client.connect()

    with pytest.raises(ObsidianPathTraversalError):
        client.read_note("escape-link.md")

    client.disconnect()
