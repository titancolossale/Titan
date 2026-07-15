# =====================================
# Titan Obsidian Decision Tests
# =====================================

"""Tests for Phase 12.5 Batch 2 — Obsidian decision layer and search (P125-007–P125-010)."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.reasoning import Reasoning
from tools.connectors.obsidian_connector import ObsidianConnector
from tools.decision import Intent, ToolDecisionEngine
from tools.decision.models import FallbackAction
from tools.decision.obsidian_decision import (
    ObsidianDecision,
    ObsidianDecisionEngine,
    ObsidianSearchMode,
    is_casual_or_ephemeral,
    is_worthy_persistence,
)
from tools.obsidian_tool import ObsidianTool


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
    projects = vault / "projects"
    projects.mkdir()
    (projects / "roadmap.md").write_text(
        "---\ntags: [roadmap, titan]\n---\n# Roadmap\n",
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def connector(vault_root: Path) -> ObsidianConnector:
    return ObsidianConnector(vault_root, enabled=True)


@pytest.fixture
def engine(connector: ObsidianConnector) -> ObsidianDecisionEngine:
    return ObsidianDecisionEngine(connector)


# ---------------------------------------------------------------------------
# P125-007 — Decision cases
# ---------------------------------------------------------------------------


def test_decision_do_not_use_when_unconfigured(tmp_path: Path) -> None:
    """P125-007: unconfigured vault → DO_NOT_USE_OBSIDIAN."""
    missing = ObsidianConnector(None, enabled=True)
    result = ObsidianDecisionEngine(missing).decide(
        "Documente le projet Titan dans Obsidian",
    )
    assert result.decision == ObsidianDecision.DO_NOT_USE_OBSIDIAN
    assert "non configuré" in result.reason.lower()


def test_decision_do_not_use_for_casual_greeting(engine: ObsidianDecisionEngine) -> None:
    """P125-007: casual greeting → DO_NOT_USE_OBSIDIAN."""
    result = engine.decide("Bonjour Titan, comment ça va ?")
    assert result.decision == ObsidianDecision.DO_NOT_USE_OBSIDIAN


def test_decision_do_not_use_for_ephemeral_context(engine: ObsidianDecisionEngine) -> None:
    """P125-007: temporary session context → DO_NOT_USE_OBSIDIAN."""
    result = engine.decide("Juste pour info temporaire dans cette session")
    assert result.decision == ObsidianDecision.DO_NOT_USE_OBSIDIAN


def test_decision_read_existing_note_with_explicit_path(
    engine: ObsidianDecisionEngine,
) -> None:
    """P125-007: explicit note path → READ_EXISTING_NOTE."""
    result = engine.decide("Lis la note notes/welcome.md dans Obsidian")
    assert result.decision == ObsidianDecision.READ_EXISTING_NOTE
    assert result.target_path == "notes/welcome.md"
    assert result.tool_params_dict()["action"] == "read_note"


def test_decision_search_notes_on_vault_search(engine: ObsidianDecisionEngine) -> None:
    """P125-007: vault search phrasing → SEARCH_NOTES."""
    result = engine.decide("Cherche dans Obsidian les notes avec tag #project")
    assert result.decision == ObsidianDecision.SEARCH_NOTES
    assert result.search_mode == ObsidianSearchMode.TAG
    assert result.tool_params_dict()["action"] == "search_notes"


def test_decision_update_existing_note_before_create(
    engine: ObsidianDecisionEngine,
    connector: ObsidianConnector,
) -> None:
    """P125-007/014: durable write with existing match → PATCH_EXISTING_NOTE (append)."""
    connector.execute(
        "create_note",
        {"path": "notes/titan-overview.md", "content": "# Titan\nAncien contenu."},
    )
    result = engine.decide(
        "Documente le projet Titan dans Obsidian contenu: # Titan\nVue d'ensemble.",
    )
    assert result.decision == ObsidianDecision.PATCH_EXISTING_NOTE
    assert result.matched_notes
    assert result.tool_params_dict()["action"] == "patch_note"
    assert result.tool_params_dict()["update_mode"] == "append"


def test_decision_create_new_note_when_no_match(
    engine: ObsidianDecisionEngine,
) -> None:
    """P125-007: durable write without match → CREATE_NEW_NOTE."""
    result = engine.decide(
        "Crée une note de procédure déploiement dans Obsidian "
        "contenu: # Déploiement\nÉtapes importantes.",
    )
    assert result.decision == ObsidianDecision.CREATE_NEW_NOTE
    assert result.tool_params_dict()["action"] == "create_note"
    assert result.target_path is not None


def test_decision_do_not_create_for_joke(engine: ObsidianDecisionEngine) -> None:
    """P125-007: joke content → DO_NOT_USE_OBSIDIAN."""
    result = engine.decide("Haha blague du jour dans obsidian lol")
    assert result.decision == ObsidianDecision.DO_NOT_USE_OBSIDIAN


# ---------------------------------------------------------------------------
# P125-008 — Cleanliness rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected_casual"),
    [
        ("Bonjour", True),
        ("Juste pour info temporaire", True),
        ("Documente la procédure backup importante", False),
        ("Objectif long term pour le projet Titan", False),
    ],
)
def test_cleanliness_helpers(message: str, expected_casual: bool) -> None:
    """P125-008: casual/ephemeral vs worthy persistence detection."""
    if expected_casual:
        assert is_casual_or_ephemeral(message) or not is_worthy_persistence(message)
    else:
        assert is_worthy_persistence(message)
        assert not is_casual_or_ephemeral(message)


# ---------------------------------------------------------------------------
# P125-009 — Search modes
# ---------------------------------------------------------------------------


def test_search_by_filename(connector: ObsidianConnector) -> None:
    """P125-009: filename search matches note names."""
    matches = connector.find_notes(mode="filename", query="welcome")
    assert "notes/welcome.md" in matches


def test_search_by_keyword(connector: ObsidianConnector) -> None:
    """P125-009: keyword search matches note content."""
    matches = connector.find_notes(mode="keyword", query="roadmap")
    assert "projects/roadmap.md" in matches


def test_search_by_tag_inline(connector: ObsidianConnector) -> None:
    """P125-009: tag search matches inline #tags."""
    matches = connector.find_notes(mode="tag", query="project")
    assert "notes/titan-project.md" in matches


