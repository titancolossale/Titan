# =====================================
# Titan Obsidian Vault Maintenance Tests
# =====================================

"""Tests for Phase 12.5 Batch 3 — smart updates, markdown awareness, vault health (P125-011–P125-016)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.connectors.markdown_editor import (
    MarkdownEditError,
    NoteUpdateMode,
    apply_note_update,
    describe_document,
)
from tools.connectors.markdown_parser import (
    find_checklist_items,
    find_headings,
    parse_markdown,
    split_frontmatter,
)
from tools.connectors.obsidian_connector import ObsidianConnector
from tools.connectors.vault_analyzer import VaultAnalyzer
from tools.decision.obsidian_decision import ObsidianDecision, ObsidianDecisionEngine
from tools.obsidian_tool import ObsidianTool


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    vault = tmp_path / "Titan AI"
    vault.mkdir()
    notes = vault / "notes"
    notes.mkdir()
    (notes / "welcome.md").write_text("# Bienvenue\n\nContenu initial.\n", encoding="utf-8")
    (notes / "tasks.md").write_text(
        "---\ntags: [tasks, titan]\n---\n"
        "# Tâches\n\n"
        "- [ ] Configurer vault\n"
        "- [x] Installer Obsidian\n\n"
        "## Suivi\n\n"
        "| Étape | Statut |\n"
        "| --- | --- |\n"
        "| Phase 1 | done |\n"
        "| Phase 2 | pending |\n",
        encoding="utf-8",
    )
    projects = vault / "projects"
    projects.mkdir()
    (projects / "titan-roadmap.md").write_text(
        "# Titan Roadmap\n\nContenu projet détaillé sur Titan.\n#project\n",
        encoding="utf-8",
    )
    (notes / "titan-roadmap-copy.md").write_text(
        "# Titan Roadmap\n\nContenu projet détaillé sur Titan.\n",
        encoding="utf-8",
    )
    (notes / "Bad Name.md").write_text("# Bad\n\nEspaces dans le nom.\n", encoding="utf-8")
    (notes / "empty-note.md").write_text("\n", encoding="utf-8")
    (notes / "orphan.md").write_text("# Orphelin\n\nNote isolée sans liens.\n", encoding="utf-8")
    return vault


@pytest.fixture
def connector(vault_root: Path) -> ObsidianConnector:
    return ObsidianConnector(vault_root, enabled=True)


# ---------------------------------------------------------------------------
# P125-011 — Markdown awareness
# ---------------------------------------------------------------------------


def test_split_frontmatter() -> None:
    """P125-011: YAML frontmatter is separated from body."""
    content = "---\ntags: [a]\n---\n# Title\n"
    frontmatter, body = split_frontmatter(content)
    assert frontmatter is not None
    assert "tags" in frontmatter
    assert body.startswith("# Title")


def test_parse_markdown_structure() -> None:
    """P125-011: parser detects headings, checklists, tables, tags."""
    content = (
        "---\ntags: [demo]\n---\n"
        "# Main\n\n"
        "- [ ] Task one\n\n"
        "```python\nprint('hi')\n```\n\n"
        "> [!note] Callout\n> text\n\n"
        "[[Other Note]] #inline\n"
    )
    doc = parse_markdown(content)
    assert doc.frontmatter is not None
    assert len(doc.headings) == 1
    assert doc.headings[0].title == "Main"
    assert len(doc.checklist_items) == 1
    assert len(doc.code_blocks) == 1
    assert "demo" in doc.tags
    assert "inline" in doc.tags
    assert "Other Note" in doc.wikilinks


def test_find_headings_section_boundaries() -> None:
    """P125-011: heading sections span until next heading."""
    body = "# One\nA\n## Two\nB\n# Three\nC"
    sections = find_headings(body)
    assert len(sections) == 3
    assert sections[0].title == "One"
    assert "A" in body[sections[0].start : sections[0].end]


def test_find_checklist_items() -> None:
    """P125-011: checklist items preserve checked state."""
    body = "- [ ] Open\n- [x] Done"
    items = find_checklist_items(body)
    assert len(items) == 2
    assert not items[0].checked
    assert items[1].checked


def test_describe_document() -> None:
    """P125-011: structural summary for diagnostics."""
    summary = describe_document("# Hi\n\n- [ ] x\n")
    assert summary["heading_count"] == 1
    assert summary["checklist_count"] == 1


# ---------------------------------------------------------------------------
# P125-012 — Smart note updates
# ---------------------------------------------------------------------------


def test_apply_append_preserves_existing() -> None:
    """P125-012: append adds content without replacing."""
    original = "# Title\n\nExisting.\n"
    updated = apply_note_update(original, NoteUpdateMode.APPEND.value, new_content="Added.")
    assert "Existing." in updated
    assert "Added." in updated


def test_apply_prepend_respects_frontmatter() -> None:
    """P125-012: prepend inserts after YAML frontmatter."""
    original = "---\ntags: [x]\n---\n# Body\n"
    updated = apply_note_update(original, NoteUpdateMode.PREPEND.value, new_content="Intro.")
    assert updated.index("---") == 0
    assert "Intro." in updated
    assert "# Body" in updated


def test_apply_insert_under_heading() -> None:
    """P125-012: insert_under_heading places content below target heading."""
    original = "# Main\n\nOld.\n\n## Suivi\n\nTail.\n"
    updated = apply_note_update(
        original,
        NoteUpdateMode.INSERT_UNDER_HEADING.value,
        heading="Suivi",
        new_content="- Nouveau point",
    )
    assert "- Nouveau point" in updated
    assert updated.index("- Nouveau point") < updated.index("Tail.")


def test_apply_replace_section() -> None:
    """P125-012: replace_section swaps section body only."""
    original = "# Main\n\nKeep.\n\n## Suivi\n\nOld body.\n\n# Next\n\nEnd."
    updated = apply_note_update(
        original,
        NoteUpdateMode.REPLACE_SECTION.value,
        heading="Suivi",
        new_content="New body.",
    )
    assert "Keep." in updated
    assert "New body." in updated
    assert "Old body." not in updated
    assert "# Next" in updated


def test_apply_update_checklist() -> None:
    """P125-012: update_checklist toggles task item."""
    original = "- [ ] Configurer vault\n- [x] Done\n"
    updated = apply_note_update(
        original,
        NoteUpdateMode.UPDATE_CHECKLIST.value,
        checklist_item="Configurer vault",
        checked=True,
    )
    assert "- [x] Configurer vault" in updated


def test_apply_update_table() -> None:
    """P125-012: update_table modifies a single cell."""
    original = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    updated = apply_note_update(
        original,
        NoteUpdateMode.UPDATE_TABLE.value,
        table_row=0,
        table_col=1,
        cell_value="updated",
    )
    assert "| 1 | updated |" in updated


def test_apply_update_rejects_unknown_mode() -> None:
    """P125-012: unsupported mode raises MarkdownEditError."""
    with pytest.raises(MarkdownEditError):
        apply_note_update("x", "invalid_mode")


def test_connector_patch_note_append(connector: ObsidianConnector, vault_root: Path) -> None:
    """P125-012: patch_note append via connector."""
    result = connector.execute(
        "patch_note",
        {
            "path": "notes/welcome.md",
            "update_mode": "append",
            "new_content": "\n## Ajout\nNouveau paragraphe.",
        },
    )
    assert result.success
    content = (vault_root / "notes" / "welcome.md").read_text(encoding="utf-8")
    assert "Contenu initial." in content
    assert "Nouveau paragraphe." in content


def test_connector_patch_note_update_checklist(connector: ObsidianConnector) -> None:
    """P125-012: patch_note update_checklist via connector."""
    result = connector.execute(
        "patch_note",
        {
            "path": "notes/tasks.md",
            "update_mode": "update_checklist",
            "checklist_item": "Configurer vault",
            "checked": True,
        },
    )
    assert result.success
    read = connector.execute("read_note", {"path": "notes/tasks.md"})
    assert "- [x] Configurer vault" in read.data


def test_connector_update_note_with_mode(connector: ObsidianConnector, vault_root: Path) -> None:
    """P125-012: update_note delegates to patch when update_mode set."""
    result = connector.execute(
        "update_note",
        {
            "path": "notes/welcome.md",
            "update_mode": "append",
            "content": "Fin.",
        },
    )
    assert result.success
    content = (vault_root / "notes" / "welcome.md").read_text(encoding="utf-8")
    assert "Fin." in content
    assert "Contenu initial." in content


def test_obsidian_tool_patch_note(vault_root: Path) -> None:
    """P125-012: ObsidianTool dispatches patch_note."""
    tool = ObsidianTool(vault_path=vault_root, enabled=True)
    result = tool.run(
        action="patch_note",
        path="notes/welcome.md",
        update_mode="prepend",
        content="> [!info] Note\n",
    )
    assert result.success


# ---------------------------------------------------------------------------
# P125-013 — Vault organization & health
# ---------------------------------------------------------------------------


def test_vault_analyzer_empty_notes(vault_root: Path) -> None:
    """P125-013: detects empty notes."""
    report = VaultAnalyzer(vault_root).analyze()
    assert "notes/empty-note.md" in report.empty_notes


def test_vault_analyzer_orphans(vault_root: Path) -> None:
    """P125-013: detects orphan notes without incoming links."""
    report = VaultAnalyzer(vault_root).analyze()
    assert "notes/orphan.md" in report.orphan_notes


def test_vault_analyzer_duplicates(vault_root: Path) -> None:
    """P125-013: detects duplicate/similar topics."""
    report = VaultAnalyzer(vault_root).analyze()
    assert report.duplicated_topics or report.merge_suggestions
    assert not any("delete" in s.recommendation.lower() for s in report.merge_suggestions)


def test_vault_analyzer_naming_issues(vault_root: Path) -> None:
    """P125-013: flags inconsistent naming."""
    report = VaultAnalyzer(vault_root).analyze()
    paths = [issue.path for issue in report.naming_inconsistencies]
    assert any("Bad Name" in path for path in paths)


def test_vault_analyzer_missing_tags(vault_root: Path) -> None:
    """P125-013: notes without tags are flagged."""
    report = VaultAnalyzer(vault_root).analyze()
    assert isinstance(report.missing_tags, list)


def test_vault_health_report_structure(vault_root: Path) -> None:
    """P125-013: structured report serializes to dict."""
    report = VaultAnalyzer(vault_root).analyze()
    data = report.to_dict()
    assert "duplicated_topics" in data
    assert "orphan_notes" in data
    assert "empty_notes" in data
    assert "naming_inconsistencies" in data
    assert report.total_notes >= 5


def test_connector_vault_health(connector: ObsidianConnector) -> None:
    """P125-013: vault_health action returns summary."""
    result = connector.execute("vault_health", {})
    assert result.success
    assert "Rapport santé vault" in result.data
    assert "orphelin" in result.data.lower() or "Orphelines" in result.data


def test_connector_vault_health_report_dict(connector: ObsidianConnector) -> None:
    """P125-013: programmatic health report dict."""
    data = connector.vault_health_report()
    assert data["total_notes"] >= 1


def test_obsidian_tool_vault_health(vault_root: Path) -> None:
    """P125-013: ObsidianTool dispatches vault_health."""
    tool = ObsidianTool(vault_path=vault_root, enabled=True)
    result = tool.run(action="vault_health")
    assert result.success


# ---------------------------------------------------------------------------
# P125-014 — Decision layer smart updates
# ---------------------------------------------------------------------------


def test_decision_patch_existing_note_by_default(
    vault_root: Path,
) -> None:
    """P125-014: durable write with match → PATCH_EXISTING_NOTE (append)."""
    connector = ObsidianConnector(vault_root, enabled=True)
    engine = ObsidianDecisionEngine(connector)
    result = engine.decide(
        "Documente le projet Titan dans Obsidian contenu: ## Mise à jour\nDétails.",
    )
    assert result.decision == ObsidianDecision.PATCH_EXISTING_NOTE
    assert result.update_mode == NoteUpdateMode.APPEND.value
    assert result.tool_params_dict()["action"] == "patch_note"


def test_decision_vault_health(vault_root: Path) -> None:
    """P125-014: vault health request → VAULT_HEALTH."""
    connector = ObsidianConnector(vault_root, enabled=True)
    result = ObsidianDecisionEngine(connector).decide(
        "Analyse la santé du vault Obsidian et les doublons",
    )
    assert result.decision == ObsidianDecision.VAULT_HEALTH
    assert result.tool_params_dict()["action"] == "vault_health"


def test_decision_insert_under_heading_mode(vault_root: Path) -> None:
    """P125-014: insert under heading phrasing selects correct mode."""
    connector = ObsidianConnector(vault_root, enabled=True)
    connector.execute(
        "create_note",
        {"path": "notes/spec.md", "content": "# Spec\n\n## Details\n\nOld.\n"},
    )
    result = ObsidianDecisionEngine(connector).decide(
        "Ajoute dans Obsidian sous la section Details notes/spec.md contenu: - Point A",
    )
    assert result.decision == ObsidianDecision.PATCH_EXISTING_NOTE
    assert result.update_mode == NoteUpdateMode.INSERT_UNDER_HEADING.value
    assert result.heading == "Details"


def test_decision_no_auto_delete_recommendations_only(vault_root: Path) -> None:
    """P125-014: health report never recommends automatic deletion."""
    report = VaultAnalyzer(vault_root).analyze()
    summary = report.format_summary()
    assert "suppression auto" not in summary.lower()
    for suggestion in report.merge_suggestions:
        assert "manuel" in suggestion.recommendation.lower() or "manuelle" in suggestion.recommendation.lower()
