# =====================================
# Titan Core Obsidian Tool V1 Tests
# =====================================

"""Tests for read-only Obsidian integration in core/tools/obsidian."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.permissions import Permission, PermissionLevel, PermissionManager
from core.tools.obsidian import (
    ObsidianClient,
    ObsidianConfig,
    ObsidianNotConnectedError,
    ObsidianNoteNotFoundError,
    ObsidianPathTraversalError,
    ObsidianPermissionDeniedError,
    ObsidianTool,
    ObsidianVaultNotFoundError,
    PERMISSION_LIST_FOLDERS,
    PERMISSION_LIST_NOTES,
    PERMISSION_READ_NOTE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VAULT = PROJECT_ROOT / "sample_vault"
INVALID_VAULT = PROJECT_ROOT / "missing_sample_vault"


@pytest.fixture
def sample_config() -> ObsidianConfig:
    return ObsidianConfig.for_vault(SAMPLE_VAULT)


@pytest.fixture
def connected_client(sample_config: ObsidianConfig) -> ObsidianClient:
    client = ObsidianClient(sample_config)
    client.connect()
    yield client
    client.disconnect()


@pytest.fixture
def obsidian_tool(sample_config: ObsidianConfig) -> ObsidianTool:
    tool = ObsidianTool(config=sample_config, auto_connect=True)
    yield tool
    tool.disconnect()


def test_valid_vault_connects(sample_config: ObsidianConfig) -> None:
    client = ObsidianClient(sample_config)
    assert client.is_connected() is False

    client.connect()

    assert client.is_connected() is True
    assert client.vault_root == SAMPLE_VAULT.resolve()

    client.disconnect()
    assert client.is_connected() is False


def test_invalid_vault_raises() -> None:
    config = ObsidianConfig.for_vault(INVALID_VAULT)
    client = ObsidianClient(config)

    with pytest.raises(ObsidianVaultNotFoundError):
        client.connect()


def test_read_note(connected_client: ObsidianClient) -> None:
    note = connected_client.read_note("welcome.md")

    assert note.relative_path == "welcome.md"
    assert "Sample Vault" in note.content
    assert note.metadata.filename == "welcome.md"
    assert note.metadata.extension == ".md"
    assert note.metadata.size > 0


def test_missing_note_raises(connected_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianNoteNotFoundError):
        connected_client.read_note("does-not-exist.md")


def test_list_folders(connected_client: ObsidianClient) -> None:
    folders = connected_client.list_folders()

    assert "projects" in folders
    assert "daily" in folders
    assert ".obsidian" not in folders


def test_list_files(connected_client: ObsidianClient) -> None:
    files = connected_client.list_files()

    assert "welcome.md" in files
    assert "projects/titan-roadmap.md" in files
    assert "daily/journal.md" in files
    assert not any(".obsidian" in path for path in files)


def test_get_note_metadata(connected_client: ObsidianClient) -> None:
    metadata = connected_client.get_note_metadata("projects/titan-roadmap.md")

    assert metadata.filename == "titan-roadmap.md"
    assert metadata.extension == ".md"
    assert metadata.relative_path == "projects/titan-roadmap.md"
    assert metadata.size > 0
    assert metadata.created <= metadata.modified


def test_note_exists(connected_client: ObsidianClient) -> None:
    assert connected_client.note_exists("daily/journal.md") is True
    assert connected_client.note_exists("missing.md") is False


def test_path_traversal_is_blocked(connected_client: ObsidianClient) -> None:
    with pytest.raises(ObsidianPathTraversalError):
        connected_client.normalize_relative_path("../main.py")

    with pytest.raises(ObsidianPathTraversalError):
        connected_client.read_note("../main.py")


def test_disconnected_client_raises(sample_config: ObsidianConfig) -> None:
    client = ObsidianClient(sample_config)

    with pytest.raises(ObsidianNotConnectedError):
        client.list_files()


def test_permission_denied_for_read_note(
    sample_config: ObsidianConfig,
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
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_LIST_NOTES,
            name="List Notes",
            description="Allowed list.",
            level=PermissionLevel.SAFE,
        )
    )
    permission_manager.register_permission(
        Permission(
            id=PERMISSION_LIST_FOLDERS,
            name="List Folders",
            description="Allowed folders.",
            level=PermissionLevel.SAFE,
        )
    )

    tool = ObsidianTool(
        config=sample_config,
        permission_manager=permission_manager,
        auto_connect=True,
    )

    with pytest.raises(ObsidianPermissionDeniedError):
        tool.execute(action="read_note", path="welcome.md")


def test_tool_execute_read_note(obsidian_tool: ObsidianTool) -> None:
    result = obsidian_tool.execute(action="read_note", path="welcome.md")

    assert result["action"] == "read_note"
    assert result["note"]["relative_path"] == "welcome.md"
    assert "Sample Vault" in result["note"]["content"]


def test_tool_execute_list_notes(obsidian_tool: ObsidianTool) -> None:
    result = obsidian_tool.execute(action="list_notes")

    assert result["action"] == "list_notes"
    assert result["count"] == 3
    assert "welcome.md" in result["files"]


def test_tool_execute_list_folders(obsidian_tool: ObsidianTool) -> None:
    result = obsidian_tool.execute(action="list_folders")

    assert result["action"] == "list_folders"
    assert "projects" in result["folders"]
    assert "daily" in result["folders"]


def test_tool_execute_metadata(obsidian_tool: ObsidianTool) -> None:
    result = obsidian_tool.execute(action="metadata", path="daily/journal.md")

    assert result["action"] == "metadata"
    assert result["metadata"]["relative_path"] == "daily/journal.md"
    assert result["metadata"]["filename"] == "journal.md"


def test_tool_registers_default_permissions(obsidian_tool: ObsidianTool) -> None:
    manager = obsidian_tool.permission_manager

    assert manager.permission_exists(PERMISSION_READ_NOTE)
    assert manager.permission_exists(PERMISSION_LIST_NOTES)
    assert manager.permission_exists(PERMISSION_LIST_FOLDERS)

    read_result = manager.check_permission(PERMISSION_READ_NOTE)
    assert read_result.allowed is True


def test_tool_metadata_properties(obsidian_tool: ObsidianTool) -> None:
    metadata = obsidian_tool.to_metadata()

    assert metadata.id == "obsidian"
    assert metadata.category == "notes"
    assert "read_notes" in metadata.capabilities
    assert "list_notes" in metadata.capabilities
    assert "list_folders" in metadata.capabilities
    assert "metadata" in metadata.capabilities
    assert "create_note" in metadata.capabilities
    assert "edit_note" in metadata.capabilities
    assert "delete_note" in metadata.capabilities