def test_search_by_tag_frontmatter(connector: ObsidianConnector) -> None:
    """P125-009: tag search matches YAML frontmatter tags."""
    matches = connector.find_notes(mode="tag", query="roadmap")
    assert "projects/roadmap.md" in matches


def test_search_by_folder(connector: ObsidianConnector) -> None:
    """P125-009: folder search scopes to a vault directory."""
    matches = connector.find_notes(mode="folder", query="projects")
    assert "projects/roadmap.md" in matches
    assert "notes/welcome.md" not in matches


def test_connector_search_notes_action(connector: ObsidianConnector) -> None:
    """P125-009: search_notes action returns formatted results."""
    result = connector.execute(
        "search_notes",
        {"mode": "keyword", "query": "projet"},
    )
    assert result.success
    assert "titan-project.md" in result.data


def test_obsidian_tool_search_notes(vault_root: Path) -> None:
    """P125-009: ObsidianTool dispatches search_notes."""
    tool = ObsidianTool(vault_path=vault_root, enabled=True)
    result = tool.run(action="search_notes", mode="filename", query="welcome")
    assert result.success
    assert "welcome.md" in result.data


# ---------------------------------------------------------------------------
# P125-010 — Brain routing integration
# ---------------------------------------------------------------------------


def test_tool_decision_engine_routes_obsidian_intent() -> None:
    """P125-010: Obsidian phrasing selects obsidian tool."""
    engine = ToolDecisionEngine()
    report = engine.decide(
        "Cherche dans mon vault Obsidian la note projet Titan",
        available_tools=frozenset({"obsidian", "file_read", "web_search"}),
    )
    assert report.intent == Intent.OBSIDIAN
    assert report.selected_tool == "obsidian"
    assert report.fallback_action == FallbackAction.EXECUTE_TOOL


def test_reasoning_skips_tool_for_casual_obsidian(vault_root: Path) -> None:
    """P125-010: Brain reasoning avoids vault writes for casual messages."""
    reasoning = Reasoning(project_root=vault_root)
    analysis = reasoning.analyze(
        "Salut obsidian",
        available_tools=frozenset({"obsidian"}),
    )
    assert analysis["fallback_action"] == FallbackAction.DIRECT_ANSWER.value
    assert analysis["tool_requests"] == []


def test_reasoning_emits_search_for_vault_query(vault_root: Path, monkeypatch) -> None:
    """P125-010: Brain reasoning emits search_notes for vault search."""
    monkeypatch.setattr("brain.reasoning.TITAN_OBSIDIAN_VAULT_PATH", str(vault_root))
    monkeypatch.setattr("brain.reasoning.TITAN_OBSIDIAN_ENABLED", True)
    reasoning = Reasoning(project_root=vault_root)
    analysis = reasoning.analyze(
        "Search vault Obsidian for tag #project",
        available_tools=frozenset({"obsidian"}),
    )
    assert analysis["tool_requests"]
    params = analysis["tool_requests"][0].params
    assert params["action"] == "search_notes"
    assert params["mode"] == "tag"
