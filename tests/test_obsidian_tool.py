# =====================================
# Titan Obsidian Tool Tests
# =====================================

"""Tests for Phase 12.5 — Obsidian external connector (P125-001–P125-006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.connectors.obsidian_connector import ObsidianConnector
from tools.connectors.vault_path_guard import VaultPathGuardError, resolve_vault_path
from tools.obsidian_tool import ObsidianTool
from tools.tool_manager import ToolManager


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    """Isolated Obsidian vault for connector tests."""
    vault = tmp_path / "ObsidianVault"
    vault.mkdir()
    notes_dir = vault / "notes"
    notes_dir.mkdir()
    (notes_dir / "welcome.md").write_text("# Bienvenue\n", encoding="utf-8")
    return vault


@pytest.fixture
def connector(vault_root: Path) -> ObsidianConnector:
    return ObsidianConnector(vault_root, enabled=True)


@pytest.fixture
def obsidian_tool(vault_root: Path) -> ObsidianTool:
    return ObsidianTool(vault_path=vault_root, enabled=True)


def test_vault_path_guard_blocks_traversal(vault_root: Path) -> None:
    """P125-003: traversal outside vault root is rejected."""
    with pytest.raises(VaultPathGuardError):
        resolve_vault_path("../../etc/passwd", vault_root)


def test_vault_path_guard_allows_relative_note(vault_root: Path) -> None:
    """P125-003: valid relative paths resolve under vault root."""
    resolved = resolve_vault_path(
        "notes/welcome.md",
        vault_root,
        must_exist=True,
        expect_file=True,
    )
    assert resolved.name == "welcome.md"
    assert resolved.read_text(encoding="utf-8") == "# Bienvenue\n"


def test_connector_read_note(connector: ObsidianConnector) -> None:
    """P125-004: read_note returns markdown content."""
    result = connector.execute("read_note", {"path": "notes/welcome.md"})
    assert result.success
    assert result.data == "# Bienvenue\n"
    assert result.target_path == "notes/welcome.md"


def test_connector_read_note_adds_md_extension(connector: ObsidianConnector) -> None:
    """P125-004: note paths without .md are normalized."""
    result = connector.execute("read_note", {"path": "notes/welcome"})
    assert result.success
    assert result.data == "# Bienvenue\n"


def test_connector_create_note(connector: ObsidianConnector, vault_root: Path) -> None:
    """P125-004: create_note writes a new markdown file."""
    result = connector.execute(
        "create_note",
        {"path": "ideas/new-idea", "content": "# Idée\nContenu."},
    )
    assert result.success
    created = vault_root / "ideas" / "new-idea.md"
    assert created.exists()
    assert created.read_text(encoding="utf-8") == "# Idée\nContenu."


def test_connector_create_note_rejects_existing(connector: ObsidianConnector) -> None:
    """P125-004: create_note fails when note already exists."""
    result = connector.execute(
        "create_note",
        {"path": "notes/welcome.md", "content": "duplicate"},
    )
    assert not result.success
    assert "existe déjà" in result.error.lower()


def test_connector_update_note(connector: ObsidianConnector, vault_root: Path) -> None:
    """P125-004: update_note overwrites existing content."""
    result = connector.execute(
        "update_note",
        {"path": "notes/welcome.md", "content": "# Mis à jour\n"},
    )
    assert result.success
    assert (vault_root / "notes" / "welcome.md").read_text(encoding="utf-8") == "# Mis à jour\n"


def test_connector_delete_note(connector: ObsidianConnector, vault_root: Path) -> None:
    """P125-004: delete_note removes a markdown file."""
    result = connector.execute("delete_note", {"path": "notes/welcome.md"})
    assert result.success
    assert not (vault_root / "notes" / "welcome.md").exists()


def test_connector_create_folder(connector: ObsidianConnector, vault_root: Path) -> None:
    """P125-004: create_folder creates nested directories."""
    result = connector.execute("create_folder", {"folder": "projects/titan"})
    assert result.success
    assert (vault_root / "projects" / "titan").is_dir()


def test_connector_list_notes_root(connector: ObsidianConnector) -> None:
    """P125-004: list_notes returns markdown files at vault root scope."""
    connector.execute(
        "create_note",
        {"path": "notes/second.md", "content": "deux"},
    )
    result = connector.execute("list_notes", {"folder": "notes"})
    assert result.success
    assert "welcome.md" in result.data
    assert "second.md" in result.data


def test_connector_list_notes_recursive(connector: ObsidianConnector) -> None:
    """P125-004: recursive list_notes includes nested markdown files."""
    connector.execute("create_folder", {"folder": "deep/nested"})
    connector.execute(
        "create_note",
        {"path": "deep/nested/hidden.md", "content": "secret"},
    )
    result = connector.execute(
        "list_notes",
        {"folder": "", "recursive": True},
    )
    assert result.success
    assert "deep/nested/hidden.md" in result.data


def test_connector_blocks_escape(connector: ObsidianConnector) -> None:
    """P125-003: operations outside vault are rejected."""
    result = connector.execute(
        "read_note",
        {"path": "../outside.md"},
    )
    assert not result.success
    assert "accès refusé" in result.error.lower() or "introuvable" in result.error.lower()


def test_connector_unconfigured_returns_error(tmp_path: Path) -> None:
    """P125-002: missing vault path yields actionable error."""
    connector = ObsidianConnector(None, enabled=True)
    result = connector.execute("list_notes", {})
    assert not result.success
    assert "titan_obsidian_vault_path" in result.error.lower()
    assert "ne crée jamais" in result.error.lower()


def test_connector_missing_vault_directory_returns_error(tmp_path: Path) -> None:
    """P125-002: path set but vault folder missing — do not create vault."""
    missing = tmp_path / "Titan AI"
    connector = ObsidianConnector(missing, enabled=True)
    result = connector.execute("list_notes", {})
    assert not result.success
    assert "introuvable" in result.error.lower()
    assert "existant" in result.error.lower()


def test_connector_disabled_returns_error(vault_root: Path) -> None:
    """P125-002: disabled connector rejects operations."""
    connector = ObsidianConnector(vault_root, enabled=False)
    result = connector.execute("list_notes", {})
    assert not result.success
    assert "désactivé" in result.error.lower()


def test_obsidian_tool_dispatches_actions(obsidian_tool: ObsidianTool) -> None:
    """P125-001: ObsidianTool routes actions through the connector."""
    result = obsidian_tool.run(action="read_note", path="notes/welcome.md")
    assert result.success
    assert result.data == "# Bienvenue\n"
    assert result.metadata["connector"] == "obsidian"


def test_obsidian_tool_rejects_unknown_action(obsidian_tool: ObsidianTool) -> None:
    """P125-001: unsupported actions return structured errors."""
    result = obsidian_tool.run(action="sync_graph")
    assert not result.success
    assert "non supportée" in result.error.lower()


def test_tool_manager_registers_obsidian(vault_root: Path) -> None:
    """P125-005: ToolManager exposes obsidian in default registry."""
    manager = ToolManager(project_root=vault_root)
    assert "obsidian" in manager.list_tools()


def test_tool_manager_runs_obsidian_when_configured(vault_root: Path) -> None:
    """P125-005: Brain caller can invoke obsidian through ToolManager."""
    manager = ToolManager(project_root=vault_root, register_defaults=False)
    manager.registry.register(ObsidianTool(vault_path=vault_root, enabled=True))
    result = manager.run(
        "obsidian",
        {"action": "read_note", "path": "notes/welcome.md"},
        caller="brain",
    )
    assert result.success
    assert "Bienvenue" in result.data
