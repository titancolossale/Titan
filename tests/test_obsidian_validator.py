# =====================================
# Titan Obsidian Validator Tests
# =====================================

"""Tests for Obsidian production readiness validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.connectors.obsidian_validator import (
    ObsidianValidationCode,
    validate_obsidian_config,
)


def test_disabled_obsidian_returns_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disabled connector reports OBSIDIAN_DISABLED."""
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "false")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", "/any/path")
    result = validate_obsidian_config()
    assert not result.ok
    assert result.code == ObsidianValidationCode.OBSIDIAN_DISABLED
    assert "désactivé" in result.message.lower()


def test_missing_vault_path_returns_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty vault path reports MISSING_VAULT_PATH."""
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", "")
    result = validate_obsidian_config()
    assert not result.ok
    assert result.code == ObsidianValidationCode.MISSING_VAULT_PATH
    assert "ne crée jamais" in result.message.lower()


def test_vault_not_found_never_creates_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Missing vault directory fails validation without creating it."""
    missing = tmp_path / "Titan AI"
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", str(missing))
    result = validate_obsidian_config()
    assert not result.ok
    assert result.code == ObsidianValidationCode.VAULT_NOT_FOUND
    assert not missing.exists()


def test_valid_vault_passes_read_write_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Existing writable vault passes full validation."""
    vault = tmp_path / "Titan AI"
    vault.mkdir()
    (vault / "welcome.md").write_text("# Bienvenue\n", encoding="utf-8")
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", str(vault))
    result = validate_obsidian_config()
    assert result.ok
    assert result.code == ObsidianValidationCode.OK
    assert result.readable
    assert result.writable
    assert result.vault_name == "Titan AI"


def test_file_path_instead_of_directory_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A file path (not directory) reports INVALID_VAULT_PATH."""
    file_path = tmp_path / "not-a-vault.md"
    file_path.write_text("x", encoding="utf-8")
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", str(file_path))
    result = validate_obsidian_config()
    assert not result.ok
    assert result.code == ObsidianValidationCode.INVALID_VAULT_PATH


def test_unsafe_system_path_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """System directories are rejected as unsafe vault paths."""
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", "C:\\Windows\\System32")
    result = validate_obsidian_config()
    assert not result.ok
    assert result.code == ObsidianValidationCode.UNSAFE_VAULT_PATH


def test_read_only_vault_reports_not_writable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Read-only vault directory reports VAULT_NOT_WRITABLE."""
    vault = tmp_path / "Titan AI"
    vault.mkdir()
    vault.chmod(0o555)
    monkeypatch.setenv("TITAN_OBSIDIAN_ENABLED", "true")
    monkeypatch.setenv("TITAN_OBSIDIAN_VAULT_PATH", str(vault))
    try:
        result = validate_obsidian_config()
    finally:
        vault.chmod(0o755)
    if result.ok:
        pytest.skip("Platform does not enforce directory write permissions in this test")
    assert result.code == ObsidianValidationCode.VAULT_NOT_WRITABLE


def test_connector_configuration_error_uses_validator(
    vault_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ObsidianConnector surfaces validator messages when disabled."""
    from tools.connectors.obsidian_connector import ObsidianConnector

    connector = ObsidianConnector(vault_root, enabled=False)
    error = connector.configuration_error()
    assert "désactivé" in error.lower()
    ok, message = connector.health_check()
    assert not ok
    assert message


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    vault = tmp_path / "Titan AI"
    vault.mkdir()
    return vault
