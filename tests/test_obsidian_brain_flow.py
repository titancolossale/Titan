# =====================================
# Titan Obsidian Brain Flow Tests
# =====================================

"""End-to-end Brain routing tests for natural-language Obsidian requests."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.reasoning import Reasoning
from tools.decision import Intent, ToolDecisionEngine
from tools.decision.obsidian_decision import ObsidianDecision
from tools.permission_manager import PermissionLevel, PermissionManager


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    vault = tmp_path / "Titan AI"
    vault.mkdir()
    notes = vault / "notes"
    notes.mkdir()
    (notes / "welcome.md").write_text("# Bienvenue\n", encoding="utf-8")
    (notes / "titan-project.md").write_text(
        "# Titan\nContenu projet.\n#project\n",
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def obsidian_env(vault_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.reasoning.TITAN_OBSIDIAN_VAULT_PATH", vault_root)
    monkeypatch.setattr("brain.reasoning.TITAN_OBSIDIAN_ENABLED", True)


def test_brain_routes_vault_health_french(vault_root: Path, obsidian_env: None) -> None:
    """« Analyse la santé de mon vault Obsidian. » → vault_health."""
    reasoning = Reasoning(project_root=vault_root)
    analysis = reasoning.analyze(
        "Analyse la santé de mon vault Obsidian.",
        available_tools=frozenset({"obsidian"}),
    )
    assert analysis["tool_requests"]
    assert analysis["tool_requests"][0].params["action"] == "vault_health"


def test_brain_routes_test_note_creation(vault_root: Path, obsidian_env: None) -> None:
    """« Ajoute une note de test dans Obsidian. » → create or patch via decision layer."""
    reasoning = Reasoning(project_root=vault_root)
    analysis = reasoning.analyze(
        "Ajoute une note de test dans Obsidian.",
        available_tools=frozenset({"obsidian"}),
    )
    assert analysis["tool_requests"]
    action = analysis["tool_requests"][0].params["action"]
    assert action in {"create_note", "patch_note", "search_notes"}


def test_brain_routes_titan_note_search(vault_root: Path, obsidian_env: None) -> None:
    """« Cherche les notes liées à Titan. » → search_notes."""
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Cherche les notes liées à Titan.",
        available_tools=frozenset({"obsidian", "file_read", "web_search"}),
    )
    assert report.intent == Intent.OBSIDIAN
    reasoning = Reasoning(project_root=vault_root)
    analysis = reasoning.analyze(
        "Cherche les notes liées à Titan.",
        available_tools=frozenset({"obsidian"}),
    )
    assert analysis["tool_requests"]
    params = analysis["tool_requests"][0].params
    assert params["action"] == "search_notes"


def test_brain_routes_patch_existing_note(vault_root: Path, obsidian_env: None) -> None:
    """« Ajoute cette information dans la bonne note Obsidian. » → search then patch."""
    reasoning = Reasoning(project_root=vault_root)
    analysis = reasoning.analyze(
        "Ajoute cette information dans la bonne note Obsidian : milestone atteint.",
        available_tools=frozenset({"obsidian"}),
    )
    assert analysis["tool_requests"]
    action = analysis["tool_requests"][0].params["action"]
    assert action in {"patch_note", "create_note", "search_notes", "update_note"}


def test_delete_note_requires_confirmation_in_brain_flow() -> None:
    """Delete without confirmation is blocked by PermissionManager."""
    result = PermissionManager().evaluate(
        "obsidian",
        "delete_note",
        {"action": "delete_note", "path": "notes/old.md"},
    )
    assert result.level == PermissionLevel.CONFIRMATION_REQUIRED
    assert result.reason
