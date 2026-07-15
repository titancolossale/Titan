# =====================================
# Titan Obsidian Phase 22.0 Tests
# =====================================

"""Tests for Phase 22.0 Obsidian Brain Extension — extended vault operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.memory_activity import format_memory_activity
from api.tool_activity import format_tool_activity, normalize_tool_key
from brain.pipeline.context_bundle import ThinkContext
from memory.models import RetrievalResult
from tools.connectors.obsidian_connector import ObsidianConnector
from tools.connectors.vault_link_index import (
    build_backlink_index,
    note_display_name,
    rewrite_wikilinks_after_rename,
)
from tools.obsidian_tool import ObsidianTool
from tools.tool_result import ToolResult


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    notes = vault / "notes"
    notes.mkdir()
    projects = vault / "projects"
    projects.mkdir()
    (notes / "welcome.md").write_text("# Bienvenue\n", encoding="utf-8")
    (notes / "index.md").write_text(
        "Voir [[welcome]] et [[titan-project]].\n",
        encoding="utf-8",
    )
    (projects / "titan-project.md").write_text(
        "---\ntags: [project, titan]\nstatus: active\n---\n# Titan\n",
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def connector(vault_root: Path) -> ObsidianConnector:
    return ObsidianConnector(vault_root, enabled=True)


def test_note_display_name_hides_path() -> None:
    assert note_display_name("notes/welcome.md") == "welcome"
    assert "notes" not in note_display_name("projects/titan-project.md")


def test_get_backlinks(connector: ObsidianConnector) -> None:
    result = connector.execute("get_backlinks", {"path": "notes/welcome.md"})
    assert result.success
    assert "index" in result.data.lower()
    assert "notes/" not in result.data


def test_get_outlinks(connector: ObsidianConnector) -> None:
    result = connector.execute("get_outlinks", {"path": "notes/index.md"})
    assert result.success
    assert "welcome" in result.data.lower()
    assert "titan" in result.data.lower()


def test_read_frontmatter(connector: ObsidianConnector) -> None:
    result = connector.execute(
        "read_frontmatter",
        {"path": "projects/titan-project.md"},
    )
    assert result.success
    assert "tags" in result.data
    assert "active" in result.data
    assert "projects/" not in result.data


def test_list_tags(connector: ObsidianConnector) -> None:
    result = connector.execute("list_tags", {})
    assert result.success
    assert "#project" in result.data or "#titan" in result.data


def test_rename_note_rewrites_wikilinks(
    connector: ObsidianConnector,
    vault_root: Path,
) -> None:
    result = connector.execute(
        "rename_note",
        {"path": "notes/welcome.md", "new_path": "notes/bienvenue.md"},
    )
    assert result.success
    assert (vault_root / "notes" / "bienvenue.md").exists()
    index_content = (vault_root / "notes" / "index.md").read_text(encoding="utf-8")
    assert "[[bienvenue]]" in index_content
    assert "[[welcome]]" not in index_content


def test_move_note(connector: ObsidianConnector, vault_root: Path) -> None:
    result = connector.execute(
        "move_note",
        {"path": "projects/titan-project.md", "folder": "notes"},
    )
    assert result.success
    assert (vault_root / "notes" / "titan-project.md").exists()
    assert not (vault_root / "projects" / "titan-project.md").exists()


def test_list_folders(connector: ObsidianConnector) -> None:
    result = connector.execute("list_folders", {})
    assert result.success
    assert "notes" in result.data.lower()
    assert "projects" in result.data.lower()


def test_obsidian_tool_facade_api(vault_root: Path) -> None:
    tool = ObsidianTool(vault_path=vault_root, enabled=True)
    read_result = tool.read("notes/welcome.md")
    assert read_result.success
    search_result = tool.search("welcome", mode="filename")
    assert search_result.success
    folders = tool.list_folders()
    assert folders.success


def test_build_backlink_index(vault_root: Path) -> None:
    notes = ["notes/index.md", "notes/welcome.md"]
    connector = ObsidianConnector(vault_root, enabled=True)

    def read(path: str) -> str:
        return connector._read_note_content(path)

    index = build_backlink_index(notes, read)
    assert "welcome" in index
    assert any("index" in item for item in index["welcome"])


def test_rewrite_wikilinks_after_rename() -> None:
    content = "Link to [[welcome|Intro]] and [[welcome]]."
    updated = rewrite_wikilinks_after_rename(content, "welcome", "bienvenue")
    assert "[[bienvenue|Intro]]" in updated
    assert "[[bienvenue]]" in updated


def test_format_memory_activity_includes_obsidian_consultation() -> None:
    ctx = ThinkContext(
        user_message="Lis ma note Obsidian",
        retrieval_result=RetrievalResult(
            text="Aucune mémoire pertinente trouvée.",
            items=[],
            user="Nolan",
        ),
        obsidian_consulted=True,
        obsidian_note_titles=["welcome"],
    )

    activity = format_memory_activity(ctx)
    sources = {record["source"] for record in activity}
    assert "obsidian" in sources

    obsidian_recall = next(
        record for record in activity if record.get("run_id") == "mem-recall-obsidian"
    )
    assert "Note · welcome" in obsidian_recall["cards"]
    serialized = str(activity)
    assert "notes/" not in serialized


def test_tool_activity_obsidian_title() -> None:
    from tools.audit.tool_audit_models import ToolAuditEvent

    events = [
        ToolAuditEvent.build(
            event_type="started",
            tool_name="obsidian",
            run_id="run-obs",
        ),
        ToolAuditEvent.build(
            event_type="completed",
            tool_name="obsidian",
            run_id="run-obs",
            success=True,
        ),
    ]
    activity = format_tool_activity(events)
    assert activity[0]["title"] == "Consultation d'Obsidian"
    assert normalize_tool_key("vault_search") == "obsidian"


def test_track_obsidian_from_tool_results() -> None:
    from brain.pipeline.stages import ThinkPipeline

    ctx = ThinkContext(user_message="test")
    ctx.tool_results = [
        ToolResult(
            tool_name="obsidian",
            success=True,
            data="content",
            metadata={"target_path": "notes/welcome.md", "action": "read_note"},
        ),
    ]
    ThinkPipeline._track_obsidian_consultation(ctx)
    assert ctx.obsidian_consulted is True
    assert ctx.obsidian_note_titles == ["welcome"]
