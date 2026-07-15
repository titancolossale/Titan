# =====================================
# Titan Obsidian CLI Tests
# =====================================

"""Tests for Obsidian health and smoke-test CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.obsidian_cli import run_obsidian_health, run_obsidian_smoke_test
from tools.connectors.obsidian_connector import ObsidianConnector


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    vault = tmp_path / "Titan AI"
    vault.mkdir()
    notes = vault / "notes"
    notes.mkdir()
    (notes / "existing.md").write_text("# Existing\n", encoding="utf-8")
    return vault


def test_obsidian_health_success(
    vault_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """obsidian-health exits 0 when vault is valid."""
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", str(vault_root))
    exit_code = run_obsidian_health()
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "PRÊT" in captured
    assert "Titan AI" in captured


def test_obsidian_health_failure_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """obsidian-health exits 1 when Obsidian is disabled."""
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "false")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", "")
    exit_code = run_obsidian_health()
    captured = capsys.readouterr().out
    assert exit_code == 1
    assert "ÉCHEC" in captured
    assert "désactivé" in captured.lower()


def test_obsidian_smoke_test_leaves_vault_unchanged(
    vault_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Smoke test creates, exercises, and removes a temporary note only."""
    before = {
        rel.as_posix(): path.read_bytes()
        for path in vault_root.rglob("*.md")
        for rel in [path.relative_to(vault_root)]
    }
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", str(vault_root))
    exit_code = run_obsidian_smoke_test()
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "SUCCÈS" in captured
    after = {
        rel.as_posix(): path.read_bytes()
        for path in vault_root.rglob("*.md")
        for rel in [path.relative_to(vault_root)]
    }
    assert before == after
    assert not (vault_root / "_titan_smoke_test").exists()


def test_smoke_test_verifies_delete_requires_confirmation(vault_root: Path) -> None:
    """Smoke test path confirms PermissionManager blocks unconfirmed delete."""
    from tools.permission_manager import PermissionLevel, PermissionManager

    connector = ObsidianConnector(vault_root, enabled=True)
    note_path = "_titan_smoke_test/delete-check.md"
    connector.execute(
        "create_note",
        {"path": note_path, "content": "# temp\n"},
    )
    try:
        result = PermissionManager().evaluate(
            "obsidian",
            "delete_note",
            {"action": "delete_note", "path": note_path},
        )
        assert result.level == PermissionLevel.CONFIRMATION_REQUIRED
        assert "confirmation" in result.reason.lower() or "suppression" in result.reason.lower()
    finally:
        connector.execute("delete_note", {"path": note_path})
